#!/usr/bin/env python3
"""PMTEC 参谋官 SFT——Qwen2.5-7B-Instruct QLoRA 微调（4090 24GB 单卡）
语料: output/sft_pmtec.jsonl (174 条, 全部来自仓库真实产物)
产出: /data/out/sft_pmtec_lora (LoRA 适配器) + 训练日志 JSON
路线依据: 《端侧大模型自主训练技术路线》阶段二 SFT
"""
import json, os, sys, time
import torch
from transformers import (AutoModelForCausalLM, AutoTokenizer,
                          TrainingArguments, Trainer, DataCollatorForSeq2Seq)
from peft import LoraConfig, get_peft_model

BASE = "/data/models/Qwen2.5-7B-Instruct"
DATA = os.environ.get("PMTEC_SFT_DATA", "/data/out/sft_pmtec.jsonl")
OUT = os.environ.get("PMTEC_SFT_OUT", "/data/out/sft_pmtec_lora")
MAXLEN = 512

print("== 环境 ==")
print("torch", torch.__version__, "| GPU:", torch.cuda.get_device_name(0),
      "| 卡数:", torch.cuda.device_count())

tok = AutoTokenizer.from_pretrained(BASE)
if tok.pad_token is None:
    tok.pad_token = tok.eos_token

rows = [json.loads(l) for l in open(DATA, encoding="utf-8")]
rows.sort(key=lambda r: hash(json.dumps(r["messages"], sort_keys=True)) % 1000)
eval_rows = rows[:8]
train_rows = rows[8:]
print(f"语料: train {len(train_rows)} / eval {len(eval_rows)}")


def to_features(row):
    text = tok.apply_chat_template(row["messages"], tokenize=False,
                                   add_generation_prompt=False)
    ids = tok(text, truncation=True, max_length=MAXLEN, add_special_tokens=False)
    ids["labels"] = list(ids["input_ids"])
    return ids


train_ds = [to_features(r) for r in train_rows]
eval_ds = [to_features(r) for r in eval_rows]

# bf16 全精度底座 + LoRA（bitsandbytes 0.50.2 在 torch2.6/4090 上 dequant 触发
# CUBLAS_STATUS_INTERNAL_ERROR，弃 4bit 改 bf16——质量更优且移除该依赖）
model = AutoModelForCausalLM.from_pretrained(
    BASE, device_map={"": 1}, torch_dtype=torch.bfloat16)
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
    num_train_epochs=8,
    learning_rate=2e-4,
    lr_scheduler_type="cosine",
    warmup_ratio=0.1,
    logging_steps=5,
    eval_strategy="epoch",
    save_strategy="epoch",
    save_total_limit=2,
    bf16=True,
    load_best_model_at_end=True,
    metric_for_best_model="eval_loss",
    greater_is_better=False,
    report_to=[],
    optim="paged_adamw_8bit",
    seed=42,
)
from transformers import EarlyStoppingCallback
trainer = Trainer(model=model, args=args, train_dataset=train_ds,
                  eval_dataset=eval_ds,
                  data_collator=DataCollatorForSeq2Seq(tok, padding=True),
                  callbacks=[EarlyStoppingCallback(early_stopping_patience=2)])

t0 = time.time()
trainer.train()
train_time = time.time() - t0

model.save_pretrained(os.path.join(OUT, "adapter"))
tok.save_pretrained(os.path.join(OUT, "adapter"))
metrics = {k: float(v) for k, v in trainer.state.log_history[-1].items()
           if isinstance(v, (int, float))}
meta = {"base": BASE, "corpus": len(train_rows) + len(eval_rows),
        "train": len(train_rows), "eval": len(eval_rows),
        "train_time_s": round(train_time, 1),
        "final_metrics": metrics,
        "route": "端侧大模型自主训练技术路线 阶段二 SFT (QLoRA)"}
with open(os.path.join(OUT, "training_meta.json"), "w", encoding="utf-8") as f:
    json.dump(meta, f, ensure_ascii=False, indent=1)
print("训练完成:", json.dumps(meta, ensure_ascii=False)[:300])
