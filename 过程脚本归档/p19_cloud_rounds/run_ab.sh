#!/usr/bin/env bash
# P19 A/B 轮：组A=干净事实语料 SFT；组B=事实+28.6%拒答 SFT；门禁=基座+双适配器
set -uo pipefail
cd /data/pmtec19/pmtec_system
PY=/data/venv/bin/python
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export PMTEC_BASE=/data/models/Qwen2.5-7B-Instruct
# MAXLEN 384: 512 时 logits 张量(1x512x152Kx2B≈156MB)在 24GB 顶格, backward 差 130MB 爆
# (10-28 实测两连爆; 384→117MB 有余量; 历史 DPO 标定 256 稳/384 爆为拼接前向口径, SFT 单前向更松)
export PMTEC_MAXLEN=384
# 强制单卡：双卡实例上 Trainer 检测 n_gpu=2 会包 DataParallel（train_batch_size=1x2卡=2,
# dataloader 352→176 即证据），DP+LoRA+检查点组合异常（v1 时代同款教训）。单卡后 bs=1、
# dataloader=352、总步 176。
export CUDA_VISIBLE_DEVICES="${PMTEC_GPU:-0}"
M=/data/pmtec19
rm -rf /data/out/sft_clean /data/out/sft_refusal
rm -f $M/A_DONE $M/A_FAIL $M/B_DONE $M/B_FAIL $M/G_DONE $M/G_FAIL $M/AB_ALL_DONE
touch $M/AB_STARTED

echo "== [A] SFT clean =="
PMTEC_SFT_DATA=$PWD/data/corpora/sft_facts.jsonl \
PMTEC_SFT_OUT=/data/out/sft_clean PMTEC_GPU=0 \
  $PY -u scripts/train_sft_pmtec.py > $M/sft_clean.log 2>&1 \
  && touch $M/A_DONE || { touch $M/A_FAIL; exit 1; }

echo "== [B] SFT refusal =="
PMTEC_SFT_DATA=$PWD/data/corpora/sft_refusal.jsonl \
PMTEC_SFT_OUT=/data/out/sft_refusal PMTEC_GPU=0 \
  $PY -u scripts/train_sft_pmtec.py > $M/sft_refusal.log 2>&1 \
  && touch $M/B_DONE || { touch $M/B_FAIL; exit 1; }

echo "== [G] gate =="
$PY -u scripts/eval_citation_gate.py \
  --base $PMTEC_BASE \
  --adapter sft_clean=/data/out/sft_clean/adapter \
  --adapter sft_refusal=/data/out/sft_refusal/adapter \
  --corpus data/corpora/sft_facts.jsonl \
  --out /data/out/gate_sft_ab.json > $M/gate_ab.log 2>&1 \
  && touch $M/G_DONE || { touch $M/G_FAIL; exit 1; }
touch $M/AB_ALL_DONE
