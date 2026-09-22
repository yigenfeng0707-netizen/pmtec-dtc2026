#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P14 Test Suite: 目标特性本体（TO 五元组）+ HermiT/SHACL 校验 + D-S 置信度 + 杀伤网查询

Validates (全部离线，不依赖外网):
  1. TBox/ABox 结构：67 实体、子类互斥、属性完备
  2. HermiT 一致性 + LaunchCapable/AccessDeniedSite 推理 + 状态翻转测试
  3. SHACL 正样本全绿 + 负样本（删属性/越界/缺状态）必须报警
  4. D-S 证据理论：mass 归一、Dempster 恒等元、Bel/Pl 区间、Tinian B 级宽区间
  5. PROV-O 溯源链完整；Brier 分数基准值
  6. SPARQL 杀伤网：PAE 排序、主权基地效应器匹配、COA 替代方案

Run: python -X utf8 test_p14_ontology.py
"""
import copy
import os
import sys

import rdflib
from rdflib.namespace import RDF, RDFS

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "ontology"))

ONTOLOGY_DIR = os.path.join(PROJECT_ROOT, "ontology")
OWL_FILE = os.path.join(ONTOLOGY_DIR, "target_characteristics.owl")

PASS = 0
FAIL = 0
RESULTS = []


def test(name, condition, detail=""):
    global PASS, FAIL
    ok = bool(condition)
    (PASS, FAIL) = (PASS + 1, FAIL) if ok else (PASS, FAIL + 1)
    RESULTS.append((ok, name, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail if not ok else ''}")


SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")
PROV = rdflib.Namespace("http://www.w3.org/ns/prov#")
TC = rdflib.Namespace("http://pmtec.example.org/tc#")


def main():
    # ---------- 组 1: 结构（rdflib 数据面） ----------
    test("01 本体文件存在且非空", os.path.getsize(OWL_FILE) > 10000,
         f"size={os.path.getsize(OWL_FILE)}")
    g = rdflib.Graph()
    g.parse(OWL_FILE, format="xml")

    inst_types = {}
    for sub in ("AirBase", "NavalBase", "LandBase", "SupportSite"):
        inst_types[sub] = {s for s in g.subjects(RDF.type, TC[sub])}
    n_base = sum(len(v) for v in inst_types.values())
    test("02 ABox 67 基地实体", n_base == 67, f"got {n_base}")

    # 互斥：任一实体不得同时属于两个基地子类（AllDisjoint 落盘验证）
    overlap = set()
    keys = list(inst_types)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            overlap |= inst_types[keys[i]] & inst_types[keys[j]]
    test("03 基地四子类互斥（AllDisjoint）", not overlap, f"overlap={overlap}")

    no_branch = [b for b in set().union(*inst_types.values())
                 if not list(g.objects(b, TC.branchCode))]
    test("04 全部基地含 branchCode", not no_branch, f"missing={no_branch[:3]}")
    no_state = [b for b in set().union(*inst_types.values())
                if not list(g.objects(b, TC.hasAccessState))]
    test("05 全部基地含 hasAccessState 状态断言", not no_state,
         f"missing={no_state[:3]}")

    # ---------- 组 2: HermiT 推理 + 翻转 ----------
    from reason_check import load_ontology
    onto = load_ontology()
    hermit = None
    try:
        from reason_check import hermit_consistency_check
        hermit = hermit_consistency_check(onto)
    except Exception as e:  # noqa: BLE001
        test("06 HermiT 一致性检查", False, str(e))
    test("06 HermiT 公理集一致", hermit and hermit["consistent"])
    test("07 基线 c0：67 基地全部推入 LaunchCapable",
         hermit and hermit["launch_capable_count"] == 67,
         f"got {hermit and hermit['launch_capable_count']}")
    test("08 基线 c0：AccessDeniedSite 为空",
         hermit and hermit["access_denied_count"] == 0)

    # 翻转测试在子进程全新 World 中进行：owlready2 会把 HermiT 分类结果
    # 回写为显式公理，同进程二次同步与翻转断言表面冲突
    import json as _json
    import subprocess
    flip_script = (
        "import sys,json;sys.path.insert(0,r'{d}');"
        "sys.path.insert(0,r'{o}');"
        "from owlready2 import sync_reasoner_hermit;"
        "from reason_check import load_ontology,get_class;"
        "onto=load_ontology();inds={{i.name:i for i in onto.individuals()}};"
        "b=inds['base_JP_MISAWA'];b.hasAccessState=[inds['state_denied']];"
        "sync_reasoner_hermit();"
        "lc={{x.name for x in get_class(onto,'LaunchCapable').instances()}};"
        "ad={{x.name for x in get_class(onto,'AccessDeniedSite').instances()}};"
        "print('JSON',json.dumps({{'lc':len(lc),'ad':sorted(ad),"
        "'misawa_in_lc':'base_JP_MISAWA' in lc}}))"
    ).format(d=ONTOLOGY_DIR, o=os.path.join(PROJECT_ROOT, "ontology"))
    proc = subprocess.run([sys.executable, "-X", "utf8", "-c", flip_script],
                          capture_output=True, text=True)
    flip = {}
    for line in proc.stdout.splitlines():
        if line.startswith("JSON "):
            flip = _json.loads(line[5:])
    test("09 翻转测试：Misawa 置 Denied 后退出 LaunchCapable",
         flip.get("misawa_in_lc") is False and flip.get("lc") == 66,
         f"flip={flip} stderr={proc.stderr[-200:]}")
    test("10 翻转测试：Misawa 被推理归入 AccessDeniedSite（唯一成员）",
         flip.get("ad") == ["base_JP_MISAWA"])

    # ---------- 组 3: SHACL 正/负样本 ----------
    from pyshacl import validate
    shapes = rdflib.Graph()
    shapes.parse(os.path.join(ONTOLOGY_DIR, "shapes.ttl"), format="turtle")
    data = rdflib.Graph()
    data.parse(OWL_FILE, format="xml")
    conf, _, _ = validate(data, shacl_graph=shapes, advanced=True)
    test("11 SHACL 正样本 conforms=True", conf)

    bad = rdflib.Graph()
    bad.parse(OWL_FILE, format="xml")
    misawa = TC["base_JP_MISAWA"]
    bad.remove((misawa, TC.branchCode, None))
    for s, p, o in list(bad.triples((misawa, TC.latitude, None))):
        bad.remove((s, p, o))
        bad.add((s, p, rdflib.Literal(999.0)))
    everett = TC["base_WA_EVERETT"]
    bad.remove((everett, TC.hasAccessState, None))
    conf2, res2, _ = validate(bad, shacl_graph=shapes, advanced=True)
    msgs = [str(res2.value(n, SH.resultMessage)) for n in
            res2.subjects(RDF.type, SH.ValidationResult)]
    test("12 SHACL 负样本报警（删 branchCode/纬度越界/缺状态）",
         (not conf2) and len(msgs) >= 3, f"conforms={conf2} msgs={len(msgs)}")

    # ---------- 组 4: D-S 证据理论 ----------
    import confidence as cf
    m_ignorant = {frozenset(cf.THETA): 1.0}
    m_src = cf.PRECISION_MASS["A"]
    comb, k = cf.dempster_combine(m_src, m_ignorant)
    test("13 Dempster 合成与全无知证据=自身（K=0）",
         k == 0.0 and comb == m_src, f"K={k}")
    for grade_mass in (m_src, cf.PRECISION_MASS["A-"], cf.PRECISION_MASS["B"],
                       *cf.ACCESS_TYPE_MASS.values()):
        if abs(sum(grade_mass.values()) - 1.0) > 1e-9:
            test("14 mass 函数全帧归一", False, str(grade_mass))
            break
    else:
        test("14 mass 函数全帧归一", True)

    report = cf.run_all()
    s = report["summary"]
    test("15 置信度报告 67 基地 + 精度分级 45/21/1",
         s["total"] == 67 and s["grade_distribution"] == {"A": 45, "A-": 21, "B": 1},
         str(s))
    tinian = next(r for r in report["bases"] if r["id"] == "CNMI-TINIAN")
    test("16 Tinian B 级最宽无知区间（Pl(Open)=1, Bel(Open)<0.7）",
         tinian["bel_pl"]["Open"]["Pl"] == 1.0 and tinian["bel_pl"]["Open"]["Bel"] < 0.7,
         str(tinian["bel_pl"]))
    test("17 Brier 分数基准值（完美=0 / 0.5vs1=0.25）",
         cf.brier_score([0, 1], [0, 1]) == 0.0 and cf.brier_score([0.5], [1]) == 0.25)

    # ---------- 组 5: PROV-O 溯源 ----------
    pg = rdflib.Graph()
    pg.parse(os.path.join(ONTOLOGY_DIR, "provenance.ttl"), format="turtle")
    assertions = set(pg.subjects(RDF.type, PROV.Entity)) - set(
        s for s in pg.subjects(RDF.type, PROV.Entity)
        if "urn:pmtec:source" in str(s))
    derived = {s for s, _, _ in pg.triples((None, PROV.wasDerivedFrom, None))}
    test("18 溯源链：每条断言均有证据源 wasDerivedFrom",
         len(assertions) >= 67 and assertions <= derived,
         f"assertions={len(assertions)} derived={len(derived & assertions)}")

    # ---------- 组 6: SPARQL 杀伤网 ----------
    import sparql_service as sp
    killnet = sp.run_all()
    pae = killnet["pae_priority_targets"]
    test("19 PAE 清单：Tier 非降序且首条为 Tier1 最长跑道",
         len(pae) == 10 and [x["tier"] for x in pae] == sorted(x["tier"] for x in pae)
         and pae[0]["tier"] == 1 and pae[0]["runway_m"] >= 3000, str(pae[:2]))
    eff = {x["base"] for x in killnet["match_effector_sovereign_fighters"]}
    test("20 效应器匹配命中主权基地战斗机联队（JBER/Eielson）",
         eff == {"base_AK_JBER", "base_AK_EIELSON"}, str(eff))
    coa = {c["fragile_node"]: c["alternatives"]
           for c in killnet["coa_single_runway_alternatives"]}
    test("21 COA：单跑道脆弱节点均有同国替代方案",
         coa and all(len(alts) >= 1 for alts in coa.values()),
         f"nodes={len(coa)}")

    # ---------- 汇总 ----------
    print(f"\nP14 验收: {PASS} PASS / {FAIL} FAIL / {PASS + FAIL} 断言")
    return FAIL == 0


if __name__ == "__main__":
    sys.path.insert(0, PROJECT_ROOT)
    sys.exit(0 if main() else 1)
