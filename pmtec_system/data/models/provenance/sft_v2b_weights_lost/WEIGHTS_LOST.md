# sft_v2b 适配器权重丢失说明

## 状态

**权重已丢失，本目录仅保留 `adapter_config.json` 与 `README.md` 作为归档凭据。**

## 经过

- 2026-10-24：SFT v2（语料 1,926 行 = 352 唯一问题 × 事故性重复）在超算云实例
  `ecs-mlzsy`（RTX 4090 ×2）训出适配器，产出 `/data/out/sft_pmtec_lora_v2b/adapter`
  （170MB safetensors），经 vLLM `--enable-lora` 挂载服务验证通过。
- 该实例关机前未完整备份：关机时只落了 `adapter_config.json` 与 `README.md`，
  `adapter_model.safetensors` 未回传。
- ECS 侧无副本，且数据盘当时已 100% 满。
- 清理时确认 safetensors 不完整，遂将残留文件归档到本目录，不再保留在
  `data/models/`（避免被 DPO 脚本误认为可用基座）。

## 为什么现在不恢复

`bootstrap_gpu_instance.sh` 与 `train_dpo_pmtec.py` 都曾把这个路径当作 SFT 基座，
是「换卡续跑第一步就 `FileNotFoundError`」的直接原因。P19 改造后：

- `train_dpo_pmtec.py` 的 `PMTEC_DPO_SFT` **无默认值**，缺失即报错并列出实际可用的适配器；
- 目录存在但 `adapter_model.safetensors` 缺失时，会明确提示「权重已丢失」而非继续。

## 如何再生

语料与配方都在仓库里，重跑即可再生（这正是「重跑即再生」纪律要兑现的地方）：

```bash
# 1) 生成事实语料（352 唯一问题；如需复现历史重复量级用 --upsample 8）
cd pmtec_system && python scripts/build_sft_corpus.py --report

# 2) SFT 训练（单卡即可，设备由 PMTEC_GPU 指定）
PMTEC_SFT_DATA=data/corpora/sft_facts.jsonl \
PMTEC_SFT_OUT=/data/out/sft_clean \
python scripts/train_sft_pmtec.py

# 或用统一流水线
bash scripts/train_pipeline.sh preflight
bash scripts/train_pipeline.sh corpus
bash scripts/train_pipeline.sh sft
```

**注意**：重训得到的不是「v2b 本体」，而是同配方的新检查点。历史 v2b 的门禁成绩
（锚点 0.50 / 幻觉率 1.0）在新门禁口径下不可直接比较——门禁已改为四项指标
（见 `docs/PMTEC-门禁指标说明.md`），旧分数需在新门禁下重新标定。