#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P16 Test Suite: DoDAF 2.02 视点覆盖层 + SHACL 追溯链校验 + 视点文档生成

全部离线，不依赖外网。断言分四组：
  A. 结构：九类元个体数量必须与真实工件（SPEAR/UJTL/源码）机器重算一致
  B. 追溯链：EX→OA→CAP、EX→ENT→tc#、Role→SYS、SER→CAP/SYS、PV→SYS 无悬空
  C. 校验器：SHACL 正样本全绿 + 负样本（删边/映射表缺项）必须报警
  D. 文档生成物：八视点齐全、OV-3 行数=实测事件类型数、数字与工件一致、
     合规红线（不得出现"军工正式交付"誊写措辞）

Run: python -X utf8 test_p16_dodaf.py
"""
import os
import sys

import rdflib
from rdflib import RDF, Namespace

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ONTOLOGY_DIR = os.path.join(PROJECT_ROOT, "ontology")
sys.path.insert(0, ONTOLOGY_DIR)

import dodaf_build  # noqa: E402

DD = Namespace("http://pmtec.example.org/dodaf#")
TC = Namespace("http://pmtec.example.org/tc#")
OVERLAY = dodaf_build.OVERLAY_TTL
DOC_MD = os.path.join(dodaf_build.BASE, "docs", "PMTEC-DoDAF视点架构说明.md")

PASS = 0
FAIL = 0


def test(name, condition, detail=""):
    global PASS, FAIL
    ok = bool(condition)
    (PASS, FAIL) = (PASS + 1, FAIL) if ok else (PASS, FAIL + 1)
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail if not ok else ''}")


def main():
    # ---------- 组 A: 结构 ⇄ 真实工件机器重算 ----------
    test("01 覆盖层文件存在且可解析", OVERLAY.exists() and OVERLAY.stat().st_size > 5000)
    g = rdflib.Graph()
    g.parse(str(OVERLAY), format="turtle")
    test("02 三元组数量级合理(>400)", len(g) > 400, f"got {len(g)}")

    types, _ = dodaf_build.load_spear()
    segments = dodaf_build.load_segments()
    apps = dodaf_build.load_apps()
    services = dodaf_build.load_grpc_services()

    def n(cls):
        return len(set(g.subjects(RDF.type, DD[cls])))

    test("03 Capability 数 = UJTL 段实测数", n("Capability") == len(segments) == 33,
         f"overlay={n('Capability')} csv={len(segments)}")
    test("04 InformationExchange 数 = SPEAR 实测事件类型数(22)",
         n("InformationExchange") == len(types) == 22)
    obs_sum = sum(int(o) for s in g.subjects(RDF.type, DD.InformationExchange)
                  for o in g.objects(s, DD.observedCount))
    test("05 交换观测计数总和 = 事件总数 1506（零虚构对账）",
         obs_sum == sum(types.values()) == 1506, f"got {obs_sum}")
    test("06 Role 数 = 事件源分组实测数(10)", n("Role") == 10)
    test("07 ServiceContract 数 = 应用商店实测数(6)", n("ServiceContract") == len(apps) == 6)
    test("08 SystemNode 含全部 gRPC Servicer(4)",
         all(len(set(g.objects(DD["sys-" + s], rdflib.RDFS.label))) == 1
             and (DD["sys-" + s], None, None) in g for s in services)
         and len(services) == 4, f"services={services}")
    test("09 每个服务契约含版本号（源码 ast 解析实证）",
         all(list(g.objects(s, DD.versionInfo)) for s in g.subjects(RDF.type, DD.ServiceContract)))

    # ---------- 组 B: 追溯链无悬空（图面直查，独立于 SHACL） ----------
    exs = list(g.subjects(RDF.type, DD.InformationExchange))
    test("10 每条交换恰追溯到 1 个已声明作战活动",
         all(len(oa) == 1 and (oa[0], RDF.type, DD.OperationalActivity) in g
             for s in exs for oa in [tuple(g.objects(s, DD.tracesTo))]))
    oas = list(g.subjects(RDF.type, DD.OperationalActivity))
    test("11 每个作战活动追溯到已声明能力",
         all(list(g.objects(o, DD.tracesTo))
             and all((c, RDF.type, DD.Capability) in g
                     for c in g.objects(o, DD.tracesTo)) for o in oas))
    test("12 每条交换锚定已声明信息实体且有产生角色",
         all(list(g.objects(e, DD.aboutEntity))
             and all((e, DD.aboutEntity, x) in g
                     and (x, RDF.type, DD.InformationEntity) in g
                     for x in g.objects(e, DD.aboutEntity))
             and list(g.objects(e, DD.producedBy)) for e in exs))
    anchors = [a for s in g.subjects(RDF.type, DD.InformationEntity)
               for a in g.objects(s, DD.tracesTo)]
    tcg = rdflib.Graph()
    tcg.parse(str(dodaf_build.TC_ONT), format="xml")
    tc_classes = set(tcg.subjects(RDF.type, rdflib.OWL.Class))
    test("13 信息实体锚定的 tc# 类全部真实存在（跨本体 6/6）",
         len(anchors) == 6 and all(a in tc_classes for a in anchors),
         f"anchors={len(anchors)}")
    test("14 每个角色配置到真实存在的系统节点",
         all(list(g.objects(r, DD.allocatedTo))
             and all((x, RDF.type, DD.SystemNode) in g
                     for x in g.objects(r, DD.allocatedTo))
             for r in g.subjects(RDF.type, DD.Role)))
    test("15 每个服务契约 realize 已声明能力且由系统提供",
         all(list(g.objects(s, DD.realizes))
             and all((s, DD.realizes, c) in g and (c, RDF.type, DD.Capability) in g
                     for c in g.objects(s, DD.realizes))
             and list(g.objects(s, DD.providedBy))
             for s in g.subjects(RDF.type, DD.ServiceContract)))
    test("16 每个系统节点支撑至少一个能力（SV 无悬空）",
         all(list(g.objects(x, DD.realizes))
             and all((c, RDF.type, DD.Capability) in g
                     for c in g.objects(x, DD.realizes))
             for x in g.subjects(RDF.type, DD.SystemNode)))
    test("17 建设项目 verifies 真实系统节点（PV 断链防护）",
         all(list(g.objects(p, DD.verifies))
             and all((x, RDF.type, DD.SystemNode) in g
                     for x in g.objects(p, DD.verifies))
             for p in g.subjects(RDF.type, DD.ProjectActivity)))

    # ---------- 组 C: 校验器正/负样本 ----------
    import dodaf_check
    report = dodaf_check.run_all()
    test("18 SHACL 正样本全绿（conforms 且零违规零断锚）",
         report["shacl"]["conforms"] and not report["shacl"]["violations"]
         and not report["cross_ontology"]["broken_anchors"])

    from pyshacl import validate
    shapes = rdflib.Graph()
    shapes.parse(str(os.path.join(ONTOLOGY_DIR, "dodaf_shapes.ttl")), format="turtle")

    def conforms_of(graph):
        ok, _, _ = validate(graph, shacl_graph=shapes, advanced=True, inference="rdfs")
        return ok

    g1 = rdflib.Graph()
    g1.parse(str(OVERLAY), format="turtle")
    g1.remove((DD["ex_detect"], DD.tracesTo, None))
    test("19 负样本：删交换→活动边必须被追溯链校验拦截", not conforms_of(g1))

    g2 = rdflib.Graph()
    g2.parse(str(OVERLAY), format="turtle")
    g2.remove((DD["role_c2_chain"], DD.allocatedTo, None))
    test("20 负样本：删角色→系统配置边必须报警", not conforms_of(g2))

    g3 = rdflib.Graph()
    g3.parse(str(OVERLAY), format="turtle")
    g3.set((DD["ex_detect"], DD.observedCount, rdflib.Literal(0)))
    test("21 负样本：观测计数归零违反 minInclusive 1（禁虚构/禁清空）",
         not conforms_of(g3))

    saved = dict(dodaf_build.EX_MAPPING)
    try:
        dodaf_build.EX_MAPPING.pop("detect")
        broken = False
        try:
            dodaf_build.build_graph()
        except RuntimeError:
            broken = True
        test("22 映射表与实测事件类型双向完整性守卫（缺项即拒绝构建）", broken)
    finally:
        dodaf_build.EX_MAPPING.clear()
        dodabf = saved
        dodaf_build.EX_MAPPING.update(dodabf)

    # ---------- 组 D: 文档生成物 ----------
    import build_dodaf_views
    build_dodaf_views.main()
    test("23 视点文档已生成", os.path.exists(DOC_MD) and os.path.getsize(DOC_MD) > 6000)
    md = open(DOC_MD, encoding="utf-8").read()
    views = ["AV 全局视点", "CV 能力视点", "OV-2", "OV-3", "DIV", "SvcV", "SV", "StdV", "PV"]
    test("24 八视点章节齐全", all(v in md for v in views),
         f"missing={[v for v in views if v not in md]}")
    ov3_rows = [ln for ln in md.splitlines() if ln.startswith("| `") and "| 591 |" in ln]
    test("25 OV-3 矩阵含 detect=591 实测行（数字与工件一致）", len(ov3_rows) == 1)
    test("26 合规红线：文档不含参考文档誊写措辞",
         "军工正式交付" not in md and "陆军全域机动" not in md)

    print(f"\n=== P16 DoDAF: {PASS} passed, {FAIL} failed ===")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
