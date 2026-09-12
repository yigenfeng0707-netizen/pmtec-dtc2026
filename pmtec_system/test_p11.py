#!/usr/bin/env python3
"""
P11 Test Suite: INDOPACOM Command & Control Organization Modeling

Validates:
  1. CommandChain: base assignment to 5 service components + 3 subordinate
     joint commands (spot checks against CRS IF12175 structure)
  2. Chain of command resolution + event reporting + cross-service coordination
     (hop-by-hop routing via lowest common ancestor)
  3. Branch normalization (GeoJSON branch strings -> standard branch codes)
  4. RBAC branch-scoped access (e.g. PACAF-Operator only controls USAF assets)
  5. Auth branch claim (backward compatible, invalid branch rejected)

Run: D:/miniconda3/envs/pmtec-xpu/python.exe test_p11.py
"""

import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.stdout.reconfigure(encoding="utf-8")

GEOJSON = os.path.join(PROJECT_ROOT, "data", "bases_v2.geojson")

PASS, FAIL = 0, 0


def test(name, condition, detail=""):
    global PASS, FAIL
    tag = "PASS" if condition else "FAIL"
    print(f"  [{tag}] {name}" + (f" | {detail}" if detail else ""))
    PASS += int(bool(condition))
    FAIL += int(not condition)


# ============================================================
# 1) CommandChain 指挥链
# ============================================================
print("\n[1/3] CommandChain 指挥链建模...")
from models.c2_chain import CommandChain, normalize_branch

with open(GEOJSON, encoding="utf-8") as f:
    gj = json.load(f)
bases = [
    {
        "id": p["id"],
        "name": p.get("name", ""),
        "country": p.get("country", ""),
        "branch": p.get("branch", ""),
        "lat": ft["geometry"]["coordinates"][1],
        "lon": ft["geometry"]["coordinates"][0],
    }
    for ft, p in ((ft, ft["properties"]) for ft in gj["features"])
]

c2 = CommandChain()
n = c2.assign_bases(bases)
test("全部 67 基地分配到指挥节点", n == len(bases), f"({n}/{len(bases)})")
test("指挥节点含 5 军种组成 + 3 下属联合",
     all(k in c2.nodes for k in
         ("USARPAC", "PACFLT", "MARFORPAC", "PACAF", "USSFPAC",
          "USFJ", "USFK", "SOCPAC")),
     f"nodes={sorted(c2.nodes.keys())}")

# 军种归属抽查（CRS 架构逐条对应）
spot_checks = [
    ("JP-YOKOTA", "USFJ"),
    ("KR-HUMPHREYS", "USFK"),
    ("HI-SHAFTER", "USARPAC"),
    ("CA-VANDENBERG", "USSFPAC"),
    ("AU-DARWIN", "MARFORPAC"),
    ("SG-NRCS", "PACFLT"),
    ("HI-PHICKAM", "PACFLT"),
]
for bid, expect in spot_checks:
    got = c2.command_of(bid)
    test(f"{bid} -> {expect}", got == expect, f"(实际 {got})")

# 指挥链解析
chain_kadena = c2.chain_of_command("JP-KADENA")
test("Kadena 指挥链终止于 INDOPACOM",
     chain_kadena and chain_kadena[-1] == "INDOPACOM", f"{chain_kadena}")

# 事件上报 + 跨军种协同
msg = c2.report_event("JP-KADENA", "threat_detected", {"x": 1}, sim_time=10.0)
test("上报沿指挥链逐级到达 INDOPACOM",
     msg.hops and msg.hops[-1]["node"] == "INDOPACOM",
     f"hops={[(h['node'], h['action']) for h in msg.hops]}")
test("上报总时延 > 0", msg.total_latency_s > 0, f"{msg.total_latency_s}s")

msgs = c2.cross_service_coordination(
    "HI-SHAFTER", "JP-KADENA", "air_defense_tasking", {"track": "T1"}, sim_time=10.0
)
report, order = msgs
test("跨军种协同含上报+命令两条消息", report is not None and order is not None)
test("命令最终下达至目标基地", order.hops[-1]["node"] == "JP-KADENA",
     f"hops={[(h['node'], h['action']) for h in order.hops]}")
test("协同消息审计留痕", len(c2.messages) >= 2)

# branch 归一化
test("normalize_branch('USN/USAF')", normalize_branch("USN/USAF") == ["navy", "usaf"])
test("normalize_branch('US Army')", normalize_branch("US Army") == ["army"])
test("normalize_branch('PAF/US (EDCA)') 为空", normalize_branch("PAF/US (EDCA)") == [])
test("normalize_branch('RAAF/USMC') 仅保留美军军种", normalize_branch("RAAF/USMC") == ["usmc"])

# ============================================================
# 2) RBAC 军种扩展
# ============================================================
print("\n[2/3] RBAC 军种属性扩展...")
from security.rbac import RBACManager, Role, normalize_branch_token

rbac = RBACManager()
test("OPERATOR(usaf) 可访问 usaf 资产",
     rbac.check_asset_access(Role.OPERATOR, "usaf", ["usaf"]) is True)
test("OPERATOR(usaf) 不可访问 army 资产",
     rbac.check_asset_access(Role.OPERATOR, "usaf", ["army"]) is False)
test("OPERATOR(usaf) 多军种资产含 usaf 可访问",
     rbac.check_asset_access(Role.OPERATOR, "usaf", ["navy", "usaf"]) is True)
test("无军种属性 OPERATOR 兼容全部资产（后向兼容）",
     rbac.check_asset_access(Role.OPERATOR, "", ["army"]) is True)
test("COMMANDER 跨军种全权",
     rbac.check_asset_access(Role.COMMANDER, "usaf", ["army"]) is True)
test("OPERATOR(usaf) 对无军种资产可访问",
     rbac.check_asset_access(Role.OPERATOR, "usaf", []) is True)
test("normalize_branch_token('USAF')", normalize_branch_token("USAF") == "usaf")
test("normalize_branch_token('bogus') 拒绝", normalize_branch_token("bogus") == "")
label = rbac.scoped_role_label(Role.OPERATOR, "usaf")
test("军种限定角色标签生成", bool(label), f"{label}")

# ============================================================
# 3) Auth branch claim
# ============================================================
print("\n[3/3] JWT branch claim...")
from security.auth import AuthError, AuthManager

auth = AuthManager(secret="p11_test_secret_padding_to_32_bytes_xx", expiration_hours=1)
t = auth.issue_token("u1", "operator", branch="usaf")
payload = auth.verify_token(t.token)
test("token 携带 branch claim", payload.get("branch") == "usaf")

t2 = auth.issue_token("u2", "operator")
test("无 branch token 后向兼容", "branch" not in auth.verify_token(t2.token))

try:
    auth.authenticate("u3", "pw", "operator", branch="starfleet")
    test("非法军种签发被拒绝", False)
except AuthError as e:
    test("非法军种签发被拒绝", True, str(e))

# ============================================================
# 汇总
# ============================================================
print("\n" + "=" * 56)
print(f"P11 测试: {PASS} 通过 / {FAIL} 失败")
if FAIL:
    sys.exit(1)
print("P11 验收标准达成：指挥链 + RBAC 军种扩展 + Auth 联动 ✓")
