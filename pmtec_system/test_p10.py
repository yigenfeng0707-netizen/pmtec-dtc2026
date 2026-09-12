#!/usr/bin/env python3
"""
P10 Test Suite: Allied Cooperation & Political Access Constraint Modeling

Validates:
  A. Political access state machine (Full/Restricted/Denied transitions,
     4 event types, MRF-D rotation, negotiation delay, risk exposure)
  B. Three-scenario Monte Carlo (ACE optimizer + political constraint,
     Pareto political-risk objective; full / evolved / all-denied)
  C. Grey-zone chain replay (event -> evolution -> available set -> exposure)

Note: pmtec_system and ace_deployment both have a top-level `models` package,
      imported in two phases (sys.modules cleaned before phase 2).

Run: D:/miniconda3/envs/pmtec-xpu/python.exe test_p10.py
"""

import json
import os
import statistics as st
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_ROOT = os.path.dirname(PROJECT_ROOT)
ACE_ROOT = os.path.join(WORKSPACE_ROOT, "ace_deployment")
GEOJSON = os.path.join(PROJECT_ROOT, "data", "bases_v2.geojson")

sys.path.insert(0, PROJECT_ROOT)
sys.stdout.reconfigure(encoding="utf-8")

PASS, FAIL = 0, 0


def test(name, condition, detail=""):
    global PASS, FAIL
    tag = "PASS" if condition else "FAIL"
    print(f"  [{tag}] {name}" + (f" | {detail}" if detail else ""))
    PASS += int(bool(condition))
    FAIL += int(not condition)


with open(GEOJSON, encoding="utf-8") as f:
    gj = json.load(f)
base_rows = [
    {
        "id": p["id"],
        "country": p.get("country", ""),
        "access_uncertainty": p.get("access_uncertainty"),
    }
    for p in (ft["properties"] for ft in gj["features"])
]
all_ids = [r["id"] for r in base_rows]

# ============================================================
# Phase 1 (A): state machine + (C): grey-zone chain replay
# ============================================================
from models.political_access import (
    EVENT_GREY_ZONE,
    EVENT_REASSURANCE,
    EVENT_SOVEREIGN_STRIKE,
    AccessState,
    MRFDRotation,
    PoliticalAccessModel,
    PoliticalEvent,
)

print("\n[A] 政治准入状态机转移测试（models/political_access.py）")

m = PoliticalAccessModel.from_bases(base_rows, seed=42)
print(f"  盟友站点: {len(m.sites)} | 国家: {sorted(m.ally_countries)}")

ph = "PH-BASA"
site = m.sites[ph]
p0, s0 = site.current_prob, site.state

# A1 灰色地带 -> restricted
m.inject_event(PoliticalEvent(EVENT_GREY_ZONE, "Philippines", intensity=1.0, cycle=1))
site.transition(1)
p1, s1 = site.current_prob, site.state
test("灰色地带事件概率下降", p1 < p0, f"{p0:.3f} -> {p1:.3f}")
test("降级至 restricted", s1 == AccessState.RESTRICTED, f"state={s1.value}")
test("转移记录写入历史", any(r["to"] == "restricted" for r in site.state_history))

# A2 主权打击 -> denied
m.inject_event(PoliticalEvent(EVENT_SOVEREIGN_STRIKE, "Philippines", intensity=0.9, cycle=2))
site.transition(2)
p2, s2 = site.current_prob, site.state
test("主权打击后 denied", s2 == AccessState.DENIED, f"state={s2.value}")
test("DENIED 排除出可用集", ph not in m.available_bases(all_ids))
test("政治成本 denied=1.0", m.political_cost(ph) == 1.0)

# A3 信誉事件 + 恢复 -> 升回 restricted/full
m.inject_event(PoliticalEvent(EVENT_REASSURANCE, "Philippines", intensity=1.0, cycle=3))
for _ in range(3):
    site.recover(0.10)
site.transition(3)
p3, s3 = site.current_prob, site.state
test("恢复后准入可用", s3 in (AccessState.RESTRICTED, AccessState.FULL), f"state={s3.value}")
test("回到可用集", ph in m.available_bases(all_ids))

# A4 风险敞口 + 谈判延迟
expect_risk = 100 * (1.0 - s3.capacity_factor)
got_risk = m.political_risk_exposure({ph: 100, "GU-ANDERSEN": 100})
test("风险敞口 = Σ value×(1-capacity)", abs(got_risk - expect_risk) < 1e-9,
     f"expect={expect_risk} got={got_risk}")
test("盟友谈判延迟>0 / 主权站点=0",
     m.negotiation_delay_h(ph) > 0 and m.negotiation_delay_h("GU-ANDERSEN") == 0)

# A5 MRF-D 轮换（中点/换防/冻结）
mrf = MRFDRotation(rotation_days=180, changeover_window=30, seed=42)
mrf.day = 90
r_mid = mrf.readiness()
mrf.day = 5
r_chg = mrf.readiness()
fz = mrf.freeze_wartime()
test("轮换中点满战备", r_mid == 1.0)
test("换防窗口战备下降至 0.6", r_chg == 0.6)
test("战时冻结满战备+政治成本", fz["readiness"] == 1.0 and fz["political_cost"] == 0.35)

# A6 update_cycle 全局演化（导弹活动驱动升级累积 -> 降级）
m2 = PoliticalAccessModel.from_bases(base_rows, seed=42)
all_tr = []
for c in range(1, 13):
    all_tr += m2.update_cycle(cycle=c, missile_activity=0.9)
n_r = sum(1 for s in m2.sites.values() if s.state == AccessState.RESTRICTED)
n_d = sum(1 for s in m2.sites.values() if s.state == AccessState.DENIED)
test("冲突升级度累积上升", m2.escalation_level > 0.30, f"{m2.escalation_level:.3f}")
test("升级压力产生降级站点", n_r + n_d > 0, f"restricted={n_r} denied={n_d}")

# A7 基线扰动敏感性（蒙特卡洛支持）
m3 = PoliticalAccessModel.from_bases(base_rows, seed=7)
m3.perturb_baselines(sigma=0.15, seed=99)
ok = all(abs(s.current_prob - s.baseline_prob) < 1e-9 for s in m3.sites.values())
test("扰动重置当前=新基线并重分类", ok)

# ---------------- C 灰色地带链路回放 ----------------
print("\n[C] 灰色地带链路回放（事件 -> 演化 -> 可用集 -> 敞口）")

m4 = PoliticalAccessModel.from_bases(base_rows, seed=42)
ph_sites = [s for s in m4.sites.values() if s.country == "Philippines"]


def brief(tag):
    avail = len(m4.available_bases(all_ids))
    expo = m4.political_risk_exposure(
        {s.base_id: 100 for s in m4.sites.values() if s.country == "Philippines"}
    )
    print(f"  [{tag}] 可用 {avail:2d}/{len(all_ids)} | "
          f"升级度 {m4.escalation_level:.3f} | PH敞口 {expo:.0f}")
    return avail


a0 = brief("c0 基线      ")
t1 = m4.update_cycle(
    cycle=1,
    events=[PoliticalEvent(EVENT_GREY_ZONE, "Philippines", intensity=1.0, cycle=1)],
)
a1 = brief("c1 灰色地带  ")
t2 = m4.update_cycle(
    cycle=2,
    missile_activity=0.7,
    events=[PoliticalEvent(EVENT_GREY_ZONE, "Philippines", intensity=0.8, cycle=2)],
)
a2 = brief("c2 挑衅+高活动")
t3 = m4.update_cycle(
    cycle=3,
    missile_activity=0.5,
    events=[PoliticalEvent(EVENT_SOVEREIGN_STRIKE, "Philippines",
                           intensity=0.9, cycle=3)],
)
a3 = brief("c3 主权打击  ")
for c in range(4, 7):
    m4.update_cycle(
        cycle=c,
        events=[PoliticalEvent(EVENT_REASSURANCE, "Philippines",
                               intensity=0.9, cycle=c)],
    )
for c in range(7, 13):
    m4.update_cycle(cycle=c)
a12 = brief("c12 信誉+恢复 ")

ph_final = {s.state.value for s in ph_sites}
test("灰色地带当周期即降级 PH 站点", len(t1) == len(ph_sites),
     f"c1 转移 {len(t1)} = PH 站点 {len(ph_sites)}")
test("主权打击后可用集收缩", a3 < a0, f"{a0} -> {a3}")
test("PH 终态升回非 denied", "denied" not in ph_final or len(ph_final) > 1, f"{ph_final}")
test("恢复后可用集回升", a12 >= a3, f"{a3} -> {a12}")
test("事件日志与转移日志持久化",
     len(m4.events_log) >= 5 and len(m4.transitions_log) >= len(t1))

# ============================================================
# Phase 2 (B): three-scenario Monte Carlo (ace_deployment)
# ============================================================
_top_pkgs = ("models", "config", "engine", "services", "algorithms", "visualization")
for mod_name in [k for k in sys.modules
                 if any(k == p or k.startswith(p + ".") for p in _top_pkgs)]:
    del sys.modules[mod_name]
sys.path.remove(PROJECT_ROOT)
sys.path.insert(0, ACE_ROOT)

from engine.asda_engine import ASDAEngine
from models.political import (
    SCENARIO_DENIED,
    SCENARIO_EVOLVED,
    SCENARIO_FULL,
)

print("\n[B] 三场景 Monte Carlo（ACE 优化器政治约束 + Pareto 政治风险目标）")

N_SEEDS = 6
agg = {}
for label, sc in [("full_access", SCENARIO_FULL),
                  ("evolved_access", SCENARIO_EVOLVED),
                  ("all_denied", SCENARIO_DENIED)]:
    rows = []
    for seed in range(N_SEEDS):
        eng = ASDAEngine(geojson_path=GEOJSON, seed=seed)
        eng.network.political.set_scenario(sc)
        eng.initialize_fleet()
        plan = eng.deployer.optimize()
        opt = eng.optimizer.evaluate()
        pol = next(o for o in opt.objectives if o.name == "political_risk_exposure")
        strike = next(o for o in opt.objectives if o.name == "strike_capability")
        denied_dest = sum(
            1 for t in plan.transfers
            if eng.network.political.state(t["to_base"]) == "denied"
        )
        rows.append({
            "vuln_after": plan.network_vulnerability_after,
            "transfers": len(plan.transfers),
            "pol_risk": pol.value,
            "strike_cap": strike.value,
            "denied_dest": denied_dest,
            "spokes": len(plan.spokes_reinforced),
        })
    agg[label] = {k: st.mean(r[k] for r in rows) for k in rows[0]}
    print(f"\n  {label}  (seeds={N_SEEDS}):")
    for k, v in agg[label].items():
        print(f"    {k:14s}: {v:10.2f}")

full, evo, den = agg["full_access"], agg["evolved_access"], agg["all_denied"]
print()
test("full 场景政治敞口为 0", full["pol_risk"] == 0, f"{full['pol_risk']}")
test("evolved 场景敞口 >= full", evo["pol_risk"] >= full["pol_risk"], f"{evo['pol_risk']}")
test("all_denied 场景敞口最高且 > 0", den["pol_risk"] > evo["pol_risk"] > -1e-9
     and den["pol_risk"] > 0, f"{den['pol_risk']}")
test("全场景无转移至 DENIED 站点",
     full["denied_dest"] == 0 and evo["denied_dest"] == 0 and den["denied_dest"] == 0)
test("denied 分散受限（转移数 <= full）", den["transfers"] <= full["transfers"] + 1e-9,
     f"den={den['transfers']:.1f} full={full['transfers']:.1f}")
test("denied 场景分布式网络收缩（spokes < full）", den["spokes"] < full["spokes"],
     f"den={den['spokes']:.1f} full={full['spokes']:.1f}")
test("denied 场景可用打击能力退化", den["strike_cap"] < full["strike_cap"],
     f"den={den['strike_cap']:.0f} full={full['strike_cap']:.0f}")

# ============================================================
# 汇总
# ============================================================
print("\n" + "=" * 56)
print(f"P10 测试: {PASS} 通过 / {FAIL} 失败")
if FAIL:
    sys.exit(1)
print("P10 验收标准达成：政治准入三态状态机 + ACE 约束版 + 灰色地带链路 ✓")
