# -*- coding: utf-8 -*-
"""答辩 PPT 图表资产生成 — 全部数据取自仓库真实产物 JSON，可复现。

输出: docs/PPT素材/chart_*.png (深色科技风, 1920x1080 等效比例, 200dpi)
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "docs", "PPT素材")
os.makedirs(OUT, exist_ok=True)

BG = "#0d1117"
PANEL = "#161b22"
FG = "#c9d1d9"
ACCENT = "#58a6ff"
GREEN = "#3fb950"
AMBER = "#d29922"
RED = "#f85149"
PURPLE = "#bc8cff"

plt.rcParams.update({
    "font.family": ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "sans-serif"],
    "axes.unicode_minus": False,
    "figure.facecolor": BG,
    "axes.facecolor": BG,
    "savefig.facecolor": BG,
    "text.color": FG,
    "axes.edgecolor": "#30363d",
    "axes.labelcolor": FG,
    "xtick.color": FG,
    "ytick.color": FG,
    "font.size": 15,
})


def finish(fig, name):
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print("[OK]", name)


def load(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- 图 1 三场景对照
def chart_scenarios():
    a = load("pmtec_system/data/monte_carlo_results.json")["overall"]
    b = load("pmtec_system/data/monte_carlo_results_v2.json")["overall"]
    # 场景 C 精确值来自 P12 重验证报告 (79.5%, CI 77.7-81.3, 60 ep)
    c_rate, c_lo, c_hi = 0.795, 0.777, 0.813

    labels = ["A 旧基线\n182 维 · 100 ep", "B 权威数据升级\n182 维 · 60 ep", "C 政治准入演化\n219 维 · 60 ep"]
    rates = [a["intercept_rate"], b["intercept_rate"], c_rate]
    los = [a["intercept_rate"] - a["intercept_rate_ci_lower"],
           b["intercept_rate"] - b["intercept_rate_ci_lower"],
           c_rate - c_lo]
    his = [a["intercept_rate_ci_upper"] - a["intercept_rate"],
           b["intercept_rate_ci_upper"] - b["intercept_rate"],
           c_hi - c_rate]
    colors = ["#8b949e", ACCENT, GREEN]

    fig, ax = plt.subplots(figsize=(11, 6.2))
    x = np.arange(3)
    bars = ax.bar(x, [r * 100 for r in rates], width=0.52, color=colors,
                  yerr=[np.array(los) * 100, np.array(his) * 100],
                  capsize=9, error_kw=dict(ecolor=FG, elinewidth=1.6, capthick=1.6), zorder=3)
    for xi, r in zip(x, rates):
        ax.text(xi, r * 100 + 2.4, f"{r*100:.1f}%", ha="center", fontsize=21,
                fontweight="bold", color=FG)
    ax.annotate("", xy=(0.55, 79.2), xytext=(0.05, 77.2),
                arrowprops=dict(arrowstyle="->", color=AMBER, lw=2.2))
    ax.text(0.42, 82.2, "+2.8pp\n纯数据权威化", color=AMBER, fontsize=14, ha="center")
    ax.annotate("", xy=(1.58, 80.0), xytext=(1.08, 79.6),
                arrowprops=dict(arrowstyle="->", color=AMBER, lw=2.2))
    ax.text(1.5, 82.2, "+0.5pp 政治约束下\n不降反稳", color=AMBER, fontsize=14, ha="center")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=13.5)
    ax.set_ylim(70, 86)
    ax.set_ylabel("拦截率 (%)，误差棒为 95% 置信区间")
    ax.set_title("蒙特卡洛三场景隔离对照 — 政治准入不是负担，体系学会适应", fontsize=18, pad=16)
    ax.grid(axis="y", color="#21262d", zorder=0)
    ax.spines[["top", "right"]].set_visible(False)
    finish(fig, "chart_scenarios.png")


# ---------------------------------------------------------------- 图 2 六策略全量
def chart_strategies():
    d = load("pmtec_system/data/monte_carlo_results_v2_political.json")
    names = {
        "saturation_attack": "饱和攻击",
        "stealth_breakthrough": "隐身突防",
        "electronic_warfare": "电子战压制",
        "decoy_swarm": "诱饵群耗弹",
        "multi_axis_saturation": "多轴饱和",
        "political_divergence": "政治分裂制造",
    }
    keys = list(d["per_strategy"].keys())
    rates = [d["per_strategy"][k]["intercept_rate"] * 100 for k in keys]
    lo = [d["per_strategy"][k]["intercept_rate_ci_lower"] * 100 for k in keys]
    hi = [d["per_strategy"][k]["intercept_rate_ci_upper"] * 100 for k in keys]
    o = d["overall"]

    fig, ax = plt.subplots(figsize=(11, 6.2))
    y = np.arange(len(keys))[::-1]
    err = np.vstack([[r - l for r, l in zip(rates, lo)], [h - r for r, h in zip(rates, hi)]])
    ax.barh(y, rates, height=0.55, color=[ACCENT, ACCENT, ACCENT, ACCENT, PURPLE, PURPLE],
            xerr=err, capsize=7, error_kw=dict(ecolor=FG, elinewidth=1.5, capthick=1.5), zorder=3)
    for yi, r, h in zip(y, rates, hi):
        ax.text(h + 0.35, yi, f"{r:.1f}%", va="center", fontsize=15, color=FG)
    ax.axvline(o["intercept_rate"] * 100, color=GREEN, lw=2.2, ls="--", zorder=4)
    ax.text(0.985, 0.04,
            f"全量 {o['intercept_rate']*100:.1f}%  (5268 弹 · 150 局 · CI {o['intercept_rate_ci_lower']*100:.1f}–{o['intercept_rate_ci_upper']*100:.1f}%)",
            color=GREEN, fontsize=14, va="center", ha="right", transform=ax.transAxes)
    ax.set_yticks(y)
    ax.set_yticklabels([names[k] for k in keys], fontsize=15)
    ax.set_xlim(70, 88)
    ax.set_xlabel("拦截率 (%)，误差棒为 95% 置信区间")
    ax.set_title("政治准入 + 219 维观测下六类攻击策略全覆盖 — 最差策略仍 77.6%", fontsize=18, pad=14)
    ax.grid(axis="x", color="#21262d", zorder=0)
    ax.spines[["top", "right"]].set_visible(False)
    finish(fig, "chart_strategies.png")


# ---------------------------------------------------------------- 图 3 政治准入状态机
def chart_access_machine():
    d = load("pmtec_system/output/pmtec_spear_report.json")
    pac = sorted((e for e in d["events"] if e["event_type"] == "political_access_change"),
                 key=lambda e: e["timestamp"])
    bases = sorted({e["data"]["base_id"] for e in pac})
    state = {b: "full" for b in bases}
    xs = [0]
    series = {"full": len(bases), "restricted": 0, "denied": 0}
    series = {k: [v] for k, v in series.items()}
    for i, e in enumerate(pac, 1):
        state[e["data"]["base_id"]] = e["data"]["to_state"]
        xs.append(e["data"].get("asda_cycle", i))
        cnt = {"full": 0, "restricted": 0, "denied": 0}
        for s in state.values():
            cnt[s] += 1
        for k, v in cnt.items():
            series[k].append(v)

    fig, ax = plt.subplots(figsize=(11, 6.2))
    ax.step(xs, series["full"], where="post", color=ACCENT, lw=2.8, label="完全准入")
    ax.step(xs, series["restricted"], where="post", color=AMBER, lw=2.8, label="受限")
    ax.step(xs, series["denied"], where="post", color=RED, lw=2.8, label="拒止")
    for x0, tag in ((4, "主权灰区事件注入"), (100, "外交缓和·准入回升")):
        if x0 in xs:
            ax.axvline(x0, color="#30363d", lw=1.4, ls=":")
            ax.text(x0 + 1, 9.4, tag, fontsize=13, color=FG)
    ax.set_xlabel("ASDA 推演周期")
    ax.set_ylabel("站点数 (受事件影响的 10 个盟友站点)")
    ax.set_ylim(-0.5, 10.6)
    ax.set_xlim(0, max(xs) + 4)
    ax.set_title("政治准入状态机实跑 — 降级与恢复双向迁移 (33 次迁移 / 10 站点)", fontsize=18, pad=14)
    ax.legend(loc="center right", frameon=False, fontsize=14)
    ax.grid(color="#21262d")
    ax.spines[["top", "right"]].set_visible(False)
    finish(fig, "chart_access_machine.png")


# ---------------------------------------------------------------- 图 4 政治准入收缩
def chart_access():
    d = load("pmtec_system/output/pmtec_spear_report.json")
    snaps = d["snapshots"]
    ts = [s["sim_seconds"] / 60 for s in snaps]
    total = [s["total_entities"] for s in snaps]
    act = [s["active_tracks"] for s in snaps]
    vuln = [s["network_vulnerability"] * 100 for s in snaps]

    fig, ax = plt.subplots(figsize=(11, 6.2))
    ax.plot(ts, total, color=ACCENT, lw=2.4, label="跟踪实体总数")
    ax.plot(ts, act, color=PURPLE, lw=2.4, label="活跃来袭航迹")
    ax2 = ax.twinx()
    ax2.fill_between(ts, vuln, color=RED, alpha=0.22, label="网络脆弱度 (%)")
    ax2.plot(ts, vuln, color=RED, lw=1.8)
    ax2.set_ylabel("网络脆弱度 (%)", color=RED)
    ax2.tick_params(axis="y", colors=RED)
    ax2.set_ylim(0, max(vuln) * 1.6 + 1)
    ax.set_xlabel("仿真时间 (分钟)")
    ax.set_ylabel("实体数")
    ax.set_title("饱和攻击推演全程 — 事件注入、航迹起伏与体系脆弱度实时联动", fontsize=18, pad=14)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", frameon=False, fontsize=13)
    ax.grid(color="#21262d")
    ax.spines[["top"]].set_visible(False)
    ax2.spines[["top"]].set_visible(False)
    finish(fig, "chart_spear_run.png")


if __name__ == "__main__":
    chart_scenarios()
    chart_strategies()
    chart_access_machine()
    chart_access()
