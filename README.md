# PMTEC 数字孪生战场系统 · DTC 2026 赛道二

第八届数字孪生体挑战赛（DTC 2026）赛道二参赛作品归档。

## 目录

| 路径 | 内容 |
|---|---|
| `pmtec_system/` | 主系统：`core/`（本体与仿真内核）、`deep_rl/`（强化学习）、`distributed/`、`dt_platform/`、`learning/`、`deploy/`，含 Dockerfile 与 docker-compose |
| `ace_deployment/` | ACE 推演部署层：`algorithms/`（damage / deployment / optimization / transfer）、`engine/`、`visualization/` |
| `docs/` | 技术方案（docx/pdf）、OpenAPI 接口文档、数据字典、复现指南、参谋官 SFT 训练报告、DoDAF 视点架构、第三方接入指南、必答五问作答 |
| 根目录 | 答辩演练脚本、演示视频分镜脚本（P13 / P18-5min）、各阶段提升改造计划、严格评级报告 |

## 复现

`docs/PMTEC-复现指南.md` 为入口；`pmtec_system/docker-compose.yml` 可起完整服务，
`docker-compose.demo.yml` 为演示裁剪版。

> 私有仓库，含参赛过程材料与个人信息。
