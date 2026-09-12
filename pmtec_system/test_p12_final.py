#!/usr/bin/env python3
"""
P12 Final Test Suite: P12.4 SPEAR Political Timeline + P12.5 Extended Threats
              + P12.6 Maven Service Contracts (REST completion)

P12-4: SPEAR interactive timeline upgrade
  - Swim-lane event rendering (THREATS / INTERCEPT / DAMAGE / POLITICAL)
  - Ally access mix band + escalation curve from political_access snapshots
  - Political state in the state panel

P12-5: Extended adversary strategies (RAND-style)
  - multi_axis_saturation: strikes spread across 10 distinct bases per wave
  - political_divergence: sustained strikes + heavy EW/cyber -> escalation

P12-6: Maven service contracts completed for the four DTB services
  - REST endpoints for war/battle/app/pnp + political/c2 (P10/P11)
  - /api/v1/maven/services contract overview

Run: D:/miniconda3/envs/pmtec-xpu/python.exe test_p12_final.py
"""

import json
import os
import sys
import tempfile
import urllib.request
from types import SimpleNamespace

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.stdout.reconfigure(encoding="utf-8")

PASS, FAIL = 0, 0


def test(name, condition, detail=""):
    global PASS, FAIL
    tag = "PASS" if condition else "FAIL"
    print(f"  [{tag}] {name}" + (f" | {detail}" if detail else ""))
    PASS += int(bool(condition))
    FAIL += int(not condition)


# ============================================================
# 1) P12-4: SPEAR 时间轴政治泳道
# ============================================================
print("\n[1/3] P12-4 SPEAR 交互式回放时间轴升级...")
from visualization.spear_timeline import SpearTimeline

fake_spear = SimpleNamespace(
    snapshots=[
        {
            "sim_seconds": c * 10,
            "asda_cycle": c,
            "asda_phase": "Decide",
            "total_entities": 10 + c,
            "active_tracks": 3,
            "network_vulnerability": 0.2,
            "political_access": {
                "ally_sites": 5,
                "escalation_level": 0.02 * c,
                "by_country": {
                    "Philippines": [
                        {"base_id": "PH-BASA", "country": "Philippines",
                         "state": "restricted" if c > 5 else "full", "prob": 0.5},
                        {"base_id": "PH-LALLO", "country": "Philippines",
                         "state": "full", "prob": 0.9},
                    ],
                    "Australia": [
                        {"base_id": "AU-DARWIN", "country": "Australia",
                         "state": "full", "prob": 0.95},
                    ],
                },
            },
        }
        for c in range(1, 21)
    ],
    events=[
        {"event_id": f"E{i}", "event_type": t, "timestamp": i, "source": "test",
         "description": "synthetic", "data": {"asda_cycle": i}}
        for i, t in enumerate(
            ["missile_launch", "intercept_decision", "political_grey_zone",
             "damage", "political_access_change"] * 6
        )
    ],
    metrics={"active_entities": [{"value": 10 + i} for i in range(20)]},
    generate_report=lambda: {"total_events": 30},
)

timeline = SpearTimeline()
timeline.load_from_spear(fake_spear)
html_path = os.path.join(tempfile.gettempdir(), "p12_spear_timeline_test.html")
timeline.generate_html(output_path=html_path)
with open(html_path, encoding="utf-8") as f:
    tl_html = f.read()

test("时间轴 HTML 生成", len(tl_html) > 10000, f"{len(tl_html):,} bytes")
test("四泳道渲染（含 POLITICAL 泳道）",
     all(x in tl_html for x in ("THREATS", "INTERCEPT", "DAMAGE", "POLITICAL")))
test("政治事件配色（灰色地带/准入变化）",
     "political_grey_zone" in tl_html and "political_access_change" in tl_html)
test("准入构成带 + 升级度曲线代码",
     "ALLY ACCESS MIX" in tl_html and "drawPoliticalChart" in tl_html)
test("政治态势图表画布存在", 'id="chart-political"' in tl_html)
test("状态面板含升级度/三态计数",
     "st-esc" in tl_html and "st-access" in tl_html)
os.remove(html_path)

# ============================================================
# 2) P12-5: 扩展对手策略
# ============================================================
print("\n[2/3] P12-5 多威胁扩展（RAND 风格策略库）...")
_scripts_dir = os.path.join(PROJECT_ROOT, "scripts")
sys.path.insert(0, _scripts_dir)
import monte_carlo_validation as mcv

names = [s.name for s in mcv.STRATEGIES]
test("策略库扩展至 6 项", len(names) == 6, f"{names}")
test("multi_axis_saturation 已注册", "multi_axis_saturation" in names)
test("political_divergence 已注册", "political_divergence" in names)

ma = next(s for s in mcv.STRATEGIES if s.name == "multi_axis_saturation")
test("multi_axis 分散打击参数 distinct_targets=10", ma.distinct_targets == 10)

# 多轴饱和行为：一波导弹覆盖 >= 8 个不同基地
env_ma = mcv.StrategyEnv(strategy=ma, duration=120, seed=42)
env_ma.reset(seed=42)
env_ma._missiles = []  # 清空初始波，仅测策略波
env_ma._spawn_threats()
targets = {m["target_base"] for m in env_ma._missiles}
test("多轴饱和单波覆盖 >= 8 个不同基地", len(targets) >= 8,
     f"(distinct={len(targets)}, missiles={len(env_ma._missiles)})")

pd = next(s for s in mcv.STRATEGIES if s.name == "political_divergence")
test("political_divergence 高 EW/网攻压制",
     pd.ew_prob >= 0.4 and pd.cyber_prob >= 0.4,
     f"(ew={pd.ew_prob}, cyber={pd.cyber_prob})")

# 新策略可跑完整 episode（前向兼容随机策略）
env_pd = mcv.StrategyEnv(strategy=pd, duration=120, seed=7)
obs, info = env_pd.reset(seed=7)
ok = True
try:
    for _ in range(5):
        obs, r, term, trunc, info = env_pd.step(0)
        if term or trunc:
            obs, info = env_pd.reset()
except Exception as e:
    ok = False
    print(f"    异常: {e}")
test("political_divergence 策略 episode 可运行", ok)

# ============================================================
# 3) P12-6: Maven 服务契约 REST 补全
# ============================================================
print("\n[3/3] P12-6 四大服务 Maven 接口补全...")
from dt_platform.rest_gateway import RestGateway
from services.grpc_server import PMTECEngine

GEOJSON_V2 = os.path.join(PROJECT_ROOT, "data", "bases_v2.geojson")
engine = PMTECEngine()
engine.load_bases(GEOJSON_V2)
engine.setup_scenario("PMTEC-P12-6")

gw = RestGateway(engine=engine, port=8099)
gw.start()


def http_get(path: str, timeout=8.0):
    url = f"http://localhost:8099{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return 0, {"error": str(e)}


test("网关启动", gw._server is not None)

status, svc = http_get("/api/v1/maven/services")
test("Maven 契约总览端点", status == 200 and len(svc.get("services", [])) == 5,
     f"({len(svc.get('services', []))} services)")
contract_modules = {s["module"] for s in svc.get("services", [])}
test("四大服务 + P10/P11 模块全覆盖",
     {"dtb-war-engine", "dtb-battle-network", "dtb-application-store",
      "dtb-plug-and-play"} <= contract_modules, f"{sorted(contract_modules)}")

status, ew = http_get("/api/v1/war/ew-threats")
test("war-engine: EW 威胁端点", status == 200 and "count" in ew)
status, cy = http_get("/api/v1/war/cyber-threats")
test("war-engine: 网攻威胁端点", status == 200 and "count" in cy)
status, lvc = http_get("/api/v1/network/lvc-status")
test("battle-network: LVC 状态端点", status == 200 and "lvc" in lvc)
status, dqn = http_get("/api/v1/app/dqn/status")
test("application-store: DQN 状态端点", status == 200 and "is_trained" in dqn or "active" in dqn)
status, pnp = http_get("/api/v1/pnp/health")
test("plug-and-play: 健康端点", status == 200 and pnp.get("healthy") is True)

status, pol = http_get("/api/v1/political/access")
test("P10: 政治准入态势端点", status == 200 and pol.get("ally_sites") == 36,
     f"(ally_sites={pol.get('ally_sites')})")
status, c2 = http_get("/api/v1/c2/chain")
test("P11: 指挥链态势端点", status == 200 and len(c2.get("nodes", [])) >= 8,
     f"(nodes={len(c2.get('nodes', []))})")

gw.stop()

# ============================================================
# 汇总
# ============================================================
print("\n" + "=" * 56)
print(f"P12 收官测试: {PASS} 通过 / {FAIL} 失败")
if FAIL:
    sys.exit(1)
print("P12.4 / P12.5 / P12.6 验收标准全部达成 ✓")
