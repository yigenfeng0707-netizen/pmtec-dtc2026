# -*- coding: utf-8 -*-
"""P13/S: 从 asda_simulation_report.json 提取规格三指标（出动架次/损失率/恢复时间）"""
import json, sys
sys.stdout.reconfigure(encoding="utf-8")
r = json.load(open(r"d:\APPs\数字孪生挑战赛\ace_deployment\output\asda_simulation_report.json", encoding="utf-8"))

print("== damage_report ==")
print(json.dumps(r["damage_report"], ensure_ascii=False, indent=1)[:800])
print("\n== initial fleet ==")
print(json.dumps(r["initial_state"]["fleet"], ensure_ascii=False)[:400])
print("\n== final fleet ==")
print(json.dumps(r["final_state"]["fleet"], ensure_ascii=False)[:400])
print("\n== deployment_plan 摘要 ==")
dp = r["deployment_plan"]
for k in ("total_transfers", "vulnerability_before", "vulnerability_after",
          "strike_before", "strike_after", "strike_retention_pct", "spokes_reinforced"):
    print(f"  {k}: {dp.get(k)}")
print("\n== transfer_plans 汇总 ==")
for tp in r["transfer_plans"]:
    print(f"  {tp['threat_uid']} -> {tp['target_base']}: 响应 {tp['response_time_min']}min, "
          f"疏散 {tp['evacuated']}/{tp['evacuated'] + tp['stranded']} "
          f"({tp['evacuation_rate_pct']}%), 挽救价值 {tp['value_saved']}")
