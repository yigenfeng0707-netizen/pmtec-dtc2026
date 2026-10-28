# P19 云端实验轮 runbook 与排障探针归档（2026-10-28）

对应 docs/PMTEC-参谋官SFT训练报告.md 里程碑 9-14（实例 36.103.199.153，双卡 4090）。
这些脚本在实例 /data/pmtec19/ 上执行；启动方式与 marker 通道见各文件头。

## 五轮 runbook（setsid nohup + 标记文件通道）

| 文件 | 轮次 | 语料 | 结果 |
|---|---|---|---|
| run_baseline.sh | 基线重标定 | — | clean 0.2917 / 锚点 0（里程碑 9） |
| run_ab.sh | A/B 对照 | sft_facts 352 / sft_refusal 492 | A 灾难 0.0417；B 拒答 0.7917（里程碑 10） |
| run_c.sh | C 配比 | sft_up3_refusal 1476 | 锚点 2/42 不动（里程碑 11） |
| run_d.sh | D 覆盖 | sft_d_refusal 552 | 毛锚点 5/42（里程碑 12） |
| run_e.sh | E 出处 | sft_e_refusal 550 | 毛锚点 9/42 首次显著（里程碑 13） |
| run_f.sh | F drill | sft_f_refusal 607 | 净锚点 8/42 显著（里程碑 14） |

每轮唯一变量与结论见训练报告；语料全部在 data/corpora/（manifest sha 校验链）。

## 排障探针（复用价值）

- diag_mem.py：SFT OOM 逐阶段显存探针——定位「Trainer 路径 22.95GB vs 手写路径
  17.76GB」分歧的关键工具；下次训练 OOM 先跑它再改配置。
- diag_train.py：完整 Trainer 循环 + 逐步内存回调（复现 OOM 用）。
- check_env.py：实例依赖体检（torch/transformers/peft/trl/liger 版本一览）。

## 已删除（一次性，无归档价值）

relaunch_ab.py（被 cloud_ssh/instance_exec.py 取代）、diag_ab.py、
pmtec_system.tar.gz / baseline_bundle.tar.gz（内容在 git）。

## 实例侧遗留（实例关机中，下次开机清理）

/data/pmtec19/ 下的 A_*/B_*/C_*/D_*/E_*/F_*/AB_* 标记文件、sft_*.log、
gate_*.log、run_*.log 为实验过程痕迹，可整目录删除（结果 JSON 已回传入库）；
/data/out/ 下 sft_clean/sft_refusal/sft_up3/sft_d/sft_e/sft_f 适配器按需保留
（sft_d/sft_f 已回传本地 sft_d_best/sft_f_best）。
