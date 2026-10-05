# PMTEC OpenAPI 接口文档（人类可读版）

> 评审 P2 整改项 ｜ 机器可读规格：`docs/openapi.yaml`（OpenAPI 3.0.3，与 `dt_platform/rest_gateway.py` 路由实现逐条对照）
> 接入示例（curl/Python/JS-WebSocket）：`docs/PMTEC-第三方接入指南.md` ｜ 全链路自测：`pmtec_system/scripts/third_party_integration_test.py`（实跑 14/14 通过，2026-10-06）
> 基地址 `http://<host>:8080` ｜ WebSocket `ws://<host>:8765`（公网经 nginx `/ws` 同源反代）
> 鉴权：JWT Bearer + HttpOnly Cookie 双通道；角色 observer < operator < commander；未配置 `PMTEC_WEB_USERS` 时门禁关闭（`/api/v1/health` 的 `auth_enabled` 可探测）
> 口径：67=权威库实体总数 / 22=引擎实时推演口径 / 15=引擎政治准入盟友站点 ｜ 信息截至 2026-09

## 端点总表（28 端点）

| 端点 | 方法 | 鉴权/角色 | 说明 |
|------|------|-----------|------|
| `/` · `/api` | GET | 公开 | 服务索引（端点自描述） |
| `/api/v1/health` | GET | 公开 | 健康检查（status/auth_enabled/服务清单） |
| `/api/v1/auth/login` | POST | 公开 | 登录 → JWT + Set-Cookie(HttpOnly) |
| `/api/v1/auth/logout` | POST | 会话 | 注销 + 清 Cookie |
| `/api/v1/auth/check` | GET | 会话 | 会话校验（Cookie 或 Bearer） |
| `/api/v1/state` | GET | observer+ | 引擎全量状态（24 键，含 `coord_guard` 坐标审计） |
| `/api/v1/bases` | GET | observer+ | 基地数据库（引擎口径 22 站；权威库 67 见 GeoJSON） |
| `/api/v1/entities` | GET | observer+ | 动态实体（经度已归一 [-180,180)，lat 恒在 ±90） |
| `/api/v1/tracks` | GET | observer+ | 活动航迹 |
| `/api/v1/spear/report` | GET | observer+ | SPEAR 事件流报告（22 类事件+快照+指标） |
| `/api/v1/threat-summary` | GET | observer+ | 威胁汇总（发射/拦截/突防/拦截率） |
| `/api/v1/war/ew-threats` | GET | observer+ | 电子战干扰机态势 |
| `/api/v1/war/cyber-threats` | GET | observer+ | 网络攻击态势 |
| `/api/v1/network/lvc-status` | GET | observer+ | LVC 三层网络状态 |
| `/api/v1/political/access` | GET | observer+ | 政治准入（15 盟友站点三态+升级度+MRF-D） |
| `/api/v1/c2/chain` | GET | observer+ | 指挥链（8 机构+消息流） |
| `/api/v1/dt/instances` | GET | observer+ | 孪生体实例列表 |
| `/api/v1/dt/sync` | GET | observer+ | 孪生同步摘要（保真度） |
| `/api/v1/dt/register` | POST | **commander** | 注册第三方孪生体（Maven 契约） |
| `/api/v1/analysis` | POST | **operator+** | 触发 AI 参谋官报告（**同步长端点 30-90s，超时设 ≥150s**；未配 LLM key → 503 预期降级） |
| `/api/v1/analysis/download` | GET | observer+ | 下载最近一次报告（md/html/docx） |
| `/api/v1/plugins` | GET | observer+ | 应用商店插件清单 |
| `/api/v1/app/dqn/status` | GET | observer+ | DQN 推理服务状态 |
| `/api/v1/pnp/health` | GET | observer+ | 即插即用总线健康 |
| `/api/v1/maven/services` | GET | observer+ | Maven 服务契约清单 |
| `/api/v1/sim/start` | POST | **commander** | 启动仿真 |
| `/api/v1/sim/stop` | POST | **commander** | 停止仿真 |

## 错误语义（统一 `{"error": "..."}`）

| 码 | 含义 | 备注 |
|----|------|------|
| 401 | 未认证 | 令牌缺失/过期 → 重新 login |
| 403 | 已认证但角色不足 | 返回 `role`/`required_role`，属门禁正确行为 |
| 503 | 引擎未挂载 / LLM 未配置 | **预期降级**（冷启动或演示环境无 key），不是故障 |
| 400 | 请求体非法 | JSON 解析失败等 |

## 数据结构

- `/state` 响应 24 键逐键定义：`docs/PMTEC-数据字典.md` §2
- SPEAR 22 类事件逐类定义：`docs/PMTEC-数据字典.md` §3
- WS 消息 = REST `/state` 同源全量/增量帧（websockets 库服务端，`realtime/websocket_server.py`）

## 与实现的一致性保障

`openapi.yaml` 的路径清单由 `dt_platform/rest_gateway.py` 的 `do_GET`/`do_POST` 分发链逐条对照生成（P18）；每次路由变更必须同步 yaml 与本表（`scripts/caliber_check.py` 的精神：文档-实现不漂移）。第三方接入验收以 `third_party_integration_test.py` 实跑结果为准。
