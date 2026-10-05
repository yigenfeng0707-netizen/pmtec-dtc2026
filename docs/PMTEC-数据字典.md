# PMTEC 数据字典（Data Dictionary）

> 评审 P0 整改项：补齐数据字典与本体文件说明 ｜ 生成时间：2026-10-06 00:06 ｜ 生成器：`pmtec_system/scripts/generate_data_dictionary.py`（重跑即再生，数字不手填）
> **信息截至 2026-09**（CRS R47589 / DoD FY2024 Base Structure Report）；数量口径遵循 README「评估口径说明」：**67**=权威库实体总数、**22**=引擎实时推演口径、**15**=引擎政治准入盟友站点。

## 1. 基地权威库 `data/bases_v2.geojson`（67 实体 × 34 字段）

置信度四级标注（评审 P1 整改项）：**A 多源核验 45 站 / A- v1沿用 21 站 / B 降级 1 站（Tinian）/ D 待核验 0 站（留白口径，当前无）**。字段级来源见 `data_source` 列与 P14 PROV-O 溯源图（643 三元组）。

| 字段 | 类型 | 覆盖 | 示例 | 说明 |
|------|------|------|------|------|
| `access_uncertainty` | str | 67/67 | host_nation | 政治准入不确定性类型 |
| `ace_hub` | bool | 67/67 | False | 是否 ACE 枢纽 |
| `aircraft` | str | 67/67 | F-35A (48 planned), P-8A, RC-135 | 驻扎机型（自由文本） |
| `asda_mapping` | str | 67/67 | Act (strike launch) + Sense (ISR colle… | ASDA 四相位映射 |
| `branch` | str | 67/67 | USAF | 军种 |
| `country` | str | 67/67 | Japan | 所在国家/地区 |
| `crs_no` | int | 66/67 | 40 | CRS 报告站点编号 |
| `crs_service` | str | 45/67 | Army | CRS 军种口径 |
| `data_source` | str | 67/67 | v1 (22-base database, P1-P8) | 数据来源代际 |
| `dod_operated` | bool | 67/67 | True | 是否 DoD 运营 |
| `dtb_mapping` | str | 67/67 | Battle Network node + Application Stor… | DTB 四组件映射 |
| `facility_code` | str | 67/67 | FAC 2001 | 设施编码 |
| `fy24_bldgs_leased` | int | 56/67 | 0 | 租赁建筑数 |
| `fy24_bldgs_other` | int | 56/67 | 698 | 其他建筑数 |
| `fy24_bldgs_owned` | int | 56/67 | 330 | 自有建筑数 |
| `fy24_bsr_site` | str | 56/67 | Misawa AB (Japan) | FY2024 BSR 站名 |
| `fy24_bsr_status` | str | 67/67 | matched | BSR 匹配状态 |
| `fy24_prv_musd` | float | 56/67 | 15774.7 | 不动产重置价值（百万美元） |
| `fy24_prv_quartile` | str | 56/67 | 1st Quartile | PRV 四分位 |
| `fy24_total_acres` | float | 56/67 | 3864.42 | 占地英亩 |
| `id` | str | 67/67 | JP-MISAWA | 实体唯一标识 |
| `lvc_layer` | str | 67/67 | Virtual (simulator source) | LVC 图层归属 |
| `name` | str | 67/67 | Misawa Air Base | 基地官方名称 |
| `name_cn` | str | 67/67 | 三泽空军基地 | 中文名称 |
| `personnel` | int | 67/67 | 3600 | 驻留人员（约数） |
| `region` | str | 67/67 | Japan-North | 战区分区 |
| `role` | str | 67/67 | Tactical strike, air superiority, SEAD | 任务角色 |
| `runway_m` | int | 67/67 | 3050 | 跑道长度（米） |
| `scars` | bool | 67/67 | True | 是否 SCARS 关联 |
| `tier` | int | 67/67 | 2 | 基地层级 1-4 |
| `tier_label` | str | 67/67 | Tier 2 主要作战基地 (Main Operating Base) | 层级中文标签 |
| `unit` | str | 67/67 | 35th Fighter Wing | 驻扎主力单位 |
| `us_territory` | bool | 67/67 | False | 是否美国本土/属地 |
| `vs26_role` | str | 67/67 | F-35 Effect Simulator source - first v… | Valiant Shield 2026 角色 |

## 2. 引擎运行时状态 schema（REST `/api/v1/state` · WS 快照 · SPEAR 快照同源）

| 键 | 含义 |
|----|------|
| `sim_time` | 仿真时钟（可读） |
| `sim_seconds` | 仿真秒数 |
| `total_entities` | 实体总数 |
| `active_tracks` | 活动航迹数 |
| `asda_cycle` | ASDA 周期计数 |
| `asda_phase` | 当前 ASDA 相位 |
| `network_vulnerability` | 指挥链网络脆弱度 0-1 |
| `entities` | 动态实体列表（经 _coord_check 坐标防护） |
| `tracks` | 航迹列表（经坐标防护） |
| `kalman_tracks` | Kalman 融合航迹 |
| `coord_guard` | P18 坐标防护审计计数（rejected/原因） |
| `weather` | 气象影响叠加层 |
| `live_data_stats` | Live 数据注入统计 |
| `lvc_live_entities` | LVC Live 实体数 |
| `adversary_stats` | 对手智能体统计 |
| `political_access` | P10 政治准入态势快照（15 盟友站点三态+升级度+MRF-D） |
| `c2_chain` | P11 指挥链快照（8 指挥机构+消息流） |
| `ma_dqn_stats` | P12 多智能体 DQN 统计 |
| `persistence` | P4 持久化摘要 |
| `twin_summary` | P13 数字孪生同步层摘要（保真度） |
| `twin_top` | Top 孪生体（保真度排序） |
| `threat_stats` | 威胁/拦截统计（发射/拦截/突防/拦截率） |
| `dqn_agent` | DQN 模型在场与可用性 |

## 3. SPEAR 事件类字典（实测 22 类 / 1506 事件，与 P16 OV-3 交换矩阵 22 行对账一致）

| 事件类 | 计数 | 含义 |
|--------|------|------|
| `detect` | 591 | 传感器检测 |
| `intercept_decision` | 230 | 拦截决策（DQN/规则） |
| `c2_order` | 230 | 指挥链指令下发 |
| `asda_cycle` | 120 | ASDA 周期推进（每 10s） |
| `dqn_dispersal` | 42 | DQN 疏散决策 |
| `c2_feedback` | 35 | 指挥链反馈 |
| `political_access_change` | 33 | 政治准入状态变更（三态迁移） |
| `intercept_success` | 33 | 拦截成功 |
| `live_data_inject` | 30 | Live 数据注入（ADS-B/AIS/气象） |
| `kalman_fuse` | 30 | Kalman 多源航迹融合 |
| `ma_dqn_decision` | 30 | 多智能体 DQN 决策 |
| `adapt_summary` | 30 | Adapt 相位汇总 |
| `political_grey_zone` | 22 | 灰色地带政治事件注入 |
| `c2_report` | 15 | 指挥链上报 |
| `missile_launch` | 14 | 红方导弹发射 |
| `cyber_attack` | 8 | 网络攻击 |
| `ew_jam_start` | 5 | 电子干扰开始 |
| `transfer` | 2 | 兵力转移 |
| `cyber_detected` | 2 | 网络攻击检出 |
| `intercept_fail` | 2 | 拦截失败（突防） |
| `sim_start` | 1 | 仿真启动 |
| `recover` | 1 | 跑道/基地恢复 |

## 4. 本体语义对象（P17 语义工具层 manifest 实测）

四类语义对象：**term 85 / mapping 16 / constraint 3 / evidence 71**。

```python
from ontology.semantic_tools import browse, resolve, manifest
browse('Misawa')            # 四类对象子串检索（确定性排序）
resolve('base_JP_MISAWA')   # 个体全档案：属性+约束+Bel/Pl 区间+溯源证据
manifest()                  # 唯一进提示词的轻量清单（按需检索，不全量注入）
```

## 5. 本体文件三件套（评审 P0「本体文件」项）

| 文件 | 内容 | 加载/校验方式 |
|------|------|--------------|
| `ontology/target_characteristics.owl` | TO 五元组本体（OWL 2 DL）：67 基地四子类互斥 + 16 跑道 + 3 准入状态共 86 实体；`AirBase≡∃hasPart.Runway` 等定义类公理；BFO 对齐 | `rdflib` 加载；`ontology/reason_check.py` 跑 HermiT 一致性 + 分类推理（需 JVM java≥8，owlready2） |
| `ontology/shapes.ttl` | SHACL 形状：InstallationShape/RunwayShape/NoOrphanPartShape 等，正负样本双向验证 | `pyshacl` 校验，`conforms` 布尔 |
| `ontology/provenance.ttl` | PROV-O 溯源图 643 三元组：逐断言回指 CRS R47589 / FY2024 BSR / v1 库 | `rdflib` SPARQL 查询 |
| `ontology/dodaf_overlay.ttl` | P16 DoDAF 视点投影 123 个体/578 三元组（CAP/OV-3/SvcV 追溯链） | `pyshacl` 9 形状校验，`dodaf_validation_report.json` conforms=true |

## 6. Monte Carlo 结果文件字典（`data/monte_carlo_results*.json`）

| 文件 | 场景 | 关键键 |
|------|------|--------|
| `monte_carlo_results.json` | A：原 22 站 · 182 维 P6 | `overall.intercept_rate`、`intercept_rate_ci_lower/upper`、`n_episodes`、`total_missiles` |
| `monte_carlo_results_v2.json` | B：v2 权威数据 · 182 维 P6 | 同上 |
| `monte_carlo_results_v2_political.json` | C：v2+政治准入 · 219 维 P12（**基准口径 79.1%**） | 同上 + `per_strategy`（六策略分列） |

## 7. REST API 与第三方接入

全量端点/请求响应 schema/鉴权见 `docs/PMTEC-OpenAPI接口文档.md`（openapi.yaml）；接入示例（curl/Python/JS）见 `docs/PMTEC-第三方接入指南.md`；端到端复现见 `docs/PMTEC-复现指南.md`。
