#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P13 Test Suite: AI 参谋官 + 数字孪生同步层 + 饱和攻击 + REST 扩展

Validates (全部离线，不依赖外网 LLM):
  1. TwinSyncManager: 基地/威胁/场景孪生创建、同步、保真度、结局校准
  2. AdversaryAgent salvo: 齐射规模生成 + max_concurrent 约束
  3. LLMAnalyst.build_battle_context: P10/P11/孪生层数据注入（不调用 API）
  4. SituationSerializer: twin_summary 进入 full/delta 消息
  5. REST gateway 路由注册（/api/v1/analysis, /api/v1/dt/sync）

Run: python -X utf8 test_p13.py
"""
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

PASS = 0
FAIL = 0
RESULTS = []


def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        RESULTS.append(f"  [PASS] {name}")
    else:
        FAIL += 1
        RESULTS.append(f"  [FAIL] {name} {detail}")


print("\n[1/5] TwinSyncManager - 基地/场景孪生...")
from dt_platform.twin_sync import TwinSyncManager
from models.adversary_agent import AdversaryAgent

tsm = TwinSyncManager(registry=None)


class _Clock:
    class current:
        sim_seconds = 120.0


class _Pol:
    sites = {}
    escalation_level = 0.1


class _FakeEngine:
    _bases = [
        {"id": "JP-YOKOTA", "name": "Yokota AB", "lat": 35.7, "lon": 139.35},
        {"id": "PH-EDCA-1", "name": "EDCA Site", "lat": 15.0, "lon": 120.9},
    ]
    _entities = []
    _sensors = []
    _missiles = []
    clock = _Clock()
    political = _Pol()
    asda_cycle_count = 12

    def _calc_network_vulnerability(self):
        return 0.0

    class _Adv:
        baseline_aggression = 0.8

    adversary = _Adv()


tsm.sync(_FakeEngine())
summary = tsm.summary()
test("基地孪生创建", summary["by_kind"].get("base") == 2, f"got {summary['by_kind']}")
test("场景孪生创建", summary["by_kind"].get("scenario") == 1)
test("引擎同步计数", summary["engine_syncs"] == 1)
test("保真度满值(无偏差)", summary["avg_fidelity"] == 1.0)
top = tsm.top_twins(kind="base", limit=4)
test("top_twins 返回结构", len(top) == 2 and "physical" in top[0])

print("\n[2/5] AdversaryAgent salvo 齐射...")
adv = AdversaryAgent(
    aggression_level=0.9, seed=42, max_concurrent_threats=12, max_missiles_per_salvo=4
)
bases = [{"id": f"B{i}", "name": f"Base{i}", "lat": 30, "lon": 140} for i in range(5)]


_M_N = 0


class _M:
    def __init__(self):
        global _M_N
        _M_N += 1
        self.status = "active"
        self.id = f"M{_M_N}"


missiles = []
salvo_sizes = []
for i in range(60):
    d = adv.decide_attack(
        bases=bases, entities=[], missiles=missiles, sensors=[], asda_cycle=i
    )
    if d["should_attack"]:
        salvo_sizes.append(d.get("salvo_size", 1))
        missiles = [m for m in missiles if m.status == "active"]
        for _ in range(d["salvo_size"]):
            missiles.append(_M())
test("饱和模式下有多次攻击", len(salvo_sizes) >= 5, f"got {len(salvo_sizes)}")
test("齐射规模 >= 1 且 <= 4", all(1 <= s <= 4 for s in salvo_sizes), f"{salvo_sizes[:8]}")
test("齐射存在多弹", max(salvo_sizes) >= 2, f"max={max(salvo_sizes)}")

print("\n[2.5/5] 孪生策略反哺模型...")
tsm2 = TwinSyncManager(registry=None)
# 证据不足 -> 不干预
s, p = tsm2.recommend_strategy("DF-17", ["direct", "predictive", "saturation"])
test("无样本不干预", s is None and p == 0.0)
# 灌入历史：saturation 对 DF-17 成功率高（8/10），direct 低（1/5）
for _ in range(8):
    tsm2.record_threat_outcome("T1", True, missile_type="DF-17", strategy="saturation")
for _ in range(2):
    tsm2.record_threat_outcome("T2", False, missile_type="DF-17", strategy="saturation")
for _ in range(1):
    tsm2.record_threat_outcome("T3", True, missile_type="DF-17", strategy="direct")
for _ in range(4):
    tsm2.record_threat_outcome("T4", False, missile_type="DF-17", strategy="direct")
s, p = tsm2.recommend_strategy("DF-17", ["direct", "predictive", "saturation"])
test("推荐最优策略", s == "saturation", f"got {s}")
test("预测概率合理", 0.7 <= p <= 0.95, f"p={p}")
sm = tsm2.strategy_model_summary()
test("策略模型结构", sm.get("DF-17|saturation", {}).get("n") == 10)

print("\n[3/5] LLMAnalyst.build_battle_context...")
from services.llm_analyst import LLMAnalyst

analyst = LLMAnalyst()
state = {
    "scenario": "PMTEC-Pacific-Saturation",
    "sim_seconds": 600.0,
    "asda_cycle": 60,
    "total_entities": 46,
    "active_tracks": 14,
    "network_vulnerability": 0.0,
    "threat_stats": {
        "total_missiles": 16,
        "intercepted": 16,
        "impacted": 0,
        "active": 0,
        "intercept_rate": 1.0,
    },
    "adversary_stats": {"total_attacks": 7, "outcomes_recorded": 16},
    "political_access": {
        "ally_sites": 15,
        "ally_countries": ["Japan", "Philippines"],
        "escalation_level": 0.0,
        "by_country": {"Japan": [{"state": "full", "prob": 0.9}]},
        "mrfd": {"cycle_progress": 0.9, "readiness": 1.0, "frozen": False},
        "events_count": 12,
    },
    "c2_chain": {
        "nodes": [{"node_id": f"N{i}"} for i in range(9)],
        "bases_assigned": 22,
        "message_count": 103,
        "recent_messages": [
            {"total_latency_s": 1.5, "hops": [1, 2]},
            {"total_latency_s": 1.7, "hops": [1, 2, 3]},
        ],
    },
    "twin_summary": {
        "total_twins": 23,
        "by_kind": {"base": 22, "threat": 0, "scenario": 1},
        "avg_fidelity": 0.969,
        "engine_syncs": 60,
        "deviating_twins": [
            {"twin_id": "X", "name": "Camp Humphreys", "deviation": 0.2}
        ],
        "intercept_model": {"DF-17": {"p": 0.85, "n": 6}},
    },
    "weather": {"detection_range_factor": 1.0},
}
report = {
    "event_distribution": {"detect": 251, "intercept_success": 16},
    "asda_phase_activity": {"Act": 44, "Sense": 302, "Decide": 195, "Adapt": 28},
    "damage_events": 0,
    "detection_events": 251,
}
events = [
    {
        "event_type": "damage",
        "description": "F-35A destroyed at KADENA AB",
        "data": {"base": "KADENA-AB", "ac_type": "F-35A"},
    }
]
ctx = analyst.build_battle_context(state, report, events)
test("P10 数据注入", "15" in ctx and "ally_sites" not in ctx and "盟友站点总数" in ctx)
test("P11 延迟注入", "1.5" in ctx or "1.6" in ctx)
test("孪生层注入", "平均保真度" in ctx and "96.9" in ctx)
test("拦截概率模型注入", "DF-17" in ctx)
test("damage 事件提取", "KADENA-AB" in ctx)
test("拦截率格式化", "100.0%" in ctx)

print("\n[4/5] SituationSerializer twin 字段...")
from realtime.situation_serializer import SituationSerializer

ser = SituationSerializer()
fake_state = {
    "sim_time": "T+00:01:00",
    "sim_seconds": 60,
    "asda_cycle": 6,
    "asda_phase": "Adapt",
    "entities": [],
    "tracks": [],
    "twin_summary": {"total_twins": 23, "avg_fidelity": 0.969, "engine_syncs": 6},
    "twin_top": [{"twin_id": "T1"}],
}
msg = json.loads(ser.serialize_full(fake_state, []))
test("full 消息含 twin_summary", msg.get("twin_summary", {}).get("total_twins") == 23)
fake_state["twin_summary"]["total_twins"] = 24
fake_state["twin_summary"]["engine_syncs"] = 7
msg = json.loads(ser.serialize_delta(fake_state, []))
if msg:
    test("delta 消息含 twin_summary", msg.get("twin_summary", {}).get("total_twins") == 24)
else:
    test("delta 消息含 twin_summary", False, "delta returned None")

print("\n[5/5] REST gateway 路由...")
with open(
    os.path.join(PROJECT_ROOT, "dt_platform", "rest_gateway.py"), encoding="utf-8"
) as f:
    gw_src = f.read()
test("GET /api/v1/analysis 路由", '"/api/v1/analysis"' in gw_src)
test("POST /api/v1/analysis 路由", gw_src.count('"/api/v1/analysis"') >= 2)
test("GET /api/v1/dt/sync 路由", '"/api/v1/dt/sync"' in gw_src)
test("ThreadingHTTPServer 并发", "ThreadingHTTPServer(" in gw_src)

print()
print("=" * 50)
for r in RESULTS:
    print(r)
print("=" * 50)
print(f"P13 Tests: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
