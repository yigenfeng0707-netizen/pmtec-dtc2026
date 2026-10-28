# -*- coding: utf-8 -*-
"""SFT OOM 探针 2：完整 Trainer 循环 + 逐步内存回调，复现 22.95GB 并定位。

与 train_sft_pmtec.py 完全同构（模型/peft/args/collator），但每步打印：
  步号 / 该步 seq 长度 / allocated / reserved —— 22.95GB 从第几步、什么长度开始。
限制 max_steps 只看前几步即可定位。
"""
import json
import os

import torch
from transformers import (AutoModelForCausalLM, AutoTokenizer,
                          TrainingArguments, Trainer,
                          DataCollatorForSeq2Seq, TrainerCallback)
from peft import LoraConfig, get_peft_model

BASE = "/data/models/Qwen2.5-7B-Instruct"
DATA = "/data/pmtec19/pmtec_system/data/corpora/sft_facts.jsonl"
MAXLEN = int(os.environ.get("PMTEC_MAXLEN", "384"))
GPU = 0


def gb():
    return round(torch.cuda.memory_allocated(GPU) / 2**30, 2)


class MemProbe(TrainerCallback):
    def __init__(self, tok):
        self.tok = tok
        self.step = 0

    def on_step_end(self, args, state, control, **kw):
        self.step += 1
        print(f"[step {self.step:3}] alloc {gb():5.2f} GB  "
              f"reserved {round(torch.cuda.memory_reserved(GPU)/2**30,2):5.2f}",
              flush=True)


tok = AutoTokenizer.from_pretrained(BASE)
if tok.pad_token is None:
    tok.pad_token = tok.eos_token

rows = [json.loads(l) for l in open(DATA, encoding="utf-8")]
rows.sort(key=lambda r: hash(json.dumps(r["messages"], sort_keys=True)) % 1000)
print(f"rows={len(rows)}", flush=True)


def to_features(row):
    text = tok.apply_chat_template(row["messages"], tokenize=False,
                                   add_generation_prompt=False)
    ids = tok(text, truncation=True, max_length=MAXLEN, add_special_tokens=False)
    ids["labels"] = list(ids["input_ids"])
    return ids


train_ds = [to_features(r) for r in rows]
lens = sorted(len(d["input_ids"]) for d in train_ds)
print(f"seq len p50={lens[len(lens)//2]} p90={lens[int(len(lens)*0.9)]} "
      f"max={lens[-1]}", flush=True)

model = AutoModelForCausalLM.from_pretrained(
    BASE, device_map={"": GPU}, torch_dtype=torch.bfloat16)
lora = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
                  task_type="CAUSAL_LM",
                  target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                                  "gate_proj", "up_proj", "down_proj"])
model = get_peft_model(model, lora)
model.enable_input_require_grads()

args = TrainingArguments(
    output_dir="/tmp/probe2",
    per_device_train_batch_size=1,
    gradient_accumulation_steps=16,
    num_train_epochs=8,
    max_steps=int(os.environ.get("PROBE_STEPS", "6")),
    learning_rate=2e-4,
    lr_scheduler_type="cosine",
    warmup_ratio=0.1,
    logging_steps=1,
    gradient_checkpointing=True,
    gradient_checkpointing_kwargs={"use_reentrant": False},
    bf16=True,
    report_to=[],
    optim="paged_adamw_8bit",
    seed=42,
)
trainer = Trainer(model=model, args=args, train_dataset=train_ds,
                  data_collator=DataCollatorForSeq2Seq(tok, padding=True))
print(f"total steps per trainer: {len(trainer.get_train_dataloader())} micro-batches; "
      f"epochs={args.num_train_epochs} accum={args.gradient_accumulation_steps} "
      f"bs={args.per_device_train_batch_size}", flush=True)
rep0 = gb()
print(f"before train: {rep0} GB", flush=True)
trainer.add_callback(MemProbe(tok))
trainer.train()
print("PROBE2 DONE, peak:",
      round(torch.cuda.max_memory_allocated(GPU) / 2**30, 2), "GB", flush=True)
