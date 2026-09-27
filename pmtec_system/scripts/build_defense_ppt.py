# -*- coding: utf-8 -*-
"""DTC2026 赛道二答辩新版 PPT 组装 — 15 页正文 + 3 页附录，深色科技风。

素材全部来自仓库真实产物与 build_ppt_charts.py / 浏览器截图（docs/PPT素材/）。
运行: python -X utf8 pmtec_system/scripts/build_defense_ppt.py
输出: DTC2026赛道二答辩-PMTEC新版.pptx (仓库根)
"""
import os
import subprocess
import sys

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt, Emu

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ASSETS = os.path.join(ROOT, "docs", "PPT素材")
OUT = os.path.join(ROOT, "DTC2026赛道二答辩-PMTEC新版.pptx")

BG = RGBColor(0x0D, 0x11, 0x17)
PANEL = RGBColor(0x16, 0x1B, 0x22)
FG = RGBColor(0xC9, 0xD1, 0xD9)
DIM = RGBColor(0x8B, 0x94, 0x9E)
BLUE = RGBColor(0x58, 0xA6, 0xFF)
GREEN = RGBColor(0x3F, 0xB9, 0x50)
AMBER = RGBColor(0xD2, 0x99, 0x22)
RED = RGBColor(0xF8, 0x51, 0x49)
PURPLE = RGBColor(0xBC, 0x8C, 0xFF)
FONT = "Microsoft YaHei"

SW, SH = Inches(13.333), Inches(7.5)


def repo_stats():
    def run(cmd):
        return subprocess.run(cmd, cwd=ROOT, capture_output=True).stdout.decode("utf-8", "ignore").strip()
    commits = int(run(["git", "rev-list", "--count", "HEAD"]) or 0)
    files = loc = proto = 0
    for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, "pmtec_system")):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".venv", "node_modules")]
        for fn in filenames:
            if fn.endswith(".py"):
                files += 1
                with open(os.path.join(dirpath, fn), "rb") as f:
                    loc += f.read().count(b"\n")
            elif fn.endswith(".proto"):
                with open(os.path.join(dirpath, fn), "rb") as f:
                    proto += f.read().count(b"\n")
    return commits, files, loc, proto


prs = Presentation()
prs.slide_width, prs.slide_height = SW, SH
BLANK = prs.slide_layouts[6]


def new_slide():
    s = prs.slides.add_slide(BLANK)
    r = s.shapes.add_shape(1, 0, 0, SW, SH)
    r.fill.solid()
    r.fill.fore_color.rgb = BG
    r.line.fill.background()
    r.shadow.inherit = False
    return s


def tb(slide, x, y, w, h, lines, size=16, color=FG, bold=False, align=PP_ALIGN.LEFT,
       anchor=MSO_ANCHOR.TOP, leading=1.15):
    """lines: str 或 [(text, {overrides}), ...] 或 [str,...]"""
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    if isinstance(lines, str):
        lines = [lines]
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = leading
        segs = ln if isinstance(ln, list) else [(ln, {})]
        for txt, ov in segs:
            r = p.add_run()
            r.text = txt
            f = r.font
            f.name = ov.get("font", FONT)
            f.size = Pt(ov.get("size", size))
            f.bold = ov.get("bold", bold)
            f.color.rgb = ov.get("color", color)
    return box


def title_bar(slide, kicker, title, num=None):
    tb(slide, Inches(0.55), Inches(0.28), Inches(11.0), Inches(0.35),
       kicker, size=13, color=DIM, bold=True)
    tb(slide, Inches(0.55), Inches(0.62), Inches(12.2), Inches(0.85),
       title, size=30, color=BLUE, bold=True)
    ln = slide.shapes.add_shape(1, Inches(0.58), Inches(1.42), Inches(12.15), Pt(2.2))
    ln.fill.solid()
    ln.fill.fore_color.rgb = RGBColor(0x21, 0x26, 0x2D)
    ln.line.fill.background()
    ln.shadow.inherit = False
    if num:
        tb(slide, Inches(12.35), Inches(7.02), Inches(0.8), Inches(0.35),
           str(num), size=12, color=DIM, align=PP_ALIGN.RIGHT)


def pic_fit(slide, path, x, y, w, h, align="center"):
    iw, ih = Image.open(path).size
    ar, br = iw / ih, w / h
    if ar > br:
        nw, nh = w, int(w / ar)
    else:
        nh, nw = h, int(h * ar)
    nx = x + (w - nw) // 2 if align == "center" else x
    ny = y + (h - nh) // 2
    return slide.shapes.add_picture(path, nx, ny, nw, nh)


def bullets(slide, x, y, w, h, items, size=15.5, gap=1.35):
    lines = []
    for head, body in items:
        lines.append([("▍ ", {"color": BLUE, "bold": True, "size": size}),
                      (head, {"bold": True, "color": FG, "size": size})])
        if body:
            lines.append([("   " + body, {"color": DIM, "size": size - 2})])
    tf = tb(slide, x, y, w, h, lines, size=size)
    for p in tf.text_frame.paragraphs:
        p.line_spacing = gap
    return tf


def chip(slide, x, y, w, text, color=BLUE, size=13):
    c = slide.shapes.add_shape(5, x, y, w, Inches(0.42))  # rounded rect
    c.fill.solid()
    c.fill.fore_color.rgb = PANEL
    c.line.color.rgb = color
    c.line.width = Pt(1.2)
    c.shadow.inherit = False
    tf = c.text_frame
    tf.word_wrap = False
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = text
    r.font.name = FONT
    r.font.size = Pt(size)
    r.font.bold = True
    r.font.color.rgb = color
    return c


A = lambda n: os.path.join(ASSETS, n)
COMMITS, PYF, LOC, PROTO = repo_stats()
STAT_LINE = (f"{PYF} 个 Python 文件 · {LOC/10000:.1f} 万行代码 · {PROTO} 行 protobuf 接口契约 · "
             f"{COMMITS} 次提交 / 21 天")

# ================================================================ S1 封面
s = new_slide()
tb(s, Inches(0.9), Inches(0.85), Inches(11.5), Inches(0.4),
   "数字孪生挑战赛 DTC2026 · 赛道二答辩", size=15, color=DIM, bold=True)
tb(s, Inches(0.9), Inches(1.5), Inches(11.5), Inches(1.3),
   [[("PMTEC", {"size": 66, "bold": True, "color": BLUE}),
     ("  政治韧性数字孪生", {"size": 40, "bold": True, "color": FG})]])
tb(s, Inches(0.9), Inches(2.85), Inches(11.5), Inches(0.5),
   "面向印太战区盟友基地体系  ·  DTB Model 四组件全映射", size=18, color=FG)
tb(s, Inches(0.9), Inches(3.55), Inches(11.6), Inches(0.9),
   [[("当对手不开一枪、只用政治手段让盟友拒绝你使用基地时，", {"color": AMBER, "size": 20, "bold": True})],
    [("防空体系怎么活下来？", {"color": AMBER, "size": 20, "bold": True})]])
chips = [("67 权威基地", BLUE), ("219 维政治观测", PURPLE),
         ("79.5% 约束下拦截率", GREEN), ("OWL 2 DL 本体层", AMBER), ("Docker 一键起跑", FG)]
x = Inches(0.9)
for txt, col in chips:
    w = Inches(0.4 + 0.16 * len(txt))
    chip(s, x, Inches(4.85), w, txt, col)
    x += w + Inches(0.14)
tb(s, Inches(0.9), Inches(6.35), Inches(11.5), Inches(0.4),
   STAT_LINE, size=13.5, color=DIM)
tb(s, Inches(0.9), Inches(6.75), Inches(11.5), Inches(0.4),
   "汇报人：冯亦根 · 2026-09", size=13.5, color=DIM)

# ================================================================ S2 问题
s = new_slide()
title_bar(s, "第一幕 · 问题", "另一种战争：不开一枪的打击", 2)
bullets(s, Inches(0.6), Inches(1.75), Inches(6.4), Inches(4.6), [
    ("灰区剧本", "海上摩擦 → 主权事件 → 盟友国内政治发酵 → 议会给基地准入开\"否\"字"),
    ("没有爆炸", "雷达没被打掉、飞机没被击落——被废掉的是\"借你基地\"这三个字"),
    ("失效的第一假设", "传统防空数字孪生默认\"基地永远可用\"；政治准入是它们没建的那一维"),
    ("公开研究背书", "RAND 等公开智库：对手刻意\"制造政治分裂\"，让准入成为第一不确定性"),
], size=15)
box = s.shapes.add_shape(1, Inches(7.35), Inches(1.75), Inches(5.4), Inches(4.9))
box.fill.solid(); box.fill.fore_color.rgb = PANEL
box.line.color.rgb = BLUE; box.line.width = Pt(1.4); box.shadow.inherit = False
tb(s, Inches(7.65), Inches(1.95), Inches(4.9), Inches(0.45),
   "本作品回答的三个问题", size=17, color=BLUE, bold=True)
tb(s, Inches(7.65), Inches(2.5), Inches(4.9), Inches(4.0), [
   [("Q1  ", {"color": AMBER, "bold": True, "size": 15}),
    ("\"政治\"如何建模成可仿真、可推理的状态，而不是一句设定？", {"size": 14.5})],
   [("", {"size": 8})],
   [("Q2  ", {"color": AMBER, "bold": True, "size": 15}),
    ("基地体系不可单点依赖时，部署与火力如何自适应重平衡？", {"size": 14.5})],
   [("", {"size": 8})],
   [("Q3  ", {"color": AMBER, "bold": True, "size": 15}),
    ("体系里每一个数字，如何做到可溯源、可校验、机器可复现？", {"size": 14.5})],
], leading=1.3)
tb(s, Inches(0.6), Inches(6.75), Inches(12.1), Inches(0.5),
   "政治韧性，是数字孪生从\"仿真工具\"走向\"决策基础设施\"必须补上的一维。", size=15, color=GREEN, bold=True)

# ================================================================ S3 答案
s = new_slide()
title_bar(s, "第一幕 · 答案", "PMTEC：把政治准入写进仿真闭环", 3)
bullets(s, Inches(0.6), Inches(1.7), Inches(7.1), Inches(4.9), [
    ("定位", "盟友基地体系政治韧性数字孪生 — 按 DTB Model 四组件全映射实现"),
    ("第一级交付", "ASDA 算法原型：感知-研判-决策-行动闭环 + DQN/UCB1/MA-DQN 在线学习"),
    ("第二级交付", "基地部署优化工程：NSFW / NSGA-II，政治风险敞口为 Pareto 第 6 目标"),
    ("第三级交付", "可运行 PMTEC 系统：gRPC + WebSocket + REST 三通道，四块大屏 + 地球总览"),
    ("立场", "准入不是设定，是状态机；韧性不是口号，是拦截率"),
], size=15.5)
pic_fit(s, A("chart_spear_run.png"), Inches(7.9), Inches(1.8), Inches(5.0), Inches(4.4))
tb(s, Inches(0.6), Inches(6.8), Inches(12.1), Inches(0.4), STAT_LINE, size=13, color=DIM)

# ================================================================ S4 数据底座
s = new_slide()
title_bar(s, "第二幕 · 底座", "数据底座：每一颗坐标都有出处", 4)
bullets(s, Inches(0.6), Inches(1.7), Inches(7.2), Inches(5.0), [
    ("67 个权威基地实体", "坐标逐条溯源美国国会研究处 CRS 报告 + 国防部 FY2024 基地结构报告，附设施价值与政治准入属性"),
    ("UJTL 2026 联合任务清单", "1,169 项任务 / 12,414 条衡量指标 / 34 个编号段，xlsx 结构化清洗入库，快照 2026-09-15"),
    ("CJCSI 3500.02D 条款库", "六张关系表 42/14/12/8/15/55 行全量入库，任务↔条款可交叉查询"),
    ("威胁轨迹库", "弹道/突防轨迹样本支撑蒙特卡洛与在线校准"),
    ("为什么较真", "后面所有置信度、溯源、翻转测试都建立在这个\"可机器验证\"的地基上"),
], size=15)
box = s.shapes.add_shape(1, Inches(8.15), Inches(1.75), Inches(4.6), Inches(4.9))
box.fill.solid(); box.fill.fore_color.rgb = PANEL
box.line.color.rgb = AMBER; box.line.width = Pt(1.4); box.shadow.inherit = False
tb(s, Inches(8.45), Inches(1.95), Inches(4.0), Inches(0.4),
   "数据可信度三件套", size=17, color=AMBER, bold=True)
tb(s, Inches(8.45), Inches(2.5), Inches(4.05), Inches(4.0), [
   [("D-S 证据理论分级", {"bold": True, "size": 14.5, "color": FG})],
   [("67 基地按数据精度 A/A-/B = 45/21/1", {"size": 13, "color": DIM})],
   [("Bel(Open) ∈ [0.67, 0.92]", {"size": 13, "color": DIM})],
   [("", {"size": 7})],
   [("PROV-O 溯源图", {"bold": True, "size": 14.5, "color": FG})],
   [("643 三元组，断言→权威来源机器可查", {"size": 13, "color": DIM})],
   [("", {"size": 7})],
   [("翻转测试", {"bold": True, "size": 14.5, "color": FG})],
   [("改一条准入断言，推理结果实时联动", {"size": 13, "color": DIM})],
], leading=1.25)

# ================================================================ S5 架构
s = new_slide()
title_bar(s, "第二幕 · 底座", "五层架构：三级交付一体化", 5)
pic_fit(s, A("diagram_arch5.png"), Inches(0.7), Inches(1.62), Inches(11.93), Inches(5.55))

# ================================================================ S6 状态机建模
s = new_slide()
title_bar(s, "第三幕 · 核心创新", "政治准入：仿真状态机，不是一句设定", 6)
pic_fit(s, A("diagram_asda_loop.png"), Inches(0.7), Inches(1.62), Inches(8.6), Inches(5.4))
tb(s, Inches(9.55), Inches(1.8), Inches(3.3), Inches(5.2), [
   [("每个盟友站点三态", {"bold": True, "size": 15, "color": FG})],
   [("Open / Restricted / Denied，事件注入后当周期即响应", {"size": 13, "color": DIM})],
   [("", {"size": 8})],
   [("准入容量因子进观测", {"bold": True, "size": 15, "color": FG})],
   [("DQN 219 维观测向量直接感知\"哪些基地正在失去\"", {"size": 13, "color": DIM})],
   [("", {"size": 8})],
   [("部署侧同步压制", {"bold": True, "size": 15, "color": FG})],
   [("政治风险敞口 = NSGA-II Pareto 第 6 目标", {"size": 13, "color": DIM})],
], leading=1.25)

# ================================================================ S7 状态机实跑
s = new_slide()
title_bar(s, "第三幕 · 核心创新", "状态机实跑：降级与恢复双向发生", 7)
pic_fit(s, A("chart_access_machine.png"), Inches(0.55), Inches(1.62), Inches(8.7), Inches(5.35))
tb(s, Inches(9.5), Inches(1.8), Inches(3.4), Inches(5.2), [
   [("33 次准入迁移", {"bold": True, "size": 15, "color": GREEN})],
   [("饱和攻击想定实跑，10 个站点受影响，降级可恢复", {"size": 13, "color": DIM})],
   [("", {"size": 8})],
   [("峰值 9 站 Denied", {"bold": True, "size": 15, "color": RED})],
   [("主权打击事件下可用基地 67 → 58，c3 周期即响应", {"size": 13, "color": DIM})],
   [("", {"size": 8})],
   [("零人工规则", {"bold": True, "size": 15, "color": AMBER})],
   [("迁移由政治灰区事件强度驱动，状态机即模型", {"size": 13, "color": DIM})],
], leading=1.25)

# ================================================================ S8 三场景
s = new_slide()
title_bar(s, "第三幕 · 核心创新", "反直觉结论：政治约束下拦截率不降反稳", 8)
pic_fit(s, A("chart_scenarios.png"), Inches(0.55), Inches(1.62), Inches(8.7), Inches(5.35))
tb(s, Inches(9.5), Inches(1.8), Inches(3.4), Inches(5.2), [
   [("变量逐一隔离", {"bold": True, "size": 15, "color": FG})],
   [("A→B +2.8pp 纯粹来自数据权威化（模型不变）", {"size": 13, "color": DIM})],
   [("", {"size": 8})],
   [("B→C +0.5pp", {"bold": True, "size": 15, "color": FG})],
   [("政治准入 + 219 维观测，体系学会适应而非硬扛", {"size": 13, "color": DIM})],
   [("", {"size": 8})],
   [("十万次蒙特卡洛", {"bold": True, "size": 15, "color": FG})],
   [("敏感性扫描最差情形可用率仍 95.5%", {"size": 13, "color": DIM})],
], leading=1.25)

# ================================================================ S9 六策略
s = new_slide()
title_bar(s, "第三幕 · 核心创新", "六类攻击策略全覆盖，无一被打穿", 9)
pic_fit(s, A("chart_strategies.png"), Inches(0.55), Inches(1.62), Inches(8.7), Inches(5.35))
tb(s, Inches(9.5), Inches(1.8), Inches(3.4), Inches(5.2), [
   [("79.1% 全量", {"bold": True, "size": 15, "color": GREEN})],
   [("5,268 弹 · 150 局 · 95% CI 78.0–80.2%", {"size": 13, "color": DIM})],
   [("", {"size": 8})],
   [("最差 77.6%", {"bold": True, "size": 15, "color": AMBER})],
   [("\"政治分裂制造\"策略（多轴饱和+持续灰区施压）仍稳", {"size": 13, "color": DIM})],
   [("", {"size": 8})],
   [("存活率 ≈100%", {"bold": True, "size": 15, "color": FG})],
   [("各策略基地存活率 99.9%+，无穿透极端情形", {"size": 13, "color": DIM})],
], leading=1.25)

# ================================================================ S10 本体层
s = new_slide()
title_bar(s, "第三幕 · 核心创新", "P14 本体层：可推理、可校验、可溯源", 10)
pic_fit(s, A("diagram_ontology.png"), Inches(0.7), Inches(1.62), Inches(11.93), Inches(5.55))

# ================================================================ S11 DoDAF 视点投影
s = new_slide()
title_bar(s, "第三幕 · 核心创新", "P16 DoDAF 2.02 视点投影：架构完整性由机器校验", 11)
pic_fit(s, A("diagram_dodaf.png"), Inches(0.7), Inches(1.62), Inches(11.93), Inches(5.55))

# ================================================================ S12 系统实跑
s = new_slide()
title_bar(s, "第四幕 · 证明", "系统实跑：四块屏 + 地球总览，全部真实数据驱动", 12)
pic_fit(s, A("shot_globe.png"), Inches(0.55), Inches(1.7), Inches(6.15), Inches(3.55))
pic_fit(s, A("shot_realtime_ai.png"), Inches(6.9), Inches(1.7), Inches(6.0), Inches(3.55))
tb(s, Inches(0.55), Inches(5.35), Inches(6.15), Inches(0.4),
   "地球总览 COP：5 图层开关（准入演化/弹道齐射/拦截/EDCA/昼夜终结线）", size=12.5, color=DIM, align=PP_ALIGN.CENTER)
tb(s, Inches(6.9), Inches(5.35), Inches(6.0), Inches(0.4),
   "实时孪生 + LLM 参谋官在线态势分析（step 模型实跑生成）", size=12.5, color=DIM, align=PP_ALIGN.CENTER)
pic_fit(s, A("shot_dashboard.png"), Inches(2.6), Inches(5.75), Inches(8.1), Inches(1.55))
tb(s, Inches(10.8), Inches(6.2), Inches(2.3), Inches(0.8),
   "孪生仪表盘\n保真度/反哺模型/注册表", size=11.5, color=DIM)

# ================================================================ S12 工程质量与团队
s = new_slide()
title_bar(s, "第四幕 · 证明", "工程质量：一个人、21 天、可复现交付", 13)
pic_fit(s, os.path.join(ROOT, "pmtec_system", "output", "PMTEC_CICD_Run_Record.png"),
        Inches(0.55), Inches(1.7), Inches(7.3), Inches(4.6))
tb(s, Inches(8.15), Inches(1.8), Inches(4.7), Inches(4.9), [
   [("CI 六阶段全绿", {"bold": True, "size": 15, "color": GREEN})],
   [("build → lint → test → 21 项验收断言 → 产物校验 → 打包", {"size": 13, "color": DIM})],
   [("", {"size": 7})],
   [("一键复现", {"bold": True, "size": 15, "color": FG})],
   [("docker compose 起全栈；离线包 326 文件自包含", {"size": 13, "color": DIM})],
   [("", {"size": 7})],
   [(f"{COMMITS} 次提交 / 21 天（09-05 起）", {"bold": True, "size": 15, "color": FG})],
   [("单人团队；AI 辅助 + 人负责：需求拆解、口径校验、逐行审查由人把关", {"size": 13, "color": DIM})],
   [("", {"size": 7})],
   [("合规红线", {"bold": True, "size": 15, "color": AMBER})],
   [("全公开权威数据源；不做侦察/情报类功能；数字不虚构、按路径可出示", {"size": 13, "color": DIM})],
], leading=1.25)

# ================================================================ S13 指标总表
s = new_slide()
title_bar(s, "第四幕 · 证明", "规格结果指标：全部实测数值", 14)
rows = [
    ("维度", "实测结果", "证据产物（仓库内可复核）"),
    ("部署韧性", "齐射场景 100 次蒙特卡洛：出动 156 架次全保存 · 损失率 0.0% · 恢复 16.3 h", "NSFW 部署优化输出"),
    ("拦截效能", "三场景 76.2% → 79.0% → 79.5%；六策略全量 79.1%", "monte_carlo_results*.json"),
    ("概率校准", "Brier 分数 0.1128（饱和攻击 35 判定样本实算）", "P13 孪生同步层报告"),
    ("体系敏感性", "N=100,000 蒙特卡洛，最差情形可用率 95.5%", "政治韧性分析 HTML"),
    ("语义与溯源", "86 实体 OWL 2 DL · HermiT 一致性 · SHACL 全合规 · PROV-O 643 三元组", "ontology/ 产物 + 21 项断言"),
    ("数据规模", "67 基地实体 · 219 维观测 · UJTL 1,169 任务 · 14 波 35 弹头实跑", "data/ + pmtec_spear_report.json"),
]
tbl_shape = s.shapes.add_table(len(rows), 3, Inches(0.6), Inches(1.75), Inches(12.15), Inches(4.9))
tbl = tbl_shape.table
tbl.columns[0].width = Inches(1.9)
tbl.columns[1].width = Inches(6.1)
tbl.columns[2].width = Inches(4.15)
for ri, row in enumerate(rows):
    for ci, val in enumerate(row):
        cell = tbl.cell(ri, ci)
        cell.fill.solid()
        cell.fill.fore_color.rgb = PANEL if ri else RGBColor(0x1F, 0x26, 0x33)
        tfc = cell.text_frame
        tfc.word_wrap = True
        p = tfc.paragraphs[0]
        r = p.add_run()
        r.text = val
        r.font.name = FONT
        r.font.size = Pt(12.5 if ri else 13.5)
        r.font.bold = (ri == 0 or ci == 0)
        r.font.color.rgb = BLUE if ri == 0 else (FG if ci == 0 else DIM)
tb(s, Inches(0.6), Inches(6.85), Inches(12.1), Inches(0.4),
   "所有数字均有仓库内产物路径支撑——答辩现场可按路径出示。", size=13.5, color=GREEN, bold=True)

# ================================================================ S14 结论
s = new_slide()
tb(s, Inches(0.9), Inches(1.5), Inches(11.5), Inches(1.0),
   "适 应 优 于 压 制", size=48, color=BLUE, bold=True)
tb(s, Inches(0.9), Inches(2.9), Inches(11.6), Inches(2.6), [
   [("数字孪生的价值不在渲染一场必胜的战役，而在让体系于不确定中演练生存。", {"size": 18, "color": FG})],
   [("", {"size": 10})],
   [("用真实世界数据，让数字孪生更真；", {"size": 18, "color": AMBER, "bold": True})],
   [("用政治不确定性，让对抗更聪明。", {"size": 18, "color": AMBER, "bold": True})],
], leading=1.3)
tb(s, Inches(0.9), Inches(5.6), Inches(11.5), Inches(0.5),
   "一键 docker compose 起跑，全部产物可复现。", size=15, color=DIM)
tb(s, Inches(0.9), Inches(6.3), Inches(11.5), Inches(0.6),
   "谢谢聆听 · 欢迎提问（接下来为演示环节）", size=20, color=GREEN, bold=True)

# ================================================================ A1 个人简介
s = new_slide()
title_bar(s, "附录 A1", "个人简介")
pic_fit(s, A("bio_photo.jpg"), Inches(0.8), Inches(1.8), Inches(3.1), Inches(3.6), align="left")
tb(s, Inches(0.8), Inches(5.5), Inches(3.4), Inches(0.5), "冯亦根", size=24, color=FG, bold=True)
tb(s, Inches(4.6), Inches(1.8), Inches(8.2), Inches(5.2), [
   [("教育背景", {"bold": True, "size": 15, "color": BLUE})],
   [("浙江大学 计算机通信工程 本科", {"size": 13.5, "color": FG})],
   [("", {"size": 6})],
   [("学术任职 / 专家库", {"bold": True, "size": 15, "color": BLUE})],
   [("浙江邮电职业技术学院人工智能学术委员会主任 · 浙江省首批产业教授", {"size": 13.5, "color": FG})],
   [("浙江省科技厅 / 经信厅 / 杭州市科技局入库专家 · 省人工智能专家服务团 · 省智慧城市产业智库", {"size": 13.5, "color": FG})],
   [("", {"size": 6})],
   [("专业资质", {"bold": True, "size": 15, "color": BLUE})],
   [("工信部认证首席数据官 · 首席数据资产运营官 · 高级工程师", {"size": 13.5, "color": FG})],
   [("", {"size": 6})],
   [("行业委员", {"bold": True, "size": 15, "color": BLUE})],
   [("杭州数据交易所数据要素专委会委员 · 省企业促进会数据治理委员会委员", {"size": 13.5, "color": FG})],
   [("省国际经济交流协会低空经济专委会常务副主任 · 省信息通信协会低空专委会顾问", {"size": 13.5, "color": FG})],
], leading=1.22)

# ================================================================ A2 口径卡
s = new_slide()
title_bar(s, "附录 A2", "答辩口径卡（关键数字盲背清单）")
tb(s, Inches(0.6), Inches(1.7), Inches(6.1), Inches(5.3), [
   [("拦截率", {"bold": True, "size": 15, "color": GREEN}), ("  76.2 / 79.0 / 79.5%（三场景）· 79.1%（六策略全量）", {"size": 13.5, "color": FG})],
   [("基地收缩", {"bold": True, "size": 15, "color": GREEN}), ("  67 → 58 · 9 站 Denied @c3 · 33 次准入迁移", {"size": 13.5, "color": FG})],
   [("观测维度", {"bold": True, "size": 15, "color": GREEN}), ("  219 维（含准入容量因子）", {"size": 13.5, "color": FG})],
   [("敏感性", {"bold": True, "size": 15, "color": GREEN}), ("  N=100,000 · 最差可用率 95.5%", {"size": 13.5, "color": FG})],
   [("校准", {"bold": True, "size": 15, "color": GREEN}), ("  Brier 0.1128（35 样本）· Bel(Open)∈[0.67,0.92] · K<0.08", {"size": 13.5, "color": FG})],
   [("本体", {"bold": True, "size": 15, "color": GREEN}), ("  86 实体 · 643 三元组 · LC 67→66 翻转 · 21 断言", {"size": 13.5, "color": FG})],
   [("DoDAF", {"bold": True, "size": 15, "color": GREEN}), ("  8 视点 · 33 能力 · 22 交换类 1,506 对账 · SHACL conforms · 26 断言", {"size": 13.5, "color": FG})],
   [("韧性指标", {"bold": True, "size": 15, "color": GREEN}), ("  156 架次 · 损失 0.0% · 恢复 16.3 h", {"size": 13.5, "color": FG})],
   [("工程", {"bold": True, "size": 15, "color": GREEN}), (f"  {COMMITS} 提交 / 21 天 · {PYF} py · {LOC/10000:.1f} 万行 · {PROTO} 行 proto", {"size": 13.5, "color": FG})],
], leading=1.5)
box = s.shapes.add_shape(1, Inches(7.0), Inches(1.7), Inches(5.75), Inches(5.3))
box.fill.solid(); box.fill.fore_color.rgb = PANEL
box.line.color.rgb = AMBER; box.line.width = Pt(1.3); box.shadow.inherit = False
tb(s, Inches(7.3), Inches(1.9), Inches(5.2), Inches(5.0), [
   [("30 秒口径：两个拦截率都是真的", {"bold": True, "size": 15, "color": AMBER})],
   [("76.2% 是 P6 阶段旧基线，79.1% 是 P13 六策略全量口径；三场景表逐一隔离变量，+2.8pp 纯粹来自数据权威化，与模型无关。", {"size": 13, "color": FG})],
   [("", {"size": 8})],
   [("\"为什么不统一口径？\"", {"bold": True, "size": 14, "color": AMBER})],
   [("保留历史版本各自原始产物以示诚实；统一口径即 76.2 / 79.0 / 79.5。", {"size": 13, "color": FG})],
   [("", {"size": 8})],
   [("\"政治事件强度够不够？\"", {"bold": True, "size": 14, "color": AMBER})],
   [("用升级度曲线与 Denied 站点数（9 站峰值、67→58）证明事件真实发生。", {"size": 13, "color": FG})],
], leading=1.3)

# ================================================================ A3 失效边界
s = new_slide()
title_bar(s, "附录 A3", "失效边界三问（本体结论的成立条件）")
cards = [
    ("问一 · 哪些属性不可推断？", BLUE,
     "本体只从已断言事实做逻辑后承，不从缺失推缺失。油料/弹药/战备等级等无权威公开源属性在 TBox 中不存在而非留空；删除状态断言 → SHACL 报\"无状态实体不得进入推理\"（负样本实测命中）。"),
    ("问二 · 可战性判定的翻转条件？", GREEN,
     "单断言 hasAccessState(b)=denied 即令 b 退出 LaunchCapable（67→66）并自动归入 AccessDeniedSite——定义类公理保证零人工规则；仅 Restricted 不翻转，契合\"受限但未禁飞\"现实语义。"),
    ("问三 · 低精度数据会否产生假确定？", AMBER,
     "Tinian（B 级）合成后 Bel(Open)=0.68、Pl(Open)=1.0 全帧最宽区间——D-S 不装确定；缺失/越界/孤立部件三类注入 SHACL 全报警；已知最脆弱假设（单跑道依赖）显式声明，不存在静默失效通道。"),
]
y = Inches(1.75)
for t, col, body in cards:
    box = s.shapes.add_shape(1, Inches(0.6), y, Inches(12.15), Inches(1.62))
    box.fill.solid(); box.fill.fore_color.rgb = PANEL
    box.line.color.rgb = col; box.line.width = Pt(1.3); box.shadow.inherit = False
    tb(s, Inches(0.95), y + Inches(0.12), Inches(11.5), Inches(0.4), t, size=15.5, color=col, bold=True)
    tb(s, Inches(0.95), y + Inches(0.52), Inches(11.5), Inches(1.05), body, size=12.5, color=FG, leading=1.22)
    y += Inches(1.78)
tb(s, Inches(0.6), Inches(7.05), Inches(12.1), Inches(0.4),
   "三问共同结论：推理层公理保证可翻转、置信层证据弱时自我否决、假设层失效路径全部有报警——无静默失效。",
   size=13, color=GREEN, bold=True)

prs.save(OUT)
print("saved:", OUT, os.path.getsize(OUT) // 1024, "KB", len(prs.slides._sldIdLst), "slides")
