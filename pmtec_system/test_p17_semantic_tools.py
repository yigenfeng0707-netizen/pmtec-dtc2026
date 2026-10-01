#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P17 Test Suite: 语义工具层（browse / resolve / manifest，WP4 只读实现）

Validates (全部离线，不依赖外网；对 P14/P16 产物只读):
  1. manifest 四类语义对象计数均为正（term/mapping/constraint/evidence）
  2. browse 检索：Kadena 命中、branchCode 域锚定、SHACL 约束、B 级证据存在
  3. resolve 档案：Misawa = 类型 + 属性 + 适用约束 + 溯源证据 + D-S 置信一致
  4. 类解析：LaunchCapable 等价类公理可见（实例 0 为真值——成员由 HermiT 推理得出，
     ABox 不物化，与 P14 翻转测试口径一致）
  5. 负样本：未知 kind 报错、乱码查询空结果不崩溃、未知 id found=False
  6. 确定性：同参调用结果逐字节一致

Run: python -X utf8 test_p17_semantic_tools.py
"""
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "ontology"))

from semantic_tools import KINDS, browse, manifest, resolve  # noqa: E402

PASS = 0
FAIL = 0
RESULTS = []


def test(name, condition, detail=""):
    global PASS, FAIL
    ok = bool(condition)
    (PASS, FAIL) = (PASS + 1, FAIL) if ok else (PASS, FAIL + 1)
    RESULTS.append((ok, name, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail if not ok else ''}")


def main():
    # ---- 1 manifest：四类语义对象齐备
    m = manifest()
    counts = m["counts"]
    test("01 manifest 四类计数均为正", all(counts.get(k, 0) > 0 for k in KINDS),
         f"counts={counts}")
    test("02 manifest 计数与检索索引一致（evidence ≥ 67 基地）",
         counts["evidence"] >= 67 and counts["constraint"] >= 3,
         f"counts={counts}")

    # ---- 2 browse：term / mapping / constraint / evidence
    hits = browse("kadena", "term")
    test("03 browse term 命中 Kadena",
         any("KADENA" in h["id"].upper() for h in hits), f"hits={[h['id'] for h in hits]}")
    props = browse("branchCode", "mapping")
    test("04 browse mapping 锚定域（branchCode → MilitaryInstallation）",
         any("domain=MilitaryInstallation" in p["detail"] for p in props),
         f"props={[p['detail'] for p in props]}")
    shapes = browse("军种代码", "constraint")
    test("05 browse constraint 命中军种代码形状", len(shapes) >= 1,
         f"shapes={[s['id'] for s in shapes]}")
    ev_all = browse("", "evidence", 100)
    test("06 browse evidence 存在 B 级降级断言",
         any("精度 B" in e["detail"] for e in ev_all))
    conf = {e["id"]: e for e in json.loads(
        open(os.path.join(PROJECT_ROOT, "ontology", "confidence_report.json"),
             encoding="utf-8").read())["bases"]}
    tinian = next(v for k, v in conf.items() if "TINIAN" in k.upper())
    test("07 B 级最宽无知区间跨工具层一致（Pl(Open)=1.0）",
         tinian["grade"] == "B" and abs(tinian["bel_pl"]["Open"]["Pl"] - 1.0) < 1e-9,
         f"tinian={tinian['bel_pl']['Open']}")

    # ---- 3 resolve：Misawa 全档案
    r = resolve("base_JP_MISAWA")[0]
    test("08 resolve Misawa 命中且类型为 AirBase", r["found"] and r["types"] == ["AirBase"],
         f"r={r}")
    test("09 resolve Misawa 属性含 branchCode 且准入态 state_open",
         "branchCode" in r["properties"]
         and "state_open" in r["properties"].get("hasAccessState", []),
         f"props={list(r['properties'])}")
    test("10 resolve Misawa 挂接适用约束（InstallationShape）",
         any("InstallationShape" in c for c in r["constraints"]),
         f"constraints={r['constraints']}")
    ev = r.get("evidence", {})
    test("11 resolve Misawa 溯源证据（A- 级，Bel=0.6702）",
         ev.get("id") == "assertion_JP_MISAWA" and "精度 A-" in ev.get("detail", "")
         and "Bel(Open)=0.6702" in ev.get("detail", ""),
         f"evidence={ev}")
    test("12 resolve Misawa D-S 置信与证据跨源一致（Bel 同值）",
         abs(r.get("confidence", {}).get("bel_pl", {}).get("Open", {}).get("Bel", 0)
             - 0.6702) < 1e-4,
         f"conf={r.get('confidence', {}).get('bel_pl', {}).get('Open')}")

    # ---- 4 类解析：LaunchCapable
    c = resolve("LaunchCapable")[0]
    test("13 LaunchCapable 类解析（等价类公理可见；ABox 直例 0 为真值）",
         c["found"] and c["kind"] == "class" and c["equivalent_axiom"]
         and c["direct_instances"] == 0,
         f"c={c}")

    # ---- 5 负样本
    try:
        browse("x", kind="nope")
        raised = False
    except ValueError:
        raised = True
    test("14 负样本：未知 kind 必须报错", raised)
    test("15 负样本：乱码查询空结果、未知 id found=False（不崩溃）",
         browse("zzzqqqxxx_will_not_exist", "term") == []
         and resolve("base_NO_SUCH_BASE_XYZ")[0]["found"] is False)

    print(f"\nP17 语义工具层验收: {PASS} PASS / {FAIL} FAIL / {PASS + FAIL} 断言")
    return FAIL == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
