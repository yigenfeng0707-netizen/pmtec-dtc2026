"""P13 LLM Analyst - AI 智能态势分析模块 (DTC 2026 Level 3).

调用大模型（OpenAI 兼容协议，默认阶跃星辰 step-3.7-flash）对 PMTEC
仿真结束后的战场态势进行专业分析：

  1. 拦截效能评估（发射/拦截/突防统计 + 残存威胁）
  2. ASDA 循环行为解读（Act-Sense-Decide-Adapt 事件分布）
  3. 政治准入与指挥链协同瓶颈（P10/P11 模块联动）
  4. 下一步训练与战术优化建议

设计原则：
  - 优雅降级：网络/密钥/配额故障不影响仿真主流程
  - 配置外置：config.py + 环境变量覆盖（PMTEC_LLM_*）
  - 输出可复用：Markdown + HTML 双格式落盘 output/

Run: python -X utf8 services/llm_analyst.py   (自测)
"""

import json
import os
import re
import time
from datetime import datetime

import requests

# P13-3: 专业报告渲染（图表 + Word 排版）
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

try:
    import docx
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt, RGBColor

    _DOCX_AVAILABLE = True
except ImportError:
    _DOCX_AVAILABLE = False

try:
    from config import OUTPUT_DIR, LLM_CONFIG
except ImportError:  # standalone fallback
    OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
    LLM_CONFIG = {}

ENV_PREFIX = "PMTEC_LLM_"

_DEFAULTS = {
    "enabled": True,
    "api_key": "3vZfQUCfxYfjN7RP8wcTTHPL64ffq9R1ami1eXut0NxmcNQnGTmEyJhefG6V4XTfA",
    "base_url": "https://api.stepfun.com/step_plan/v1",
    "model": "step-3.7-flash",
    "max_tokens": 8192,
    "temperature": 0.4,
    "timeout_s": 180,
}

SYSTEM_PROMPT = (
    "你是 PMTEC 数字孪生反导仿真系统的 AI 参谋官（AI Battle Staff Analyst）。\n"
    "职责：基于仿真终态数据输出战术级态势分析报告，使用简体中文，Markdown 格式。\n"
    "报告结构固定为四节：\n"
    "## 1. 战场态势总览（2-3 段，给出总体判断）\n"
    "## 2. 拦截效能评估（量化分析：拦截率、突防原因、薄弱环节）\n"
    "## 3. ASDA 决策循环与指挥链协同解读（结合事件分布、政治准入、C2 延迟）\n"
    "## 4. 行动建议（按优先级列出 3-5 条，含量化目标）\n"
    "要求：所有结论必须引用输入数据中的具体数字；不要编造数据。"
)


def _cfg(key: str):
    """Read LLM config: env var > config.py > default."""
    env_val = os.environ.get(ENV_PREFIX + key.upper())
    if env_val is not None:
        if isinstance(_DEFAULTS.get(key), bool):
            return env_val.lower() in ("1", "true", "yes")
        if isinstance(_DEFAULTS.get(key), int):
            return int(env_val)
        return env_val
    return LLM_CONFIG.get(key, _DEFAULTS.get(key))


class LLMAnalyst:
    """AI 态势分析器：仿真终态 -> LLM -> Markdown/HTML 报告."""

    def __init__(self):
        self.api_key = _cfg("api_key")
        self.base_url = _cfg("base_url").rstrip("/")
        self.model = _cfg("model")
        self.max_tokens = int(_cfg("max_tokens"))
        self.temperature = float(_cfg("temperature"))
        self.timeout_s = int(_cfg("timeout_s"))
        self.last_usage = {}

    @property
    def enabled(self) -> bool:
        return bool(_cfg("enabled")) and bool(self.api_key)

    # ------------------------------------------------------------------
    # Context builder
    # ------------------------------------------------------------------
    def build_battle_context(
        self, final_state: dict, spear_report: dict, events: list | None = None
    ) -> str:
        """把仿真终态压缩为一段精炼的文本上下文（控制在 ~1500 tokens）。"""
        ts = final_state.get("threat_stats", {}) or {}
        adv = final_state.get("adversary_stats", {}) or {}
        pol = final_state.get("political_access") or {}
        c2 = final_state.get("c2_chain") or {}
        wx = final_state.get("weather", {}) or {}

        # Damaged assets from SPEAR damage events
        # (data: {base, ac_type, missile_type}; description: "...destroyed at {base}")
        damaged_summary: dict[str, list] = {}
        for e in events or []:
            if e.get("event_type") != "damage":
                continue
            base_id = e.get("data", {}).get("base", "unknown")
            desc = e.get("description", "")
            damaged_summary.setdefault(base_id, []).append(desc)
        damaged = sorted(damaged_summary.items(), key=lambda x: -len(x[1]))[:5]
        damaged_str = "; ".join(
            f"{bid}（损失{len(descs)}件: {'/'.join(descs[:3])}）"
            for bid, descs in damaged
        )

        # Top event types (top 12)
        dist = spear_report.get("event_distribution", {})
        dist_str = ", ".join(
            f"{k}:{v}" for k, v in sorted(dist.items(), key=lambda x: -x[1])[:12]
        )

        # Political access brief (P10 snapshot structure:
        # ally_sites / ally_countries / escalation_level / by_country / mrfd)
        pol_brief = ""
        if pol.get("ally_sites"):
            states = {}
            for _country, sites in pol.get("by_country", {}).items():
                for s in sites:
                    st = s.get("state", "?")
                    states[st] = states.get(st, 0) + 1
            mrfd = pol.get("mrfd", {}) or {}
            pol_brief = (
                f"盟友站点总数: {pol['ally_sites']}, "
                f"涉及国家: {', '.join(pol.get('ally_countries', []))}; "
                f"准入三态分布: {json.dumps(states, ensure_ascii=False)}; "
                f"冲突升级度: {pol.get('escalation_level', 'N/A')} (0-1); "
                f"MRF-D轮换: 进度{mrfd.get('cycle_progress', 'N/A')}, "
                f"就绪度{mrfd.get('readiness', 'N/A')}, "
                f"冻结{mrfd.get('frozen', 'N/A')}; "
                f"政治事件数: {pol.get('events_count', 0)}"
            )

        # C2 brief (P11 snapshot structure:
        # nodes / message_count / recent_messages / bases_assigned)
        c2_brief = ""
        if c2.get("nodes"):
            latencies = [
                m.get("total_latency_s")
                for m in c2.get("recent_messages", [])
                if isinstance(m.get("total_latency_s"), (int, float))
            ]
            avg_lat = round(sum(latencies) / len(latencies), 2) if latencies else None
            cross = sum(
                1
                for m in c2.get("recent_messages", [])
                if len(m.get("hops", [])) > 2
            )
            c2_brief = (
                f"C2 节点数: {len(c2['nodes'])}, "
                f"下辖基地数: {c2.get('bases_assigned', 'N/A')}, "
                f"消息总数: {c2.get('message_count', 'N/A')}, "
                f"近期消息平均延迟: {avg_lat if avg_lat is not None else 'N/A'}s "
                f"(样本{len(latencies)}条), 跨军种多跳消息: {cross}条"
            )

        # Digital twin layer summary (P13)
        twin = final_state.get("twin_summary") or {}
        twin_brief = ""
        if twin:
            im = twin.get("intercept_model", {})
            im_str = ", ".join(
                f"{k}: 预测拦截率{v.get('p', 0):.0%}(样本{v.get('n', 0)})"
                for k, v in im.items()
            )
            dev = twin.get("deviating_twins", [])
            dev_str = (
                "; ".join(
                    f"{d.get('name')} (偏差{d.get('deviation')})" for d in dev
                )
                if dev
                else "无显著偏差"
            )
            twin_brief = (
                f"孪生体总数: {twin.get('total_twins', 0)} "
                f"({json.dumps(twin.get('by_kind', {}), ensure_ascii=False)}), "
                f"平均保真度: {twin.get('avg_fidelity', 1):.1%}, "
                f"引擎同步次数: {twin.get('engine_syncs', 0)}; "
                f"虚实偏差告警: {dev_str}; "
                f"拦截概率虚拟模型: {im_str or '无样本'}; "
                f"孪生策略反哺: 本场覆盖 RL 决策 "
                f"{twin.get('strategy_overrides', 0)} 次 "
                f"(策略实效模型: "
                f"{json.dumps(twin.get('strategy_model', {}), ensure_ascii=False)})"
            )

        ctx = f"""【仿真终态摘要】
想定: {final_state.get('scenario', 'N/A')} | 仿真时长: {final_state.get('sim_seconds', 0):.0f}s | ASDA 循环数: {final_state.get('asda_cycle', 0)}

【威胁与拦截统计】(P6 核心指标)
来袭导弹总发射数: {ts.get('total_missiles', 0)}
成功拦截数: {ts.get('intercepted', 0)}
突防命中数: {ts.get('impacted', 0)}
仿真结束时仍活跃: {ts.get('active', 0)}
综合拦截率: {ts.get('intercept_rate', 0):.1%}

【网络脆弱度】 {final_state.get('network_vulnerability', 0):.1%}
【实体规模】 活跃实体: {final_state.get('total_entities', 0)} | 活动航迹: {final_state.get('active_tracks', 0)} | LVC Live 注入: {final_state.get('lvc_live_entities', 0)}

【敌方行为 (AdversaryAgent)】 {json.dumps({k: v for k, v in adv.items() if not isinstance(v, (list, dict))}, ensure_ascii=False)[:400]}

【政治准入态势 (P10)】 {pol_brief or '模块未启用'}
【指挥链态势 (P11)】 {c2_brief or '模块未启用'}
【数字孪生层 (P13)】 {twin_brief or '未启用'}
【天气影响】 检测因子: {wx.get('detection_range_factor', 'N/A')} | 能见度: {wx.get('visibility', 'N/A')} | 侧风: {wx.get('crosswind', 'N/A')}

【受损基地 Top5】 {damaged_str or '无'}

【SPEAR 事件分布 (Top12)】 {dist_str}
ASDA 各环节事件数: {json.dumps(spear_report.get('asda_phase_activity', {}), ensure_ascii=False)}
受损事件数: {spear_report.get('damage_events', 0)} | 探测事件数: {spear_report.get('detection_events', 0)}
"""
        return ctx

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------
    def chat(self, messages: list[dict]) -> str | None:
        """OpenAI 兼容 chat 调用；失败返回 None（不抛异常）。"""
        if not self.api_key:
            return None
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                },
                timeout=self.timeout_s,
            )
            if resp.status_code != 200:
                print(f"  [LLMAnalyst] API error {resp.status_code}: {resp.text[:200]}")
                return None
            data = resp.json()
            self.last_usage = data.get("usage", {})
            return data["choices"][0]["message"]["content"]
        except requests.RequestException as e:
            print(f"  [LLMAnalyst] request failed: {e}")
            return None
        except (KeyError, ValueError) as e:
            print(f"  [LLMAnalyst] unexpected response: {e}")
            return None

    def analyze(
        self, final_state: dict, spear_report: dict, events: list | None = None
    ) -> str | None:
        """生成态势分析 Markdown。失败返回 None。"""
        if not self.enabled:
            print("  [LLMAnalyst] disabled (no config), skip")
            return None
        context = self.build_battle_context(final_state, spear_report, events)
        t0 = time.time()
        content = self.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": context + "\n请输出完整态势分析报告。",
                },
            ]
        )
        dt = time.time() - t0
        if content is None:
            return None
        print(
            f"  [LLMAnalyst] analysis done in {dt:.1f}s "
            f"(prompt={self.last_usage.get('prompt_tokens')} "
            f"completion={self.last_usage.get('completion_tokens')})"
        )
        return content

    # ------------------------------------------------------------------
    # Report output
    # ------------------------------------------------------------------
    def generate_report_files(
        self, final_state: dict, spear_report: dict, events: list | None = None
    ) -> dict | None:
        """分析并写出 md + html + docx（含图表），失败返回 None。"""
        content = self.analyze(final_state, spear_report, events)
        if content is None:
            return None

        os.makedirs(OUTPUT_DIR, exist_ok=True)

        md_path = os.path.join(OUTPUT_DIR, "ai_situation_analysis.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(
                f"# PMTEC AI 态势分析报告\n\n"
                f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
                f"模型: {self.model}\n\n"
            )
            f.write(content)

        html_path = os.path.join(OUTPUT_DIR, "ai_situation_analysis.html")
        html = _markdown_to_html(content)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(_html_template(html))

        # P13-3: 专业图表 + Word 富文本导出
        charts = _render_charts(final_state, spear_report, events or [])
        docx_path = None
        if _DOCX_AVAILABLE:
            try:
                docx_path = _build_docx(
                    content,
                    charts,
                    model=self.model,
                    scenario=str(final_state.get("scenario", "N/A")),
                )
            except Exception as e:
                print(f"  [LLMAnalyst] docx export failed: {e}")

        return {
            "markdown": content,
            "md_path": md_path,
            "html_path": html_path,
            "docx_path": docx_path,
            "charts": [c[0] for c in charts],
        }


# ----------------------------------------------------------------------
# P13-3: 专业图表渲染 (matplotlib) + Word 富文本导出 (python-docx)
# ----------------------------------------------------------------------
def _render_charts(final_state: dict, spear_report: dict, events: list) -> list:
    """渲染 4 张专业图表，返回 [(png_path, caption), ...]"""
    chart_dir = os.path.join(OUTPUT_DIR, "charts")
    os.makedirs(chart_dir, exist_ok=True)
    charts = []
    ts = final_state.get("threat_stats", {}) or {}
    twin = final_state.get("twin_summary") or {}

    # 图1: 拦截效能环形图
    try:
        fig, ax = plt.subplots(figsize=(5.2, 4.2), dpi=150)
        vals = [ts.get("intercepted", 0), ts.get("impacted", 0), ts.get("active", 0)]
        vals = [max(v, 0) for v in vals]
        if sum(vals) == 0:
            vals = [1]
            labels, colors = ["无交战"], ["#888888"]
        else:
            labels = ["成功拦截", "突防命中", "仍活跃"]
            colors = ["#2ec4b6", "#e63946", "#f5b84e"]
        wedges, _, autotexts = ax.pie(
            vals,
            labels=labels if sum(vals) > 1 else None,
            colors=colors,
            autopct=lambda p: f"{p:.0f}%" if p > 3 else "",
            startangle=90,
            wedgeprops=dict(width=0.42, edgecolor="#0a0e17"),
        )
        for t in autotexts:
            t.set_color("white")
            t.set_fontweight("bold")
        rate = ts.get("intercept_rate", 0)
        ax.text(
            0, 0, f"{rate:.1%}", ha="center", va="center",
            fontsize=22, fontweight="bold", color="#2ec4b6",
        )
        ax.set_title(f"拦截效能总览（发射 {ts.get('total_missiles', 0)} 枚）", fontsize=12)
        p1 = os.path.join(chart_dir, "chart_intercept.png")
        fig.tight_layout()
        fig.savefig(p1, facecolor="white")
        plt.close(fig)
        charts.append((p1, "图 1  拦截效能环形图（中心为综合拦截率）"))
    except Exception:
        pass

    # 图2: ASDA 四环事件分布
    try:
        phases = spear_report.get("asda_phase_activity", {}) or {}
        if phases:
            fig, ax = plt.subplots(figsize=(6.4, 3.8), dpi=150)
            names = list(phases.keys())
            nums = [phases[k] for k in names]
            bar_colors = ["#4e9af5", "#4ef59e", "#f5b84e", "#9e4ef5"][: len(names)]
            bars = ax.bar(names, nums, color=bar_colors, width=0.55)
            for b, n in zip(bars, nums):
                ax.text(b.get_x() + b.get_width() / 2, b.get_height() + max(nums) * 0.02,
                        str(n), ha="center", fontsize=11, fontweight="bold")
            total = max(sum(nums), 1)
            ax.set_title(f"ASDA 决策循环四环事件分布（总计 {total} 次）", fontsize=12)
            ax.spines[["top", "right"]].set_visible(False)
            ax.set_ylabel("事件数")
            p2 = os.path.join(chart_dir, "chart_asda.png")
            fig.tight_layout()
            fig.savefig(p2, facecolor="white")
            plt.close(fig)
            charts.append((p2, "图 2  ASDA 决策循环 Act-Sense-Decide-Adapt 事件分布"))
    except Exception:
        pass

    # 图3: SPEAR 事件分布 Top10
    try:
        dist = spear_report.get("event_distribution", {}) or {}
        if dist:
            top = sorted(dist.items(), key=lambda x: -x[1])[:10][::-1]
            fig, ax = plt.subplots(figsize=(6.8, 4.4), dpi=150)
            names = [k for k, _ in top]
            nums = [v for _, v in top]
            ax.barh(names, nums, color="#4e9af5", height=0.6)
            for i, n in enumerate(nums):
                ax.text(n + max(nums) * 0.01, i, str(n), va="center", fontsize=10)
            ax.set_title("SPEAR 事件分布 Top10", fontsize=12)
            ax.spines[["top", "right"]].set_visible(False)
            p3 = os.path.join(chart_dir, "chart_events.png")
            fig.tight_layout()
            fig.savefig(p3, facecolor="white")
            plt.close(fig)
            charts.append((p3, "图 3  SPEAR 全事件类型分布（前 10）"))
    except Exception:
        pass

    # 图4: 孪生体构成 + 保真度
    try:
        bk = twin.get("by_kind", {}) or {}
        if bk:
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.2, 3.6), dpi=150)
            ax1.pie(
                list(bk.values()),
                labels=list(bk.keys()),
                colors=["#2ec4b6", "#e63946", "#4e9af5"][: len(bk)],
                autopct="%0f",
                startangle=90,
                wedgeprops=dict(width=0.42, edgecolor="#0a0e17"),
            )
            ax1.set_title(f"孪生体构成（{twin.get('total_twins', 0)} 个）", fontsize=11)
            fid = twin.get("avg_fidelity", 1.0)
            ax2.barh(["平均保真度"], [fid], color="#2ec4b6", height=0.4)
            ax2.barh(["平均保真度"], [1 - fid], left=[fid], color="#333333", height=0.4)
            ax2.set_xlim(0, 1)
            ax2.text(fid / 2, 0, f"{fid:.1%}", ha="center", va="center",
                     fontweight="bold", color="white")
            ax2.set_title("虚实同步保真度", fontsize=11)
            ax2.spines[["top", "right"]].set_visible(False)
            p4 = os.path.join(chart_dir, "chart_twin.png")
            fig.tight_layout()
            fig.savefig(p4, facecolor="white")
            plt.close(fig)
            charts.append((p4, "图 4  数字孪生层：孪生体构成与虚实同步保真度"))
    except Exception:
        pass

    return charts


def _set_cn_font(run):
    run.font.name = "微软雅黑"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")


def _build_docx(
    content: str, charts: list, model: str = "", scenario: str = ""
) -> str:
    """把 Markdown 报告 + 图表渲染成排版良好的 Word 文档。"""
    doc = Document()

    # 全局样式
    style = doc.styles["Normal"]
    style.font.name = "微软雅黑"
    style.element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
    style.font.size = Pt(10.5)

    # 封面标题
    title = doc.add_heading("PMTEC 数字孪生战场 AI 态势分析报告", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in title.runs:
        _set_cn_font(run)
        run.font.color.rgb = RGBColor(0x0B, 0x3D, 0x91)

    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = meta.add_run(
        f"想定：{scenario} ｜ 分析模型：{model} ｜ "
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    _set_cn_font(run)
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
    doc.add_paragraph()

    chart_i = 0
    # 图表前置插入第 1 张（拦截效能总览）
    if charts:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(charts[0][0], width=Inches(5.2))
        cap = doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = cap.add_run(charts[0][1])
        _set_cn_font(run)
        run.font.size = Pt(8.5)
        run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
        chart_i = 1

    def add_runs(par, text):
        """处理 **加粗** 的混合文本段。"""
        parts = re.split(r"(\*\*.+?\*\*)", text)
        for part in parts:
            if part.startswith("**") and part.endswith("**"):
                run = par.add_run(part[2:-2])
                run.bold = True
                _set_cn_font(run)
            elif part:
                run = par.add_run(part)
                _set_cn_font(run)

    for line in content.split("\n"):
        line = line.rstrip()
        if not line.strip():
            continue
        if line.startswith("### "):
            h = doc.add_heading(line[4:].strip(), level=3)
            for r in h.runs:
                _set_cn_font(r)
        elif line.startswith("## "):
            h = doc.add_heading(line[3:].strip(), level=2)
            for r in h.runs:
                _set_cn_font(r)
            # 二级标题后插入下一张图
            if chart_i < len(charts):
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p.add_run().add_picture(charts[chart_i][0], width=Inches(5.6))
                cap = doc.add_paragraph()
                cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = cap.add_run(charts[chart_i][1])
                _set_cn_font(run)
                run.font.size = Pt(8.5)
                run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
                chart_i += 1
        elif line.startswith("# "):
            continue  # 主标题已由封面呈现
        elif re.match(r"^\s*[-*] ", line):
            par = doc.add_paragraph(style="List Bullet")
            add_runs(par, line.strip()[2:])
        elif re.match(r"^\s*\d+[.、)] ", line):
            par = doc.add_paragraph(style="List Number")
            add_runs(par, re.sub(r"^\s*\d+[.、)] ", "", line))
        else:
            par = doc.add_paragraph()
            add_runs(par, line.strip())
            par.paragraph_format.space_after = Pt(6)

    # 尾部插入剩余图表
    while chart_i < len(charts):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(charts[chart_i][0], width=Inches(5.6))
        cap = doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = cap.add_run(charts[chart_i][1])
        _set_cn_font(run)
        run.font.size = Pt(8.5)
        run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
        chart_i += 1

    # 页脚说明
    doc.add_paragraph()
    foot = doc.add_paragraph()
    run = foot.add_run(
        "本报告由 PMTEC 数字孪生战场系统 AI 参谋官自动生成；"
        "全部数据来源于仿真引擎物理域实测（SPEAR 事件流 / 数字孪生同步层 / P10 政治准入 / P11 指挥链）。"
    )
    _set_cn_font(run)
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    path = os.path.join(OUTPUT_DIR, "ai_situation_analysis.docx")
    doc.save(path)
    return path


# ----------------------------------------------------------------------
# Minimal markdown -> html (no external deps)
# ----------------------------------------------------------------------
def _markdown_to_html(md: str) -> str:
    """极简 Markdown 渲染（标题/列表/粗体/段落），避免引入额外依赖。"""
    lines = md.split("\n")
    out: list[str] = []
    in_list = False
    for line in lines:
        esc = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
        if line.startswith("### "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h3>{esc[4:]}</h3>")
        elif line.startswith("## "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h2>{esc[3:]}</h2>")
        elif line.startswith("# "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h1>{esc[2:]}</h1>")
        elif line.startswith("- ") or line.startswith("  - "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{esc.lstrip()[2:]}</li>")
        elif line.strip():
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<p>{esc}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def _html_template(body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>PMTEC AI 态势分析报告</title>
<style>
  body {{ font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
         max-width: 860px; margin: 40px auto; padding: 0 24px;
         color: #1a1a2e; line-height: 1.75; background: #f8f9fb; }}
  h1 {{ color: #0b3d91; border-bottom: 3px solid #0b3d91; padding-bottom: 10px; }}
  h2 {{ color: #0b3d91; margin-top: 2em; border-left: 5px solid #e63946; padding-left: 12px; }}
  h3 {{ color: #333; }}
  p, li {{ font-size: 15px; }}
  strong {{ color: #c1121f; }}
</style>
</head>
<body>
{body}
</body>
</html>"""


if __name__ == "__main__":
    # 自测：用最小构造的终态数据跑一次真实 LLM 调用
    demo_state = {
        "scenario": "PMTEC-Pacific (self-test)",
        "sim_seconds": 300.0,
        "asda_cycle": 30,
        "total_entities": 142,
        "active_tracks": 11,
        "network_vulnerability": 0.22,
        "lvc_live_entities": 6,
        "threat_stats": {
            "total_missiles": 46,
            "intercepted": 33,
            "impacted": 11,
            "active": 2,
            "intercept_rate": 0.7174,
        },
        "adversary_stats": {"launches": 46, "aggression": 0.3},
        "political_access": {
            "ally_sites": 3,
            "ally_countries": ["JP", "PH"],
            "escalation_level": 0.42,
            "by_country": {
                "JP": [{"state": "granted", "prob": 0.92}],
                "PH": [
                    {"state": "granted", "prob": 0.78},
                    {"state": "conditional", "prob": 0.51},
                ],
            },
            "mrfd": {"cycle_progress": 0.61, "readiness": 0.74, "frozen": False},
            "events_count": 5,
        },
        "c2_chain": {
            "nodes": [{"node_id": f"N{i}"} for i in range(9)],
            "bases_assigned": 12,
            "message_count": 57,
            "recent_messages": [
                {"total_latency_s": 1.8, "hops": [1, 2]},
                {"total_latency_s": 2.1, "hops": [1, 2, 3]},
            ],
        },
        "weather": {"detection_range_factor": 0.85, "visibility": "moderate"},
    }
    demo_events = [
        {
            "event_type": "damage",
            "description": "F-35A AC-017 destroyed at KADENA AB",
            "data": {"base": "KADENA-AB", "ac_type": "F-35A"},
        }
    ]
    demo_report = {
        "total_events": 612,
        "event_distribution": {
            "detect": 180,
            "intercept_attempt": 96,
            "intercept_success": 68,
            "missile_launch": 46,
            "impact": 11,
            "damage": 4,
            "c2_order": 57,
        },
        "asda_phase_activity": {"Act": 120, "Sense": 210, "Decide": 180, "Adapt": 102},
        "damage_events": 4,
        "detection_events": 180,
    }
    analyst = LLMAnalyst()
    result = analyst.generate_report_files(demo_state, demo_report, demo_events)
    if result:
        print("[SELF-TEST OK]")
        print("  MD  :", result["md_path"])
        print("  HTML:", result["html_path"])
    else:
        print("[SELF-TEST FAILED]")
