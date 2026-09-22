# -*- coding: utf-8 -*-
"""T4: SPARQL 杀伤网语义查询服务

对赛题B支撑材料（胡权 PDF）"目标特性→杀伤网"应用面的落地，三类样例查询：
1. PAE（并列目标清单/攻击优先级）：按功能特性排序高价值机场目标
2. Match Effector（效应器-目标匹配）：给定来袭弹型威胁轴，检索可执行
   拦截/分散响应的基地-效应器配对（基于驻防机型与政治敞口的语义约束）
3. COA（行动方案生成）：单点依赖脆弱节点的同国冗余替代方案

数据面 = target_characteristics.owl（rdflib 直接解析，无需推理机）；
输出 JSON 报告 sparql_killnet_report.json 供 T5 断言与大屏/报告引用。
"""
import json
from pathlib import Path

import rdflib
from rdflib.namespace import RDF

ONTOLOGY_DIR = Path(__file__).resolve().parent
ONTOLOGY_FILE = ONTOLOGY_DIR / "target_characteristics.owl"
REPORT_JSON = ONTOLOGY_DIR / "sparql_killnet_report.json"

TC = rdflib.Namespace("http://pmtec.example.org/tc#")
PREFIXES = "PREFIX tc: <http://pmtec.example.org/tc#>\nPREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"


def load_graph():
    g = rdflib.Graph()
    g.parse(str(ONTOLOGY_FILE), format="xml")
    return g


# ------------------------------------------------------- Q1 PAE 攻击优先级

Q_PAE = PREFIXES + """
SELECT ?base ?label ?tier ?personnel ?runwayM WHERE {
  ?base a tc:AirBase ;
        rdfs:label ?label ;
        tc:tierLevel ?tier .
  OPTIONAL { ?base tc:personnelCount ?personnel }
  ?base tc:hasPart ?rwy .
  ?rwy tc:runwayLengthM ?runwayM
}
ORDER BY ASC(?tier) DESC(?runwayM)
LIMIT 10"""


def q_pae(g):
    """Tier1 且跑道最长者优先——PAE 头部目标清单"""
    rows = g.query(Q_PAE)
    out = []
    for r in rows:
        out.append({
            "base": str(r.base).split("#")[-1],
            "name": str(r.label),
            "tier": int(r.tier),
            "personnel": int(r.personnel) if r.personnel is not None else None,
            "runway_m": float(r.runwayM),
        })
    return out


# ---------------------------------------- Q2 效应器-目标匹配（拦截响应侧）

Q_MATCH = PREFIXES + """
SELECT ?base ?label ?branch ?aircraft WHERE {
  ?base rdf:type/rdfs:subClassOf* tc:MilitaryInstallation ;
        rdfs:label ?label ;
        tc:branchCode ?branch ;
        tc:accessUncertainty ?unc ;
        tc:basedAircraft ?aircraft .
  FILTER(str(?unc) = "sovereign" && CONTAINS(str(?aircraft), "F-"))
}
ORDER BY ?base"""


def q_match_effector(g):
    """可无前敌政治敞口执行拦截响应的主权基地效应器（驻防战斗机部队）"""
    out = []
    for r in g.query(Q_MATCH):
        out.append({
            "base": str(r.base).split("#")[-1],
            "name": str(r.label),
            "branch": str(r.branch),
            "aircraft": str(r.aircraft) if r.aircraft is not None else "",
        })
    return out


# ----------------------------------------------------------- Q3 COA 生成

Q_COA = PREFIXES + """
SELECT ?fragile ?f_label ?f_country ?alt ?a_label ?a_runwayM WHERE {
  ?fragile a tc:AirBase ;
           tc:singleRunwayDependency true ;
           tc:countryName ?f_country ;
           rdfs:label ?f_label .
  ?alt a tc:AirBase ;
       tc:countryName ?f_country ;
       rdfs:label ?a_label ;
       tc:hasAccessState tc:state_open .
  ?alt tc:hasPart ?arwy .
  ?arwy tc:runwayLengthM ?a_runwayM .
  FILTER(?alt != ?fragile)
  FILTER(?a_runwayM >= 2000)
}
ORDER BY ?fragile DESC(?a_runwayM)"""


def q_coa(g):
    """单跑道依赖节点受打击时的同国疏散/再进驻替代方案"""
    groups = {}
    for r in g.query(Q_COA):
        frag = str(r.fragile).split("#")[-1]
        groups.setdefault(frag, {"name": str(r.f_label), "country": str(r.f_country),
                                 "alternatives": []})
        alt = str(r.alt).split("#")[-1]
        if not any(a["base"] == alt for a in groups[frag]["alternatives"]):
            groups[frag]["alternatives"].append({
                "base": alt, "name": str(r.a_label), "runway_m": float(r.a_runwayM)})
    return [{"fragile_node": k, **v} for k, v in sorted(groups.items())]


def run_all():
    g = load_graph()
    report = {
        "pae_priority_targets": q_pae(g),
        "match_effector_sovereign_fighters": q_match_effector(g),
        "coa_single_runway_alternatives": q_coa(g),
        "counts": {"pae": None, "effector": None, "coa": None},
    }
    report["counts"]["pae"] = len(report["pae_priority_targets"])
    report["counts"]["effector"] = len(report["match_effector_sovereign_fighters"])
    report["counts"]["coa"] = len(report["coa_single_runway_alternatives"])
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"PAE top={report['counts']['pae']} effector={report['counts']['effector']} "
          f"coa_nodes={report['counts']['coa']}")
    return report


if __name__ == "__main__":
    run_all()
