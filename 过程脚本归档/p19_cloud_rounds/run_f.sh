#!/usr/bin/env bash
# P19 F 轮：出处纪律正向 drill 对照（唯一变量 = I+J 族 57 行增量）
# 门禁只跑 base + sft_f（贪心解码确定性，D/E/B 引用 E 轮同轮存档数字）
set -uo pipefail
cd /data/pmtec19/pmtec_system
PY=/data/venv/bin/python
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export PMTEC_BASE=/data/models/Qwen2.5-7B-Instruct
export PMTEC_MAXLEN=384
export CUDA_VISIBLE_DEVICES="${PMTEC_GPU:-0}"
M=/data/pmtec19
rm -f $M/F1_DONE $M/F1_FAIL $M/GF_DONE $M/GF_FAIL $M/F_ALL_DONE
touch $M/F_STARTED

echo "== [F1] SFT f_refusal（607 行 × 8ep ≈ 303 步）=="
PMTEC_SFT_DATA=$PWD/data/corpora/sft_f_refusal.jsonl \
PMTEC_SFT_OUT=/data/out/sft_f PMTEC_GPU=0 \
  $PY -u scripts/train_sft_pmtec.py > $M/sft_f.log 2>&1 \
  && touch $M/F1_DONE || { touch $M/F1_FAIL; exit 1; }

echo "== [G] 门禁 v2.1：base + sft_f =="
$PY -u scripts/eval_citation_gate.py \
  --base $PMTEC_BASE \
  --adapter sft_f=/data/out/sft_f/adapter \
  --corpus data/corpora/sft_f_refusal.jsonl \
  --out /data/out/gate_drill_f.json > $M/gate_f.log 2>&1 \
  && touch $M/GF_DONE || { touch $M/GF_FAIL; exit 1; }
touch $M/F_ALL_DONE
