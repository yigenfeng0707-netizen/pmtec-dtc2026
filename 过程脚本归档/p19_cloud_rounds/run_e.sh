#!/usr/bin/env bash
# P19 E 轮：出处纪律对照（唯一变量=H 族 19 条伪造出处诱导）
set -uo pipefail
cd /data/pmtec19/pmtec_system
PY=/data/venv/bin/python
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export PMTEC_BASE=/data/models/Qwen2.5-7B-Instruct
export PMTEC_MAXLEN=384
export CUDA_VISIBLE_DEVICES="${PMTEC_GPU:-0}"
M=/data/pmtec19
rm -f $M/E1_DONE $M/E1_FAIL $M/GE_DONE $M/GE_FAIL $M/E_ALL_DONE
touch $M/E_STARTED

echo "== [E1] SFT e_refusal（550 行 × 8ep ≈ 271 步）=="
PMTEC_SFT_DATA=$PWD/data/corpora/sft_e_refusal.jsonl \
PMTEC_SFT_OUT=/data/out/sft_e PMTEC_GPU=0 \
  $PY -u scripts/train_sft_pmtec.py > $M/sft_e.log 2>&1 \
  && touch $M/E1_DONE || { touch $M/E1_FAIL; exit 1; }

echo "== [G] 门禁 v2.1：base + sft_refusal(B) + sft_d(D) + sft_e(E) =="
$PY -u scripts/eval_citation_gate.py \
  --base $PMTEC_BASE \
  --adapter sft_refusal=/data/out/sft_refusal/adapter \
  --adapter sft_d=/data/out/sft_d/adapter \
  --adapter sft_e=/data/out/sft_e/adapter \
  --corpus data/corpora/sft_e_refusal.jsonl \
  --out /data/out/gate_citation_e.json > $M/gate_e.log 2>&1 \
  && touch $M/GE_DONE || { touch $M/GE_FAIL; exit 1; }
touch $M/E_ALL_DONE
