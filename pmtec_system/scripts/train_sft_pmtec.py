#!/usr/bin/env python3
"""PMTEC 参谋官 SFT——Qwen2.5-7B-Instruct bf16 LoRA 微调。

相对 v1（早期主干）的改造，逐条对应 2026-10-27 复核发现的缺陷：

  1. **去掉早停**（v1 的 `EarlyStoppingCallback(patience=2)` + `load_best_model_at_end`）：
     v4 锚点跌到 0.125 的根因就是「8 条 eval 上早停 + load_best 选出的不是最优」。
     现在改为训满固定 epoch、`save_strategy="no"`，最终 adapter 训练结束直接落盘。
     确需早停时传 `PMTEC_EARLY_STOP=1` 显式启用（不推荐）。

  2. **切分可复现且不泄漏**（v1 用 `hash(...)%1000` 排序）：
     Python 字符串 hash 每进程随机化，实测同一语料三次运行 eval[0] 各不相同；
     且 v1 按**行**切 8 条 eval，而语料最大重复 8 次 → 同一问题必同时进 train/eval，
     eval_loss 全程被污染。现改为按**唯一问题**分组：先 `sha256(question)` 稳定排序，
     取前 N 个唯一问题**连同其全部重复行**入 eval。

  3. **设备可配**（v1 硬编码 `device_map={"": 1}`）：双 4090 时代为绕开 transformers
     4.51 跨设备 loss bug 而写死，在单卡 48G 实例上直接 `invalid device ordinal`。
     现由 `PMTEC_GPU` 指定，默认 0。

  4. **参数全部走环境变量**，不再靠 sed 改写源码（bootstrap 的 `sed s/MAXLEN = 256/`
     因实际是 192 而静默失效，是历史事故的直接来源）。

  5. **语料 manifest 强校验**：训练前读同目录 `corpus_manifest.json`（若存在），
     断言 sha256 / 行数一致，不符即拒训 —— 防止语料静默降级（HEAD 构建器只产 352 行
     却能正常训练、正常打印"训练完成"，是史上最危险的失败形态）。

用法:
  PMTEC_SFT_DATA=/data/corpora/sft_v7_refusal.jsonl \\
  PMTEC_SFT_OUT=/data/out/sft_v7 python3 train_sft_pmtec.py

环境变量:
  PMTEC_BASE        基座目录（默认 /data/models/Qwen2.5-7B-Instruct）
  PMTEC_SFT_DATA    语料（必填）
  PMTEC_SFT_OUT     产物目录（必填）
  PMTEC_GPU         CUDA 序号（默认 0）
  PMTEC_MAXLEN      截断长度（默认 512）
  PMTEC_EPOCHS      轮数（默认 8）
  PMTEC_LR          学习率（默认 2e-4）
  PMTEC_EVAL_GROUPS eval 唯一问题数（默认 8）
  PMTEC_EARLY_STOP  1 = 启用早停（默认关，详见上文第 1 条）
  PMTEC_SKIP_MANIFEST_CHECK  1 = 跳过 manifest 校验（仅限调试）
  PMTEC_DRY_RUN     1 = 只做语料校验与切分并打印结果，不加载模型（无需 GPU）
"""
import hashlib
import json
import os
import sys
import time

import torch
from transformers import (AutoModelForCausalLM, AutoTokenizer,
                          TrainingArguments, Trainer, DataCollatorForSeq2Seq)
from peft import LoraConfig, get_peft_model

BASE = os.environ.get("PMTEC_BASE", "/data/models/Qwen2.5-7B-Instruct")
DATA = os.environ.get("PMTEC_SFT_DATA")
OUT = os.environ.get("PMTEC_SFT_OUT")
GPU = int(os.environ.get("PMTEC_GPU", "0"))
MAXLEN = int(os.environ.get("PMTEC_MAXLEN", "512"))
EPOCHS = int(os.environ.get("PMTEC_EPOCHS", "8"))
LR = float(os.environ.get("PMTEC_LR", "2e-4"))
EVAL_GROUPS = int(os.environ.get("PMTEC_EVAL_GROUPS", "8"))
EARLY_STOP = os.environ.get("PMTEC_EARLY_STOP") == "1"
SKIP_MANIFEST = os.environ.get("PMTEC_SKIP_MANIFEST_CHECK") == "1"

if not DATA or not OUT:
    sys.exit("必须设置 PMTEC_SFT_DATA 与 PMTEC_SFT_OUT")
if not os.path.exists(DATA):
    sys.exit(f"语料不存在: {DATA}")

print("== 环境 ==")
print("torch", torch.__version__, "| 卡数:", torch.cuda.device_count() if torch.cuda.is_available() else 0)
GPU_NAME = (torch.cuda.get_device_name(GPU)
            if torch.cuda.is_available() and GPU < torch.cuda.device_count() else "CPU/无 CUDA")
print("GPU:", GPU_NAME)
import transformers, peft, accelerate  # noqa: E402
print("transformers", transformers.__version__, "| peft", peft.__version__,
      "| accelerate", accelerate.__version__)


def manifest_candidates(data_path):
    """可能的 manifest 路径，按优先级。

    语料不都叫 corpus_manifest.json：事实语料的清单是 corpus_manifest.json，
    拒答语料是 sft_refusal_manifest.json，历史归档是 <stem>_manifest.json。
    早先只认死一个文件名，会让「拒答语料 + 强校验」这条组合直接拒训。
    """
    d = os.path.dirname(os.path.abspath(data_path))
    stem = os.path.splitext(os.path.basename(data_path))[0]
    # 顺序关键：先找与本语料同名的清单，再退回通用名——
    # 否则拒答语料会先命中事实语料的 corpus_manifest.json 而 sha 不符被拒。
    return [os.path.join(d, f"{stem}_manifest.json"),  # <stem>_manifest.json 优先
            os.path.join(d, "corpus_manifest.json")]   # 事实语料惯例


def verify_manifest(data_path):
    """语料完整性校验：sha256 与行数必须与 manifest 一致，否则拒训。

    sha 按 LF 归一化后计算（CRLF→LF）：构建器写文件用 LF，manifest 记录的是
    LF 内容的 sha；而 Windows 上 core.autocrlf 会让 rebase/checkout 把磁盘文件
    变成 CRLF（P19 当天实测：rebase 后 facts 语料 sha 从 be737404 变 bb5e5411）。
    按原始字节哈希会让校验在每次 git 触碰后误报「语料被换」，按内容等价比较才稳。
    """
    if SKIP_MANIFEST:
        print("!! 已跳过 manifest 校验（PMTEC_SKIP_MANIFEST_CHECK=1）")
        return None
    mpath = next((p for p in manifest_candidates(data_path) if os.path.exists(p)), None)
    if mpath is None:
        # 默认强校验：manifest 缺失即拒训。曾经的形态是"警告后继续"，
        # 而语料静默降级（HEAD 构建器只产 352 行却正常训练）正是这样漏过去的。
        msg = "\n".join([
            f"未找到语料 manifest（已试 {len(manifest_candidates(data_path))} 个候选路径）:",
            *["    " + p for p in manifest_candidates(data_path)],
            "  训练前必须能证明语料是哪一份。生成方式:",
            "    python scripts/build_sft_corpus.py --report",
            "    python scripts/build_sft_refusal_corpus.py --facts ... --report",
            "  确认语料无误后可 PMTEC_SKIP_MANIFEST_CHECK=1 临时跳过（会在 meta 留痕）。",
        ])
        sys.exit(msg)
    m = json.load(open(mpath, encoding="utf-8"))
    raw = open(data_path, "rb").read()
    sha = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    rows = sum(1 for _ in open(data_path, encoding="utf-8"))
    problems = []
    if m.get("sha256") and m["sha256"] != sha:
        problems.append(f"sha256 不符：manifest={m['sha256'][:16]}… 实际={sha[:16]}…"
                        f"（按 LF 归一化比较；若确认语料被换过，请用构建器重出 manifest）")
    if m.get("rows") is not None and m["rows"] != rows:
        problems.append(f"行数不符：manifest={m['rows']} 实际={rows}")
    if problems:
        sys.exit("语料校验失败，拒绝训练（这通常意味着语料被换成了别的配方）：\n  "
                 + "\n  ".join(problems))
    print(f"语料校验通过: {rows} 行, sha256={sha[:16]}…, recipe={m.get('recipe')}")
    return m


manifest = verify_manifest(DATA)

rows = [json.loads(l) for l in open(DATA, encoding="utf-8")]
print(f"语料: {len(rows)} 行")

# ── 按唯一问题分组切分（可复现 + 不泄漏）──
by_q = {}
for r in rows:
    q = r["messages"][1]["content"]
    by_q.setdefault(q, []).append(r)
uniq_qs = sorted(by_q, key=lambda q: hashlib.sha256(q.encode("utf-8")).hexdigest())
eval_qs = set(uniq_qs[:EVAL_GROUPS])
train_rows, eval_rows = [], []
for q in uniq_qs:
    (eval_rows if q in eval_qs else train_rows).extend(by_q[q])
print(f"唯一问题 {len(uniq_qs)} ｜ train {len(train_rows)} 行 / eval {len(eval_rows)} 行 "
      f"（eval 含 {len(eval_qs)} 个唯一问题，切分按 sha256 稳定排序）")
assert not (set(r["messages"][1]["content"] for r in train_rows) & eval_qs), "切分泄漏！"

if os.environ.get("PMTEC_DRY_RUN") == "1":
    print("\n== DRY RUN ==")
    print("eval 唯一问题（按 sha256 顺序）:")
    for q in uniq_qs[:EVAL_GROUPS]:
        print("  -", q[:70])
    split_sig = hashlib.sha256("\n".join(uniq_qs[:EVAL_GROUPS]).encode("utf-8")).hexdigest()
    print(f"切分指纹 sha256(eval 题集) = {split_sig[:16]}…")
    print("（同一语料重复运行应得到相同指纹；变化即说明切分不确定）")
    sys.exit(0)

tok = AutoTokenizer.from_pretrained(BASE)
if tok.pad_token is None:
    tok.pad_token = tok.eos_token


def to_features(row):
    text = tok.apply_chat_template(row["messages"], tokenize=False,
                                   add_generation_prompt=False)
    ids = tok(text, truncation=True, max_length=MAXLEN, add_special_tokens=False)
    ids["labels"] = list(ids["input_ids"])
    return ids


train_ds = [to_features(r) for r in train_rows]
eval_ds = [to_features(r) for r in eval_rows]

# Liger 融合核（PMTEC_LIGER=0 关闭）：fused linear cross-entropy 不物化
# 152K 词表 logits——24GB 卡上 backward 的 OOM 主因（10-28 实测三连爆 22.95GB，
# 探针证 seq 最长仅 357、MAXLEN 降档无效；DPO 侧同款方案已验证 16.4GB 峰值）。
USE_LIGER = os.environ.get("PMTEC_LIGER", "1") == "1"
if USE_LIGER:
    try:
        from liger_kernel.transformers import apply_liger_kernel_to_qwen2
        apply_liger_kernel_to_qwen2(rope=True, rms_norm=True, swiglu=True,
                                    cross_entropy=False,
                                    fused_linear_cross_entropy=True)
        print("liger kernel: ON（fused CE，logits 不物化）")
    except ImportError:
        USE_LIGER = False
        print("!! liger_kernel 未安装——24GB 卡大概率 OOM（pip install liger-kernel==0.5.10）")

model = AutoModelForCausalLM.from_pretrained(
    BASE, device_map={"": GPU}, torch_dtype=torch.bfloat16)
lora = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
                  task_type="CAUSAL_LM",
                  target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                                  "gate_proj", "up_proj", "down_proj"])
model = get_peft_model(model, lora)
model.enable_input_require_grads()
model.print_trainable_parameters()

# ── 训练循环：默认 manual（手写），HF Trainer 可选 ──
# 10-28 实测：双卡 4090 实例上 HF Trainer 路径五连 OOM（allocated 恒 22.95GB、
# 差额恒 130MB，对 liger/检查点路径/CUDA_VISIBLE_DEVICES/MAXLEN 全部不敏感，
# tqdm 步数 0/80 与配置不符）——Trainer+accelerate+DP 黑盒在双卡环境行为不可控。
# 而同构配置的手写前向/反向探针峰值仅 17.76GB（余量 5.9GB）。故默认手写循环：
# 每 10 步打印显存，一切可见可控。PMTEC_TRAINER=hf 可切回（单卡机上用于对照）。
MANUAL = os.environ.get("PMTEC_TRAINER", "manual") == "manual"

if MANUAL:
    import random

    from transformers import get_cosine_schedule_with_warmup

    try:
        import bitsandbytes as bnb
        opt = bnb.optim.AdamW8bit(model.parameters(), lr=LR)
        optim_name = "bnb AdamW8bit"
    except ImportError:
        opt = torch.optim.AdamW(model.parameters(), lr=LR)
        optim_name = "torch AdamW"

    total_steps = max(1, (len(train_ds) * EPOCHS) // 16)
    sched = get_cosine_schedule_with_warmup(opt, int(total_steps * 0.1), total_steps)
    mem0 = (round(torch.cuda.memory_allocated(model.device) / 2**30, 2)
            if torch.cuda.is_available() else 0)
    print(f"manual 循环: {len(train_ds)} 行 × {EPOCHS}ep ÷ 16 累积 = {total_steps} 步"
          f" ｜ 优化器 {optim_name} ｜ 显存起始 {mem0}GB",
          flush=True)

    rng = random.Random(42)
    order = list(range(len(train_ds)))
    model.train()
    t0 = time.time()
    micro, step, running = 0, 0, 0.0
    done = False
    for epoch in range(EPOCHS):
        rng.shuffle(order)
        for i in order:
            ids = train_ds[i]
            input_ids = torch.tensor([ids["input_ids"]], device=model.device)
            out = model(input_ids=input_ids, labels=input_ids)
            (out.loss / 16).backward()
            running += out.loss.item()
            micro += 1
            if micro % 16 == 0:
                opt.step()
                sched.step()
                opt.zero_grad(set_to_none=True)
                step += 1
                if step % 10 == 0 or step == total_steps:
                    mem = (round(torch.cuda.memory_allocated(model.device) / 2**30, 2)
                           if torch.cuda.is_available() else 0)
                    print(f"step {step}/{total_steps}  loss {running/16:.4f}  "
                          f"alloc {mem}GB", flush=True)
                running = 0.0
                if step >= total_steps:
                    done = True
                    break
        if done:
            break
    train_time = time.time() - t0
    final_loss = running / 16 if running else 0.0
    print(f"训练结束: {step} 步 / {train_time:.0f}s ｜ 末段 loss ≈ {final_loss:.4f}",
          flush=True)
    metrics = {"train_loss_approx": round(final_loss, 4),
               "steps": step, "manual_loop": True}
else:
    args = TrainingArguments(
        output_dir=OUT,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=16,
        num_train_epochs=EPOCHS,
        learning_rate=LR,
        lr_scheduler_type="cosine",
        warmup_ratio=0.1,
        logging_steps=5,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        eval_strategy="epoch" if EARLY_STOP else "no",
        save_strategy="epoch" if EARLY_STOP else "no",
        save_total_limit=2 if EARLY_STOP else None,
        load_best_model_at_end=EARLY_STOP,
        metric_for_best_model="eval_loss" if EARLY_STOP else None,
        greater_is_better=False if EARLY_STOP else None,
        bf16=True,
        report_to=[],
        optim="paged_adamw_8bit",
        seed=42,
    )
    trainer = Trainer(model=model, args=args, train_dataset=train_ds,
                      eval_dataset=eval_ds,
                      data_collator=DataCollatorForSeq2Seq(tok, padding=True))
    if EARLY_STOP:
        from transformers import EarlyStoppingCallback
        trainer.add_callback(EarlyStoppingCallback(early_stopping_patience=2))
        print("!! 早停已启用（PMTEC_EARLY_STOP=1）——已知会造成锚点回退，仅用于对照")
    t0 = time.time()
    trainer.train()
    train_time = time.time() - t0
    metrics = {k: float(v) for k, v in trainer.state.log_history[-1].items()
               if isinstance(v, (int, float))}

adapter_dir = os.path.join(OUT, "adapter")
model.save_pretrained(adapter_dir)
tok.save_pretrained(adapter_dir)
meta = {
    "base": BASE,
    "corpus_path": os.path.abspath(DATA),
    "corpus_rows": len(rows),
    "corpus_manifest": manifest,
    "train_rows": len(train_rows),
    "eval_rows": len(eval_rows),
    "unique_questions": len(uniq_qs),
    "eval_unique_questions": len(eval_qs),
    "split_method": "sha256(question) 稳定排序 + 按唯一问题分组（无泄漏）",
    "maxlen": MAXLEN, "epochs": EPOCHS, "lr": LR, "gpu": GPU,
    "early_stop": EARLY_STOP,
    "gpu_name": GPU_NAME,
    "versions": {"torch": torch.__version__,
                 "transformers": transformers.__version__,
                 "peft": peft.__version__,
                 "accelerate": accelerate.__version__},
    "train_time_s": round(train_time, 1),
    "final_metrics": metrics,
    "route": "端侧大模型自主训练技术路线 阶段二 SFT",
}
with open(os.path.join(OUT, "training_meta.json"), "w", encoding="utf-8") as f:
    json.dump(meta, f, ensure_ascii=False, indent=1)
print("训练完成:", json.dumps(meta, ensure_ascii=False)[:400])