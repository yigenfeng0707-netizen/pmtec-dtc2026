# -*- coding: utf-8 -*-
"""T3: PROV-O 溯源 + D-S 证据理论置信度传播层

对赛题B支撑材料（胡权 PDF）两条硬性要求的落地：
1. 溯源（PDF §4.3 数据可信度）：每条基地状态断言以 PROV-O 记录
   「证据源文档 → 提取活动 → 断言实体」链路，落盘 provenance.ttl
2. 置信度（PDF §3.2 不确定量化）：接入状态帧 Θ={Open,Restricted,Denied}，
   两路独立证据——坐标/数据精度分级（A/A-/B）+ 政治准入不确定性类型
   （sovereign/host_nation/territory）——各建 mass 函数，Dempster 合成，
   输出每基地 Bel/Pl 区间与冲突系数 K（K 超阈拒绝合成并标记）

Brier 分数校准接口: brier_score() 供仿真终态回算预测概率校准度。
"""
import json
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

import rdflib
from rdflib.namespace import OWL, RDF, RDFS

ONTOLOGY_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[2]
GEOJSON_PATH = REPO_ROOT / "过程脚本归档" / "indopacom_bases_v2.geojson"
PROV_TTL = ONTOLOGY_DIR / "provenance.ttl"
CONF_REPORT_JSON = ONTOLOGY_DIR / "confidence_report.json"

PROV = rdflib.Namespace("http://www.w3.org/ns/prov#")
TC = rdflib.Namespace("http://pmtec.example.org/tc#")

THETA = ("Open", "Restricted", "Denied")
CONFLICT_REJECT_THRESHOLD = 0.7  # K 超此值视为证据高度冲突，拒绝 Dempster 合成


# ---------------------------------------------------------------- D-S 核心

def _normalize(mass):
    total = sum(mass.values())
    return {k: v / total for k, v in mass.items() if v > 0}


def dempster_combine(m1, m2):
    """Dempster 合式规则；返回 (合成 mass, 冲突系数 K)"""
    combined = {}
    conflict = 0.0
    for (a, ma), (b, mb) in product(m1.items(), m2.items()):
        inter = frozenset(set(a) & set(b))
        if not inter:
            conflict += ma * mb
        else:
            combined[inter] = combined.get(inter, 0.0) + ma * mb
    if conflict >= 1.0:
        raise ValueError("证据完全冲突（K=1），不可合成")
    return _normalize(combined), conflict


def bel_pl(mass, hypothesis):
    """Bel/Pl 区间：Bel=全含于假设的 focal 质量和；Pl=与假设相交者之和"""
    h = set(hypothesis)
    bel = sum(m for f, m in mass.items() if set(f) <= h)
    pl = sum(m for f, m in mass.items() if set(f) & h)
    return round(bel, 4), round(pl, 4)


# ------------------------------------------------- 证据源 1：数据精度分级

# 精度 A=多源核验 45 站 / A-=v1 沿用 22 站 / B=Tinian 坐标降级（评级报告 #7）
# v1 沿用站未独立核验，"状态可维持"的支持弱化、无知质量增大
PRECISION_MASS = {
    "A": {frozenset({"Open"}): 0.60, frozenset({"Open", "Restricted"}): 0.15,
          frozenset(THETA): 0.25},
    "A-": {frozenset({"Open"}): 0.40, frozenset({"Open", "Restricted"}): 0.20,
           frozenset(THETA): 0.40},
    "B": {frozenset({"Open"}): 0.20, frozenset({"Open", "Restricted"}): 0.25,
          frozenset(THETA): 0.55},
}

# ------------------------------------------- 证据源 2：政治准入不确定性类型

# sovereign 本土无政治敞口；host_nation 东道国准入受条约/政局扰动；
# territory 属地介于两者之间（RAND RRA967-2 参数定性校准）
ACCESS_TYPE_MASS = {
    "sovereign": {frozenset({"Open"}): 0.80, frozenset(THETA): 0.20},
    "host_nation": {frozenset({"Open"}): 0.45, frozenset({"Open", "Restricted"}): 0.20,
                    frozenset({"Denied"}): 0.10, frozenset(THETA): 0.25},
    "territory": {frozenset({"Open"}): 0.60, frozenset({"Open", "Restricted"}): 0.20,
                  frozenset(THETA): 0.20},
}


def precision_grade(props):
    if props["id"] == "CNMI-TINIAN":
        return "B"
    ds = props.get("data_source", "")
    return "A" if ds.startswith("CRS") else "A-"


def evaluate_base(props):
    """两路证据独立合成，输出单态 Bel/Pl 与冲突系数"""
    m_src = PRECISION_MASS[precision_grade(props)]
    m_pol = ACCESS_TYPE_MASS[props.get("access_uncertainty", "host_nation")]
    m, k = dempster_combine(m_src, m_pol)
    intervals = {h: bel_pl(m, {h}) for h in THETA}
    return {
        "id": props["id"],
        "name": props["name"],
        "grade": precision_grade(props),
        "access_type": props.get("access_uncertainty"),
        "conflict_K": round(k, 4),
        "rejected": k >= CONFLICT_REJECT_THRESHOLD,
        "bel_pl": {h: {"Bel": v[0], "Pl": v[1]} for h, v in intervals.items()},
    }


# ---------------------------------------------------------------- PROV-O

SOURCE_DOC = {
    "A": ("crs:R47589-TableA-1", "dod:FY2024-Base-Structure-Report", "web:coordinate-verification"),
    "A-": ("v1:pmtec-22base-database",),
    "B": ("v1:pmtec-22base-database",),
}
SOURCE_LABEL = {
    "crs:R47589-TableA-1": "CRS Report R47589 Table A-1（美日菲澳基地清单）",
    "dod:FY2024-Base-Structure-Report": "DoD FY2024 Base Structure Report",
    "web:coordinate-verification": "多源坐标核验（公开地理数据交叉）",
    "v1:pmtec-22base-database": "P1-P8 时代 v1 基地库（22 站）",
}


def build_provenance_graph(results, generated_at=None):
    g = rdflib.Graph()
    g.bind("prov", PROV)
    g.bind("tc", TC)
    g.bind("rdfs", RDFS)
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    activity = rdflib.URIRef("urn:pmtec:activity:geojson-to-abox-extraction")
    g.add((activity, RDF.type, PROV.Activity))
    g.add((activity, RDFS.label,
           rdflib.Literal("indopacom_bases_v2.geojson → 目标特性本体 ABox 提取")))
    g.add((activity, PROV.atLocation, rdflib.Literal(str(GEOJSON_PATH.name))))
    agent = rdflib.URIRef("urn:pmtec:agent:tc-ontology-pipeline")
    g.add((agent, RDF.type, PROV.SoftwareAgent))
    g.add((activity, PROV.wasAssociatedWith, agent))

    doc_nodes = {}
    for r in results:
        assertion = rdflib.URIRef(TC + f"assertion_{r['id'].replace('-', '_')}")
        g.add((assertion, RDF.type, PROV.Entity))
        g.add((assertion, RDFS.label,
               rdflib.Literal(f"{r['name']} 接入状态断言（基线 c0=Open）")))
        g.add((assertion, PROV.wasGeneratedBy, activity))
        g.add((assertion, PROV.generatedAtTime, rdflib.Literal(generated_at)))
        g.add((assertion, TC.precisionGrade, rdflib.Literal(r["grade"])))
        g.add((assertion, TC.beliefOpen,
               rdflib.Literal(r["bel_pl"]["Open"]["Bel"])))
        g.add((assertion, TC.plausibilityOpen,
               rdflib.Literal(r["bel_pl"]["Open"]["Pl"])))
        for ref in SOURCE_DOC[r["grade"]]:
            if ref not in doc_nodes:
                uri = rdflib.URIRef("urn:pmtec:source:" + ref)
                g.add((uri, RDF.type, PROV.Entity))
                g.add((uri, RDFS.label, rdflib.Literal(SOURCE_LABEL[ref])))
                doc_nodes[ref] = uri
            g.add((assertion, PROV.wasDerivedFrom, doc_nodes[ref]))
            g.add((activity, PROV.used, doc_nodes[ref]))
    return g


# ---------------------------------------------------------------- Brier 校准

def brier_score(predictions, outcomes):
    """Brier 分数 BS = Σ(p-o)²/N；predictions/outcomes 为 0-1 对齐序列。
    仿真终态回写接口：p=孪生层预测拦截概率，o=实际结局(1/0)。"""
    if len(predictions) != len(outcomes) or not predictions:
        raise ValueError("预测与结局长度不一致或为空")
    return sum((p - o) ** 2 for p, o in zip(predictions, outcomes)) / len(predictions)


# ---------------------------------------------------------------- 主流程

def run_all():
    data = json.loads(GEOJSON_PATH.read_text(encoding="utf-8"))
    results = [evaluate_base(f["properties"]) for f in data["features"]]
    graph = build_provenance_graph(results)
    graph.serialize(destination=str(PROV_TTL), format="turtle")

    grades = {}
    for r in results:
        grades[r["grade"]] = grades.get(r["grade"], 0) + 1
    bel_opens = [r["bel_pl"]["Open"]["Bel"] for r in results]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "frame": list(THETA),
        "bases": results,
        "summary": {
            "total": len(results),
            "grade_distribution": grades,
            "conflict_rejections": sum(1 for r in results if r["rejected"]),
            "max_conflict_K": max(r["conflict_K"] for r in results),
            "belief_open_min": min(bel_opens),
            "belief_open_max": max(bel_opens),
            "belief_open_mean": round(sum(bel_opens) / len(bel_opens), 4),
        },
    }
    CONF_REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                encoding="utf-8")
    s = report["summary"]
    print(f"PROV triples={len(graph)} bases={s['total']} grades={s['grade_distribution']}")
    print(f"Bel(Open) min/mean/max = {s['belief_open_min']}/{s['belief_open_mean']}/"
          f"{s['belief_open_max']} | maxK={s['max_conflict_K']} rejections={s['conflict_rejections']}")
    return report


if __name__ == "__main__":
    run_all()
