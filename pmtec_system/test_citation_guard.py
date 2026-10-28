#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""推理端出处守卫单测（P19 训练研究线部署落点）。

覆盖 services/citation_guard.py 与 llm_analyst.analyze 的接入路径：
  - citation_check 五规则（真引用回查 / 假引用判罚 / 白名单缺失失效）
  - guard_answer 拦截声明与审计字段
  - analyze 集成：假引用替换 / 真引用放行 / 开关控制

Run: python -X utf8 test_citation_guard.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services import citation_guard as cg
from services.citation_guard import citation_check, guard_answer, load_guard

PASS = []


def check(name, cond):
    PASS.append((name, bool(cond)))
    print(("ok   " if cond else "FAIL ") + name)


def main():
    loaded = load_guard()
    check("白名单加载（346 文件）", loaded and len(cg._STATE["files"]) >= 300)

    # ── citation_check 规则 ──
    ok, bad = citation_check(
        "拦截率 79.1%。出处：output/five_questions_report.json 与 "
        "twin_summary.calibration 节点。")
    check("真路径+语料短语可回查", ok and not bad)
    ok, bad = citation_check(
        "详见 twin_summary.txt 和 data/musix_calibration.html。")
    check("D 组实证假路径判罚", bad == ["data/musix_calibration.html",
                                        "twin_summary.txt"])
    ok, bad = citation_check(
        "monte_carlo_results_v2_polICY.json 是拼写腐蚀（E 轮形态）。")
    check("近似拼写腐蚀判罚", "monte_carlo_results_v2_polICY.json" in bad)

    # 中文文件名走 basenames 兜底
    ok, bad = citation_check("出处：docs/必答五问作答.md。")
    check("中文文件名 basenames 匹配", ok and not bad)

    # ── guard_answer ──
    safe, audit = guard_answer("没有引用的普通回答。")
    check("无引用原样放行", safe == "没有引用的普通回答。" and not audit["guarded"])
    safe, audit = guard_answer(
        "拦截率 79.1%，出处见 twin_summary.txt。")
    check("假引用整答替换为拦截声明", safe.startswith("【出处守卫拦截】"))
    check("审计保留原文与 bad 列表",
          audit["guarded"] and audit["bad_citations"] == ["twin_summary.txt"]
          and "twin_summary" in audit["original"])
    safe, audit = guard_answer(
        "拦截率 79.1%，出处见 output/five_questions_report.json。", enabled=False)
    check("enabled=False 显式关闭", safe.startswith("拦截率 79.1%"))

    # ── llm_analyst.analyze 集成 ──
    os.environ["PMTEC_LLM_API_KEY"] = "test-key"
    import services.llm_analyst as m
    a = m.LLMAnalyst()
    check("LLMAnalyst 经环境变量启用", a.enabled)

    fake = "拦截率 79.1%。详见 twin_summary.txt 与 data/musix_calibration.html。\n"
    a.chat = lambda msgs: fake
    out = a.analyze({}, {}, [])
    check("analyze: 假引用 → 拦截声明", out and out.startswith("【出处守卫拦截】"))

    real = "拦截率 79.1%。出处：output/five_questions_report.json。\n"
    a.chat = lambda msgs: real
    check("analyze: 真引用 → 原样", a.analyze({}, {}, []) == real)

    os.environ["PMTEC_CITATION_GUARD"] = "0"
    a.chat = lambda msgs: fake
    check("analyze: 环境变量关闭守卫", a.analyze({}, {}, []) == fake)
    del os.environ["PMTEC_CITATION_GUARD"]

    # ── 汇总 ──
    n_fail = sum(1 for _, c in PASS if not c)
    print(f"\nGUARD TESTS: {len(PASS) - n_fail}/{len(PASS)} passed")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main() or 0)