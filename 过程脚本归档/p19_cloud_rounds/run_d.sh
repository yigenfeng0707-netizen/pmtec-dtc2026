#!/usr/bin/env bash
# P19 D 轮：锚点覆盖实验（唯一变量 = 46 个改写问法；拒答剂量对齐 B 组）
set -uo pipefail
cd /data/pmtec19/pmtec_system
PY=/data/venv/bin/python
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export PMTEC_BASE=/data/models/Qwen2.5-7B-Instruct
export PMTEC_MAXLEN=384
export CUDA_VISIBLE_DEVICES="${PMTEC_GPU:-0}"
M=/data/pmtec19
rm -f $M/D1_DONE $M/D1_FAIL $M/GD_DONE $M/GD_FAIL $M/D_ALL_DONE
touch $M/D_STARTED

echo "== [D1] SFT d_refusal（552 行 × 8ep ≈ 276 步）=="
PMTEC_SFT_DATA=$PWD/data/corpora/sft_d_refusal.jsonl \
PMTEC_SFT_OUT=/data/out/sft_d PMTEC_GPU=0 \
  $PY -u scripts/train_sft_pmtec.py > $M/sft_d.log 2>&1 \
  && touch $M/D1_DONE || { touch $M/D1_FAIL; exit 1; }

echo "== [G] 门禁 base+B+D =="
$PY -u scripts/eval_citation_gate.py \
  --base $PMTEC_BASE \
  --adapter sft_refusal=/data/out/sft_refusal/adapter \
  --adapter sft_d=/data/out/sft_d/adapter \
  --corpus data/corpora/sft_facts.jsonl \
  --out /data/out/gate_anchorcov.json > $M/gate_d.log 2>&1 \
  && touch $M/GD_DONE || { touch $M/GD_FAIL; exit 1; }
touch $M/D_ALL_DONE
