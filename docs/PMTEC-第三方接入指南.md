# PMTEC 第三方接入指南（Integration Guide）

> 评审 P2 整改项：OpenAPI 接口文档 + 第三方接入示例（支撑 D3 互操作分与 B2 加分）
> 机器可读规格：`docs/openapi.yaml`（OpenAPI 3.0.3，28 端点全量）；本文给三种语言的最小可运行示例
> 接入自测：`pmtec_system/scripts/third_party_integration_test.py`——以第三方身份（独立进程、仅走公开通道）跑通全链路并输出通过证据
> 口径声明：67=权威库实体总数 / 22=引擎实时推演口径 / 15=引擎政治准入盟友站点

## 0. 基地址与通道

| 通道 | 地址 | 用途 |
|------|------|------|
| REST | `http://<host>:8080/api/v1/...` | 状态查询/分析触发/孪生注册 |
| WebSocket | `ws://<host>:8765`（公网经 nginx `/ws` 同源反代） | 实时快照推送（≤10Hz，消息结构 = REST `/state` 同源） |
| 展示中心 | `http://<host>:8888`（nginx） | 浏览器入口，`/api`、`/ws` 同源反代 |

鉴权：`POST /api/v1/auth/login` 获取 JWT（`Authorization: Bearer <token>`）+ HttpOnly Cookie；未配置 `PMTEC_WEB_USERS` 的部署门禁关闭（`/api/v1/health` 的 `auth_enabled` 可探测）。角色：observer 只读 / operator 可触发分析 / commander 可控仿真。

## 1. curl

```bash
BASE=http://localhost:8080
# 1) 登录拿 JWT
curl -s -X POST $BASE/api/v1/auth/login -H 'Content-Type: application/json' \
     -d '{"username":"pingwei","password":"<口令>"}'
# 2) 健康与状态
curl -s $BASE/api/v1/health
curl -s $BASE/api/v1/state -H "Authorization: Bearer $JWT" | head -c 400
# 3) 政治准入态势（15 盟友站点三态）
curl -s $BASE/api/v1/political/access
# 4) 触发 AI 参谋官（operator+；未配 LLM key 时返回 503 属预期降级）
curl -s -X POST $BASE/api/v1/analysis -H "Authorization: Bearer $JWT"
```

## 2. Python（requests）

```python
import requests

BASE = "http://localhost:8080"
s = requests.Session()

r = s.post(f"{BASE}/api/v1/auth/login",
           json={"username": "pingwei", "password": "<口令>"}, timeout=5)
r.raise_for_status()
token = r.json()["token"]
s.headers["Authorization"] = f"Bearer {token}"

state = s.get(f"{BASE}/api/v1/state", timeout=5).json()
print("ASDA 周期:", state["asda_cycle"],
      "| 实体:", len(state["entities"]),
      "| 坐标防护:", state["coord_guard"])

pol = s.get(f"{BASE}/api/v1/political/access", timeout=5).json()
denied = [x for x in pol.get("sites", []) if x.get("state") == "denied"]
print("政治拒止站点数:", len(denied))

r = s.post(f"{BASE}/api/v1/analysis", timeout=30)
print("AI 参谋官:", r.status_code, r.json())
```

## 3. JavaScript / 浏览器（WebSocket 订阅）

```html
<script>
const ws = new WebSocket("ws://localhost:8765");
ws.onopen = () => console.log("已连接 PMTEC 推送通道");
ws.onmessage = (ev) => {
  const snap = JSON.parse(ev.data);        // 结构 = REST /api/v1/state 同源
  console.log("周期", snap.asda_cycle,
              "| 拦截率", (snap.threat_stats?.intercept_rate * 100).toFixed(1) + "%",
              "| coord_guard", snap.coord_guard);
};
ws.onclose = () => console.log("断线（引擎重启/网络）——建议指数退避重连");
</script>
```

## 4. 接入自测（交付验收证据）

```bash
# 需要演示栈在跑：docker compose -f pmtec_system/docker-compose.demo.yml up -d
python pmtec_system/scripts/third_party_integration_test.py
```

脚本以"第三方身份"独立进程运行：服务发现 → 健康探测 → 登录 → 状态/实体/政治态势拉取 → WS 订阅 ≥3 帧快照 → 触发分析（容忍 503 降级）→ 孪生注册 → 注销，逐步输出 PASS 与最终结论，全程输出落 `output/third_party_integration_result.json`。

## 5. 边界与纪律（接入方须知）

1. **数字口径**：引用系统数字必须带口径限定语（见上方声明与 README 口径表）；拒绝二手抽取；
2. **AI 参谋官**：503 = 未配置 LLM（预期降级），不是故障；其输出是建议位产物，不得当作执行指令；
3. **写操作**：`sim/start|stop`、`dt/register` 受角色门禁；未授权调用返回 403 并留审计；
4. **限频**：REST 轮询建议 ≤1Hz，实时需求走 WS（内置 10Hz 上限与回放缓冲）；
5. **`POST /api/v1/analysis` 是同步长端点**：LLM 调用+图表+docx 渲染实测 30-90s，客户端超时请设 ≥150s（未配 LLM key 时立即 503，属预期降级）；
6. **跨日期变更线实体**：阿拉斯加巡逻等实体的经度会在 ±180 间卷绕，引擎出口已统一归一到 [-180,180)（`_coord_check`，审计字段 `coord_guard` 随 `/state` 下发），第三方无需自行处理。

**本地验证结论（2026-10-06）**：带三级角色门禁的引擎实例上，本指南全部示例与 `third_party_integration_test.py` 实跑 **14/14 通过**（登录/JWT/状态/坐标复核/政治态势/WS 3帧/参谋官 200/commander 注册 201/注销），证据文件 `output/third_party_integration_result.json`。
