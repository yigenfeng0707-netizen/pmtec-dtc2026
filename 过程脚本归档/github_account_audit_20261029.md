# GitHub 账户整理审计（2026-10-29）

账户：yigenfeng0707-netizen（free 套餐）｜执行：ZCode 会话（gh CLI，token 已认证）

## 一、Actions 停摆（CI 失败）诊断结论

提示语：*"recent account payments have failed or your spending limit needs to be increased"*

| 排查项 | 结果 |
|---|---|
| Actions 分钟（9 月） | ≈896 分钟（未超 free 私仓 2000 分钟/月） |
| Actions 分钟（10 月） | ≈722 分钟（pmtec-dtc2026 独占 494 分钟/59 runs） |
| billing API | 旧端点 410 迁移、新端点对 classic token 不可用 |
| Packages API | 403（token 无 read:packages scope） |
| **最大嫌疑** | **ghcr.io 私有镜像存储**：CI 每次 push 推私有镜像（GB 级/个），免费 500MB 超额→小额账单→无支付方式→payment failed→Actions 全停 |

**已做止血**（pmtec-dtc2026，提交 9eefeaf/3610d73）：
- docker build / ghcr 推镜像 / security scan 仅 tag v* 或手动触发；日常 push 只跑 lint+test+P18/P19 门禁（~3-5 分钟）
- CI 接入 P19 训练链路门禁（selftest + 零碰撞/manifest + 守卫单测）

**需用户人工**（网页操作，无法代办）：
1. Settings → Billing and plans → 查欠费/支付方式/Spending limit，清理后 Actions 恢复
2. 可选：`gh auth refresh -s read:packages,write:packages`（浏览器授权）后，我可以
   用 API 诊断 ghcr 镜像占用并批量清理旧版本

## 二、批量归档（36 个，全部可逆）

规则：>21 天无 push 的完结比赛仓（排除 keepalive/heartbeat 功能仓）。
归档效果：只读化、退出个人主页、Actions 自动停（私有 cron 滴漏根除）。

<details>归档清单（2026-10-29 执行）：
linguaflow, bioagent, finmind-ai, hainan-opc, meetgrow-office-assistant, yibao-eeg,
lineops-factory-agent, MedEvidence-AI, DataAgent-Governance-Innovation-Award,
guardelder, tiktok-shop-video-agent, fitai, wuhu-dun-dun-ip, finagent-pro-afac2026,
yibao-zhinao, legal-ai-assistant, chengmai-opc-2026, local-meeting-minutes,
TsinghuaEmbodiedAI, xinghe-ai-employee-demo, goai-embodied-solo,
chuyun-cup-yuanhezhishu-2026, FinAgent-Agent-Hackathon, quantinsight-pro, h2brain,
ft-ai-agent-system, alphaquant, voiceguard, AI-Movie-Agent, key-action-plan,
canalpilot, chengjuntai, factory26-harness, tradepilot-app, kaiwu-factory,
yiwu-global-ai-agent, metrix-ai
</details>

**逐仓撤销**（如某比赛还在评审期需要展示）：
`gh repo unarchive yigenfeng0707-netizen/<仓库名> --yes`

## 三、整理后状态

- 仓库总数 85 → 已归档 45 / 活跃 **39**（其中私有 16）
- 活跃私有 = 在役比赛（10-12 之后有活动）+ pmtec 主仓
- 新消耗常态预估：<100 分钟/月（CI 瘦身 + cron 归档），远低于 2000 额度

## 四、遗留

- keepalive×4（canalpilot/tradepilot/oumed/logibrain-heartbeat）为演示保活功能仓，
  PUBLIC 不计费，保留；若对应演示下线可手动归档
- 重复仓对（qiming33 vs qiming-3-3、finagent-pro vs afac2026 等）主副已分明，
  副本多为归档态；如需删除需用户逐个拍板（删除不可逆）
- bidding-intelligence-assistant 描述乱码：已归档只读无法改，留档无妨
