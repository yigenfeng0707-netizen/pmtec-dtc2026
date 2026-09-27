# -*- coding: utf-8 -*-
"""P16-D3: DoDAF 追溯链 SHACL 校验 + 跨本体锚点核验

- pySHACL（advanced + rdfs 推理）：CAP←OA←EX→ENT / Role→SYS / SER→CAP / PV→SYS
  每一跳 minCount 1 + sh:class，链路任何一环悬空即违规
- 跨本体核验：dd:InformationEntity 锚定的 tc# 类必须真实存在于目标特性本体
- 基线本体一致性由既有 reason_check.py（HermiT）守护，覆盖层为个体投影层，
  不新增 OWL 公理，故判定程序为 SHACL 而非再跑一次描述逻辑推理。
产出 dodaf_validation_report.json。
"""
import json
import sys
from pathlib import Path

import rdflib
from pyshacl import validate
from rdflib import RDF, Namespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dodaf_build  # noqa: E402

OVERLAY = dodaf_build.OVERLAY_TTL
SHAPES = Path(__file__).resolve().parent / "dodaf_shapes.ttl"
REPORT_JSON = Path(__file__).resolve().parent / "dodaf_validation_report.json"
PUBLIC_ID = "http://pmtec.example.org/dodaf_overlay.ttl"
DD = Namespace("http://pmtec.example.org/dodaf#")
TC = Namespace("http://pmtec.example.org/tc#")


def shacl_check():
    data = rdflib.Graph()
    data.parse(str(OVERLAY), format="turtle", publicID=PUBLIC_ID)
    shapes = rdflib.Graph()
    shapes.parse(str(SHAPES), format="turtle")
    conforms, results_graph, _ = validate(data, shacl_graph=shapes,
                                          advanced=True, inference="rdfs")
    SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")
    violations = []
    for node in results_graph.subjects(RDF.type, SH.ValidationResult):
        violations.append({
            "focusNode": str(results_graph.value(node, SH.focusNode) or ""),
            "path": str(results_graph.value(node, SH.resultPath) or ""),
            "message": str(results_graph.value(node, SH.resultMessage) or ""),
        })
    return {"conforms": bool(conforms), "violations": violations}, data


def cross_ontology_check(data):
    """dd 实体锚定的 tc# 类必须在目标特性本体中真实存在"""
    tcg = rdflib.Graph()
    tcg.parse(str(dodaf_build.TC_ONT), format="xml")
    tc_classes = {s for s in tcg.subjects(RDF.type, rdflib.OWL.Class)}
    broken = []
    for ent, _, anchor in data.triples((None, DD.tracesTo, None)):
        if str(ent).startswith(str(DD)) and str(anchor).startswith(str(TC)):
            cls = str(anchor).split("#")[-1]
            if anchor not in tc_classes:
                broken.append({"entity": str(ent).split("#")[-1], "missing_tc_class": cls})
    anchored = sorted({str(a).split("#")[-1] for e, _, a in
                       data.triples((None, DD.tracesTo, None))
                       if str(e).startswith(str(DD)) and str(a).startswith(str(TC))})
    return {"broken_anchors": broken, "anchored_tc_classes": anchored}


def run_all():
    shacl, data = shacl_check()
    cross = cross_ontology_check(data)
    counts = {}
    for cls in ["Capability", "OperationalActivity", "InformationExchange",
                "InformationEntity", "Role", "ServiceContract", "SystemNode",
                "ProjectActivity", "StandardBaseline"]:
        counts[cls] = len(set(data.subjects(RDF.type, DD[cls])))
    report = {"source_artifact": OVERLAY.name,
              "class_counts": counts,
              "shacl": {"conforms": shacl["conforms"],
                        "violation_count": len(shacl["violations"]),
                        "violations": shacl["violations"][:20]},
              "cross_ontology": cross}
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(json.dumps({"class_counts": counts,
                      "conforms": shacl["conforms"],
                      "violations": len(shacl["violations"]),
                      "broken_anchors": len(cross["broken_anchors"])},
                     ensure_ascii=False))
    return report


if __name__ == "__main__":
    r = run_all()
    sys.exit(0 if r["shacl"]["conforms"] and not r["cross_ontology"]["broken_anchors"] else 1)
