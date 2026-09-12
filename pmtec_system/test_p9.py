#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P9 Test Suite: Authoritative Base Database Upgrade (22 -> 67 entities)

Validates:
  1. bases_v2.geojson: 67 entities, P9.5 new fields (crs_no / fy24_prv_quartile /
     dod_operated / us_territory / access_uncertainty / tier), Tier distribution
  2. PMTECEngine smoke start with the new GeoJSON (load + scenario + ASDA cycles)
  3. RL environment (PMTECEnv) forward compatibility (182-dim observation intact)
  4. Battle network graph full build on all 67 entities

Data sources: CRS R47589 Table A-1 (66 sites + Tinian North Field)
              DoD Base Structure Report FY2024 (PRV quartile / facility data)

Run: D:/miniconda3/envs/pmtec-xpu/python.exe test_p9.py
"""

import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.stdout.reconfigure(encoding="utf-8")

GEOJSON_V2 = os.path.join(PROJECT_ROOT, "data", "bases_v2.geojson")

PASS, FAIL = 0, 0


def test(name, condition, detail=""):
    global PASS, FAIL
    tag = "PASS" if condition else "FAIL"
    print(f"  [{tag}] {name}" + (f" | {detail}" if detail else ""))
    PASS += int(bool(condition))
    FAIL += int(not condition)


# ============================================================
# 1) GeoJSON 数据完整性
# ============================================================
print("\n[1/4] bases_v2.geojson 数据完整性...")

with open(GEOJSON_V2, encoding="utf-8") as f:
    gj = json.load(f)
feats = gj["features"]
props = [ft["properties"] for ft in feats]

test("实体数 = 67 (CRS 66 + Tinian)", len(feats) == 67, f"(实际 {len(feats)})")
test("id 唯一", len({p["id"] for p in props}) == 67)
test("crs_no 字段存在且可溯源", sum(1 for p in props if p.get("crs_no")) >= 60,
     f"(有 crs_no 的实体 {sum(1 for p in props if p.get('crs_no'))})")
test("fy24_prv_quartile 字段存在",
      sum(1 for p in props if p.get("fy24_prv_quartile")) > 0)
test("access_uncertainty 字段存在（P10 接口预留）",
      sum(1 for p in props if p.get("access_uncertainty") is not None) > 0)

tiers = {}
for p in props:
    tiers[p.get("tier", 0)] = tiers.get(p.get("tier", 0), 0) + 1
test("四级 Tier 分层齐全", all(t in tiers for t in (1, 2, 3, 4)), f"{tiers}")

# ============================================================
# 2) PMTEC 引擎冒烟启动（67 实体 + ASDA 闭环）
# ============================================================
print("\n[2/4] PMTECEngine 冒烟启动（67 实体）...")
from services.grpc_server import PMTECEngine  # noqa: E402

engine = PMTECEngine()
n = engine.load_bases(GEOJSON_V2)
test("引擎载入站点数 = 67", n == 67, f"(实际 {n})")

engine.setup_scenario("PMTEC-Pacific-P9")
n_sensors = len(engine._sensors)
test("每站点 Live 层传感器已部署", n_sensors >= n, f"(传感器 {n_sensors})")

cycles_ok = True
try:
    for _ in range(8):  # 2 轮完整 Act->Sense->Decide->Adapt 闭环
        engine._execute_asda_cycle()
except Exception as e:
    cycles_ok = False
    print(f"    异常: {e}")
test("ASDA 闭环 2 轮无异常", cycles_ok,
     f"(cycle_count={getattr(engine, 'asda_cycle_count', '?')})")

# ============================================================
# 3) RL 环境前向兼容（182 维观测不变）
# ============================================================
print("\n[3/4] PMTECEnv 前向兼容（新数据 -> 既有 182 维观测空间）...")
from deep_rl.pmtec_env import PMTECEnv, OBS_DIM  # noqa: E402

v2_bases = [
    {
        "id": p.get("id", p.get("name", "")),
        "name": p.get("name", ""),
        "lat": ft["geometry"]["coordinates"][1],
        "lon": ft["geometry"]["coordinates"][0],
        "is_hub": bool(p.get("ace_hub", False)),
    }
    for ft, p in ((ft, ft["properties"]) for ft in gj["features"])
]
tier_by_id = {p["id"]: p.get("tier", 2) for p in props}
tier_order = {1: 0, 2: 1, 3: 2, 4: 3}
v2_top22 = sorted(
    v2_bases, key=lambda b: (tier_order.get(tier_by_id.get(b["id"], 2), 2), b["id"])
)[:22]

import numpy as np  # noqa: E402

env = PMTECEnv(bases=v2_top22, duration=60, seed=42)
obs, info = env.reset(seed=42)
test("reset() 观测维度 = 182", obs.shape == (OBS_DIM,), f"(实际 {obs.shape})")
test("观测值无 NaN/Inf", bool(np.isfinite(obs).all()),
     f"(min={obs.min():.3f}, max={obs.max():.3f})")

steps_ok, total_reward = True, 0.0
try:
    for _ in range(5):
        obs, r, term, trunc, info = env.step(env.action_space.sample())
        total_reward += r
        if term or trunc:
            obs, info = env.reset()
except Exception as e:
    steps_ok = False
    print(f"    异常: {e}")
test("step() x5 无异常", steps_ok, f"(累计奖励 {total_reward:.2f})")

# ============================================================
# 4) 战斗网络图全量建图（67 实体不截断）
# ============================================================
print("\n[4/4] 战斗网络图 67 实体全量建图...")
env67 = PMTECEnv.__new__(PMTECEnv)  # 仅验证 _build_network 兼容性
env67._bases = v2_bases
env67._build_network()
test("网络图节点数 = 67", env67._graph.number_of_nodes() == 67,
     f"(节点 {env67._graph.number_of_nodes()}, 边 {env67._graph.number_of_edges()})")

# ============================================================
# 汇总
# ============================================================
print("\n" + "=" * 56)
print(f"P9 测试: {PASS} 通过 / {FAIL} 失败")
if FAIL:
    sys.exit(1)
print("P9 验收标准达成：权威数据库 67 实体 + 引擎冒烟启动 ✓")
