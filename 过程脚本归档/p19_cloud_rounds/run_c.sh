#!/usr/bin/env bash
# P19 C 轮（修正版）：语料已在本地构建并上传，实例只做训练+门禁
set -uo pipefail
cd /data/pmtec19/pmtec_system
PY=/data/venv/bin/python
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export PMTEC_BASE=/data/models/Qwen2.5-7B-Instruct
export PMTEC_MAXLEN=384
export CUDA_VISIBLE_DEVICES="${PMTEC_GPU:-0}"
M=/data/pmtec19
rm -f $M/C3_DONE $M/C3_FAIL $M/GC_DONE $M/GC_FAIL $M/C_ALL_DONE
touch $M/C_STARTED

echo "== [C3] SFT up3（1476 行 × 8ep ≈ 738 步）=="
PMTEC_SFT_DATA=$PWD/data/corpora/sft_up3_refusal.jsonl \
PMTEC_SFT_OUT=/data/out/sft_up3 PMTEC_GPU=0 \
  $PY -u scripts/train_sft_pmtec.py > $M/sft_up3.log 2>&1 \
  && touch $M/C3_DONE || { touch $M/C3_FAIL; exit 1; }

echo "== [G] 门禁 base+B+C =="
$PY -u scripts/eval_citation_gate.py \
  --base $PMTEC_BASE \
  --adapter sft_refusal=/data/out/sft_refusal/adapter \
  --adapter sft_up3=/data/out/sft_up3/adapter \
  --corpus data/corpora/sft_facts.jsonl \
  --out /data/out/gate_ratio.json > $M/gate_ratio.log 2>&1 \
  && touch $M/GC_DONE || { touch $M/GC_FAIL; exit 1; }
touch $M/C_ALL_DONE
