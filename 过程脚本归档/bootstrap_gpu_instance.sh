#!/bin/bash
# ============================================================
# PMTEC 参谋官训练 · 新 GPU 实例 Bootstrap（一键全流程）
# 用法: 在新 Ubuntu GPU 实例上 (建议 NVIDIA 24GB+, CUDA 12.4, Ubuntu 22.04, Python 3.10):
#   1. 把本仓库的 pmtec_system/ 整目录上传到实例 (如 /data/pmtec_system)
#   2. bash bootstrap_gpu_instance.sh /data/pmtec_system
# 流程: venv + 固定版本依赖 → 语料校验 → SFT(1926条) → DPO(72组偏好对) → 引用门禁
# 产物: /data/out/sft_pmtec_lora_v2/adapter (SFT) + /data/out/dpo_pmtec/adapter (DPO)
# ============================================================
set -e
PMTEC_DIR="${1:-/data/pmtec_system}"
VENV="/data/venv_train"
MIRROR="-i https://pypi.tuna.tsinghua.edu.cn/simple"

echo "=== [1/6] 环境体检 ==="
python3 --version
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
command -v git >/dev/null || { echo "缺 git"; exit 1; }

echo "=== [2/6] venv + 固定版本依赖（清华镜像）==="
python3 -m venv "$VENV"
PIP="$VENV/bin/pip"
$PIP install -q $MIRROR --upgrade pip
# torch 按实例 CUDA 选择: CUDA 12.4 → cu124 轮子
$PIP install -q $MIRROR torch --index-url https://download.pytorch.org/whl/cu124
$PIP install -q $MIRROR "transformers==4.51.3" "peft==0.21.2" "trl==0.17.0" \
    "datasets==3.6.0" "accelerate" "bitsandbytes" "liger-kernel==0.5.10"
$PIP install -q $MIRROR "huggingface_hub<1.0"
$VENV/bin/python -c "import torch, transformers, peft, trl; print('依赖 OK:', torch.__version__, transformers.__version__)"

echo "=== [3/6] SFT: 语料飞轮 v2 (1926 条) ==="
cd "$PMTEC_DIR"
PY="$VENV/bin/python"
$PY scripts/build_sft_corpus.py
mkdir -p /data/out
cp output/sft_pmtec.jsonl /data/out/sft_pmtec_v2.jsonl
# 训练脚本按语料路径参数化（env 传入）
PMTEC_SFT_DATA=/data/out/sft_pmtec_v2.jsonl \
PMTEC_SFT_OUT=/data/out/sft_pmtec_lora_v2 \
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
setsid nohup $PY -u scripts/train_sft_pmtec.py /data/out/sft_pmtec_v2.jsonl /data/out/sft_pmtec_lora_v2 \
    > /data/out/sft_train.log 2>&1 < /dev/null &
SFT_PID=$!
echo "SFT 已启动 pid=$SFT_PID，监控: tail -f /data/out/sft_train.log"
# 等待完成（轮询，最长 3 小时）
for i in $(seq 1 180); do
    sleep 60
    if ! kill -0 $SFT_PID 2>/dev/null; then break; fi
done
tail -3 /data/out/sft_train.log
grep -q "训练完成" /data/out/sft_train.log || { echo "SFT 失败"; exit 1; }

echo "=== [4/6] DPO: 偏好对齐 (阶段三) ==="
mkdir -p /data/sft
cp output/dpo_pairs.jsonl /data/out/dpo_pairs.jsonl
cp scripts/train_dpo_pmtec.py /data/sft/
# 48GB 卡: MAXLEN 回升到 384（24GB 卡经验值 256 会 OOM 的位置在此有富余）
sed -i "s/MAXLEN = 256/MAXLEN = 384/" /data/sft/train_dpo_pmtec.py
PMTEC_DPO_DATA=/data/out/dpo_pairs.jsonl \
PMTEC_DPO_OUT=/data/out/dpo_pmtec \
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
setsid nohup $PY -u /data/sft/train_dpo_pmtec.py > /data/sft/dpo_train.log 2>&1 < /dev/null &
DPO_PID=$!
echo "DPO 已启动 pid=$DPO_PID，监控: tail -f /data/sft/dpo_train.log"
for i in $(seq 1 120); do
    sleep 60
    if ! kill -0 $DPO_PID 2>/dev/null; then break; fi
done
tail -3 /data/sft/dpo_train.log
grep -q "DPO 训练完成" /data/sft/dpo_train.log || { echo "DPO 失败"; exit 1; }

echo "=== [5/6] 引用式评测门禁（基座 vs SFT vs DPO 三方） ==="
$PY scripts/eval_citation_gate.py --model /data/out/dpo_pmtec/adapter \
    --out /data/out/gate_final.json || echo "门禁失败（继续，人工复核）"

echo "=== [6/6] 完成 ==="
echo "SFT 适配器:  /data/out/sft_pmtec_lora_v2/adapter"
echo "DPO 适配器:  /data/out/dpo_pmtec/adapter"
echo "门禁报告:    /data/out/gate_final.json"
echo "回传本地: scp -r <实例>:/data/out/sft_pmtec_lora_v2 /data/out/dpo_pmtec <本地>/pmtec_system/data/models/"
