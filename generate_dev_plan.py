#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate DTC 2026 follow-up competition development plan (P9-P13) docx."""

import sys
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

sys.stdout.reconfigure(encoding='utf-8')

doc = Document()

# Global font setup
style = doc.styles["Normal"]
style.font.name = "Microsoft YaHei"
style.font.size = Pt(10.5)
style.element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

DARK = RGBColor(0x1F, 0x3A, 0x5F)
GRAY = RGBColor(0x66, 0x66, 0x66)


def set_cjk(run, name="Microsoft YaHei"):
    run.font.name = name
    run._element.rPr.rFonts.set(qn('w:eastAsia'), name)


def h(text, level):
    p = doc.add_heading(text, level=level)
    for r in p.runs:
        set_cjk(r)
        if level <= 2:
            r.font.color.rgb = DARK
    return p


def para(text, bold=False, size=10.5, color=None, indent=0.0):
    p = doc.add_paragraph()
    if indent:
        p.paragraph_format.left_indent = Cm(indent)
    r = p.add_run(text)
    r.bold = bold
    r.font.size = Pt(size)
    if color:
        r.font.color.rgb = color
    set_cjk(r)
    return p


def bullets(items, indent=0.5):
    for it in items:
        p = doc.add_paragraph(it, style="List Bullet")
        p.paragraph_format.left_indent = Cm(indent)
        for r in p.runs:
            set_cjk(r)


def table(headers, rows, widths=None):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Light Grid Accent 1"
    for i, htxt in enumerate(headers):
        cell = t.rows[0].cells[i]
        cell.text = htxt
        for r in cell.paragraphs[0].runs:
            r.bold = True
            r.font.size = Pt(9.5)
            set_cjk(r)
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = str(v)
            for r in cells[i].paragraphs[0].runs:
                r.font.size = Pt(9)
                set_cjk(r)
    if widths:
        for i, w in enumerate(widths):
            for row in t.rows:
                row.cells[i].width = Cm(w)
    return t


# ============================================================
# Title page
# ============================================================
title = doc.add_heading("DTC 2026 后续比赛开发计划", level=0)
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
for r in title.runs:
    set_cjk(r)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("基于比赛方正式通知的权威数据升级与体系化对抗深化（P9–P13）")
r.font.size = Pt(13)
r.font.color.rgb = GRAY
set_cjk(r)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("根深叶茂团队 | 冯亦根 | 2026年9月11日")
r.font.size = Pt(10.5)
r.font.color.rgb = GRAY
set_cjk(r)

para("触发事件：接到比赛方正式通知，随通知下发四份权威参考资料，要求基于此继续完成后续比赛。"
     "本计划是对通知资料的深度解读、与现有 P1–P8 交付物的差距分析，以及由此驱动的五个开发阶段"
     "（P9–P13）的完整任务分解。", indent=0.2)

# ============================================================
# Chapter 1
# ============================================================
h("一、通知解读：四份资料的战略信号", 1)

h("1.1 通知资料清单", 2)
table(
    ["序号", "资料名称", "来源", "篇幅", "核心信号"],
    [
        ["1", "U.S. Defense Infrastructure in the Indo-Pacific: Background and Issues for Congress",
         "国会研究服务处（CRS）R47589，2023-06-06", "55页",
         "给出 Table A-1 完整 66 个印太国防站点权威清单；PDI 太平洋威慑倡议；FY2020-2023 印太军事建设拨款 89.9 亿美元"],
        ["2", "美国国防部基地结构报告 FY2024（Base Structure Report）",
         "美国国防部（DoD）", "Excel 8 工作表",
         "权威设施数据：五军种设施总数 712,258、PRV 2.23 万亿美元、土地 2,675 万英亩（海外 75.8 万英亩）；按州/国家×军种站点统计"],
        ["3", "U.S. Major Combat Operations in the Indo-Pacific: Partner and Ally Views",
         "兰德公司（RAND）RRA967-2，2023", "153页",
         "盟友与伙伴（日、韩、澳、菲、新加坡等）对印太主要作战行动的观点；基地准入的政治约束与联盟动态"],
        ["4", "U.S. Indo-Pacific Command (INDOPACOM)",
         "CRS，2024-03-05", "3页",
         "组织架构：5 个军种组成司令部 + 3 个下属联合司令部；约 375,000 军事与文职人员；驻日 53,246 / 驻夏威夷 44,545 / 驻韩 24,159 / 驻关岛 6,363；40+ 军事站点"],
    ],
    widths=[1.0, 5.0, 3.0, 1.6, 6.4],
)

h("1.2 资料核心内容提取", 2)
para("（一）CRS R47589：66 个站点的权威分级", bold=True)
bullets([
    "美国领土站点（#1–30）：阿拉斯加 6 个（Fort Wainwright、Fort Greely、JBER、Eielson、Eareckson、Clear SFS）、"
    "华盛顿州 5 个（JBLM、Kitsap、Everett、Whidbey Island、Fairchild）、加州 9 个（Ventura County、Coronado、"
    "San Diego、Point Loma、Miramar、Camp Pendleton、Beale、Travis、Vandenberg SFB）、夏威夷 6 个（Schofield、"
    "Fort Shafter、Wheeler、JB Pearl Harbor-Hickam、PMRF Barking Sands、MCB Hawaii）、威克岛 1 个、关岛 3 个"
    "（Naval Base Guam、Camp Blaz、Andersen AFB）；",
    "海外 DoD 运营站点（#31–51）：马绍尔群岛 1（Kwajalein）、日本本土 9（Camp Zama、Shariki、Kyogamisaki、"
    "Yokosuka、Sasebo、Atsugi、Iwakuni、Yokota、Misawa）、冲绳 4（Army Garrison Okinawa、Camp Butler、Futenma、"
    "Kadena）、韩国 7（Camp Humphreys、Daegu、Yongsan-Casey、Chinhae、Camp Mujuk、Osan、Kunsan）；",
    "盟友/伙伴站点（#52–66）：菲律宾 EDCA 站点 9 个（Antonio Bautista、Basa、Fort Magsaysay、Lumbia、"
    "Benito Ebuen、Camilo Osias、Lal-lo、Camp Melchor Dela、Balabac）、新加坡 1（Navy Region Center Singapore）、"
    "澳大利亚 4（RAAF Darwin、Robertson Barracks、RAAF Tindal、Naval Comm Station Harold E. Holt）、迪戈加西亚 1。",
])
para("关键动向：自 2011 年以来美国在菲律宾与澳大利亚新获 12 个基地使用权；FY2020 起国会为印太军事建设拨款 "
     "89.2 亿美元（占比由 22% 升至 29.1%）；AUKUS 框架下 HMAS Stirling 自 2027 年起轮换部署美英核潜艇。",
     indent=0.2)

para("（二）FY2024 基地结构报告：可量化的设施价值", bold=True)
bullets([
    "五军种设施总量：陆军 374,011 / 海军 118,684 / 空军 168,231 / 海军陆战队 50,387 / WHS 945，合计 712,258；",
    "厂库重置价值（PRV）：陆军 $827.3B / 海军 $521.0B / 空军 $680.3B / 陆战队 $192.5B，合计约 $2.23 万亿；",
    "土地面积：合计 2,675 万英亩（美国本土 2,579 万 + 领地 20.4 万 + 海外 75.8 万）；",
    "站点按 PRV 四分位分级——为基地档案提供\u201c价值密度\u201d量化维度，可用于打击优先级与 ACE 分散权重建模。",
])

para("（三）RAND 报告：盟友视角与政治约束", bold=True)
bullets([
    "印太主要作战行动离不开盟友基地准入——但各国政治意愿存在显著差异与不确定性；",
    "盟友关切：冲突升级风险、被卷入主动挑衅、联盟承诺可信度、主权与国内政治压力；",
    "对建模的启示：基地可用性不是 0/1 常量，而是随政治态势演化的随机变量——这应进入 ASDA 闭环的 Adapt 环节；",
    "盟友力量（澳 MRF-D 轮换、菲 EDCA 准入、日韩基地战时使用谈判）应作为 LVC 构建层的一部分建模。",
])

para("（四）INDOPACOM 概况：指挥控制组织架构", bold=True)
bullets([
    "5 个军种组成司令部：USARPAC（陆军太平洋）、PACFLT（太平洋舰队）、MARFORPAC（陆战队太平洋）、"
    "PACAF（太平洋空军）、USSF Pacific（太空军太平洋）；",
    "3 个下属联合司令部：USFJ（驻日美军）、USFK（驻韩美军）、SOCPAC（特种作战司令部太平洋）；",
    "兵力部署：日本 53,246、夏威夷 44,545、韩国 24,159、关岛 6,363（2023 年 9 月现役）；",
    "AOR 覆盖太平洋与半个印度洋，司令部位于檀香山（胡尼湾）。",
])

h("1.3 对三级任务的影响判断", 2)
table(
    ["资料", "影响的三级任务", "具体升级要求"],
    [
        ["CRS 66 站点清单", "第一级（基地标绘）",
         "现有 22 基地须扩充至 66 站点（+45 缺失，含 1 个 CNMI Tinian 特殊保留 = 67 实体），补齐华州/加州/夏威夷纵深与菲律宾 EDCA 全量 9 站点"],
        ["FY2024 结构报告", "第一级 + 第三级",
         "基地档案增加 PRV、设施数、土地面积等权威量化字段；仿真引擎基地价值权重改用真实 PRV 分位数据"],
        ["RAND 盟友观点", "第二级 + 第三级",
         "ACE 部署算法与 PMTEC 仿真引入\u201c政治准入\u201d约束：盟友站点可用性建模为随机变量并进入 ASDA-Adapt"],
        ["INDOPACOM 架构", "第三级",
         "指挥链建模：五军种组成部队 + 三下属联合司令部映射到 gRPC 服务的角色与权限体系（RBAC）"],
    ],
    widths=[3.2, 3.6, 10.2],
)

# ============================================================
# Chapter 2
# ============================================================
h("二、现状基线与差距分析", 1)

h("2.1 现有交付物基线（P1–P8 成果）", 2)
bullets([
    "第一级：22 个 INDOPACOM 基地 GeoJSON（含 VS26 角色、SCARS、LVC 层、ACE Hub 等 17 个属性字段）、"
    "QGIS 工程、Leaflet 交互式地图、基地情报档案；",
    "第二级：ACE 分布式部署算法（部署优化器、紧急转移规划器、Monte Carlo 损伤评估、5 目标 Pareto 优化）；",
    "第三级：PMTEC 数字孪生战场系统——78 文件 / 20,697 行代码，gRPC 四服务（433 行 proto）、ASDA 闭环、"
    "LVC 三层架构、深度强化学习决策（DQN 182 维、MADDPG、IQL）、安全体系（JWT/RBAC/mTLS/审计）、"
    "分布式高可用、Prometheus/Grafana 可观测、Docker 7 服务编排、CI/CD 6 阶段；",
    "关键指标：Monte Carlo 总体拦截率 76.2%（95% CI 74.7–77.7%）、隐身突防 79.1%；165 项测试全部通过；",
    "既有自我诊断：《DTC2026 三级交付物提升改造计划》已识别 9 项不足（详见 2.4）。",
])

h("2.2 数据层差距：22 vs 66 站点", 2)
para("现有 22 个基地中 21 个在 CRS Table A-1 清单内（Tinian North Field 属 CNMI 美军重启机场，作为 VS26 "
     "相关特殊保留），对照 66 站点权威清单，共缺失 45 个站点：")
table(
    ["区域", "缺失站点", "数量"],
    [
        ["阿拉斯加", "Fort Wainwright、Fort Greely、Eareckson Air Station、Clear SFS", "4"],
        ["华盛顿州", "JBLM、Naval Base Kitsap、NS Everett、NAS Whidbey Island、Fairchild AFB", "5"],
        ["加州", "NB Ventura County、NB Coronado、NB San Diego、NB Point Loma、MCAS Miramar、"
         "MCB Camp Pendleton、Beale AFB、Travis AFB、Vandenberg SFB", "9"],
        ["夏威夷", "Fort Shafter、Wheeler AAF、PMRF Barking Sands、MCB Hawaii", "4"],
        ["威克岛/关岛/RMI", "Wake Island Airfield、Camp Blaz、Army Garrison-Kwajalein Atoll", "3"],
        ["日本", "Camp Zama、Shariki、Kyogamisaki、NAF Atsugi、Army Garrison Okinawa、MCB Camp Butler", "6"],
        ["韩国", "Army Garrison Daegu、Yongsan-Casey、Fleet Activities Chinhae、Camp Mujuk", "4"],
        ["菲律宾 EDCA", "Antonio Bautista、Basa、Fort Magsaysay、Lumbia、Benito Ebuen、Camp Melchor Dela", "6"],
        ["新加坡/澳洲/迪戈加西亚", "Navy Region Center Singapore、Robertson Barracks、"
         "Naval Comm Station Harold E. Holt、NSF Diego Garcia", "4"],
        ["合计", "", "45"],
    ],
    widths=[3.4, 11.0, 1.4],
)

h("2.3 建模层差距", 2)
bullets([
    "无盟友政治准入建模：现有菲律宾/澳洲基地在仿真中与美军基地同等对待，未反映 EDCA 准入不确定性、"
    "MRF-D 六个月轮换周期等政治约束（RAND 核心观点）；",
    "无组织架构建模：未体现 INDOPACOM 五军种组成 + 三下属联合司令部的指挥链，RBAC 角色与真实指挥关系脱节；",
    "无权威价值量化：基地价值权重为经验估计，未使用 FY2024 PRV 四分位与设施数据；",
    "兵力数据不完整：未按 CRS 数据校准驻日 53K / 驻夏威夷 44K / 驻韩 24K / 驻关岛 6.4K 的真实兵力分布。",
])

h("2.4 与既有 9 项改进的整合关系", 2)
table(
    ["既有改进项（旧计划）", "处置", "融入阶段"],
    [
        ["改进项一：实时战术态势显示（WebSocket 推送）", "保留，与 66 站点地图升级协同", "P12"],
        ["改进项二：3D 战场可视化（集成 AH-64 渲染器）", "保留，低优先级", "P12"],
        ["改进项三：ASDA Adapt 学习闭环", "升级——融入政治准入随机变量", "P10"],
        ["改进项四：SPEAR 交互式回放时间轴", "保留", "P12"],
        ["改进项五：数字孪生平台化转型", "保留", "P12"],
        ["改进项六：多威胁类型扩展", "升级——对手策略参考 RAND 盟友弱点", "P12"],
        ["改进项七：Maven 接口补全", "保留", "P12"],
        ["改进项八：分布式部署拆分", "保留，低优先级", "P12"],
        ["改进项九：LVC Live 层真实数据接入", "保留，持续验证", "P10/P12"],
    ],
    widths=[7.0, 5.5, 3.5],
)

# ============================================================
# Chapter 3
# ============================================================
h("三、总体开发策略", 1)

h("3.1 制胜主线", 2)
para("以比赛方下发的四份权威资料为数据基座，把交付物从\u201c仿真正序\u201d推向\u201c权威数据驱动的体系级数字孪生\u201d："
     "66 站点权威清单（CRS）× 真实设施价值（FY2024）× 盟友政治动态（RAND）× 真实指挥架构（INDOPACOM），"
     "全部贯通到既有 DTB Model 四组件与 ASDA 闭环中。评审叙事聚焦："
     "\u201c用真实世界数据让数字孪生更真，用政治不确定性让对抗更聪明。\u201d")

h("3.2 优先级矩阵", 2)
table(
    ["优先级", "任务", "理由"],
    [
        ["P0（最高）", "P9 权威基地数据库升级（22→66）", "通知最直接信号；一切后续任务的数据底座；工作量可控、确定可得"],
        ["P0", "P10 盟友协同与政治约束建模", "RAND 资料的核心指向；ASDA-Adapt 的实质深化；差异化竞争力"],
        ["P1", "P12 PMTEC 系统升级与重验证", "第三级交付物主体；66 节点重跑 + Monte Carlo 复验"],
        ["P1", "P13 交付物体系升级", "评审可见度的最终载体"],
        ["P2", "P11 INDOPACOM 组织架构建模", "锦上添花；映射 RBAC 即可，工作量小但体现严谨"],
        ["P2", "改进项二 3D 可视化、改进项八分布式拆分", "锦上添花，时间允许时执行"],
    ],
    widths=[2.2, 7.0, 6.8],
)

h("3.3 技术约束（不变）", 2)
bullets([
    "运行环境：Windows 11 + Intel Arc GPU（XPU），禁止 CUDA 依赖；torch 2.14.0+xpu；",
    "编码优先级：QSV 硬件加速优先，CPU 回退兜底；",
    "接口规范：DTB Model 四大服务同时支持 gRPC 与 Maven 接口；",
    "数据链路：GeoJSON 基地数据 → ACE 算法 → PMTEC 仿真引擎三级贯通保持完整；",
    "全部军事事实与坐标数据经多源交叉验证（CRS/DoD 权威来源优先），不以 AI 输出为唯一来源。",
])

# ============================================================
# Chapter 4  P9
# ============================================================
h("四、P9：权威基地数据库升级（22 → 66 站点）", 1)
para("时间：9月11日–9月17日（1 周）| 产出：indopacom_bases_v2.geojson（67 实体）", bold=True)

h("4.1 任务分解", 2)
table(
    ["任务", "内容", "数据来源"],
    [
        ["P9.1 站点清单提取", "从 CRS Table A-1 提取 66 站点：名称、位置、军种、美国领土否、DoD 运营否",
         "CRS R47589 附录 A"],
        ["P9.2 坐标补全", "45 个新增站点的 WGS-84 坐标（含 Tinian 复核），逐一交叉验证",
         "多源交叉验证"],
        ["P9.3 FY2024 字段融合", "为站点附加 PRV 四分位、所属州/国家站点统计、军种设施数占比",
         "FY2024 结构报告"],
        ["P9.4 分级标注", "三级分层：Tier-1 核心枢纽（现 22）/ Tier-2 纵深节点（华州/加州/夏威夷/日韩新增 26）"
         "/ Tier-3 盟友与前沿（菲律宾 EDCA 9 + 澳洲/新加坡/迪戈加西亚 6）", "CRS 分区"],
        ["P9.5 属性扩展", "既有 17 字段基础上新增：crs_no、prv_quartile、dod_operated、us_territory、"
         "ally_host、political_access（盟友站点专用）", "本阶段定义"],
        ["P9.6 地图与工程更新", "QGIS 工程重生成；Leaflet 地图按 Tier 分层渲染 + 按军种着色切换", "—"],
    ],
    widths=[3.4, 9.0, 4.0],
)

h("4.2 技术方案要点", 2)
bullets([
    "沿用现有 GeoJSON schema 前向兼容：新增字段全部可选，22 个既有实体属性原样保留；",
    "EDCA 9 站点全部标注 political_access 属性（准入约束参数），为 P10 建模预留接口；",
    "FY2024 Excel 的 Total Site by State 表可直接解析出各国/州站点数，作为完整性校验基准（66 = 清单一一对应）；",
    "威克岛、迪戈加西亚、Harold E. Holt 等远程站点纳入\u201c第二岛链以远\u201d分组，服务 ACE 分散纵深。",
])

h("4.3 验收标准", 2)
bullets([
    "GeoJSON 实体数 = 67（CRS 66 + Tinian），与 Table A-1 逐条对应无遗漏；",
    "每个实体坐标经两个独立来源交叉验证；",
    "QGIS 工程与 Leaflet 地图可按 Tier/军种/国家三维过滤；",
    "PMTEC 引擎可用新 GeoJSON 完成一次冒烟启动（为 P12 铺路）。",
])

# ============================================================
# Chapter 5  P10
# ============================================================
h("五、P10：盟友协同与政治约束建模（RAND 深化）", 1)
para("时间：9月18日–9月24日（1 周）| 产出：政治准入模型 + 盟友力量建模 + ASDA-Adapt 升级", bold=True)

h("5.1 任务分解", 2)
table(
    ["任务", "内容", "对应 RAND 观点"],
    [
        ["P10.1 政治准入状态机", "盟友站点可用性建模为三态：Full（全面准入）/ Restricted（有限准入，如仅轮换/补给）/"
         " Denied（准入被拒）；状态随仿真内政治事件演化", "盟友政治意愿不确定性"],
        ["P10.2 准入概率模型", "每个盟友站点定义 baseline_access_prob + 演化参数（冲突升级度、对手挑衅行为、"
         "联盟信誉值），事件驱动状态转移", "升级风险与联盟可信度关切"],
        ["P10.3 盟友力量建模", "澳 MRF-D（六个月轮换周期）、菲 EDCA 站点、日韩基地战时使用谈判延迟等构建层实体", "盟友军力贡献"],
        ["P10.4 ASDA-Adapt 融合", "Decide 环节增加\u201c政治成本\u201d维度：使用盟友基地的决策需评估准入风险；"
         "Adapt 环节将准入状态变化反馈进对手模型与再部署", "适应优于压制的政治维度"],
        ["P10.5 ACE 算法升级", "第二级 ACE 部署优化器加入政治准入约束：分散方案不得假设被拒站点可用；"
         "Pareto 目标新增\u201c政治风险敞口\u201d", "基地准入是作战前提"],
    ],
    widths=[3.6, 8.8, 4.0],
)

h("5.2 技术方案要点", 2)
bullets([
    "政治准入状态机实现为独立模块 pmtec_system/models/political_access.py，与实体模型解耦；",
    "准入演化参数可配置（YAML/JSON），支持蒙特卡洛敏感性分析——\u201c盟友准入不确定性对拦截率的影响\u201d"
    "本身就是一个有说服力的分析交付物；",
    "MRF-D 轮换按六个月周期建模，战时 Assume 可加速激活但付出政治成本；",
    "对手策略（多威胁类型改进项六）参考 RAND：对手会主动制造政治分化事件（如针对盟友本土的灰色地带行动）"
    "以触发准入降级。",
])

h("5.3 验收标准", 2)
bullets([
    "注入\u201c政治事件\u201d后，盟友站点准入状态在 2 个 ASDA 周期内完成转移并影响可用基地集合；",
    "ACE 部署优化器在 Denied 站点场景下仍能产出可行 Pareto 前沿；",
    "Monte Carlo 对比实验：Full 准入 vs 演化准入 vs 全拒三种场景的拦截率差异量化输出；",
    "至少一组\u201c对手灰色地带行动 → 准入降级 → 拦截率下降\u201d的完整 ASDA 演化链路可回放。",
])

# ============================================================
# Chapter 6  P11
# ============================================================
h("六、P11：INDOPACOM 指挥控制组织架构建模", 1)
para("时间：9月25日–9月28日（4 天）| 产出：指挥链模型 + RBAC 映射", bold=True)

h("6.1 任务分解", 2)
table(
    ["任务", "内容"],
    [
        ["P11.1 组织架构数据", "五军种组成司令部 + 三下属联合司令部 → 指挥关系树；375K 兵力按 CRS 数据校准到各基地群"],
        ["P11.2 指挥链建模", "仿真指挥关系：战区级（INDOPACOM）→ 军种组成/下属联合 → 基地；事件上报与命令下发沿指挥链传递"],
        ["P11.3 RBAC 映射", "既有 Commander/Operator/Observer 三级角色扩展军种属性：如 PACAF-Operator 只能操作空军资产"],
        ["P11.4 gRPC 服务映射", "四大 gRPC 服务的角色标注对应真实司令部职能（WarEngine↔战区联合指挥、"
         "BattleNetwork↔网络域感知、ApplicationStore↔能力交付、PlugAndPlay↔联接集成）"],
    ],
    widths=[4.0, 12.4],
)

h("6.2 验收标准", 2)
bullets([
    "指挥链数据文件（JSON）+ 架构图交付，与 CRS 描述逐条对应；",
    "RBAC 扩展不破坏既有 165 项测试；",
    "演示一个跨军种协同事件沿指挥链的上报-决策-执行全链路。",
])

# ============================================================
# Chapter 7  P12
# ============================================================
h("七、P12：PMTEC 系统全链路升级与重验证", 1)
para("时间：9月29日–10月12日（2 周）| 产出：PMTEC v2（66 站点 + 政治约束 + 指挥链）", bold=True)

h("7.1 任务分解", 2)
table(
    ["任务", "内容", "对应旧改进项"],
    [
        ["P12.1 引擎升级", "仿真引擎接入 67 实体基地集；基地价值权重改用 PRV 四分位；威胁想定覆盖第二岛链以远纵深",
         "—"],
        ["P12.2 观测空间再扩维", "DQN 观测空间增加政治准入特征向量（每个盟友站点 1 维准入状态）；重训练", "—"],
        ["P12.3 实时态势显示", "WebSocket 态势推送（每 ASDA 周期广播、10 并发浏览器、暂停/回溯）；地图升级 66 站点分层",
         "改进项一"],
        ["P12.4 SPEAR 回放时间轴", "交互式回放：态势演化、准入状态变化、拦截决策逐帧回溯", "改进项四"],
        ["P12.5 多威胁扩展", "对手策略库增加：政治分化型攻击（配合 P10 灰色地带）、多方向协同饱和（覆盖新增纵深基地）",
         "改进项六"],
        ["P12.6 平台化与接口", "插件管理器支持新基地集热加载；Maven 接口补全四大服务", "改进项五/七"],
        ["P12.7 Monte Carlo 重验证", "全策略 × 新场景 100+ episode 重新评估；输出新旧对照报告", "—"],
        ["P12.8 3D 可视化（可选）", "集成 AH-64 WebGL2 渲染器 3D 视图（时间允许）", "改进项二"],
    ],
    widths=[4.2, 10.0, 2.2],
)

h("7.2 关键验收标准", 2)
bullets([
    "新基线拦截率报告：66 站点 + 政治准入演化场景 vs 原 22 站点场景的完整对照（预期政治约束会拉低名义拦截率，"
    "但这恰恰证明了模型的真实性——这是评审叙事的加分点而非减分点）；",
    "观测空间扩维后 DQN 重训练收敛，隐身突防拦截率不低于 75%；",
    "全部测试（既有 165 项 + 新增）通过；负载测试不劣化；",
    "Docker 7 服务编排在新数据集下端到端可用。",
])

# ============================================================
# Chapter 8  P13
# ============================================================
h("八、P13：交付物体系升级与评审准备", 1)
para("时间：10月13日–10月19日（1 周）| 产出：全套定稿交付物", bold=True)

h("8.1 交付物清单", 2)
table(
    ["交付物", "升级内容"],
    [
        ["第一级：基地档案文档", "66 站点完整档案（含 CRS 编号、PRV 四分位、FY2024 数据、政治准入属性）"],
        ["第一级：QGIS 工程 + Leaflet 地图", "67 实体、Tier 分层、军种着色、EDCA 专区图层"],
        ["第二级：ACE 算法包", "政治准入约束版优化器 + Pareto 前沿对比报告"],
        ["第三级：PMTEC v2 系统", "全量代码 + 架构文档更新（P9–P12 演进章节）+ 灾备 Runbook"],
        ["分析报告（新增亮点）", "《盟友准入不确定性对印太防空体系韧性的影响》——基于 10 万+ episode 蒙特卡洛分析"],
        ["参赛作品 PPT", "更新：66 站点、权威数据链路、政治约束建模、新基线指标"],
        ["演示视频", "完整 ASDA 演示：政治事件 → 准入降级 → 战术适应 → 体系重平衡"],
    ],
    widths=[6.0, 10.4],
)

h("8.2 评审叙事主线", 2)
bullets([
    "数据权威性：全部基地数据可溯源至 CRS/DoD/FY2024 权威公开报告——\u201c每一颗坐标都有出处\u201d；",
    "政治真实性：首个将盟友准入不确定性纳入 ASDA 闭环的参赛系统——\u201c适应优于压制\u201d的政治维度体现；",
    "体系完整性：从 66 站点数据底座到五军种指挥链到智能决策的全链路数字孪生；",
    "工程成熟度：78+ 文件、2 万+ 行代码、200+ 项测试、Docker/CI/CD/可观测性齐备。",
])

# ============================================================
# Chapter 9
# ============================================================
h("九、时间计划与里程碑总表", 1)
table(
    ["阶段", "时间", "核心产出", "里程碑"],
    [
        ["P9 数据库升级", "9.11–9.17", "indopacom_bases_v2.geojson（67 实体）+ 新地图", "M5：权威数据库交付"],
        ["P10 盟友建模", "9.18–9.24", "政治准入模型 + ASDA-Adapt 升级 + ACE 约束版", "M6：盟友模型交付"],
        ["P11 组织架构", "9.25–9.28", "指挥链模型 + RBAC 映射", "M7：组织架构建模完成"],
        ["P12 系统升级", "9.29–10.12", "PMTEC v2 + Monte Carlo 重验证报告", "M8：系统重验证通过"],
        ["P13 交付物定稿", "10.13–10.19", "全套文档/地图/系统/PPT/视频", "M9：交付物定稿"],
        ["缓冲与机动", "10.20–10.26", "查漏补缺、评审答辩演练", "—"],
    ],
    widths=[3.4, 3.2, 7.4, 2.4],
)
para("节奏说明：延续 P1–P8 的迭代验证工作法——每个阶段以可运行、可复现的产物收口；"
     "P9 与 P10 是本计划的两大支柱，P11 轻量穿插，P12 集中两周完成系统性重验证。")

# ============================================================
# Chapter 10
# ============================================================
h("十、风险管理与应对", 1)
table(
    ["风险", "概率", "影响", "应对"],
    [
        ["45 站点坐标搜集工作量大、来源不一", "高", "P9 延期传导",
         "优先使用 CRS 报告正文描述 + 公开机场/基地数据交叉；批量处理脚本化；Tinian 等特殊站点允许降级精度标注"],
        ["政治准入建模引入后拦截率显著下降", "中", "指标叙事被动",
         "对照实验设计：同时报告 Full/演化/全拒三场景，将\u201c下降\u201d转化为\u201c真实性证明\u201d的叙事"],
        ["DQN 扩维重训练不收敛或时间超限", "中", "P12 延期",
         "沿用 P6/P7 课程学习成熟路径；XPU 训练 + 检查点续训；最坏情况保持原 182 维并仅以特征工程叠加准入信号"],
        ["个人精力有限（无团队分工）", "中", "全链路质量波动",
         "严格按优先级矩阵执行：P9/P10 必保，P11/P12.8 可裁剪；每阶段验收标准明确止损点"],
        ["比赛方后续再有新指令", "低", "计划重排",
         "架构上保持 GeoJSON/模型/引擎三层解耦，新数据或新约束以增量方式接入，不动主干"],
    ],
    widths=[4.6, 1.4, 3.0, 7.4],
)

# ============================================================
# Chapter 11
# ============================================================
h("十一、验收总清单", 1)
bullets([
    "数据：67 实体 GeoJSON，字段含 crs_no / prv_quartile / political_access，与 Table A-1 逐条对应；",
    "建模：政治准入三态状态机 + 演化参数配置 + MRF-D 轮换建模全部可演示；",
    "架构：指挥链 JSON + 架构图 + RBAC 军种扩展通过全量回归测试；",
    "系统：PMTEC v2 在 67 实体 + 政治约束场景下 Monte Carlo 重验证，输出新旧对照报告；",
    "交付：66 站点档案、ACE 约束版、分析报告、PPT、演示视频六件套齐备；",
    "叙事：\u201c权威数据 × 政治真实 × 体系完整\u201d三段式评审故事线成稿。",
])

para("")
para("—— 本计划自 2026 年 9 月 11 日起执行，每周以可运行产物收口，随比赛方后续指令动态调整。——",
     color=GRAY)

out = "DTC2026后续比赛开发计划-基于比赛方通知（P9-P13）.docx"
doc.save(out)
print("Saved:", out)
print("Paragraphs:", len(doc.paragraphs), "Tables:", len(doc.tables))
