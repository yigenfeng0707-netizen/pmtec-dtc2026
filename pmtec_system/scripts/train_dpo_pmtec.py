#!/usr/bin/env python3
"""PMTEC 参谋官 DPO 训练（路线图阶段三：偏好对齐）
SFT v2 适配器之上做 DPO。偏好对：正例=引用式回答，负例=评测门禁真实编造输出。
产出: /data/out/dpo_pmtec/adapter
"""
import json, os, sys, time
import torch
from datasets import Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
from trl import DPOTrainer, DPOConfig
from liger_kernel.transformers import apply_liger_kernel_to_qwen2

# Liger 融合核：分块交叉熵不物化 152K 词表 logits——DPO 拼接前向的 OOM 根治
apply_liger_kernel_to_qwen2(rope=True, rms_norm=True, swiglu=True,
                            cross_entropy=False, fused_linear_cross_entropy=True)

BASE = "/data/models/Qwen2.5-7B-Instruct"
SFT = "/data/out/sft_pmtec_lora_v2b/adapter"
DATA = "/data/out/dpo_pairs.jsonl"
OUT = "/data/out/dpo_pmtec"
MAXLEN = 192

print("== 环境 ==", torch.__version__, torch.cuda.get_device_name(0))
tok = AutoTokenizer.from_pretrained(BASE)
if tok.pad_token is None:
    tok.pad_token = tok.eos_token

rows = [json.loads(l) for l in open(DATA, encoding="utf-8")]
rows.sort(key=lambda r: hash(r["prompt"] + r["chosen"]) % 1000)

ds = Dataset.from_list([
    {"prompt": r["prompt"], "chosen": r["chosen"], "rejected": r["rejected"]}
    for r in rows
])
print(f"DPO 对: {len(ds)} 组")

model = AutoModelForCausalLM.from_pretrained(
    BASE, device_map={"": 0}, torch_dtype=torch.bfloat16)
model = PeftModel.from_pretrained(model, SFT)
model.enable_input_require_grads()  # 无此行则 reentrant 检查点静默失效→激活全存→OOM
model.config.use_cache = False

dpo_cfg = DPOConfig(
    output_dir=OUT,
    per_device_train_batch_size=1,
    gradient_accumulation_steps=16,
    num_train_epochs=4,
    learning_rate=5e-7,
    lr_scheduler_type="cosine",
    warmup_ratio=0.1,
    beta=0.1,
    precompute_ref_log_probs=True,
    max_length=MAXLEN,
    max_prompt_length=96,
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
print("== 训练前显存 ==")
print("allocated:", round(torch.cuda.memory_allocated(0) / 1048576, 1), "MB")
print("reserved:", round(torch.cuda.memory_reserved(0) / 1048576, 1), "MB")
trainer.train()
train_time = time.time() - t0

model.save_pretrained(os.path.join(OUT, "adapter"))
tok.save_pretrained(os.path.join(OUT, "adapter"))
meta = {"base": BASE, "sft": SFT, "pairs": len(ds), "beta": 0.1,
        "train_time_s": round(train_time, 1),
        "final_metrics": {k: float(v) for k, v in trainer.state.log_history[-1].items()
                          if isinstance(v, (int, float))},
        "route": "端侧大模型自主训练技术路线 阶段三 DPO"}
with open(os.path.join(OUT, "training_meta.json"), "w", encoding="utf-8") as f:
    json.dump(meta, f, ensure_ascii=False, indent=1)
print("DPO 训练完成:", json.dumps(meta, ensure_ascii=False)[:300])
