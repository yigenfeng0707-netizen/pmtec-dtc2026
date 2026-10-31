# P19 收尾一次性窗口 runbook：冒烟 + 重标定 + 清理 + 关机（约 1.5~2 小时）

> 对应 `docs/PMTEC-参谋官训练体系改造计划-P19.md` A-6 遗留事项 ③/2/5。
> 一次开机销掉全部 GPU 遗留；**顺序刻意设计：先评测冒烟 → 后清理**（防误删）。
> 实例 **ubuntu@**36.103.199.248（双卡 4090，按量计费；旧 IP .153 已随停机释放，
> 10-31 重开分配新 IP），密码认证 → 一律走
> `过程脚本归档/cloud_ssh/instance_exec.py`（密码放 `PMTEC_GPU_PW` 环境变量，控制台
> 「登录信息」可查；下文 ssh/scp 均可换算成其 exec/put/get，长管道命令改用
> 「本地 git archive 出 tar → put → exec tar -x」三步）。

## 0｜本地准备（开机前，仓库根执行一次）

```bash
# 同步 HEAD 的门禁脚本/守卫/探针/语料到实例（覆盖旧副本）
# 密码认证走法：本地出 tar → put → exec 解包
git archive HEAD pmtec_system/scripts pmtec_system/services pmtec_system/data/corpora \
  -o /tmp/pmtec_sync.tar
python 过程脚本归档/cloud_ssh/instance_exec.py put /tmp/pmtec_sync.tar /tmp/pmtec_sync.tar
python 过程脚本归档/cloud_ssh/instance_exec.py exec \
  "tar -xf /tmp/pmtec_sync.tar -C /data/pmtec19/ && ls /data/pmtec19/pmtec_system/scripts/gate_probes_v2.json" 60
# 若已配好 SSH 密钥，也可直接：git archive ... | ssh ubuntu@36.103.199.153 "tar -x -C /data/pmtec19/"
```

## 1｜开机 + 预检（10 min）

控制台开机（**按量计费**：确认计费模式，窗口结束记得关机/释放）。SSH 上去：

```bash
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader   # 预期 2 × 24564MiB
df -h /data                                                      # 记录清理前基线
ls /data/models/Qwen2.5-7B-Instruct/config.json                  # 基座在位
/data/venv/bin/python -c "import torch,transformers,peft;print(torch.__version__)"
```

## 2｜核对云端 sft_f 与本地 sft_f_best 一致（1 min）

```bash
sha256sum /data/out/sft_f/adapter/adapter_model.safetensors
# 必须等于本地 provenance 存证：
# 551e38a693bf5ac23e1637620a2f5f38915205e34f55ff70bf6a62fdcb72306c
```
不一致 → 停止，先排查（本地 `pmtec_system/data/models/sft_f_best/` 有 README 与 manifest）。

## 3｜【GPU 1】vLLM 起服务挂 sft_f（10 min，与步骤 4 并行）

```bash
# venv_vllm 从隔离区取回（必须回原路径，符号链接才有效；原路径以
# /data/_nanhu_quarantine/ISOLATION_README.md 记录为准）
mv /data/_nanhu_quarantine/venv_vllm /data/venv_vllm

CUDA_VISIBLE_DEVICES=1 nohup /data/venv_vllm/bin/python -m vllm.entrypoints.openai.api_server \
  --model /data/models/Qwen2.5-7B-Instruct --dtype bfloat16 \
  --enable-lora --lora-modules sft_f=/data/out/sft_f/adapter --max-lora-rank 16 \
  --gpu-memory-utilization 0.90 --port 8000 \
  > /data/pmtec19/vllm_serve.log 2>&1 &

# 就绪判据（约 2-5 分钟）：返回 JSON 且含 "sft_f"
curl -s http://127.0.0.1:8000/v1/models | head -c 400
```

**失败回退**：隔离区 venv 版本不兼容（读 `vllm_serve.log` 尾部）→
`python3 -m venv /data/venv_vllm2 && /data/venv_vllm2/bin/pip install -U vllm`，
再把上面命令的 python 路径换成 `/data/venv_vllm2/bin/python` 重试。

## 4｜【GPU 0】v6b/v6 旧分数重标定（40 min，与步骤 3 并行）

```bash
# 4a. 从 NAS 拉 v6b/v6 适配器（路径按 NAS 存档填，解压后目录须直接含
#     adapter_config.json / adapter_model.safetensors）
# scp <NAS>:<v6b路径>  → /data/out/v6b/
# scp <NAS>:<v6路径>   → /data/out/v6/

# 4b. 新门禁 90 探针（42 事实 + 48 陷阱）三方同口径：base + v6b + v6
cd /data/pmtec19/pmtec_system
PMTEC_GPU=0 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  /data/venv/bin/python -u scripts/eval_citation_gate.py \
  --base /data/models/Qwen2.5-7B-Instruct \
  --adapter v6b=/data/out/v6b --adapter v6=/data/out/v6 \
  --corpus data/corpora/sft_v6_2696.jsonl \
  --out /data/out/gate_rescore_v6b_v6.json \
  2>&1 | tee /data/pmtec19/gate_rescore_v6b_v6.log | tail -40
```

- 零碰撞断言以 v6 历史语料 `sft_v6_2696.jsonl`（已入库带 manifest）为准。
- 预期量级：base ≈ 10-15 min，每个适配器再各 ≈ 10 min。
- 判读：新旧口径对照表——旧口径 v6b 锚点 0.50 / v6 拒答克隆锚点 0.50（训练报告
  里程碑 5/6）在新门禁四指标下是否保持方向；重点看 `clean_refusal_rate_unseen`
  与 `anchor_hit_rate_citation_clean`。**这是历史「负例剂量-反应」结论的复验。**

## 5｜vLLM 冒烟（10 min，服务就绪后）

```bash
cd /data/pmtec19/pmtec_system
/data/venv/bin/python -u scripts/smoke_vllm_gate.py \
  --api http://127.0.0.1:8000/v1 --model sft_f \
  --out /data/out/smoke_vllm_sft_f.json
```

通过判据（脚本末行自动打印 `SMOKE_PASS`）：净锚点 8/42、clean 32/48、假出处 6/90，
各 **±2 题**容差。
**偏差排查顺序**：① 确认请求 temperature=0（脚本已固定）② max_tokens=200 ③
`--lora-modules` 模块名与 `--model` 一致 ④ 仍超差 → 逐题 diff
`rows`（脚本 JSON 已存 `ans` 前 600 字），定位是否 vLLM 与 transformers 的
kernel 数值差异在个别边界题上翻转；附 diff 记入里程碑 15。

## 6｜结果回传（本地，5 min）

```bash
mkdir -p artifacts/p19_cloud_rounds
python 过程脚本归档/cloud_ssh/instance_exec.py get /data/out/smoke_vllm_sft_f.json     artifacts/p19_cloud_rounds/
python 过程脚本归档/cloud_ssh/instance_exec.py get /data/out/gate_rescore_v6b_v6.json  artifacts/p19_cloud_rounds/
python 过程脚本归档/cloud_ssh/instance_exec.py get /data/out/gate_drill_f.json         artifacts/p19_cloud_rounds/
```

## 7｜清理 ①②（15 min，**必须确认第 6 步 JSON 已落本地后执行**）

```bash
# ① /data/pmtec19/ 实验痕迹（结果 JSON 均已回传入库；保留 pmtec_system/ 与 vllm_serve.log 之外的决策见下）
cd /data/pmtec19
rm -f *_STARTED *_DONE *_FAIL A_* B_* C_* D_* E_* F_* AB_* \
      sft_*.log gate_*.log run_*.log

# ② /data/out/ 适配器：sft_d/sft_f 已回传本地（sha256 存证），其余按需——
#    冒烟已过、门禁 JSON 已回传 → 全部可删（语料+脚本在库，符合重跑即再生）
rm -rf /data/out/sft_clean /data/out/sft_refusal /data/out/sft_up3 \
       /data/out/sft_d /data/out/sft_e /data/out/sft_f \
       /data/out/v6b /data/out/v6
rm -f /data/out/sft_f_adapter.tar.gz
df -h /data   # 记录释放量（对照步骤 1 基线）
```

保留不动：`/data/models/Qwen2.5-7B-Instruct`（基座，复现入口）、
`/data/pmtec19/pmtec_system/`、`/data/_nanhu_quarantine/`（除已取回的 venv_vllm）。
venv_vllm 若赛后无推理需求，可在下次清理时再隔离，本次不处理。

## 8｜关机

控制台关机；按量计费确认状态变为「已停止」，若非节省停机模式则按需释放。

## 9｜本地销账（30 min，见仓库纪律）

1. `docs/PMTEC-参谋官SFT训练报告.md` 追加「里程碑 15：vLLM 冒烟 + v6b/v6 重标定」
   （冒烟三指标 vs 基准、重标定四指标 vs 旧口径对照、偏差排查记录如有）。
2. P19 计划 A-6 五条逐条标注闭环（③ 冒烟 / 2 重标定 / 5 清理完成；1/3/4 已闭环保留）。
3. commit + push（含 smoke_vllm_gate.py、本 runbook、artifacts 两份 JSON 的摘要）。
