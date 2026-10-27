#!/usr/bin/env python3
"""PMTEC 参谋官 DPO 训练（路线图阶段三：偏好对齐）——在 SFT 适配器之上做 DPO。

相对 v1 的改造（2026-10-27）：

  1. **全部参数走环境变量**：v1 的 DATA/OUT/SFT 是硬编码，bootstrap 传的
     `PMTEC_DPO_DATA` / `PMTEC_DPO_OUT` 从未被读取（环境变量空转），
     且 `sed s/MAXLEN = 256/` 因实际是 192 而静默失效。现在没有一行 sed 需要。

  2. **SFT 基座路径必填**：v1 默认指向 `/data/out/sft_pmtec_lora_v2b/adapter`，
     而 bootstrap 的 SFT 步骤产出到 `sft_pmtec_lora_v2`（无 b），且 v2b 权重已确认丢失
     → 换卡续跑必然 FileNotFoundError。现在不设默认值，缺失即报错并列出可选项。

  3. **启动前显存/产物体检**：明确打印 GPU、显存、SFT 适配器文件是否完整、
     偏好对条数与正负比例，避免"跑到一半才发现路径错"。

关键训练参数沿用 2026-10-26 的实测结论（见 docs/PMTEC-参谋官SFT训练报告.md 里程碑 5）：
  - **DPO 不需要 48GB 卡**：4090 时代的"结构性 OOM"结论已被推翻。功臣是
    `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` + torch 新版分配器 +
    liger-kernel 0.5.10 的 fused_linear_cross_entropy（不物化 152K 词表 logits）。
  - 实测 A10 24GB 上 `precompute_ref_log_probs=True` + MAXLEN 192 → 峰值 16.4GB。
  - MAXLEN 384 在同卡上 OOM（训练阶段即断），256 可跑满。
  - liger-kernel 必须 0.5.10（新版要求 transformers≥4.52，与锁定的 4.51.3 冲突）。

环境变量:
  PMTEC_BASE       基座（默认 /data/models/Qwen2.5-7B-Instruct）
  PMTEC_DPO_SFT    SFT 适配器目录（必填）
  PMTEC_DPO_DATA   偏好对 jsonl（必填）
  PMTEC_DPO_OUT    产物目录（必填）
  PMTEC_GPU        CUDA 序号（默认 0）
  PMTEC_DPO_MAXLEN 截断长度（默认 192；24GB 卡勿超 256）
  PMTEC_DPO_EPOCHS 轮数（默认 4）
  PMTEC_DPO_LR     学习率（默认 5e-7）
  PMTEC_DPO_BETA   beta（默认 0.1）
  PMTEC_DPO_DRY_RUN 1 = 只做体检与数据统计，不加载模型
"""
import json
import os
import sys
import time

BASE = os.environ.get("PMTEC_BASE", "/data/models/Qwen2.5-7B-Instruct")
SFT = os.environ.get("PMTEC_DPO_SFT")
DATA = os.environ.get("PMTEC_DPO_DATA")
OUT = os.environ.get("PMTEC_DPO_OUT")
GPU = int(os.environ.get("PMTEC_GPU", "0"))
MAXLEN = int(os.environ.get("PMTEC_DPO_MAXLEN", "192"))
EPOCHS = int(os.environ.get("PMTEC_DPO_EPOCHS", "4"))
LR = float(os.environ.get("PMTEC_DPO_LR", "5e-7"))
BETA = float(os.environ.get("PMTEC_DPO_BETA", "0.1"))
DRY = os.environ.get("PMTEC_DPO_DRY_RUN") == "1"

# ── 启动前体检（不依赖 torch / trl，先fail fast）──
_missing = [n for n, v in [("PMTEC_DPO_SFT", SFT), ("PMTEC_DPO_DATA", DATA),
                           ("PMTEC_DPO_OUT", OUT)] if not v]
if _missing:
    sys.exit("缺少必需环境变量: " + ", ".join(_missing)
             + f"\n  提示: SFT 适配器应为 <PMTEC_SFT_OUT>/adapter，例如 /data/out/sft_v7/adapter")

if not os.path.isdir(SFT):
    avail = []
    for root in ("/data/out", "/mnt/workspace"):
        if os.path.isdir(root):
            for d in sorted(os.listdir(root)):
                p = os.path.join(root, d, "adapter", "adapter_model.safetensors")
                if os.path.exists(p):
                    avail.append(p)
    sys.exit(f"SFT 适配器目录不存在: {SFT}\n"
             f"  已发现的可用适配器:\n    " + ("\n    ".join(avail) if avail
                                              else "（无——是否还没跑 SFT？）"))
sft_weights = os.path.join(SFT, "adapter_model.safetensors")
if not os.path.exists(sft_weights):
    sys.exit(f"SFT 适配器文件缺失: {sft_weights}\n"
             f"  目录存在但权重不在，通常是复制中断或权重已丢失。")
if not os.path.exists(DATA):
    sys.exit(f"偏好对文件不存在: {DATA}")

pairs_raw = [json.loads(l) for l in open(DATA, encoding="utf-8")]
if not pairs_raw:
    sys.exit(f"偏好对为空: {DATA}")
for need in ("prompt", "chosen", "rejected"):
    if need not in pairs_raw[0]:
        sys.exit(f"偏好对缺少字段 {need}: {DATA}")
same = sum(1 for p in pairs_raw if p["chosen"].strip() == p["rejected"].strip())
print("== 体检 ==")
print(f"SFT 适配器: {SFT}（{os.path.getsize(sft_weights)/1e6:.1f} MB）")
print(f"偏好对: {len(pairs_raw)} 组" + (f"（chosen==rejected 的无效对 {same} 组）" if same else ""))
if same:
    pairs_raw = [p for p in pairs_raw if p["chosen"].strip() != p["rejected"].strip()]
    print(f"  剔除无效对后 {len(pairs_raw)} 组")
src = {}
for p in pairs_raw:
    src[p.get("source", "unknown")] = src.get(p.get("source", "unknown"), 0) + 1
print("  来源分布:", src)

if DRY:
    print("\n== DRY RUN：体检通过，未加载模型 ==")
    sys.exit(0)

import torch  # noqa: E402
from datasets import Dataset  # noqa: E402
from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: E402
from peft import PeftModel  # noqa: E402
from trl import DPOTrainer, DPOConfig  # noqa: E402

# Liger 融合核：分块交叉熵不物化 152K 词表 logits——DPO 拼接前向的 OOM 根治
try:
    from liger_kernel.transformers import apply_liger_kernel_to_qwen2
    apply_liger_kernel_to_qwen2(rope=True, rms_norm=True, swiglu=True,
                                cross_entropy=False, fused_linear_cross_entropy=True)
    LIGER = True
except ImportError:
    LIGER = False
    print("!! liger_kernel 未安装——24GB 卡大概率 OOM（需 pip install liger-kernel==0.5.10）")

print("torch", torch.__version__,
      "| GPU:", torch.cuda.get_device_name(GPU) if torch.cuda.is_available() else "无 CUDA",
      "| liger:", LIGER)
if torch.cuda.is_available():
    total = torch.cuda.get_device_properties(GPU).total_memory / 2**30
    print(f"显存 {total:.1f} GB ｜ MAXLEN={MAXLEN}"
          + ("（24GB 卡建议 ≤256）" if total < 32 and MAXLEN > 256 else ""))

tok = AutoTokenizer.from_pretrained(BASE)
if tok.pad_token is None:
    tok.pad_token = tok.eos_token

rows = sorted(pairs_raw, key=lambda r: r["prompt"] + r["chosen"])
ds = Dataset.from_list([{"prompt": r["prompt"], "chosen": r["chosen"],
                         "rejected": r["rejected"]} for r in rows])

model = AutoModelForCausalLM.from_pretrained(
    BASE, device_map={"": GPU}, torch_dtype=torch.bfloat16)
model = PeftModel.from_pretrained(model, SFT)
model.enable_input_require_grads()  # 缺此行则检查点静默失效→激活全存→OOM
model.config.use_cache = False

dpo_cfg = DPOConfig(
    output_dir=OUT,
    per_device_train_batch_size=1,
    gradient_accumulation_steps=16,
    num_train_epochs=EPOCHS,
    learning_rate=LR,
    lr_scheduler_type="cosine",
    warmup_ratio=0.1,
    beta=BETA,
    precompute_ref_log_probs=True,
    max_length=MAXLEN,
    max_prompt_length=min(96, MAXLEN),
    gradient_checkpointing=True,
    gradient_checkpointing_kwargs={"use_reentrant": False},
    bf16=True,
    logging_steps=2,
    optim="paged_adamw_8bit",
    report_to=[],
    seed=42,
)
trainer = DPOTrainer(model=model, ref_model=None, args=dpo_cfg,
                     train_dataset=ds, processing_class=tok)

t0 = time.time()
if torch.cuda.is_available():
    print("训练前显存 allocated:",
          round(torch.cuda.memory_allocated(GPU) / 1048576, 1), "MB")
trainer.train()
train_time = time.time() - t0

adapter_dir = os.path.join(OUT, "adapter")
model.save_pretrained(adapter_dir)
tok.save_pretrained(adapter_dir)
meta = {
    "base": BASE, "sft": SFT, "data": os.path.abspath(DATA),
    "pairs": len(ds), "sources": src, "beta": BETA,
    "maxlen": MAXLEN, "epochs": EPOCHS, "lr": LR, "gpu": GPU,
    "liger": LIGER,
    "gpu_name": (torch.cuda.get_device_name(GPU) if torch.cuda.is_available() else "CPU"),
    "peak_mem_gb": (round(torch.cuda.max_memory_allocated(GPU) / 2**30, 2)
                    if torch.cuda.is_available() else None),
    "train_time_s": round(train_time, 1),
    "final_metrics": {k: float(v) for k, v in trainer.state.log_history[-1].items()
                      if isinstance(v, (int, float))},
    "route": "端侧大模型自主训练技术路线 阶段三 DPO",
}
with open(os.path.join(OUT, "training_meta.json"), "w", encoding="utf-8") as f:
    json.dump(meta, f, ensure_ascii=False, indent=1)
print("DPO 训练完成:", json.dumps(meta, ensure_ascii=False)[:400])