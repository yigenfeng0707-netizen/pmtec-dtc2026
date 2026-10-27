#!/usr/bin/env bash
# ============================================================
# PMTEC 参谋官训练流水线（P19 改造）
#
# 替代 bootstrap_gpu_instance.sh。旧脚本的三处硬故障：
#   1. train_sft_pmtec.py 硬编码 device_map={"": 1} → 单卡 48G 实例必崩
#   2. DPO 期望 sft_pmtec_lora_v2b，实际产出 sft_pmtec_lora_v2（且 v2b 权重已丢）
#   3. sed "s/MAXLEN = 256/" 而文件里是 192 → 静默失效
# 本脚本的做法：全部参数走环境变量，一行 sed 都没有；每步失败即停并留下 .fail 标记。
#
# 用法:
#   bash train_pipeline.sh preflight           # 只体检（无 GPU 也能跑，检查语料/脚本/依赖）
#   bash train_pipeline.sh corpus              # 构建语料 + manifest（CPU 即可）
#   bash train_pipeline.sh sft                 # SFT 训练
#   bash train_pipeline.sh dpo                 # DPO 训练（需先有 SFT 适配器）
#   bash train_pipeline.sh gate                # 门禁评测（基座 vs SFT vs DPO 真三方）
#   bash train_pipeline.sh all                 # preflight → corpus → sft → dpo → gate
#
# 常用环境变量:
#   PMTEC_ROOT      仓库根（默认脚本上级）
#   PMTEC_BASE      基座目录（默认 /data/models/Qwen2.5-7B-Instruct）
#   PMTEC_OUT       产物根（默认 /data/out）
#   PMTEC_GPU       CUDA 序号（默认 0）
#   PMTEC_RECIPE    语料配方：clean(默认) | upsample8 | refusal
#   PMTEC_REFUSAL_RATIO  拒答占比（recipe=refusal 时生效，默认 0.286）
#   PMTEC_DPO_DATA  偏好对路径（默认 $PMTEC_ROOT/data/corpora/dpo_v2_2395.jsonl）
#   PMTEC_PYTHON    python 解释器（默认 python3）
# ============================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${PMTEC_ROOT:-$(dirname "$HERE")}"

# Git Bash / MSYS2 会把以 / 开头的参数自动转换成 Windows 路径，但要区分两类：
#   - 脚本自身路径（HERE/ROOT）：POSIX 形式 /d/APPs/... 需转成 Windows 形式给 Python；
#   - 远端设备路径（/data/models/...）：必须原样传给云端脚本，不能被改写。
# 做法：脚本路径用 cygpath 转原生形式；设备路径保持字符串原样（见下面 export）。
if command -v cygpath >/dev/null 2>&1; then
  ROOT_NATIVE="$(cygpath -w "$ROOT" 2>/dev/null || echo "$ROOT")"
else
  ROOT_NATIVE="$ROOT"
fi

# 解释器：显式指定 > python3 > python（Windows/Git Bash 常见只有 python）
if [ -n "${PMTEC_PYTHON:-}" ]; then
  PY="$PMTEC_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  PY="python3"
elif command -v python >/dev/null 2>&1; then
  PY="python"
else
  PY="python3"
fi
BASE="${PMTEC_BASE:-/data/models/Qwen2.5-7B-Instruct}"
OUT="${PMTEC_OUT:-/data/out}"
GPU="${PMTEC_GPU:-0}"
RECIPE="${PMTEC_RECIPE:-clean}"
REFUSAL_RATIO="${PMTEC_REFUSAL_RATIO:-0.286}"
DPO_DATA="${PMTEC_DPO_DATA:-$ROOT/data/corpora/dpo_v2_2395.jsonl}"
STATE="$OUT/STEP_STATE"

export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
export PMTEC_GPU="$GPU"
export PMTEC_BASE="$BASE"

ok()   { echo "  [ok] $*"; }
warn() { echo "  [warn] $*"; }
die()  { echo "  [FAIL] $*" >&2; return 1; }

mark_done() { mkdir -p "$STATE"; : > "$STATE/$1.done"; rm -f "$STATE/$1.fail"; }
mark_fail() { mkdir -p "$STATE"; printf '%s\n' "$2" > "$STATE/$1.fail"; rm -f "$STATE/$1.done"; }

# 每个 python 调用都记录脚本 sha256，防止远程副本漂移导致结果不可复现
fingerprint() {
  local f="$1"
  [ -f "$f" ] || { echo "missing"; return; }
  "$PY" - "$f" <<'PYEOF'
import hashlib, sys
print(hashlib.sha256(open(sys.argv[1], 'rb').read()).hexdigest()[:16])
PYEOF
}

# ────────────────────────── preflight ──────────────────────────
step_preflight() {
  echo "== [preflight] =="
  local fail=0

  command -v "$PY" >/dev/null || { echo "  [FAIL] 找不到 $PY"; return 1; }
  ok "$($PY --version 2>&1)"

  # GPU
  if command -v nvidia-smi >/dev/null 2>&1; then
    local gpu_line
    gpu_line="$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -1)"
    ok "GPU: $gpu_line"
    local n_gpu
    n_gpu="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | wc -l)"
    if [ "$GPU" -ge "$n_gpu" ]; then
      echo "  [FAIL] PMTEC_GPU=$GPU 超出可用卡数 $n_gpu"; fail=1
    fi
  else
    warn "无 nvidia-smi —— 只能跑 corpus/preflight，训练步骤会失败"
  fi

  # 基座
  if [ -d "$BASE" ]; then ok "基座存在: $BASE"
  else echo "  [FAIL] 基座缺失: $BASE（modelscope download --model Qwen/Qwen2.5-7B-Instruct --local_dir $BASE）"; fail=1; fi

  # 依赖（分项报告，不因缺 CUDA 版 torch 就整体失败）
  "$PY" - <<'PYEOF' || fail=1
import importlib
need = ["torch", "transformers", "peft", "accelerate", "datasets"]
missing = []
for m in need:
    try:
        mod = importlib.import_module(m)
        print(f"  [ok] {m} {getattr(mod,'__version__','?')}")
    except Exception as e:
        missing.append(m); print(f"  [FAIL] {m}: {e}")
try:
    import trl; print(f"  [ok] trl {trl.__version__}")
except Exception as e:
    missing.append("trl"); print(f"  [FAIL] trl: {e}")
try:
    import liger_kernel; print(f"  [ok] liger_kernel {getattr(liger_kernel,'__version__','?')}")
except Exception:
    print("  [warn] liger_kernel 缺失 —— DPO 在 24GB 卡会 OOM（pip install liger-kernel==0.5.10）")
raise SystemExit(1 if missing else 0)
PYEOF

  # 脚本指纹（可复现性存证）
  echo "  脚本指纹:"
  for f in build_sft_corpus.py build_sft_refusal_corpus.py eval_citation_gate.py \
           train_sft_pmtec.py train_dpo_pmtec.py gate_probes_v2.json; do
    [ -f "$ROOT/scripts/$f" ] && ok "$f $(fingerprint "$ROOT/scripts/$f")" \
      || { echo "  [FAIL] 缺脚本 $f"; fail=1; }
  done

  # 语料 + manifest（若已生成）
  local facts="$ROOT/data/corpora/sft_facts.jsonl"
  if [ -f "$facts" ]; then
    local rows; rows="$(wc -l < "$facts")"
    ok "事实语料 $rows 行"
    if [ -f "$ROOT/data/corpora/corpus_manifest.json" ]; then
      "$PY" - "$facts" "$ROOT/data/corpora/corpus_manifest.json" <<'PYEOF' || fail=1
import hashlib, json, sys
data, mf = sys.argv[1], sys.argv[2]
m = json.load(open(mf, encoding="utf-8"))
sha = hashlib.sha256(open(data, "rb").read().replace(b"
", b"
")).hexdigest()
rows = sum(1 for _ in open(data, encoding="utf-8"))
bad = []
if m.get("sha256") != sha: bad.append(f"sha256 {m.get('sha256','')[:12]}!={sha[:12]}")
if m.get("rows") != rows: bad.append(f"rows {m.get('rows')}!={rows}")
if bad:
    print("  [FAIL] manifest 不一致: " + "; ".join(bad)); raise SystemExit(1)
print(f"  [ok] manifest 一致（{rows} 行 / 唯一 {m.get('unique_questions')} / 配方 {m.get('recipe')}）")
PYEOF
    else
      warn "无 corpus_manifest.json —— 建议先跑 corpus 步骤"
    fi
  else
    warn "事实语料尚未生成（跑 corpus 步骤）"
  fi

  # DPO 语料
  if [ -f "$DPO_DATA" ]; then
    ok "偏好对 $(wc -l < "$DPO_DATA") 组: $(basename "$DPO_DATA")"
  else
    warn "偏好对缺失: $DPO_DATA"
  fi

  # 磁盘
  local avail; avail="$(df -Pk "$OUT" 2>/dev/null | awk 'NR==2{print int($4/1048576)}')"
  [ -n "${avail:-}" ] && { [ "$avail" -ge 20 ] && ok "磁盘可用 ${avail}GB" \
    || { echo "  [FAIL] 磁盘仅 ${avail}GB，7B 训练建议 ≥20GB"; fail=1; }; }

  if [ "$fail" -eq 0 ]; then ok "preflight 全过"; mark_done preflight
  else mark_fail preflight "preflight failed"; fi
  return "$fail"
}

# ────────────────────────── corpus ──────────────────────────
step_corpus() {
  echo "== [corpus] 配方=$RECIPE =="
  local out="$ROOT/data/corpora/sft_facts.jsonl"
  local mf="$ROOT/data/corpora/corpus_manifest.json"
  local up=1
  case "$RECIPE" in
    clean)     up=1 ;;
    upsample8) up=8 ;;
    refusal)   up=1 ;;
    *) die "未知配方 $RECIPE（clean|upsample8|refusal）"; return 1 ;;
  esac
  ( cd "$ROOT_NATIVE" && "$PY" scripts/build_sft_corpus.py --upsample "$up" --report --manifest "$mf" ) \
    || { mark_fail corpus "build_sft_corpus failed"; return 1; }

  if [ "$RECIPE" = "refusal" ]; then
    local rf="$ROOT/data/corpora/sft_refusal.jsonl"
    mkdir -p "$ROOT/data/corpora"
    ( cd "$ROOT_NATIVE" && "$PY" scripts/build_sft_refusal_corpus.py \
        --facts "$out" --out "$rf" --refusal-ratio "$REFUSAL_RATIO" \
        --report --manifest "$ROOT/data/corpora/sft_refusal_manifest.json" ) \
      || { mark_fail corpus "build_sft_refusal_corpus failed"; return 1; }
    echo "  最终语料: $rf"
  fi
  mark_done corpus
}

# ────────────────────────── sft ──────────────────────────
step_sft() {
  echo "== [sft] =="
  mkdir -p "$OUT"
  local sft_out="$OUT/sft_${RECIPE}"
  local data="$ROOT/data/corpora/sft_facts.jsonl"
  [ "$RECIPE" = "refusal" ] && data="$ROOT/data/corpora/sft_refusal.jsonl"
  [ -f "$data" ] || { die "语料缺失: $data"; mark_fail sft "no corpus"; return 1; }

  PMTEC_SFT_DATA="$data" PMTEC_SFT_OUT="$sft_out" PMTEC_GPU="$GPU" \
    "$PY" -u "$ROOT_NATIVE/scripts/train_sft_pmtec.py" 2>&1 | tee "$OUT/sft.log" | tail -20
  local rc=${PIPESTATUS[0]}
  [ "$rc" -eq 0 ] || { mark_fail sft "train_sft rc=$rc"; return 1; }
  [ -f "$sft_out/adapter/adapter_model.safetensors" ] \
    || { die "无适配器产物: $sft_out/adapter"; mark_fail sft "no adapter"; return 1; }
  ok "SFT 适配器: $sft_out/adapter"
  echo "  （下一步用 PMTEC_DPO_SFT=$sft_out/adapter）"
  SFT_ADAPTER="$sft_out/adapter"
  mark_done sft
}

# ────────────────────────── dpo ──────────────────────────
step_dpo() {
  echo "== [dpo] =="
  mkdir -p "$OUT"
  local sft_adapter="${PMTEC_DPO_SFT:-$OUT/sft_${RECIPE}/adapter}"
  local dpo_out="$OUT/dpo_${RECIPE}"
  [ -f "$DPO_DATA" ] || { die "偏好对缺失: $DPO_DATA"; mark_fail dpo "no pairs"; return 1; }

  PMTEC_DPO_SFT="$sft_adapter" PMTEC_DPO_DATA="$DPO_DATA" PMTEC_DPO_OUT="$dpo_out" \
    PMTEC_GPU="$GPU" \
    "$PY" -u "$ROOT_NATIVE/scripts/train_dpo_pmtec.py" 2>&1 | tee "$OUT/dpo.log" | tail -20
  local rc=${PIPESTATUS[0]}
  [ "$rc" -eq 0 ] || { mark_fail dpo "train_dpo rc=$rc"; return 1; }
  [ -f "$dpo_out/adapter/adapter_model.safetensors" ] \
    || { die "无适配器产物: $dpo_out/adapter"; mark_fail dpo "no adapter"; return 1; }
  ok "DPO 适配器: $dpo_out/adapter"
  mark_done dpo
}

# ────────────────────────── gate ──────────────────────────
step_gate() {
  echo "== [gate] 基座 vs SFT vs DPO 真三方 =="
  mkdir -p "$OUT"
  local args=(--corpus "$ROOT/data/corpora/sft_facts.jsonl" --out "$OUT/gate_${RECIPE}.json")
  local sft_adapter="${PMTEC_DPO_SFT:-$OUT/sft_${RECIPE}/adapter}"
  local dpo_out="$OUT/dpo_${RECIPE}"
  [ -f "$sft_adapter/adapter_model.safetensors" ] && args+=(--adapter "sft=$sft_adapter") \
    || warn "跳过 SFT：$sft_adapter 不存在"
  [ -f "$dpo_out/adapter/adapter_model.safetensors" ] && args+=(--adapter "dpo=$dpo_out/adapter") \
    || warn "跳过 DPO：$dpo_out/adapter 不存在"

  "$PY" -u "$ROOT_NATIVE/scripts/eval_citation_gate.py" "${args[@]}" 2>&1 | tee "$OUT/gate.log" | tail -40
  local rc=${PIPESTATUS[0]}
  [ "$rc" -eq 0 ] || { mark_fail gate "gate rc=$rc"; return 1; }
  ok "门禁结果: $OUT/gate_${RECIPE}.json"
  mark_done gate
}

# ────────────────────────── 调度 ──────────────────────────
CMD="${1:-help}"
case "$CMD" in
  preflight) step_preflight ;;
  corpus)    step_corpus ;;
  sft)       step_sft ;;
  dpo)       step_dpo ;;
  gate)      step_gate ;;
  all)
    step_preflight || { echo "preflight 失败，中止"; exit 1; }
    step_corpus    || { echo "corpus 失败，中止";    exit 1; }
    step_sft       || { echo "sft 失败，中止";       exit 1; }
    step_dpo       || { echo "dpo 失败，中止（SFT 产物完好，可单独排查 DPO）"; exit 1; }
    step_gate      || { echo "gate 失败，中止";      exit 1; }
    echo "== 全流程完成 =="
    ;;
  selftest)
    "$PY" "$ROOT_NATIVE/scripts/eval_citation_gate.py" --selftest || exit 1
    echo "== 自检通过 =="
    ;;
  *)
    sed -n '2,40p' "${BASH_SOURCE[0]}"
    exit 0 ;;
esac