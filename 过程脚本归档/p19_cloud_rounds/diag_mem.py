# -*- coding: utf-8 -*-
"""SFT OOM 显存探针：逐阶段打印 allocated，定位 22.95GB 在哪积累。"""
import json
import os
import sys

import torch
from transformers import (AutoModelForCausalLM, AutoTokenizer,
                          TrainingArguments, DataCollatorForSeq2Seq)
from peft import LoraConfig, get_peft_model

BASE = "/data/models/Qwen2.5-7B-Instruct"
DATA = "/data/pmtec19/pmtec_system/data/corpora/sft_facts.jsonl"
MAXLEN = int(os.environ.get("PMTEC_MAXLEN", "384"))


def gb():
    return round(torch.cuda.memory_allocated(0) / 2**30, 2)


def rep(tag):
    print(f"[{tag:26}] allocated {gb():6.2f} GB", flush=True)


print("torch", torch.__version__, flush=True)
tok = AutoTokenizer.from_pretrained(BASE)
if tok.pad_token is None:
    tok.pad_token = tok.eos_token

rep("before load")
model = AutoModelForCausalLM.from_pretrained(
    BASE, device_map={"": 0}, torch_dtype=torch.bfloat16)
rep("after load")

lora = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
                  task_type="CAUSAL_LM",
                  target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                                  "gate_proj", "up_proj", "down_proj"])
model = get_peft_model(model, lora)
model.enable_input_require_grads()
model.config.use_cache = False
rep("after peft wrap")

# 一个真实 batch
rows = [json.loads(l) for l in open(DATA, encoding="utf-8")][:4]
longest = max(rows, key=lambda r: len(r["messages"][2]["content"]))
text = tok.apply_chat_template(longest["messages"], tokenize=False,
                               add_generation_prompt=False)
ids = tok(text, truncation=True, max_length=MAXLEN, add_special_tokens=False,
          return_tensors="pt").to(0)
print("seq len =", ids["input_ids"].shape, flush=True)

args = TrainingArguments(output_dir="/tmp/probe", per_device_train_batch_size=1,
                         gradient_checkpointing=True,
                         gradient_checkpointing_kwargs={"use_reentrant": False},
                         report_to=[])
from transformers import Trainer  # noqa: E402
trainer = Trainer(model=model, args=args, train_dataset=[{"input_ids": ids["input_ids"][0], "labels": ids["input_ids"][0]}])
rep("after trainer init (ckpt args)")
print("model.training =", model.training,
      "| grad ckpt flag =", getattr(model, "is_gradient_checkpointing", None),
      "| base ckpt =", model.base_model.model.model.gradient_checkpointing if hasattr(model.base_model.model.model, "gradient_checkpointing") else "?",
      flush=True)

model.train()
rep("after model.train()")
out = model(input_ids=ids["input_ids"], labels=ids["input_ids"])
rep(f"after forward (loss={out.loss.item():.4f})")
out.loss.backward()
rep("after backward")
print("peak:", round(torch.cuda.max_memory_allocated(0) / 2**30, 2), "GB", flush=True)
