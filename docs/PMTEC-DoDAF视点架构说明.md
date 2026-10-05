# PMTEC 政治韧性数字孪生体系 — DoDAF 2.02 视点架构说明

> 生成日期：2026-10-06（由 `pmtec_system/ontology/build_dodaf_views.py` 自动导出，重跑可再生）  
> 方法声明：本文借用 DoDAF 2.02 公开视点框架（AV/CV/OV/DIV/SvcV/SV/StdV/PV）与追溯链范式；全部内容针对 PMTEC 自有体系独立建模，所有矩阵行由脚本从仓库真实工件（SPEAR 实跑报告、UJTL 数据集、gRPC 服务源码、配置文件、页面文件）推导，无人工誊写行。  
> 追溯链校验：SHACL `conforms=True`，违规 0 条，跨本体锚点断裂 0 处。

## 1. AV 全局视点（视角总纲）

**体系**：PMTEC 政治韧性数字孪生试验床——以政治准入模型为一等公民的INDOPACOM 基地群数字孪生与推演体系。

**视角投影总表**（每行 = 覆盖层一个类，个体数机器统计）：

| DoDAF 视点 | 覆盖层类 | 个体数 | 真实工件来源 |
|---|---|---:|---|
| CV 能力 | `dd:Capability` | 33 | data/ujtl/ujtl_segments.csv（UJTL 编号段） |
| OV-2 活动 | `dd:OperationalActivity` | 33 | 同上（段名即活动） |
| OV-2 角色 | `dd:Role` | 10 | output/pmtec_spear_report.json 事件 source 分组 |
| OV-3 交换 | `dd:InformationExchange` | 22 | 同上，22 事件类型 × 观测计数 |
| DIV 信息实体 | `dd:InformationEntity` | 6 | 引擎状态语义 + tc# 本体类型锚定 |
| SvcV 服务 | `dd:ServiceContract` | 6 | services/grpc_server.py _init_app_store（ast 解析） |
| SV 系统 | `dd:SystemNode` | 10 | grpc_server.py Servicer 类 + config.py 端口 + 页面文件 |
| PV 项目 | `dd:ProjectActivity` | 2 | .github/workflows + Dockerfile |

追溯主链：`CAP ← OA ← EX → ENT`（能力—活动—交换—实体），旁链 `Role →allocatedTo→ SYS`、`SER →realizes→ CAP`、`SYS →realizes→ CAP`、`PRO →verifies→ SYS`，全部由 SHACL 形状强制无悬空。

## 2. CV 能力视点

能力基线取自 UJTL（通用联合任务清单）33 个编号段，任务/指标计数为数据集实测值：

| 能力代码 | 能力名称 | 层级 | UJTL任务数 | 衡量指标数 |
|---|---|---|---:|---:|
| OP 1 | 实施战役机动 | 战役层 | 40 | 479 |
| OP 2 | 实施联合情报行动 | 战役层 | 47 | 736 |
| OP 3 | 实施火力打击 | 战役层 | 40 | 410 |
| OP 4 | 提供战役后勤保障 | 战役层 | 55 | 765 |
| OP 5 | 提供指挥与控制 | 战役层 | 95 | 1177 |
| OP 6 | 提供战役部队防护 | 战役层 | 32 | 419 |
| OP 7 | 实施反大规模杀伤性武器行动 | 战役层 | 8 | 209 |
| OP 8 | 实施军事接触 | 战役层 | 14 | 77 |
| SN 1 | 管理部署与重新部署 | 战略—国家层 | 15 | 305 |
| SN 2 | 提供战略情报 | 战略—国家层 | 57 | 452 |
| SN 3 | 运用部队 | 战略—国家层 | 102 | 802 |
| SN 4 | 提供后勤保障 | 战略—国家层 | 54 | 345 |
| SN 5 | 发布战略指导 | 战略—国家层 | 107 | 674 |
| SN 6 | 实施动员 | 战略—国家层 | 21 | 148 |
| SN 7 | 实施部队发展 | 战略—国家层 | 36 | 288 |
| SN 8 | 协调军事接触活动 | 战略—国家层 | 19 | 195 |
| SN 9 | 协调反大规模杀伤性武器行动 | 战略—国家层 | 21 | 275 |
| ST 1 | 部署部队 | 战略—战区层 | 29 | 251 |
| ST 2 | 提供战区情报 | 战略—战区层 | 63 | 706 |
| ST 3 | 运用火力 | 战略—战区层 | 24 | 288 |
| ST 4 | 保障部队 | 战略—战区层 | 36 | 486 |
| ST 5 | 实施指挥与控制 | 战略—战区层 | 72 | 865 |
| ST 6 | 协调防护 | 战略—战区层 | 27 | 341 |
| ST 7 | 确定部队需求 | 战略—战区层 | 17 | 159 |
| ST 8 | 遂行军事接触 | 战略—战区层 | 44 | 581 |
| ST 9 | 实施反大规模杀伤性武器行动 | 战略—战区层 | 9 | 264 |
| TA 1 | 执行机动 | 战术层 | 13 | 76 |
| TA 2 | 共享情报 | 战术层 | 12 | 64 |
| TA 3 | 执行火力打击 | 战术层 | 23 | 177 |
| TA 4 | 保障已部署部队 | 战术层 | 3 | 15 |
| TA 5 | 遂行指挥与控制 | 战术层 | 21 | 215 |
| TA 6 | 防护部队 | 战术层 | 9 | 120 |
| TA 7 | 在化学、生物、放射或核危险区域行动 | 战术层 | 4 | 50 |

## 3. OV-2 作战活动与角色

### 3.1 作战角色（事件源实测分组）

| 角色 | 名称 | 观测事件数 | 配置系统 |
|---|---|---:|---|
| `role_asda_engine` | ASDA 决策引擎 | 417 | sys-WarEngine |
| `role_c2_chain` | 指挥链模型 | 280 | sys-WarEngine |
| `role_dqn_agent` | DQN 分散决策智能体 | 42 | sys-WarEngine |
| `role_hostile_forces` | 红方对手兵力 | 49 | sys-WarEngine |
| `role_lvc_fusion` | LVC 航迹融合 | 30 | sys-WarEngine |
| `role_lvc_live` | LVC 实装数据接入 | 30 | sys-realtime-ws |
| `role_maddpg_agent` | MADDPG 多智能体 | 30 | sys-WarEngine |
| `role_platform_clock` | 平台系统自身 | 1 | sys-WarEngine |
| `role_political_access_model` | 政治准入模型 | 33 | sys-WarEngine |
| `role_sensor_grid` | 传感网与友邻单元 | 594 | sys-WarEngine |

### 3.2 作战活动

与能力一一对应（33 项，段名原文即活动名），此处仅列各活动被哪些信息交换触达：

| 作战活动（原文） | 触达交换数 | 交换（事件类型） |
|---|---:|---|
| Provide Command and Control (C2) | 5 | adapt_summary, asda_cycle, c2_feedback, c2_order, c2_report |
| Share Intelligence | 4 | detect, kalman_fuse, live_data_inject, transfer |
| Execute Fires | 4 | intercept_decision, intercept_fail, intercept_success, missile_launch |
| Execute Maneuver | 3 | dqn_dispersal, ma_dqn_decision, sim_start |
| Protect the Force | 3 | cyber_attack, cyber_detected, ew_jam_start |
| Issue Strategic Direction | 2 | political_access_change, political_grey_zone |
| Sustain Deployed Forces | 1 | recover |

## 4. OV-3 信息交换矩阵

全部 22 行由 SPEAR 实跑报告事件流聚合生成，观测计数 = 该事件类型在一次完整推演中的出现次数：

| 交换（事件类型） | 观测次数 | 追溯到活动 | 信息实体 | 产生角色 |
|---|---:|---|---|---|
| `detect` | 591 | Share Intelligence | 传感器航迹信息 | 传感网与友邻单元 |
| `c2_order` | 230 | Provide Command and Control (C2) | 拦截火力协同信息 | 指挥链模型 |
| `intercept_decision` | 230 | Execute Fires | 拦截火力协同信息 | ASDA 决策引擎 |
| `asda_cycle` | 120 | Provide Command and Control (C2) | 指挥控制状态信息 | ASDA 决策引擎 |
| `dqn_dispersal` | 42 | Execute Maneuver | 平台与数字孪生体状态信息 | DQN 分散决策智能体 |
| `c2_feedback` | 35 | Provide Command and Control (C2) | 指挥控制状态信息 | 指挥链模型 |
| `intercept_success` | 33 | Execute Fires | 拦截火力协同信息 | ASDA 决策引擎 |
| `political_access_change` | 33 | Issue Strategic Direction | 政治准入状态信息 | 政治准入模型 |
| `adapt_summary` | 30 | Provide Command and Control (C2) | 指挥控制状态信息 | ASDA 决策引擎 |
| `kalman_fuse` | 30 | Share Intelligence | 传感器航迹信息 | LVC 航迹融合 |
| `live_data_inject` | 30 | Share Intelligence | 传感器航迹信息 | LVC 实装数据接入 |
| `ma_dqn_decision` | 30 | Execute Maneuver | 平台与数字孪生体状态信息 | MADDPG 多智能体 |
| `political_grey_zone` | 22 | Issue Strategic Direction | 政治准入状态信息 | 红方对手兵力 |
| `c2_report` | 15 | Provide Command and Control (C2) | 指挥控制状态信息 | 指挥链模型 |
| `missile_launch` | 14 | Execute Fires | 导弹与网络电磁威胁信息 | 红方对手兵力 |
| `cyber_attack` | 8 | Protect the Force | 导弹与网络电磁威胁信息 | 红方对手兵力 |
| `ew_jam_start` | 5 | Protect the Force | 导弹与网络电磁威胁信息 | 红方对手兵力 |
| `cyber_detected` | 2 | Protect the Force | 导弹与网络电磁威胁信息 | ASDA 决策引擎 |
| `intercept_fail` | 2 | Execute Fires | 拦截火力协同信息 | ASDA 决策引擎 |
| `transfer` | 2 | Share Intelligence | 传感器航迹信息 | 传感网与友邻单元 |
| `recover` | 1 | Sustain Deployed Forces | 平台与数字孪生体状态信息 | 传感网与友邻单元 |
| `sim_start` | 1 | Execute Maneuver | 平台与数字孪生体状态信息 | 平台系统自身 |

## 5. DIV 数据/信息视点（信息实体契约）

| 信息实体 | 名称 | 锚定的目标特性本体类型 |
|---|---|---|
| `ent_c2_status` | 指挥控制状态信息 | `tc:AccessDeniedSite` |
| `ent_fire_control` | 拦截火力协同信息 | `tc:LaunchCapable` |
| `ent_missile_threat` | 导弹与网络电磁威胁信息 | `tc:MilitaryInstallation` |
| `ent_platform_state` | 平台与数字孪生体状态信息 | `tc:FacilityPart` |
| `ent_political_access` | 政治准入状态信息 | `tc:AccessState` |
| `ent_sensor_track` | 传感器航迹信息 | `tc:MilitaryInstallation` |

信息实体是 OV-3 交换与目标特性本体（TO 五元组）之间的类型契约：交换必须aboutEntity 到实体、实体必须锚定 tc# 已声明类，跨本体悬空由 dodaf_check.py 拦截。

## 6. SvcV 服务视点

| 服务契约 | 名称 | 版本 | 类别 | 支撑能力 | 提供方 |
|---|---|---|---|---|---|
| `svc_app_ace_dispersal` | ACE Agile Combat Employment | v2.5 | logistics | 保障已部署部队 | sys-ApplicationStore |
| `svc_app_f35_strike` | F-35A Strike Package | v2.1 | strike | 实施火力打击 | sys-ApplicationStore |
| `svc_app_iamd_defense` | IAMD Integrated Air Defense | v3.0 | defense | 防护部队 | sys-ApplicationStore |
| `svc_app_isr_collection` | ISR Sensor Collection | v1.8 | isr | 提供战区情报 | sys-ApplicationStore |
| `svc_app_jad_ai` | JAD-AI Joint All-Domain AI | v0.9-beta | decision | 提供指挥与控制 | sys-ApplicationStore |
| `svc_app_spear_replay` | SPEAR Replay Analysis | v1.2 | analysis | 提供指挥与控制 | sys-ApplicationStore |

## 7. SV 系统视点

| 系统节点 | 名称 | 接口/工件端点 | 支撑能力 |
|---|---|---|---|
| `sys-ApplicationStore` | 应用商店服务 | pmtec://grpc:50051 | 提供指挥与控制 |
| `sys-BattleNetwork` | 作战网络服务 | pmtec://grpc:50051 | 提供指挥与控制, 防护部队 |
| `sys-PlugAndPlay` | 即插即用服务 | pmtec://grpc:50051 | 提供指挥与控制 |
| `sys-WarEngine` | 战争引擎服务 | pmtec://grpc:50051 | 提供指挥与控制 |
| `sys-page-dt_dashboard` | dt_dashboard.html | static://output/dt_dashboard.html | 提供指挥与控制 |
| `sys-page-pmtec_globe` | pmtec_globe.html | static://output/pmtec_globe.html | 提供指挥与控制 |
| `sys-page-pmtec_realtime_display` | pmtec_realtime_display.html | static://output/pmtec_realtime_display.html | 提供指挥与控制 |
| `sys-page-pmtec_spear_timeline` | pmtec_spear_timeline.html | static://output/pmtec_spear_timeline.html | 提供指挥与控制 |
| `sys-realtime-ws` | 实时态势 WebSocket 服务 | :8765 | 共享情报 |
| `sys-rest-gateway` | 数字孪生 REST 网关 | :8080 | 部署部队 |

## 8. StdV 标准视点

- **DoDAF 2.02 视点投影基线（方法借用，非条款引用）**（`std_dodaf_projection`）：视点方法与追溯链遵循 DoDAF 2.02 公开框架；数据侧遵循既有基线——UJTL/CJCSI 3500.02D 任务清单口径、PROV-O 溯源、OWL 2 DL + HermiT 一致性（tc 基线本体）、SHACL 形状校验、军用不在场（纯公开资料研究建模，无任何侦察采集能力）。

## 9. PV 项目视点

| 建设项目 | 验证的系统节点 | 真实工件 |
|---|---|---|
| CI/CD 质量门建设 | sys-ApplicationStore, sys-BattleNetwork, sys-PlugAndPlay, sys-WarEngine | `../.github/workflows` |
| 容器化交付建设 | sys-ApplicationStore, sys-BattleNetwork, sys-PlugAndPlay, sys-WarEngine | `Dockerfile` |

## 10. 全链路追溯与机器校验

抽一条链走读（机器遍历）：

- EX(intercept_decision, 230 次观测) → OA(Execute Fires) → CAP(执行火力打击)
- EX → ENT(拦截火力协同信息) → tc:LaunchCapable
- EX ← Role(ASDA 决策引擎) → SYS(sys-WarEngine)

**校验结论**（`dodaf_check.py` 输出，报告落盘 `pmtec_system/ontology/dodaf_validation_report.json`）：

- SHACL 追溯链（9 个形状，覆盖 123 个体）：conforms = **True**，违规 0 条
- 跨本体锚点（dd:InformationEntity → tc# 类）：断裂 0 处
- 基线本体（target_characteristics.owl）HermiT 一致性由既有 `reason_check.py` 守护；覆盖层为个体投影层，判定程序为 SHACL。

---
*本文档为脚本生成物：修改任何真实工件后重跑 `dodaf_build.py → dodaf_check.py → build_dodaf_views.py` 即自动同步。*
