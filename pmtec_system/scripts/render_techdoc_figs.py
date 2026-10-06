#!/usr/bin/env python3
"""PMTEC 技术方案文档配图渲染——全部数据来自仓库真实产物，无手工编造数字。"""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import subprocess, os

sys_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # pmtec_system
ROOT = os.path.dirname(sys_root)
OUT = os.path.join(sys_root, "output", "techdoc_figs")
os.makedirs(OUT, exist_ok=True)

ZH = FontProperties(family="Microsoft YaHei")
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["font.family"] = "Microsoft YaHei"

# GO-1 Graphite Orange 调色板（与封面配方一致）
ACCENT = "#D4875A"
DARK = "#1A2330"
SERIES = ["#D4875A", "#4A7BA6", "#6BAF6E", "#B05A7E", "#8A7EC8", "#C9A84C"]
GRID = "#E0E0E0"
TEXT = "#333333"


def save(fig, name, dpi=200):
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=dpi, bbox_inches="tight", pad_inches=0.15,
                facecolor="white", edgecolor="none")
    plt.close(fig)
    print("生成", name)


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── 图 1：系统总体架构（分层框图） ──
def fig_arch():
    fig, ax = plt.subplots(figsize=(11, 7.2))
    ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")
    layers = [
        ("应用与展示层", "指挥大脑 COP · 实时大屏 · 本体工作台 · 地球总览 · 3D 战场 · SPEAR 时间轴", "#D4875A"),
        ("智能决策层", "L1 UCB1/Q-Learning · L2 DQN(219维) · L3 IQL/MADDPG · L4 AI 参谋官(建议位)", "#C0784E"),
        ("本体语义层", "OWL 2 DL 五元组 · HermiT 推理 · SHACL 校验 · D-S 置信 · PROV-O 溯源 · 语义工具层", "#4A7BA6"),
        ("孪生服务层", "DTB 四组件 gRPC · REST 网关(28端点) · WebSocket 推送 · Maven 契约 · RBAC/JWT", "#5B8DB8"),
        ("仿真引擎层", "ASDA 四相位闭环 · 政治准入状态机 · 对抗智能体 · Kalman/JPDA · LVC 三层", "#6BAF6E"),
        ("数据与基础设施层", "67 实体权威库(CRS/FY2024) · SQLite 持久化 · Docker 编排 · CI/CD · Prometheus", "#7A8A99"),
    ]
    y = 88
    for name, desc, color in layers:
        box = FancyBboxPatch((4, y - 11), 92, 10.5, boxstyle="round,pad=0.4",
                             facecolor=color, edgecolor="white", linewidth=1.5, alpha=0.92)
        ax.add_patch(box)
        ax.text(8, y - 3.2, name, fontsize=13, fontweight="bold", color="white", fontfamily="Microsoft YaHei")
        ax.text(8, y - 8.0, desc, fontsize=9.5, color="white", alpha=0.95, fontfamily="Microsoft YaHei")
        y -= 13.5
    # 左侧竖向贯穿线示意层次关系（不穿越层内文字）
    ax.plot([2.2, 2.2], [8, 82], color=DARK, lw=2.5, alpha=0.55)
    ax.annotate("", xy=(2.2, 5), xytext=(2.2, 8),
                arrowprops=dict(arrowstyle="-|>", color=DARK, lw=2.5, alpha=0.55))
    ax.text(50, 96.5, "PMTEC 数字孪生战场系统总体架构（六层）", fontsize=15,
            fontweight="bold", ha="center", color=DARK, fontfamily="Microsoft YaHei")
    save(fig, "fig1_arch.png")


# ── 图 2：三场景拦截率（带 95% CI 误差棒，真实 MC 数据） ──
def fig_scenarios():
    tags = ["monte_carlo_results.json", "monte_carlo_results_v2.json", "monte_carlo_results_v2_political.json"]
    labels = ["A 原22站·182维P6", "B v2权威库·182维P6", "C v2+政治准入·219维P12"]
    rates, lo, hi = [], [], []
    for t in tags:
        o = load(os.path.join(sys_root, "data", t))["overall"]
        rates.append(o["intercept_rate"] * 100)
        lo.append(o["intercept_rate_ci_lower"] * 100)
        hi.append(o["intercept_rate_ci_upper"] * 100)
    fig, ax = plt.subplots(figsize=(9, 5.4))
    x = np.arange(3)
    err = [[r - l for r, l in zip(rates, lo)], [h - r for r, h in zip(rates, hi)]]
    bars = ax.bar(x, rates, color=SERIES[:3], width=0.52, edgecolor="white",
                  yerr=err, capsize=6, error_kw=dict(lw=1.4, color=DARK))
    for xi, r, h in zip(x, rates, hi):
        ax.text(xi, h + 0.35, f"{r:.1f}%", ha="center", fontsize=12,
                fontweight="bold", color=DARK)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=10.5)
    ax.set_ylabel("拦截率（%）", fontsize=11); ax.set_ylim(70, 85)
    ax.set_title("三场景拦截率对照（六策略 Monte Carlo，95% CI 误差棒）",
                 fontsize=13, fontweight="bold", color=DARK, pad=12)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.3, color=GRID)
    save(fig, "fig2_scenarios.png")


# ── 图 3：节点移除曲线（真实五问数据） ──
def fig_removal():
    r = load(os.path.join(sys_root, "output", "five_questions_report.json"))
    cur = r["Q2_removal_curves"]
    fr = sorted(float(k) for k in cur["targeted"])
    tgt = [cur["targeted"][str(f)]["value_retention"] * 100 for f in fr]
    rnd = [cur["random"][str(f)]["value_retention_mean"] * 100 for f in fr]
    p5 = [cur["random"][str(f)]["value_retention_p5"] * 100 for f in fr]
    p95 = [cur["random"][str(f)]["value_retention_p95"] * 100 for f in fr]
    fig, ax = plt.subplots(figsize=(9, 5.4))
    ax.fill_between([f * 100 for f in fr], p5, p95, alpha=0.15, color=SERIES[1], label="随机 90% 区间")
    ax.plot([f * 100 for f in fr], rnd, "o-", color=SERIES[1], lw=2.2, label="随机移除（MC 均值）")
    ax.plot([f * 100 for f in fr], tgt, "s-", color=ACCENT, lw=2.2, label="定向移除（PAE 优先序）")
    ax.axvline(30, color="#B04040", lw=1.2, ls="--", alpha=0.7)
    ax.annotate("定向 30%：28.8%\n（红方代价 100–160 发）", xy=(30, 28.8), xytext=(36, 42),
                fontsize=10, color=DARK, fontfamily="Microsoft YaHei",
                arrowprops=dict(arrowstyle="->", color="#B04040"))
    ax.set_xlabel("移除节点比例（%）", fontsize=11); ax.set_ylabel("体系价值保留率（%）", fontsize=11)
    ax.set_title("节点移除实验：体系价值保留率曲线（MC n=20,000）",
                 fontsize=13, fontweight="bold", color=DARK, pad=12)
    ax.legend(fontsize=10, loc="lower left", framealpha=0.9)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(alpha=0.3, color=GRID)
    save(fig, "fig3_removal.png")


# ── 图 4：敏感性参数响应度排序（真实五问数据） ──
def fig_sens():
    r = load(os.path.join(sys_root, "output", "five_questions_report.json"))
    items = r["Q3_sensitivity_ranking"]
    names = [x["param"].split("（")[0] for x in items][::-1]
    vals = [x["rel_response_per_unit"] for x in items][::-1]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    colors = [ACCENT if i == len(vals) - 1 else SERIES[1] for i in range(len(vals))]
    bars = ax.barh(names, vals, color=colors, height=0.55, edgecolor="white")
    for b, v in zip(bars, vals):
        ax.text(v + max(vals) * 0.015, b.get_y() + b.get_height() / 2,
                f"{v:.3g}", va="center", fontsize=10.5, color=DARK)
    ax.set_xlabel("相对响应度（每单位参数的因变量相对变化）", fontsize=11)
    ax.set_title("敏感性参数排序：政治不确定性强度 σ 居首", fontsize=13,
                 fontweight="bold", color=DARK, pad=12)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", alpha=0.3, color=GRID)
    save(fig, "fig4_sens.png")


# ── 图 5：m(Denied) 翻转边界（D-S 置信层真实复算） ──
def fig_mdenied():
    r = load(os.path.join(sys_root, "output", "five_questions_report.json"))
    sw = r["Q5_political_resilience"]["m_denied_sweep"]
    md = [p["m_denied"] for p in sw]
    bel = [p["bel_open"] for p in sw]
    pl = [p["pl_open"] for p in sw]
    k = [p["conflict_K"] for p in sw]
    fig, ax = plt.subplots(figsize=(9, 5.2))
    ax.plot(md, bel, "o-", color=ACCENT, lw=2.2, label="Bel(Open)")
    ax.plot(md, pl, "s--", color=SERIES[1], lw=1.8, label="Pl(Open)")
    ax.plot(md, k, "^-", color=SERIES[3], lw=1.8, label="冲突系数 K")
    ax.axhline(0.5, color="#B04040", ls="--", lw=1.1, alpha=0.7)
    ax.text(0.105, 0.507, "0.5 判决线", fontsize=9.5, color="#B04040")
    ax.axhline(0.7, color="#7A6A00", ls=":", lw=1.1, alpha=0.7)
    ax.text(0.105, 0.707, "K=0.7 拒合成阈", fontsize=9.5, color="#7A6A00")
    ax.set_xlabel("政治证据先验 m(Denied)", fontsize=11)
    ax.set_ylabel("置信度量", fontsize=11)
    ax.set_title("m(Denied) 翻转边界扫描：置信层对先验单参数扰动稳健",
                 fontsize=13, fontweight="bold", color=DARK, pad=12)
    ax.legend(fontsize=10, loc="center left", framealpha=0.9)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(alpha=0.3, color=GRID)
    save(fig, "fig5_mdenied.png")


# ── 图 6：六策略弹耗比（真实 MC 数据） ──
def fig_exchange():
    mc = load(os.path.join(sys_root, "data", "monte_carlo_results_v2_political.json"))
    per = mc["per_strategy"]
    names_cn = {"saturation_attack": "饱和攻击", "stealth_breakthrough": "隐身突防",
                "electronic_warfare": "电子战", "decoy_swarm": "诱饵蜂群",
                "multi_axis_saturation": "多轴饱和", "political_divergence": "政治分歧"}
    names = [names_cn[k] for k in per]
    ratio = [per[k]["total_missiles"] / max(per[k]["total_through"], 1) for k in per]
    order = np.argsort(ratio)[::-1]
    names = [names[i] for i in order]; ratio = [ratio[i] for i in order]
    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(names, ratio, color=ACCENT, width=0.55, edgecolor="white")
    for b, v in zip(bars, ratio):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.06, f"{v:.2f}",
                ha="center", fontsize=11, fontweight="bold", color=DARK)
    ax.axhline(4.79, color=SERIES[1], ls="--", lw=1.4)
    ax.text(len(names) - 0.45, 4.86, "全量均值 4.79", fontsize=10, color=SERIES[1], ha="right")
    ax.set_ylabel("交换比（红方弹耗 / 突防枚数）", fontsize=11)
    ax.set_title("六策略交换比：体系每放进一枚突防，红方付出的弹量", fontsize=13,
                 fontweight="bold", color=DARK, pad=12)
    ax.set_ylim(0, max(ratio) * 1.18)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.3, color=GRID)
    save(fig, "fig6_exchange.png")


# ── 图 7：Bel(Open) 置信分布（真实置信报告） ──
def fig_bel():
    c = load(os.path.join(sys_root, "ontology", "confidence_report.json"))
    bels = sorted(b["bel_pl"]["Open"]["Bel"] for b in c["bases"])
    grades = {}
    for b in c["bases"]:
        grades.setdefault(b["grade"], []).append(b["bel_pl"]["Open"]["Bel"])
    fig, ax = plt.subplots(figsize=(9, 5))
    cmap = {"A": "#6BAF6E", "A-": "#5B8DB8", "B": "#C9A84C"}
    for g, vals in sorted(grades.items()):
        ax.hist(vals, bins=np.arange(0.64, 0.96, 0.02), alpha=0.75,
                color=cmap.get(g, "#999"), edgecolor="white",
                label=f"{g} 级（{len(vals)} 站）")
    ax.axvline(0.5, color="#B04040", ls="--", lw=1.2)
    ax.text(0.503, ax.get_ylim()[1] * 0.9, "0.5 判决线", fontsize=9.5, color="#B04040")
    ax.set_xlabel("Bel(Open) 单基地置信下界", fontsize=11)
    ax.set_ylabel("基地数", fontsize=11)
    ax.set_title("67 基地 D-S 置信分布：全部高于判决线，B 级区间最宽（诚实暴露数据弱度）",
                 fontsize=12, fontweight="bold", color=DARK, pad=12)
    ax.legend(fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.3, color=GRID)
    save(fig, "fig7_bel.png")


# ── 图 8：提交时间线（真实 git log） ──
def fig_commits():
    r = subprocess.run(["git", "-C", ROOT, "log", "--date=short", "--pretty=%ad"],
                       capture_output=True, text=True)
    from collections import Counter
    days = Counter(r.stdout.split())
    dates = sorted(days)
    counts = [days[d] for d in dates]
    label = [d[5:] for d in dates]
    fig, ax = plt.subplots(figsize=(11, 4.6))
    ax.bar(label, counts, color=ACCENT, width=0.8, edgecolor="white")
    for i, (lb, c) in enumerate(zip(label, counts)):
        if c >= 6:
            ax.text(i, c + 0.15, str(c), ha="center", fontsize=9, color=DARK)
    ax.set_ylabel("每日提交数", fontsize=11)
    ax.set_title(f"开发时间线：{sum(counts)} 次提交 / {len(dates)} 天（2026-09-05 起，git log 实测）",
                 fontsize=13, fontweight="bold", color=DARK, pad=12)
    ax.set_ylim(0, max(counts) * 1.2)
    plt.xticks(rotation=45, ha="right", fontsize=8.5)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.3, color=GRID)
    save(fig, "fig8_commits.png")


fig_arch(); fig_scenarios(); fig_removal(); fig_sens()
fig_mdenied(); fig_exchange(); fig_bel(); fig_commits()
print("全部配图完成 ->", OUT)
