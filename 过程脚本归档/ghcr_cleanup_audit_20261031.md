# ghcr 私有镜像清理审计（2026-10-31）

## 背景
- CI 全停根因（见 github_account_audit_20261029.md）：CI 每 push 推私有镜像（GB 级/个）→ 私有包仅 500MB 免费存储 → 超额小额账单 → payment failed → Actions 全停。
- 10-29 已止血：docker build/ghcr 推镜像/security 仅 tag `v*`+手动触发。
- 本次目标：清掉历史积压的私有镜像，彻底断掉存储计费源头。

## 排查过程
1. `gh auth status` 无 packages scope → 尝试 device flow 授权，`github.com/login/device/code` 直连超时；走本机代理（127.0.0.1:7897，注册表 ProxyServer 有存但 ProxyEnable=0）后 gh 自带轮询又被代理 EOF 掐断（一次断连整轮放弃）。
2. 改用用户提供 PAT（Desktop TokenAPI/GitHub access.txt 第 3 行，scope 含 delete:packages/write:packages）直接调 REST API。
3. `GET /user/packages?package_type=container` → 3 个包：finagent-pro-backend/frontend（public，免费，不动）+ **pmtec-dtc2026/pmtec-distributed（private，元凶，10-28 仍在更新）**。

## 版本清单（留档）
- `GET /user/packages/container/pmtec-dtc2026%2Fpmtec-distributed/versions?per_page=100` 返回**整 100 条**（可能截断），时间跨度 2026-10-02（sha-812359d）～ 2026-10-28（sha-246665d/main）。
- 形态：每次 push 沉积 3 条 = `sha-<short>` tag + `main` branch tag + 1 条 untagged manifest。
- 本地引用核查：`pmtec-distributed:latest` 全部为 deploy.sh 本地 build / compose 本地 tag；CI 的 `:ci` 为 push:false；**无任何部署从 ghcr 拉取** → 删除无损。

## 删除动作
- 逐版本 DELETE 循环失败：Python `open(...,'w')` Windows 文本模式把 ID 写成 CRLF → curl "URL rejected"（与 10-29 审计 "repo\r" 404 同款坑，教训再次确认：**跨工具传清单一律 `tr -d '\r'` 或 `newline=''` 写文件**）。
- 改走整包删除：`DELETE /user/packages/container/pmtec-dtc2026%2Fpmtec-distributed` → **HTTP 204**。
- 验证：包列表只剩 2 个 public 包（免费），私有包消失。

## API 坑
- 嵌套镜像名（`namespace/image`）在 URL 里必须 **%2F 编码**，裸 slash 404。

## 遗留
- ~~网页 Billing 清欠费/调 spending limit~~ → **2026-10-31 晚浏览器实测推翻 10-29 假设，见下节**
- PAT scope 过宽（admin:org/delete_repo 等），赛后再收窄。
- 答辩/成绩公布后若要仓库转 public：先收 ECS 安全组（8765/8080 只留 8888），包可见性手动改 public。

---

# 附：Billing 页实测与 CI 熔断真根因（2026-10-31 晚，IAB 浏览器自动化 + PAT API）

## Billing 实测事实（推翻 10-29「小额账单→payment failed」假设）
- **Payment history：**"You have not made any payments" —— 账户从未产生过任何账单/坏账。
- **Payment information：** 连账单地址都没填过，无任何支付方式。
- **Budgets（新账单平台已无 spending limit 概念，改为 Budgets）：** 5 个产品（Codespaces/Packages/Actions/Git LFS/AI Credit）预算**全部已是 $0.00/$0.00、状态 Usage blocked** ——超限即物理拦截，根本不会计费。
- **Overview：** 10 月毛计用量 $30.37（私有镜像超额存储），Next payment due "-"，**included 配额 11-01 重置**。

## CI 熔断真根因（run 92→97→98 证据链）
- run 97（10-31 push）与 run 98（删包后手动 workflow_dispatch）的 Lint job 都是 **2-4 秒即死、零步骤**——runner 没启动就被账单系统拦截，非代码问题（YAML 门禁本地复现 6 文件 0 错误）。
- 机制：私有仓 Actions 属计费用量；超额存储 + 无支付方式 + $0 预算 → GitHub 直接熔断私有仓 hosted runner。时间线吻合：超额累积到阈值≈10-29 = CI 全挂同日。
- **删包（19:39）后 2 小时内阻断未自动解除**（run 98 仍 2 秒死）→ 预期 11-01 included 配额重置时解除。
- 账单地址表单为空 + 无卡 —— user 明确走「$0 预算零扣费」路线，不加支付方式。

## 恢复判定与备选（终局：转 public 一次到位）
- **用户拍板转 public（提前于原计划）**：执行前置安全动作——安全组 sg-bp1j2rzh86e3io29l1vs 摘除 8765 入方向规则（RevokeSecurityGroup，0.0.0.0/0 tcp 8765/8765；8765 为无认证裸 WS，文档公网路径本就走 8888 同源 /ws 反代，5 份文档引用核实均为本地/局域网语义，收口不破坏任何已发布路径）；8080 保留（JWT 保护且是 OpenAPI 文档基地址）、8888/22/80/443 不动。公网复验：8765 超时✅、8888 302 门禁✅、8080 /api/v1/health 200 healthy✅。
- PATCH /repos/{owner}/{repo} {"private":false} → 200，仓库转 public。
- **dispatch run 99：Lint/Test/Docker Build/Security Scan 全 success，CI 完全恢复**（public 仓 Actions 免费，计费熔断不再适用；Push to Registry 按 10-29 止血设计仅 tag 触发跳过）。
- 后续注意：公开后 IP 暴露面已收口至 8080（JWT）/8888（门禁）/22；下次 tag push 会产出 public 镜像（存储免费无账单风险）；比赛抄袭风险由用户知情拍板承担。
