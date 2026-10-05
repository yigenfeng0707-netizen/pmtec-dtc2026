#!/usr/bin/env python3
"""P18 必答五问验收测试——评审 P1"逐条作答 5 个必答问题"的门禁断言。

跑法：python -X utf8 test_p18_five_questions.py
依赖：先运行 scripts/five_questions_analysis.py --fast 生成报告（测试内自跑）。
"""

import json
import os
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.stdout.reconfigure(encoding="utf-8")

REPORT = os.path.join(PROJECT_ROOT, "output", "five_questions_report.json")

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    tag = "PASS" if cond else "FAIL"
    print(f"  [{tag}] {name}" + (f" — {detail}" if detail else ""))
    if cond:
        passed += 1
    else:
        failed += 1


def main():
    print("=" * 70)
    print("P18 Five Questions Acceptance (regenerates report in fast mode)")
    print("=" * 70)

    proc = subprocess.run(
        [sys.executable, os.path.join(PROJECT_ROOT, "scripts",
                                      "five_questions_analysis.py"), "--fast"],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    )
    check("报告生成脚本 --fast 退出码 0", proc.returncode == 0,
          proc.stderr[-200:] if proc.returncode else "")

    with open(REPORT, encoding="utf-8") as f:
        r = json.load(f)

    # ---- Q1 失效场景与红方代价 ----
    q1 = r["Q1_failure_scenarios"]
    s1, s2, s3 = q1["S1"], q1["S2"], q1["S3"]
    check("Q1 S1 政治拒止 0 弹、67→58 可用",
          s1["red_cost_missiles"] == 0 and s1["avail_bases"] == 58,
          f"cost={s1['red_cost_missiles']} avail={s1['avail_bases']}")
    check("Q1 S1 引擎口径 15 盟友/3 拒止/19 可用",
          s1["engine_caliber"]["n_ally"] == 15
          and s1["engine_caliber"]["denied_sites"] == 3
          and s1["engine_caliber"]["avail_bases"] == 19)
    check("Q1 S2 红方代价区间 100-160 发、Tier-1 14 座",
          s2["red_cost_missiles_low"] == 100 and s2["red_cost_missiles_high"] == 160
          and s2["tier1_removed"] == 14)
    check("Q1 S3 复合场景实体规模最重伤（61.2% < S2 70.1%）",
          s3["count_retention"] < s2["count_retention"] < 1
          and 0 < s3["value_retention"] < 1,
          f"S3 value={s3['value_retention']} count={s3['count_retention']}")
    check("Q1 代价模型泄漏率与 MC 拦截率自洽",
          abs(s2["red_cost_model"]["leak_p_per_missile"] - 0.2086) < 0.001,
          str(s2["red_cost_model"]["leak_p_per_missile"]))

    # ---- Q2 移除曲线 ----
    q2 = r["Q2_removal_curves"]
    t30, r30 = q2["targeted"]["0.3"], q2["random"]["0.3"]
    check("Q2 定向 30% 保留率 28.8%（最坏情形）",
          abs(t30["value_retention"] - 0.2878) < 0.01, str(t30["value_retention"]))
    check("Q2 随机 30% 均值 ~70%（体系抗随机冗余）",
          abs(r30["value_retention_mean"] - 0.70) < 0.05,
          str(r30["value_retention_mean"]))
    check("Q2 定向严格劣于随机（30% 处）",
          t30["value_retention"] < r30["value_retention_mean"])
    check("Q2 曲线单调递减（定向）",
          all(q2["targeted"][a]["value_retention"] > q2["targeted"][b]["value_retention"]
              for a, b in zip(["0.1", "0.2", "0.3", "0.4"], ["0.2", "0.3", "0.4", "0.5"])))

    # ---- Q3 敏感性排序 ----
    q3 = r["Q3_sensitivity_ranking"]
    check("Q3 五参数全排序", len(q3) == 5 and [x["rank"] for x in q3] == [1, 2, 3, 4, 5])
    check("Q3 排序按响应度降序",
          all(a["rel_response_per_unit"] >= b["rel_response_per_unit"]
              for a, b in zip(q3, q3[1:])))
    check("Q3 第一敏感参数 = 准入扰动 σ",
          "σ" in q3[0]["param"], q3[0]["param"])

    # ---- Q4 交换比 ----
    q4 = r["Q4_exchange_ratio"]
    check("Q4 全量弹耗比 4.79 发/突防",
          abs(q4["overall"]["missiles_per_through"] - 4.79) < 0.05,
          str(q4["overall"]["missiles_per_through"]))
    check("Q4 六策略区间 4.4-5.3",
          all(4.4 < v["missiles_per_through"] < 5.3
              for v in q4["per_strategy"].values()),
          str(sorted(v["missiles_per_through"] for v in q4["per_strategy"].values())))
    check("Q4 齐射场景对照在场（156 全保存/0.0% 口径）",
          "156" in q4["salvo_reference"]["blue_loss"]
          and "0.0%" in q4["salvo_reference"]["blue_loss"],
          q4["salvo_reference"]["blue_loss"][:40])

    # ---- Q5 政治韧性 ----
    q5 = r["Q5_political_resilience"]
    scen = q5["scenarios"]
    rates = [v["intercept_rate"] for v in scen.values() if v]
    check("Q5 三场景拦截率 76.2/79.0/79.1",
          len(rates) == 3 and abs(rates[0] - 0.762) < 0.005
          and abs(rates[1] - 0.790) < 0.005 and abs(rates[2] - 0.791) < 0.005,
          str([round(x, 3) for x in rates]))
    sweep = q5["m_denied_sweep"]
    ks = [p["conflict_K"] for p in sweep]
    bels = [p["bel_open"] for p in sweep]
    check("Q5 m(Denied) 扫描 K 单调递增且 ≤ md（可复算口径）",
          ks == sorted(ks) and all(p["conflict_K"] <= p["m_denied"] + 1e-9 for p in sweep),
          f"K {ks[0]}→{ks[-1]}")
    check("Q5 m(Denied) 域内 Bel(Open) 恒 >0.5（稳健性结论）",
          all(b > 0.5 for b in bels), f"Bel {bels[0]}→{bels[-1]}")
    card_txt = open(os.path.join(
        PROJECT_ROOT, "ontology", "failure_boundary_card.md"),
        encoding="utf-8").read()
    check("Q5 失效边界卡已切换为可复算口径（修正留痕在场）",
          "2026-10-05 修正为可复算口径" in card_txt
          and "five_questions_analysis" in card_txt
          and "作废" in card_txt)

    print("\n" + "=" * 70)
    print(f"P18 Five Questions: {passed} passed, {failed} failed")
    print("=" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
