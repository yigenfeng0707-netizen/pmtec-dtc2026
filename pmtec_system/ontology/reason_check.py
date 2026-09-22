# -*- coding: utf-8 -*-
"""T2: HermiT 一致性检查 + SHACL 形状约束校验

- HermiT（经 owlready2，Java 17）：公理矛盾/非法实例在建模期拦截，"本体是否正确"由算法裁决
- pySHACL：缺失值/越界值/孤立实体 → 机器可查校验报告（JSON + 控制台摘要）
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from owlready2 import get_ontology, sync_reasoner_hermit  # noqa: E402
from pyshacl import validate  # noqa: E402
import rdflib  # noqa: E402

from tc_ontology import ONTOLOGY_FILE, ONTOLOGY_DIR, ONTOLOGY_IRI  # noqa: E402

SHAPES_FILE = ONTOLOGY_DIR / "shapes.ttl"
REPORT_JSON = ONTOLOGY_DIR / "validation_report.json"
ONTO_DOC_IRI = ONTOLOGY_IRI + ".owl"


def load_ontology():
    """加载导出文档（实体统一在 tc# 命名空间；owlready2 0.51 的 Namespace
    属性访问不解析实体，改用 classes()/individuals() 名称查找）"""
    onto = get_ontology(ONTO_DOC_IRI)
    with open(ONTOLOGY_FILE, "rb") as f:
        onto.load(fileobj=f)
    return onto


def get_class(onto, name):
    return next(c for c in onto.classes() if c.name == name)


def hermit_consistency_check(onto):
    sync_reasoner_hermit()
    return {"consistent": True,
            "access_denied_count": len(get_class(onto, "AccessDeniedSite").instances()),
            "launch_capable_count": len(get_class(onto, "LaunchCapable").instances())}


def shacl_check(data_path=ONTOLOGY_FILE):
    data = rdflib.Graph()
    data.parse(str(data_path), format="xml", publicID=ONTO_DOC_IRI)
    shapes = rdflib.Graph()
    shapes.parse(str(SHAPES_FILE), format="turtle")
    conforms, results_graph, _ = validate(data, shacl_graph=shapes,
                                          advanced=True, inference="rdfs")
    SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")
    violations = []
    for node in results_graph.subjects(rdflib.RDF.type, SH.ValidationResult):
        violations.append({
            "focusNode": str(results_graph.value(node, SH.focusNode) or ""),
            "path": str(results_graph.value(node, SH.resultPath) or ""),
            "message": str(results_graph.value(node, SH.resultMessage) or ""),
        })
    return {"conforms": bool(conforms), "violations": violations}


def run_all():
    onto = load_ontology()
    hermit = hermit_consistency_check(onto)
    shacl = shacl_check()
    report = {"hermit": hermit, "shacl": {"conforms": shacl["conforms"],
                                          "violation_count": len(shacl["violations"]),
                                          "violations": shacl["violations"][:20]}}
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["hermit"], ensure_ascii=False))
    print(f"SHACL conforms={report['shacl']['conforms']} violations={report['shacl']['violation_count']}")
    return report


if __name__ == "__main__":
    run_all()
