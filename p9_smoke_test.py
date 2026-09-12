#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P9 验收：PMTEC 引擎用新 GeoJSON 冒烟启动
- 将 indopacom_bases_v2.geojson（67 实体）载入 PMTECEngine
- setup_scenario → 运行若干 ASDA 周期 → 校验传感器/飞机/网络实体规模
- 校验 RL 环境（PMTECEnv）与新数据的前向兼容（子集 22 实体，182 维观测不变）
为 P12 全量引擎升级（67 实体 + 观测空间扩维）铺路。
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pmtec_system"))
sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GEOJSON_V2 = os.path.join(BASE_DIR, "indopacom_bases_v2.geojson")
DATA_V2 = os.path.join(BASE_DIR, "pmtec_system", "data", "bases_v2.geojson")

passed, failed = [], []


def check(name, cond, detail=""):
    (passed if cond else failed).append(f"{name} {detail}")
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {detail}")


# ------------------------------------------------------------------
# 0) 复制 v2 数据到 pmtec_system/data/（保留旧 bases.geojson 兼容）
# ------------------------------------------------------------------
with open(GEOJSON_V2, encoding="utf-8") as f:
    gj = json.load(f)
with open(DATA_V2, "w", encoding="utf-8") as f:
    json.dump(gj, f, ensure_ascii=False)
print(f"[0] v2 GeoJSON 已复制到 {DATA_V2}")

# ------------------------------------------------------------------
# 1) PMTEC 引擎：加载 67 实体 + 场景初始化 + ASDA 周期
# ------------------------------------------------------------------
print("\n[1] PMTECEngine 冒烟启动（67 实体）")
from services.grpc_server import PMTECEngine

engine = PMTECEngine()
n = engine.load_bases(GEOJSON_V2)
check("引擎载入站点数 = 67", n == 67, f"(实际 {n})")

engine.setup_scenario("PMTEC-Pacific-P9")
n_sensors = len(engine._sensors)
check("每站点 Live 层传感器已部署", n_sensors >= n, f"(传感器 {n_sensors})")

# 运行 8 个 ASDA 相位（2 轮完整 Act→Sense→Decide→Adapt 闭环）
cycles_ok = True
try:
    for _ in range(8):
        engine._execute_asda_cycle()
except Exception as e:
    cycles_ok = False
    print(f"    异常: {e}")
check("ASDA 闭环 2 轮完整相位无异常", cycles_ok,
      f"(cycle_count={engine.asda_cycle_count})")

stats = getattr(engine, "_missile_stats", {})
print(f"    导弹统计: {stats}")

# ------------------------------------------------------------------
# 2) RL 环境：新数据子集前向兼容（182 维观测不变）
# ------------------------------------------------------------------
print("\n[2] PMTECEnv 前向兼容（新数据 → 既有 182 维观测空间）")
from deep_rl.pmtec_env import PMTECEnv, OBS_DIM

v2_bases = [
    {
        "id": p.get("id", p.get("name", "")),
        "name": p.get("name", ""),
        "lat": feat["geometry"]["coordinates"][1],
        "lon": feat["geometry"]["coordinates"][0],
        "is_hub": bool(p.get("ace_hub", False)),
    }
    for feat in gj["features"]
    for p in [feat["properties"]]
]
# Tier 优先级排序取前 22（战略核心 → 主要作战），与现有 NUM_BASES=22 一致
tier_order = {1: 0, 2: 1, 3: 2, 4: 3}
v2_bases_sorted = sorted(
    v2_bases,
    key=lambda b: tier_order.get(
        next((f["properties"].get("tier", 2) for f in gj["features"]
              if f["properties"].get("id") == b["id"]), 2), b["id"]),
)[:22]

import numpy as np

env = PMTECEnv(bases=v2_bases_sorted, duration=60, seed=42)
obs, info = env.reset(seed=42)
check("reset() 观测维度 = 182", obs.shape == (OBS_DIM,), f"(实际 {obs.shape})")
check("观测值无 NaN/Inf", bool(np.isfinite(obs).all()),
      f"(min={obs.min():.3f}, max={obs.max():.3f}; 旧数据基线 -6.449~1.380)")

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
check("step() × 5 无异常", steps_ok, f"(累计奖励 {total_reward:.2f})")

# 网络拓扑：67 实体全量建图（不截断）
env67 = PMTECEnv.__new__(PMTECEnv)  # 仅验证 _build_network 对 67 实体的兼容性
env67._bases = v2_bases
import networkx  # noqa: F401
env67._build_network()
check("战斗网络图节点数 = 67", env67._graph.number_of_nodes() == 67,
      f"(实际 {env67._graph.number_of_nodes()}, 边 {env67._graph.number_of_edges()})")

# ------------------------------------------------------------------
# 3) 结果汇总
# ------------------------------------------------------------------
print(f"\n{'=' * 56}")
print(f"P9 冒烟测试: {len(passed)} 通过 / {len(failed)} 失败")
if failed:
    print("失败项:", failed)
    sys.exit(1)
print("P9 验收标准达成：PMTEC 引擎可用新 GeoJSON 冒烟启动 ✓")
