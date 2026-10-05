# PMTEC 数字孪生战场系统

## DTC 2026 Level 3 - 数字孪生战场 (Digital Twin Battlefield)

## 概述

PMTEC（Pacific Multi-domain Training and Experimentation Capability）数字孪生战场仿真系统，实现 DTB Model 全链路作战逻辑，核心采用 **ASDA（Act-Sense-Decide-Adapt）闭环循环** 驱动仿真时序。

系统经 P1-P17 共 17 轮迭代演进，从基础仿真原型发展为具备多层 AI 决策、安全认证、分布式高可用、可观测性、LLM 智能参谋、虚实同步数字孪生层与本体语义层的成熟数字孪生平台。Monte Carlo 评估总体拦截率 **76.2%**（95% CI 74.7-77.7%，P6 基线）；P12 权威数据升级后 **79.1%**（95% CI 78.0-80.2%，六策略 150 episodes，219 维政治观测模型），政治准入演化场景下不降反稳——体系韧性获得量化验证。P9 起基于比赛方下发的权威资料（CRS R47589 / DoD FY2024 基地结构报告 / RAND RRA967-2 / CRS IF12175）完成权威数据升级与体系化对抗深化；P13 实现大模型融合的 AI 参谋官与虚实同步数字孪生层（23 孪生体，保真度 96.9%）。

---

## 评估口径说明（数据一致性声明）

> 信息截至 2026-09：实体/置信/溯源数据均截至 CRS R47589（2026-02 更新）与 DoD FY2024 Base Structure Report，后续源更新后会以提交历史留痕刷新。
> 本节为全仓唯一口径权威表，任何文档引用数字必须能归入以下行；口径自检脚本 `scripts/caliber_check.py`。

### 基地数量口径（评审 P1 整改项：67/22/15 统一）

| 数字 | 权威定义 | 使用位置 | 不得混用为 |
|------|----------|----------|------------|
| **67** | 印太基地**实体总数**（v2 权威库 `data/bases_v2.geojson`，CRS R47589 + FY2024 BSR 双源） | 一级标绘、本体层（86 实体）、DoDAF 投影、基地档案、部署优化、P9 负载测试 | 不等于"引擎同时推演 67 站" |
| **22** | **引擎实时推演口径**（v1 库 `data/bases.geojson`；P6 182 维/P12 219 维观测、训练模型、MC 三场景全部锚定此拓扑；P11 C2 链 22 站） | 引擎 REST/WS 实时推演、`ai_situation_analysis`（"下辖22个基地"）、P6/P12 MC | 不等于"全库只有 22 站" |
| **15** | 引擎**政治准入盟友站点**（22 站中澳/日/菲/韩 4 东道国子集；基线 15 全 Open，推演中呈 5 Open/7 Restricted/3 Denied） | P10 政治状态机、AI 参谋官报告（"盟友站点共15个"） | 不等于"盟友基地总数" |
| 36 | v2 权威库 `access_uncertainty=host_nation` 计数（**分析管线口径**：韧性分析、五问 S1 主行） | `political_resilience_analysis.py`、`five_questions_analysis.py` | 与 15 是不同管线的同义概念，引用须带"分析口径"限定语 |
| 45/21/1 | 置信度**四级标注**：A=多源核验 45 站 / A-=v1 沿用 22 站 / B=降级 1 站（Tinian）/ D=待核验（当前 0，留白口径） | P14 置信层 `confidence.py`、基地档案精度列 | D 级留白是"当前无待核验项"，非数据缺失 |

### 拦截率口径

系统中出现的拦截率数字**分属不同评估口径**，均为真实运行产物，不可混用：

| 口径 | 数值 | 数据来源 | 用途 |
|------|------|----------|------|
| **基准口径（权威）** | 79.1%（CI 78.0-80.2%） | P12 六策略 150 episodes Monte Carlo | 论文/报告引用的唯一基准 |
| 三场景对照 | 76.2% → 79.0% → 79.1% | A 22站·P6 / B v2·P6 / C v2+政治·P12 | 数据升级与政治约束的净效应对照 |
| 政治准入场景 | 79.5% | P12 场景 C（准入演化） | 体系韧性论证 |
| 饱和攻击演示 | 88.9%-100% | P13 `--saturation` 单次运行 | 孪生反哺/AI 参谋官能力演示 |

**规则**：对外引用一律使用基准口径 79.1%（三场景对照须整组引用）；演示类数字必须注明"单次运行/演示场景"；量化作答（失效场景/保留率/交换比/敏感性）以 `docs/必答五问作答.md` 与 `output/Five_Questions_Report.html` 为唯一权威出处。

---

## 技术架构

```
pmtec_system/
|-- proto/                        # gRPC 服务定义 (4 DTB 服务, 433 行)
|   |-- dtb_model.proto
|   `-- generated/                # 编译后的 Python gRPC stubs
|-- config.py                     # 系统配置 (206 行, 含安全/HA/可观测/实时数据开关)
|-- core/
|   |-- event_bus.py             # 发布/订阅事件驱动框架
|   |-- simulation_clock.py       # 仿真时钟管理 (SIM_TICK=1s, ASDA_CYCLE=10s)
|   `-- lvc_architecture.py       # LVC (Live/Virtual/Constructive) 三层架构
|-- models/
|   |-- entity.py                 # 飞机/导弹/传感器实体模型
|   |-- track.py                  # 传感器融合与航迹管理
|   |-- political_access.py       # P10 政治准入三态状态机 (Full/Restricted/Denied)
|   `-- c2_chain.py               # P11 INDOPACOM 指挥链 (5 军种组成 + 3 下属联合)
|-- deep_rl/                      # 深度强化学习模块 (2,229 行)
|   |-- pmtec_env.py              # Gymnasium 环境 (182 维观测, 800 行)
|   |-- dqn_agent.py              # DQN 智能体 (SB3 + XPU 加速)
|   |-- maddpg_agent.py           # MADDPG 多智能体 (584 行)
|   |-- multi_agent_dqn.py        # IQL 独立学习多智能体 (376 行)
|   `-- multi_agent_env.py        # 多智能体环境封装
|-- services/
|   |-- grpc_server.py            # gRPC 服务端 + 仿真引擎 (3,031 行)
|   |-- spear_replay.py           # SPEAR 重放与分析
|   `-- prometheus_metrics.py      # Prometheus 指标导出 (7 类指标)
|-- security/                     # 安全认证体系 (6 模块, 898 行)
|   |-- auth.py                   # JWT Token 管理 (HS256)
|   |-- rbac.py                   # 角色访问控制 (Commander/Operator/Observer)
|   |-- audit.py                  # 哈希链审计日志 (SQLite 持久化)
|   |-- cert_manager.py           # mTLS X.509 证书管理
|   `-- interceptor.py            # gRPC 安全拦截器
|-- distributed/                  # 分布式服务 (1,090 行)
|   |-- grpc_server_dist.py       # 分布式 gRPC 服务端
|   |-- grpc_clients.py           # gRPC 客户端 + HA 通道管理器
|   `-- docker_deploy.py          # Docker 部署工具
|-- dt_platform/                  # 数字孪生平台层 (771 行)
|   |-- plugin_manager.py         # 插件管理
|   |-- rest_gateway.py           # REST 网关
|   `-- dt_registry.py            # 数字孪生实例注册
|-- live_data/                    # 实时数据接入 (1,215 行)
|   |-- opensky_adapter.py        # OpenSky ADS-B 航迹数据
|   |-- openmeteo_adapter.py      # OpenMeteo 气象数据
|   `-- ais_adapter.py            # AIS 船舶数据
|-- persistence/
|   |-- state_store.py            # SQLite WAL 模式状态持久化
|   `-- kalman_filter.py          # Kalman/JPDA 航迹融合
|-- learning/
|   |-- ucb1_bandit.py            # UCB1 传感器选择
|   `-- q_learning.py             # Q-Learning 自适应
|-- visualization/
|   |-- tactical_display.py       # HTML/JS 战术态势图
|   `-- realtime_3d.py            # 3D 实时渲染
|-- realtime/                     # 实时态势 (597 行)
|-- scripts/                      # 工具脚本 (2,428 行)
|   |-- monte_carlo_validation.py # Monte Carlo 验证框架
|   |-- curriculum_training.py    # 课程学习训练
|   |-- load_test.py              # 负载测试套件
|   `-- retrain_multiagent_182.py # 多智能体重训练
|-- data/
|   |-- models/                   # AI 模型文件 (6 核心 + 检查点)
|   |-- persistence/              # SQLite 数据库
|   |-- bases.geojson             # 22 个 INDOPACOM 基地
|   `-- certs/                    # mTLS 证书
|-- Dockerfile                    # 多阶段构建
|-- docker-compose.yml            # 7 服务编排
`-- .github/workflows/ci-cd.yml   # GitHub Actions 6 阶段流水线
```

---

## ASDA 闭环

每个 10 秒 ASDA 周期依次执行：

1. **Act（行动）**: 执行当前命令、导弹发射、ACE 分散部署
2. **Sense（感知）**: 运行全部传感器，收集并融合多源航迹
3. **Decide（决策）**: 评估威胁，决定拦截/规避/转移对策（DQN/MADDPG/IQL 驱动）
4. **Adapt（适应）**: 执行决策、损伤评估、资源恢复、经验反馈

---

## P1-P12 技术演进

### P1: 基础仿真原型
- ASDA 四阶段闭环 + 4 gRPC 服务（WarEngine/BattleNetwork/ApplicationStore/PlugAndPlay）
- LVC 三层架构（Live/Virtual/Constructive）
- 22 个 INDOPACOM 基地 + SPEAR 重放分析
- 基础 HTML 战术态势显示

### P2: XPU 加速与分布式
- Intel Arc GPU (XPU) 加速 DQN 训练（torch 2.14.0+xpu）
- proto 扩展至 433 行 / 22 条新消息
- `distributed/` 分布式 gRPC 包
- `live_data/` LVC Live 数据适配器（ADS-B/AIS/Weather）

### P3: 多物理效应与对抗建模
- 天气影响闭环（4 级：晴/轻/中/极端，影响传感器探测距离）
- Kalman 滤波航迹融合
- DQN 扩维至 122 维 + 50K 步训练
- 对抗性建模（EW 电子战 + Cyber 网络威胁）

### P4: 持久化与多智能体
- SQLite WAL 模式状态持久化（快照/航迹/事件）
- Docker 分布式部署
- 实时 3D 战术态势渲染
- 多智能体 IQL（双 Agent 6K 步训练，avg reward 301.2）

### P5: 高级传感器融合与超长训练
- JPDA 多目标关联算法
- MADDPG 真多智能体（8K 步，avg reward 398.2）
- DQN 200K 步超长训练
- 3D 渲染性能优化

### P6: 182 维观测空间与拦截概率重构
- OBS_DIM 122→182（新增 60 维威胁特征：10 威胁 × 6 特征）
- 拦截概率模型重构：解除硬编码 ~54% 上限 → 0.95 上限
- 奖励塑形（拦截成功 + 基地存活 - 损伤 - 时间惩罚）
- 200K 步 XPU 课程学习训练
- Monte Carlo 评估：总体 76.2%（CI 74.7-77.7%）

### P7: 隐身突防与生产级安全
- 3 阶段递进难度课程学习（隐身突防场景）
- 环境层物理修复：极端天气 detection_range_factor 0.3→0.5
- 区域防空兜底概率（未探测目标 0.15+0.10×(1-TTI/120)）
- **隐身突防拦截率 79.1%**（P6 53.7% → +25.4%）
- 安全认证体系 6 模块：JWT/RBAC/审计/CA/mTLS/gRPC 拦截器
- gRPC 高可用（Health Check + HA 通道管理器 + 指数退避重连）
- 实时数据 API（OpenSky/OpenMeteo + 重试 + fallback）
- Prometheus 7 类指标 + Grafana 34 面板
- CI/CD（Dockerfile 多阶段 + docker-compose 7 服务 + GitHub Actions 6 阶段）

### P8: 多智能体重训练与运维交付
- IQL/MADDPG 182 维重训练（6K 步，avg reward 881.6）
- 负载测试套件（SQLite 写入峰值 58K wps / gRPC 峰值 158 RPS / 引擎并发 378 QPS 线程安全）
- 灾备恢复 Runbook（L1-L4 四级备份 / 5 故障恢复场景 / 巡检清单 / 灾备演练计划）
- 系统架构文档（13 章节，P1-P7 演进故事线）

### P9: 权威基地数据库升级（22 → 67 实体）
- `indopacom_bases_v2.geojson`：CRS R47589 Table A-1 全量 66 站点 + Tinian North Field = 67 实体
- FY2024 基地结构报告字段融合：`fy24_prv_quartile`（PRV 四分位）/ `fy24_prv_musd` / `fy24_total_acres` 等
- 新增 `crs_no` / `dod_operated` / `us_territory` / `access_uncertainty` / `tier` 属性，四级 Tier 分层
- QGIS 工程与 Leaflet 地图重生成；数据贯通 pmtec_system 与 ace_deployment
- 验收：`test_p9.py` 13 项（数据完整性 + 引擎 67 实体冒烟 + RL 环境前向兼容 + 全量建图）

### P10: 盟友协同与政治约束建模（RAND 深化）
- `models/political_access.py`：政治准入三态状态机（Full/Restricted/Denied）
- 4 类政治事件（灰色地带/冲突升级/主权打击/再保证）驱动事件化状态转移
- MRF-D 六个月轮换建模（换防窗战备 0.6 / 战时冻结政治成本 0.35）
- 盟友谈判延迟、政治风险敞口、基线扰动敏感性（蒙特卡洛支持）
- ACE 算法约束版：部署优化器排除 Denied 站点，Pareto 新增政治风险敞口目标
- 验收：`test_p10.py` 28 项（状态机 A1-A7 + 三场景 Monte Carlo + 灰色地带链路回放 C）

### P11: INDOPACOM 指挥控制组织架构建模
- `models/c2_chain.py`：指挥关系树（战区级 → 军种组成/下属联合 → 基地）
- 5 军种组成司令部（USARPAC/PACFLT/MARFORPAC/PACAF/USSFPAC）+ 3 下属联合司令部（USFJ/USFK/SOCPAC）
- 逐跳事件上报/命令下发 + 跨军种协同（最近共同祖先路由）+ hop-by-hop 延迟审计
- RBAC 军种扩展（如 PACAF-Operator 仅可操作空军资产）+ JWT branch claim 联动
- 验收：`test_p11.py` 31 项（指挥链抽查 + 跨军种协同 + RBAC/Auth 后向兼容）

### P12: 系统全链路升级与重验证
- P12.2 DQN 观测空间扩维 182→219（36 盟友站点准入容量 + 全局升级度），XPU 200K 步三阶段课程重训练
- P12.3 WebSocket 升级：10 并发上限、暂停/恢复/回溯（逐周期环形缓冲）、分层实时态势图（权威库 67 实体分层设计；引擎实时推演默认 v1 22 站拓扑，见口径表）
- P12.4 SPEAR 时间轴：四泳道事件渲染 + 盟友准入构成带 + 冲突升级度曲线
- P12.5 对手策略库 4→6：multi_axis_saturation（多轴协同饱和）+ political_divergence（政治分化压制）
- P12.6 REST 网关 Maven 契约补全：四大 DTB 服务 + P10 political + P11 c2
- P12.7 Monte Carlo 重验证：A 76.2%（原基线）/ B 79.0%（v2 数据）/ C 79.5%（政治准入）三场景对照；
  六策略全量 79.1%（CI 78.0-80.2%）
- 验收：`test_p12_1_obs.py` 16 项 + `test_p12_3_websocket.py` 16 项 + `test_p12_final.py` 23 项

### P13: AI 参谋官 + 数字孪生同步层 + 饱和攻击（LLM 融合迭代）

**数字孪生同步层（`dt_platform/twin_sync.py`）**——系统从"仿真"升级为真正的"孪生"：
- **22 个基地孪生体**：物理域（飞机在位/传感器/政治准入实测）↔ 虚拟域（就绪度模型 = 资产可用性 × 准入概率），实时偏差与保真度追踪
- **威胁孪生体**：每枚来袭导弹独立孪生，虚拟域按弹型滚动校准拦截概率预测模型，终结时回写实际结局 → 虚实偏差即预测误差
- **场景孪生体**：仿真时钟/网络脆弱度/冲突升级度/敌方侵略度的整体镜像
- 每 ASDA 循环同步一次，状态回写 DTRegistry + WebSocket + 终态 JSON；实测 23 孪生体、平均保真度 96.9%

**AI 参谋官（`services/llm_analyst.py`）**——大模型战术级态势分析：
- 接入 OpenAI 兼容协议 LLM（阶跃星辰 step-3.7-flash 推理模型，Token Plan），上下文聚合 P6 战斗统计 + P10 政治准入 + P11 指挥链 + P13 孪生层 + SPEAR 事件流
- 固定四节报告：态势总览 / 拦截效能 / ASDA 与指挥链协同 / 量化行动建议；优雅降级（断网不中断仿真，缓存可查）
- 交付形态：Markdown + HTML 报告落盘、`POST /api/v1/analysis` 实时触发、实时大屏"AI 参谋官"面板

**饱和攻击想定（`--saturation`）**：
- 对手齐射机制（`AdversaryAgent` max_missiles_per_salvo，弹道落点微散布），强度/并发/齐射规模全面环境变量化
- 实测：7 次齐射 16 枚来袭全部拦截，AI 报告自动识别"小规模多波次"策略（均值 2.3 枚/次）

**闭环修复**：拦截结果 C2 反馈回流（`c2_feedback` 事件与拦截 1:1 闭环）、伤害评估时序修复（由 Adapt 死代码前移至销毁现场）、Adapt 周期摘要事件、v1 基地数据 P10 兜底、REST 多线程化（ThreadingHTTPServer）
- 验收：`test_p13.py` 24 项全过（孪生层 / 齐射 / 策略反哺 / AI 上下文 / 序列化 / REST 路由）

### P13.2: 指挥中心级可视化 + Word 报告 + Docker 演示栈

**作战指挥中心级实时大屏**（对标数字地球指挥墙）：
- **三态视图循环**：2D 战术地图 → 3D 立体战场 → **数字地球**（球体投影 + 大圆弧弹道 + 地球模式基地图钉/名牌，全要素经纬度统一投影，模式切换轨迹线自动重投影）
- **杀伤链实时流**：底部 KILL CHAIN 事件条（missile_launch → detect → c2_order → intercept → c2_feedback 彩色 chips 滚动）
- **HUD 覆盖层**：中心标题 / 相位与循环读数 / 威胁与脆弱度读数 / 取景框角标 / 扫描线
- 锐化：`setPixelRatio(devicePixelRatio)` 高分屏原生渲染

**AI 参谋官 Word 富文本导出**：
- `ai_situation_analysis.docx`（封面排版 + 多级标题 + 加粗/列表渲染 + 页脚溯源）
- 4 张 matplotlib 专业图表自动嵌入对应章节（拦截效能环形图 / ASDA 四环分布 / SPEAR Top10 / 孪生保真度）
- 大屏 AI 面板一键 `⬇ 导出 Word`（GET `/api/v1/analysis/download`）

**Docker 演示栈**（一键启动完整演示）：
```bash
docker compose -f docker-compose.demo.yml up -d
# 演示中心 http://localhost:8888/ · REST :8080 · WebSocket :8765
```
生产级分布式栈（4 gRPC + Prometheus + Grafana + Jaeger）保留在 `docker-compose.yml`。

**Web 展示层会话门禁**（P7 安全模块端到端落地）：nginx auth_request 会话预检 +
REST 网关全端点 JWT 中间件，三级角色（commander 管理员 / operator 评委 / observer
普通用户）复用 gRPC RBAC 同一套语义——observer 只读、operator 可触发 AI 参谋官、
commander 全量。账号经 `deploy/web_auth_helper.py` 生成 sha256 摘要写入 `.env`
（明文口令不落盘不入仓），未配置该变量时认证关闭、行为与历史版本一致。
验收：`test_web_auth.py` 26 断言（CI 门禁步），详见 `deploy/README.md`。

### P14: 目标特性本体（TO 五元组）+ 描述逻辑推理 + 置信度溯源层

对标赛道二学术支撑材料《西太平洋战区目标特性本体构建》（胡权），把 P1-P13 的
数据与决策资产形式化为可推理、可校验、可溯源的目标特性本体：

**本体建模（`ontology/tc_ontology.py`）**——TO 五元组 ⟨E,A,R,F,Ax⟩ 落盘 OWL 2 DL：
- E-实体：MilitaryInstallation（AirBase/NavalBase/LandBase/SupportSite 四子类 AllDisjoint）
  + FacilityPart（Runway/Hangar/FuelDepot/RadarSite/DefensePosition）+ AccessState 三态 + Aircraft
- A-属性 / F-函数：可观测特性（runwayLengthM/personnelCount/坐标/tier/军种/国别/驻防机型）
  挂 observableProperty；BFO 对齐声明（独立实体/依附实体）
- R-关系：hasPart（传递）/ partOf（逆）/ hasAccessState；AirBase ≡ ∃hasPart.Runway 定义类
- Ax-公理：HermiT 一致性检查通过；LaunchCapable ≡ ∃hasAccessState.(Open⊔Restricted) 推理类，
  AccessDeniedSite ≡ hasAccessState = {state_denied} ⊑ ¬LaunchCapable
- 67 基地 + 16 跑道 + 3 状态共 86 实体自一级 GeoJSON 自动装配，实体 IRI 统一 `tc#` 命名空间

**机器校验（`ontology/reason_check.py` + `shapes.ttl`）**——"本体是否正确"由算法裁决：
- HermiT（推理机）：公理矛盾建模期拦截；基线 c0 推理 LaunchCapable=67 / AccessDenied=0
- 翻转测试：任一基地状态改 Denied → 自动退出 LaunchCapable 且归入 AccessDeniedSite（已验证）
- pySHACL：67 基地 0 违规全绿；负样本（删军种码/纬度 999/缺状态断言）全部报警命中

**置信度与溯源（`ontology/confidence.py`）**——D-S 证据理论 + PROV-O：
- 两路独立证据（坐标精度分级 A45/A-21/B1 × 政治准入类型 sovereign/host_nation/territory）
  各建 mass 函数，Dempster 合成（冲突系数 K<0.08，零拒绝），输出 67 基地 Bel/Pl 区间：
  Bel(Open) 0.67-0.92（均值 0.81）；Tinian B 级降级正确产生全帧最宽无知区间 Pl(Open)=1.0
- PROV-O 溯源图 643 三元组：每条状态断言 wereDerivedFrom 证据源（CRS R47589 / DoD FY2024 BSR / v1 库）

**杀伤网语义查询（`ontology/sparql_service.py`）**——目标特性 → 作战应用：
- PAE 并列目标清单：Tier×跑道长度序攻首十点（Hickam/Kadena/Andersen 居前）
- 效应器-目标匹配：主权基地战斗机联队检索（JBER F-22 / Eielson F-35A）零政治敞口响应轴
- COA 行动方案：13 个单跑道依赖脆弱节点全部给出同国 ≥2000m 跑道疏散替代方案

**Brier 概率校准（`dt_platform/twin_sync.py`）**：威胁孪生终结 (预测 p, 实际 o) 对回算
Brier 分数入终态 `twin_summary.calibration`。饱和攻击实测（P14 重跑）：35 个判定样本，
**BS=0.1128**（0 为完美；拦截率 90%，DF-17 模型收敛 p=0.946/n=27、DF-26 p=0.833/n=8）
——拦截概率预测模型具备可量化的校准证据。

**赛题B术语 ↔ PMTEC 资产对表**：

| 支撑材料术语 | 本体论定义要点 | 本系统对应产物 |
|--------------|----------------|----------------|
| 目标特性本体 TO=⟨E,A,R,F,Ax⟩ | 五元组形式化 | `tc_ontology.py` → target_characteristics.owl |
| 四大特性分类 | 可观测/功能/状态/脆弱性 | observableProperty / LaunchCapable / AccessState 三态 / singleRunwayDependency |
| 最小完备性原则 | 只建决策必需概念 | 86 实体全部源自 GeoJSON 实测字段，零虚构概念 |
| BFO 上层对齐 | 独立/依附实体 | BFO_ALIGNMENT 声明 + Runway ⊑ ∃partOf.基地 |
| 描述逻辑推理 | 定义类自动归类 | HermiT：67 站推入 LaunchCapable；翻转测试通过 |
| 数据质量约束 | 形状校验机器判定 | pySHACL 6 形状：正样本 0 违规 / 负样本 3/3 报警 |
| 不确定性量化 | 置信区间而非点值 | D-S Bel/Pl（confidence_report.json，67 基地） |
| 数据溯源 | 断言可回指证据源 | PROV-O provenance.ttl（643 三元组） |
| 杀伤网 / PAE / COA | 特性→效应器→方案 | sparql_service.py 三类查询 |
| 失效边界 | 结论在何种条件下翻转 | 三问答案卡（本体 validation 附录） |
| 预测校准 | 概率预测 vs 结局 | Brier 分数（twin_sync calibration） |

- 验收：`test_p14_ontology.py` 21 项全过（结构/推理/翻转/SHACL 正负/D-S 公理/溯源/杀伤网）

### P15: 全球地球总览页（MapLibre globe 投影）

- `visualization/globe_display.py` → `output/pmtec_globe.html`（单文件 + MapLibre GL JS 5.9 本地 vendor，断网可用）
- 数据全真实：67 权威实体（bases_v2.geojson）+ 饱和攻击 SPEAR 回放弧线 + 政治准入灰色地带确定性回放（seed=42，c3 主权打击峰值 9 站 Denied、可用 67→58）
- 交互：政治准入/弹道齐射/拦截突防/EDCA/昼夜线五图层开关；夜半球由浏览器端按真实时间天文计算（零外部 feed）；2.5° 格点规避跨日界线破洞

### P16: DoDAF 2.02 视点投影（机器可校验）

- `ontology/dodaf_build.py` → `dodaf_overlay.ttl`：覆盖层本体由真实产物机器生成——33 项能力（锚定 UJTL 编号段）、22 类信息交换（SPEAR 实跑 1,506 事件对账）、6 项服务契约（gRPC 源码 ast 解析）、10 系统节点
- 追溯链 CAP←OA←EX→ENT→tc# 由 `dodaf_shapes.ttl` 九形状强制校验（conforms=true，0 违规 0 断锚）；负样本（删追溯边/清零观测计数）必被拦截
- 八视点文档 `docs/PMTEC-DoDAF视点架构说明.md` 由 `build_dodaf_views.py` 自动导出（重跑即再生）
- 验收：`test_p16_dodaf.py` 26 项全过

### P17: 语义工具层 + 自进化路线图（演化受控）

- `ontology/semantic_tools.py`：browse / resolve / manifest 只读语义工具——对标 EvoOntology（RUC-DataLab, arXiv:2609.15779）的工具层形态，rdflib 直读既有产物，零新依赖；提示词只注入 manifest 轻量清单，其余语义按需检索（active access）
- 四类语义对象：term（85 类与个体）/ mapping（16 属性到 GeoJSON 字段锚定）/ constraint（3 SHACL 形状）/ evidence（71 溯源断言含 Bel/Pl 区间与证据源）
- 设计红线：只读不写——本体变更必须先过 test_p14/test_p16/test_p17 逻辑门禁（EvoOntology 消融：w/o Gate −11.2 为最大减分项）；演化闭环（轨迹诊断→归因→单层类型化补丁→行为门禁）见根目录《DTC2026自进化本体提升计划-P17.md》
- 验收：`test_p17_semantic_tools.py` 15 项全过（manifest/四类检索/Misawa 全档案/类解析/负样本/确定性）

### P18: 评审整改全面改造（2026-10-05/06，依据评审 51/100 反馈 + Palantir AIP/OntoFlow 对标）

- **P0 三项代码根治**：`var history` 全局覆盖（window.history 只读，回放 TypeError）改名 `replayHistory`；requirements 补 `requests/matplotlib/python-docx`（AI 参谋官服务器 503 的根因）；引擎统一出口坐标防护 `_coord_check`（纬度域校验+经度卷绕归一化，`coord_guard` 审计字段随状态外发）
- **"坐标大面积越界"真根因实锤**：阿拉斯加 JBER 的 F-22 巡逻跨国际日期变更线（lon +179.9→-180.1，WGS84 合法），Leaflet 画成横跨全球直线——出口统一归一 [-180,180)（含 target_lon），6000 仿真秒长跑 0 误拒 0 越界
- **必答五问实跑作答**（评审 P1）：`scripts/five_questions_analysis.py`（MC 20,000）→ `output/Five_Questions_Report.html` + `docs/必答五问作答.md`——失效场景×红方代价（政治拒止 67→58 红方 0 弹/定向打掉 30% 价值保留 28.8%/复合实体 61.2%）、随机 vs 定向移除曲线、敏感性响应度排序（σ 第一）、交换比三类口径（4.79 发/突防）、政治韧性独立判断（76.2→79.0→79.1 + m(Denied) 可复算翻转边界）；`test_p18_five_questions.py` 20 断言入 CI
- **口径统一**（评审 P1）：README「评估口径说明」扩编为唯一权威表——67=权威库实体总数 / 22=引擎实时推演口径 / 15=引擎政治盟友站点 / 36=分析管线 host_nation / 45-21-1+D0 置信度四级 + 信息截至 2026-09 声明；`scripts/caliber_check.py` 防漂移自检入 CI
- **交付物五件套**（评审 P0）：数据字典（生成器实跑再生）/《增量说明》/《智能体使用档案》/ 复现包（`scripts/reproduce_all.py` 一键复现+端到端日志）/ ≥5 分钟视频分镜（含失败与边界四段）
- **OpenAPI + 第三方接入**（评审 P2）：`docs/openapi.yaml` 28 端点全量 + 接入指南三语言示例 + `scripts/third_party_integration_test.py` 第三方身份全链路自测（带门禁引擎实跑 14/14，证据 JSON 随包）
- **本体工作台**：`output/pmtec_ontology_workbench.html`——TBox 类层级 + 语义检索台（85 术语/67 全档案离线导出）+ Bel(Open) 分布 + 决策链路审计；对标 OntoFlow/OntoStudio(MIT) 画布范式与 Palantir AIP 审计范式，未复制其代码，断网可用
- **顺带根治**：失效边界卡不可复算扫描数字作废修正（与自家 `dempster_combine` 数学不相容的旧值 0.910→0.400，换可复算口径 Bel 0.778→0.760/K 0.075→0.300，留痕在卡）


---


## AI 决策层级

| 层级 | 算法 | 用途 | 训练规模 | 状态 |
|------|------|------|----------|------|
| L1 | UCB1 Bandit | 传感器动态选择 | 在线学习 | 生产可用 |
| L1 | Q-Learning | 自适应对策优化 | 在线学习 | 生产可用 |
| L2 | DQN (SB3) | ASDA 拦截/分散决策 | 200K 步 + 课程学习 | 推荐使用 P7-v2 |
| L3 | IQL | 双 Agent 独立学习 | 6K 步 (182 维) | 生产可用 |
| L3 | MADDPG | Actor-Critic 多智能体 | 6K 步 (182 维) | 生产可用 |

### Monte Carlo 评估结果

| 对手策略 | 拦截率 | 95% 置信区间 |
|----------|--------|-------------|
| 饱和攻击 | 80.2% | 78.0-82.3% |
| 隐身突防 | 79.1% | 76.1-81.9% |
| 电子战 | 76.5% | 73.8-79.1% |
| 诱饵群 | 79.6% | 77.1-82.0% |
| **总体** | **76.2%** | **74.7-77.7%** |

---

## DTB Model gRPC 服务

| 服务 | 端口 | 核心方法 |
|------|------|----------|
| WarEngine | 50051 | Start/Stop/GetState/InjectEvent/GetSpearReport/GetEWThreats/GetCyberThreats |
| BattleNetwork | 50052 | GetTrackFeed(streaming)/GetEntityStatus/GetNetworkState/GetLiveFeed/GetLVCStatus |
| ApplicationStore | 50053 | ListApps/DeployApp/QueryCapability/DQNInfer/GetDQNStatus |
| PlugAndPlay | 50054 | RegisterComponent/DiscoverServices/HealthCheck/ListPlugins/RegisterDTInstance |

备份节点：WarEngine-Backup (50055)，gRPC HA 自动故障转移。

---

## 安全体系

| 模块 | 功能 |
|------|------|
| JWT (auth.py) | HS256 签发/验证/刷新，24h 过期 |
| RBAC (rbac.py) | 三级角色：Commander/Operator/Observer，22+ 权限矩阵 |
| 审计 (audit.py) | SHA-256 哈希链，SQLite 持久化，防篡改 |
| mTLS (cert_manager.py) | 自签名 CA + 服务端/客户端证书 |
| 拦截器 (interceptor.py) | gRPC 服务端/客户端拦截器，自动校验 |

---

## 可观测性

- **Prometheus** (端口 9090)：7 类指标（sim/intercept/dqn/grpc/live/persistence/security）
- **Grafana** (端口 3000)：34 面板，含告警规则
- 关键告警阈值：intercept_rate < 0.55 Critical / model_loaded=0 持续 30s Critical / audit_entries=0 持续 5min Critical

---

## 快速开始

### 环境要求

- Windows 11 + Python 3.10+
- Intel Arc GPU (XPU) 或 NVIDIA CUDA 或 CPU
- pmtec-xpu Conda 环境（推荐）：`D:/miniconda3/envs/pmtec-xpu/`

### 安装

```bash
pip install -r requirements.txt

# 编译 proto（如需重新生成）
python -m grpc_tools.protoc -I proto --python_out=proto/generated --grpc_python_out=proto/generated proto/dtb_model.proto
```

### 运行仿真

```bash
# 单机模式（含 gRPC 服务）
python main.py

# 自定义场景
python main.py --scenario "Custom-Threat" --duration 600 --seed 123

# 无 gRPC（独立模式）
python main.py --no-grpc
```

### Docker 全栈部署

```bash
# 构建并启动 7 个服务
docker compose up -d

# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f pmtec-war-engine
```

### Monte Carlo 验证

```bash
# 100 episode 全策略验证
python scripts/monte_carlo_validation.py --episodes 100

# 隐身突防专项
python scripts/monte_carlo_validation.py --episodes 50 --scenario stealth
```

### 负载测试

```bash
# 运行全套负载测试（SQLite + gRPC + 引擎并发）
python scripts/load_test.py
```

---

## 输出产物

- `output/pmtec_tactical_display.html` - 交互式战术态势图
- `output/pmtec_3d_display.html` - 3D 实时态势渲染
- `output/pmtec_spear_timeline.html` - SPEAR 时间轴重放
- `output/PMTEC_Load_Test_Report.html` - 负载测试报告
- `output/PMTEC_Upgrade_Plan.html` - 交互式升级看板
- `PMTEC_Architecture_Document.html` - 系统架构文档（13 章节）
- `PMTEC_Disaster_Recovery_Runbook.html` - 灾备恢复运维手册

---

## CI/CD 流水线

GitHub Actions 6 阶段：Lint → Unit Tests → Proto Compile → Docker Build → Integration Test → Deploy

```yaml
# .github/workflows/ci-cd.yml
# 触发：push to main / pull request / tag v*
```

---

## 与 Level 1/2 集成

- **Level 1**: 使用 `data/bases.geojson`（22 个 INDOPACOM 基地）初始化 Live 层
- **Level 2**: ACE 分散部署算法集成至 ASDA Act 阶段
- **Level 3**: 完整 gRPC DTB Model + LVC + ASDA + SPEAR + AI + 安全 + 可观测

---

## 项目统计

| 指标 | 数值 |
|------|------|
| Python 代码 | 144 文件 / 39,567 行（pmtec_system + ace_deployment，不含 archive 与生成桩） |
| AI 模型 | 6 核心 + 15 检查点 + P14 本体推理链（HermiT/SHACL/D-S） |
| 测试文件 | 27 个 (P3-P17 + Web 认证) |
| HTML 交付物 | 19 个 |
| Proto 定义 | 433 行 / 4 服务 |
| 安全模块 | 6 个 / 1,022 行 |
| 基地数据库 | 67 实体（CRS 66 + Tinian，33 属性字段） |
| 迭代轮次 | 17 轮 (P1-P17) |