# PMTEC 数字孪生战场系统

## DTC 2026 Level 3 - 数字孪生战场 (Digital Twin Battlefield)

## 概述

PMTEC（Pacific Multi-domain Training and Experimentation Capability）数字孪生战场仿真系统，实现 DTB Model 全链路作战逻辑，核心采用 **ASDA（Act-Sense-Decide-Adapt）闭环循环** 驱动仿真时序。

系统经 P1-P11 共 11 轮迭代演进，从基础仿真原型发展为具备多层 AI 决策、安全认证、分布式高可用、可观测性与 CI/CD 全链路的成熟数字孪生平台。Monte Carlo 评估总体拦截率 **76.2%**（95% CI 74.7-77.7%），隐身突防场景 **79.1%**。P9 起基于比赛方下发的权威资料（CRS R47589 / DoD FY2024 基地结构报告 / RAND RRA967-2 / CRS IF12175）完成权威数据升级与体系化对抗深化。

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

## P1-P11 技术演进

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
| Python 代码 | 103 文件 / 24,794 行（pmtec_system + ace_deployment） |
| AI 模型 | 6 核心 + 15 检查点 |
| 测试文件 | 18 个 (P3-P11) |
| HTML 交付物 | 12 个 |
| Proto 定义 | 433 行 / 4 服务 |
| 安全模块 | 6 个 / 898 行 |
| 基地数据库 | 67 实体（CRS 66 + Tinian，33 属性字段） |
| 迭代轮次 | 11 轮 (P1-P11) |