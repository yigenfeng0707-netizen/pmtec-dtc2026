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


def verify_manifest(data_path):
    """语料完整性校验：sha256 与行数必须与 manifest 一致，否则拒训。"""
    if SKIP_MANIFEST:
        print("!! 已跳过 manifest 校验（PMTEC_SKIP_MANIFEST_CHECK=1）")
        return None
    mpath = os.path.join(os.path.dirname(os.path.abspath(data_path)),
                         "corpus_manifest.json")
    if not os.path.exists(mpath):
        # 默认强校验：manifest 缺失即拒训。曾经的形态是"警告后继续"，
        # 而语料静默降级（HEAD 构建器只产 352 行却正常训练）正是这样漏过去的。
        msg = "\n".join([
            f"未找到语料 manifest: {mpath}",
            "  训练前必须能证明语料是哪一份。生成方式:",
            "    python scripts/build_sft_corpus.py --report",
            "    python scripts/build_sft_refusal_corpus.py --facts ... --report",
            "  确认语料无误后可 PMTEC_SKIP_MANIFEST_CHECK=1 临时跳过（会在 meta 留痕）。",
        ])
        sys.exit(msg)
    m = json.load(open(mpath, encoding="utf-8"))
    raw = open(data_path, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    rows = sum(1 for _ in open(data_path, encoding="utf-8"))
    problems = []
    if m.get("sha256") and m["sha256"] != sha:
        problems.append(f"sha256 不符：manifest={m['sha256'][:16]}… 实际={sha[:16]}…")
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

model = AutoModelForCausalLM.from_pretrained(
    BASE, device_map={"": GPU}, torch_dtype=torch.bfloat16)
model.gradient_checkpointing_enable()
lora = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
                  task_type="CAUSAL_LM",
                  target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                                  "gate_proj", "up_proj", "down_proj"])
model = get_peft_model(model, lora)
model.print_trainable_parameters()

args = TrainingArguments(
    output_dir=OUT,
    per_device_train_batch_size=1,
    gradient_accumulation_steps=16,
    num_train_epochs=EPOCHS,
    learning_rate=LR,
    lr_scheduler_type="cosine",
    warmup_ratio=0.1,
    logging_steps=5,
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

adapter_dir = os.path.join(OUT, "adapter")
model.save_pretrained(adapter_dir)
tok.save_pretrained(adapter_dir)

metrics = {k: float(v) for k, v in trainer.state.log_history[-1].items()
           if isinstance(v, (int, float))}
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