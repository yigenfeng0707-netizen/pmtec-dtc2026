#!/usr/bin/env bash
# 云端基线重标定：基座模型在新门禁（42 事实 + 48 陷阱）下的四项指标
set -uo pipefail
cd "$(dirname "$0")"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
BASE="${PMTEC_BASE:-/data/models/Qwen2.5-7B-Instruct}"

echo "=== 环境 ==="
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
python3 -c "import torch,transformers,peft;print('torch',torch.__version__,'tf',transformers.__version__,'peft',peft.__version__)"

echo "=== 门禁自检（不加载模型，先确认指标实现正确）==="
python3 pmtec_system/scripts/eval_citation_gate.py --selftest || exit 1

echo "=== 基线重标定（只跑基座，约 10-15 分钟）==="
mkdir -p /data/out
python3 -u pmtec_system/scripts/eval_citation_gate.py \
  --base "$BASE" \
  --corpus pmtec_system/data/corpora/sft_facts.jsonl \
  --out /data/out/gate_baseline_v2.json 2>&1 | tee /data/out/gate_baseline_v2.log | tail -30

echo "GATE_DONE"
