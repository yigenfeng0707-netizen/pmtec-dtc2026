# -*- coding: utf-8 -*-
"""P17-WP4: 语义工具层 — browse_semantics / resolve_semantics / session manifest

对标 EvoOntology（RUC-DataLab, arXiv:2609.15779）的工具层形态：提示词只注入轻量
清单（manifest），其余语义一律按需检索（active access），而非全量塞进上下文。
本模块为只读实现（零新依赖，rdflib 直接解析既有产物），MCP 传输层与演化闭环
见《DTC2026自进化本体提升计划-P17.md》WP1-WP3。

四类语义对象的数据面映射（全部来自仓库真实产物，零虚构）：
  term       → target_characteristics.owl 类与个体（E-实体/状态/可战性定义类）
  mapping    → owl 数据/对象属性（A-属性到 GeoJSON 字段的锚定，含域/值域/注释）
  constraint → shapes.ttl SHACL 形状（字段约束 + 报警消息，负样本注入的判据）
  evidence   → provenance.ttl 溯源断言（Bel/Pl 区间 + wasDerivedFrom 证据源）

设计红线（EvoOntology 消融教训）：语义断言必须挂证据（w/o Evidence −8.7）；
本工具只读不写——任何本体变更必须先过 test_p14/test_p16 逻辑门禁（w/o Gate −11.2）。
"""
import json
from pathlib import Path

import rdflib
from rdflib.namespace import OWL, RDF, RDFS

ONTOLOGY_DIR = Path(__file__).resolve().parent
OWL_FILE = ONTOLOGY_DIR / "target_characteristics.owl"
SHAPES_FILE = ONTOLOGY_DIR / "shapes.ttl"
PROV_FILE = ONTOLOGY_DIR / "provenance.ttl"
CONFIDENCE_FILE = ONTOLOGY_DIR / "confidence_report.json"

TC_NS = "http://pmtec.example.org/tc#"
TC = rdflib.Namespace(TC_NS)
SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")
PROV = rdflib.Namespace("http://www.w3.org/ns/prov#")

KINDS = ("term", "mapping", "constraint", "evidence")

_CACHE = {}


def _local(node) -> str:
    return str(node).split("#")[-1]


def _lit(ns: str) -> str:
    return '"' + ns + '"'


def _graphs():
    """惰性单例加载：OWL / SHACL / PROV 三图 + D-S 置信报告（只读）"""
    if "loaded" not in _CACHE:
        g = rdflib.Graph()
        g.parse(str(OWL_FILE), format="xml")
        gs = rdflib.Graph()
        gs.parse(str(SHAPES_FILE), format="turtle")
        gp = rdflib.Graph()
        gp.parse(str(PROV_FILE), format="turtle")
        conf = {}
        if CONFIDENCE_FILE.exists():
            conf = json.loads(CONFIDENCE_FILE.read_text(encoding="utf-8"))
        conf_by_base = {}
        for entry in conf.get("bases", []):
            conf_by_base["base_" + str(entry.get("id", "")).replace("-", "_")] = entry
        _CACHE["loaded"] = (g, gs, gp, conf_by_base)
    return _CACHE["loaded"]


# --------------------------------------------------------------- manifest

def manifest():
    """会话清单：唯一进提示词的轻量摘要；其余语义经 browse/resolve 按需取"""
    g, gs, gp, _ = _graphs()
    classes = {s for s in g.subjects(RDF.type, OWL.Class)
               if str(s).startswith(TC_NS)}
    individuals = {s for s in g.subjects(RDF.type, None)
                   if str(s).startswith(TC_NS) and (s, RDFS.label, None) in g}
    return {
        "sources": {
            "terms_mappings": OWL_FILE.name,
            "constraints": SHAPES_FILE.name,
            "evidence": PROV_FILE.name,
            "confidence": CONFIDENCE_FILE.name,
        },
        "counts": {
            "term": len(classes) + len(individuals),
            "mapping": len(_mappings_index()),
            "constraint": len(_shapes_index()),
            "evidence": len(_evidence_index()),
        },
        "usage": [
            "browse(q, kind, n): kind ∈ {term, mapping, constraint, evidence}",
            "resolve(id): 个体档案 = 属性(Mapping) + 适用约束(Constraint) + 证据(Evidence)",
            "个体 id 形如 base_JP_MISAWA；类 id 形如 LaunchCapable",
        ],
        "design_rule": "只读工具层；本体变更必须先过 test_p14/test_p16 逻辑门禁",
    }


# ------------------------------------------------------------ browse 索引

def _mappings_index():
    if "mappings" in _CACHE:
        return _CACHE["mappings"]
    g = _graphs()[0]
    prop_types = (OWL.DatatypeProperty, OWL.ObjectProperty, OWL.TransitiveProperty)
    items = {}
    seen = set()
    for ptype in prop_types:
        for p in g.subjects(RDF.type, ptype):
            if not str(p).startswith(TC_NS) or p in seen:
                continue
            seen.add(p)
            detail = []
            dom = g.value(p, RDFS.domain)
            rng = g.value(p, RDFS.range)
            cmt = g.value(p, RDFS.comment)
            if dom is not None:
                detail.append("domain=" + _local(dom))
            if rng is not None:
                detail.append("range=" + _local(rng))
            if cmt is not None:
                detail.append(str(cmt))
            items[_local(p)] = {"kind": "mapping", "id": _local(p),
                                "name": _local(p), "detail": "；".join(detail)}
    _CACHE["mappings"] = items
    return items


def _shapes_index():
    if "shapes" in _CACHE:
        return _CACHE["shapes"]
    gs = _graphs()[1]
    items = {}
    for shape in gs.subjects(RDF.type, SH.NodeShape):
        target = gs.value(shape, SH.targetClass)
        if target is None:
            continue
        details = []
        for ps in gs.objects(shape, SH.property):
            parts = []
            for pred, tag in ((SH.path, "path"), (SH.minCount, "minCount"),
                              (SH.datatype, "type"), (SH.minInclusive, "min"),
                              (SH.maxInclusive, "max"), (SH.message, "msg")):
                val = gs.value(ps, pred)
                if val is not None:
                    parts.append(f"{tag}={_local(val) if tag == 'path' else val}")
            if parts:
                details.append(" ".join(parts))
        for sv in gs.objects(shape, SH.sparql):
            msg = gs.value(sv, SH.message)
            if msg is not None:
                details.append(f"sparql约束 msg={msg}")
        items[_local(shape)] = {
            "kind": "constraint", "id": _local(shape),
            "name": f"{_local(shape)} → {_local(target)}",
            "detail": " | ".join(details),
        }
    _CACHE["shapes"] = items
    return items


def _evidence_index():
    if "evidence" in _CACHE:
        return _CACHE["evidence"]
    gp = _graphs()[2]
    items = {}
    for e in gp.subjects(RDF.type, PROV.Entity):
        label = gp.value(e, RDFS.label)
        if label is None:
            continue
        detail = []
        grade = gp.value(e, TC.precisionGrade)
        bel = gp.value(e, TC.beliefOpen)
        pl = gp.value(e, TC.plausibilityOpen)
        if grade is not None:
            detail.append(f"精度 {grade}")
        if bel is not None:
            detail.append(f"Bel(Open)={float(bel):.4f}")
        if pl is not None:
            detail.append(f"Pl(Open)={float(pl):.4f}")
        srcs = sorted(_local(s) if str(s).startswith("urn:") else str(s)
                      for s in gp.objects(e, PROV.wasDerivedFrom))
        if srcs:
            detail.append(f"证据源 {len(srcs)} 个: {','.join(srcs)}")
        act = gp.value(e, PROV.wasGeneratedBy)
        if act is not None:
            detail.append(f"生成活动 {_local(act)}")
        items[_local(e)] = {"kind": "evidence", "id": _local(e),
                            "name": str(label), "detail": "；".join(detail)}
    _CACHE["evidence"] = items
    return items


def _terms_index():
    if "terms" in _CACHE:
        return _CACHE["terms"]
    g = _graphs()[0]
    items = {}
    for c in g.subjects(RDF.type, OWL.Class):
        if not str(c).startswith(TC_NS):
            continue
        cmt = g.value(c, RDFS.comment)
        eq = "；含等价类公理" if (c, OWL.equivalentClass, None) in g else ""
        items[_local(c)] = {"kind": "term", "id": _local(c), "name": _local(c),
                            "detail": (str(cmt)[:80] if cmt is not None else "本体类（TBox）") + eq}
    for ind in g.subjects(RDF.type, None):
        if not str(ind).startswith(TC_NS):
            continue
        label = g.value(ind, RDFS.label)
        if label is None:
            continue
        types = sorted(_local(t) for t in g.objects(ind, RDF.type)
                       if str(t).startswith(TC_NS))
        items[_local(ind)] = {"kind": "term", "id": _local(ind),
                              "name": str(label), "detail": f"个体（{'/'.join(types)}）"}
    _CACHE["terms"] = items
    return items


# ---------------------------------------------------------------- browse

def browse(q: str = "", kind: str = "term", n: int = 10):
    """按类别检索语义对象：子串匹配 id/name/detail，确定性排序"""
    if kind not in KINDS:
        raise ValueError(f"未知 kind={kind!r}，合法值 {KINDS}")
    index = {"term": _terms_index, "mapping": _mappings_index,
             "constraint": _shapes_index, "evidence": _evidence_index}[kind]()
    needle = (q or "").strip().lower()
    hits = [item for item in index.values()
            if not needle or needle in f"{item['id']} {item['name']} {item['detail']}".lower()]
    hits.sort(key=lambda x: x["id"])
    return hits[: max(0, int(n))]


# ---------------------------------------------------------------- resolve

def _class_closure(g, ind):
    """个体类型的超类闭包（tc# 域内，Python BFS 规避 SPARQL path 兼容风险）"""
    closure = set()
    frontier = [t for t in g.objects(ind, RDF.type) if str(t).startswith(TC_NS)]
    while frontier:
        cls = frontier.pop()
        if cls in closure:
            continue
        closure.add(cls)
        frontier.extend(s for s in g.objects(cls, RDFS.subClassOf)
                        if str(s).startswith(TC_NS))
    return {_local(c) for c in closure}


def _typed_value(o):
    if isinstance(o, rdflib.URIRef):
        return _local(o) if str(o).startswith(TC_NS) else str(o)
    dt = str(o.datatype) if o.datatype else ""
    if "integer" in dt:
        return int(o)
    if "double" in dt or "decimal" in dt or "float" in dt:
        return float(o)
    return str(o)


def resolve(ids):
    """个体档案：属性(Mapping)+适用约束(Constraint)+证据(Evidence)+置信区间"""
    g, gs, gp, conf_by_base = _graphs()
    shapes = _shapes_index()
    out = []
    for raw in ids if isinstance(ids, (list, tuple)) else [ids]:
        rid = str(raw).strip()
        local = rid.split("#")[-1]
        iri = TC[local]
        entry = {"id": rid, "found": False}
        if (iri, RDF.type, OWL.Class) in g:
            comment = g.value(iri, RDFS.comment)
            entry.update({
                "found": True, "kind": "class",
                "comment": str(comment) if comment is not None else None,
                "equivalent_axiom": (iri, OWL.equivalentClass, None) in g,
                "superclasses": sorted(_local(s) for s in g.objects(iri, RDFS.subClassOf)
                                       if str(s).startswith(TC_NS)),
                "direct_instances": len(set(g.subjects(RDF.type, iri))),
                "constraints": [shapes[s]["name"] for s in sorted(shapes)
                                if shapes[s]["name"].split(" → ")[-1] == local],
            })
        elif any(str(t).startswith(TC_NS) for t in g.objects(iri, RDF.type)):
            types = sorted(_local(t) for t in g.objects(iri, RDF.type)
                           if str(t).startswith(TC_NS))
            closure = _class_closure(g, iri)
            props = {}
            for p, o in g.predicate_objects(iri):
                if not str(p).startswith(TC_NS) or p == RDF.type:
                    continue
                props.setdefault(_local(p), []).append(_typed_value(o))
            entry.update({
                "found": True, "kind": "individual",
                "types": types,
                "properties": {k: sorted(v) for k, v in sorted(props.items())},
                "constraints": [shapes[s]["name"] for s in sorted(shapes)
                                if shapes[s]["name"].split(" → ")[-1] in closure],
            })
            evidence = _evidence_index().get("assertion_" + local.replace("base_", "", 1))
            if evidence is not None:
                entry["evidence"] = evidence
            if local in conf_by_base:
                entry["confidence"] = conf_by_base[local]
        out.append(entry)
    return out


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="P17 语义工具层（只读 browse/resolve/manifest）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("manifest")
    pb = sub.add_parser("browse")
    pb.add_argument("q", nargs="?", default="")
    pb.add_argument("--kind", default="term", choices=KINDS)
    pb.add_argument("--n", type=int, default=10)
    pr = sub.add_parser("resolve")
    pr.add_argument("ids", nargs="+")
    args = ap.parse_args()

    if args.cmd == "manifest":
        print(json.dumps(manifest(), ensure_ascii=False, indent=2))
    elif args.cmd == "browse":
        print(json.dumps(browse(args.q, args.kind, args.n), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(resolve(args.ids), ensure_ascii=False, indent=2))
