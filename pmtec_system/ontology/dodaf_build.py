# -*- coding: utf-8 -*-
"""P16-D2: DoDAF 2.02 视点覆盖层本体 dodaf_overlay.ttl

建模立场：不照抄参考文档的军工交付内容，只借用 DoDAF 2.02 视点方法与追溯链
CAP → OA/Task → EX → ENT → SER → SYS (+PRO)，全部个体由仓库真实产物机器生成：
- Capability(35)      ← data/ujtl/ujtl_segments.csv（UJTL 编号段，任务/指标数为实证）
- InformationExchange ← output/pmtec_spear_report.json（22 事件类型 × 观测计数）
- Role                ← SPEAR 事件 source 分组（13 作战角色，观测到即建）
- ServiceContract(6)  ← services/grpc_server.py _init_app_store 字面量（ast 解析）
- SystemNode          ← grpc_server.py Servicer 类名正则 + config.py 端口常量 + 页面文件
- ProjectActivity(2)  ← 真实交付工件（CI 工作流 / Docker 化）
类型系统交叉引用目标特性本体 tc#（ MilitaryInstallation / LaunchCapable 等）。

事件类型→活动/能力的映射表是公理性设计资产：build 时双向完整性校验
（映射表必须恰好覆盖实测 22 类，能力代码必须存在于 UJTL 段），防悬空。
"""
import ast
import collections
import csv
import json
import re
from pathlib import Path

from rdflib import Graph, Literal, Namespace
from rdflib.namespace import OWL, RDF, RDFS

BASE = Path(__file__).resolve().parents[2]          # 仓库根
SYS = BASE / "pmtec_system"
SPEAR_JSON = SYS / "output" / "pmtec_spear_report.json"
SEGMENTS_CSV = SYS / "data" / "ujtl" / "ujtl_segments.csv"
GRPC_SRC = SYS / "services" / "grpc_server.py"
CONFIG_SRC = SYS / "config.py"
TC_ONT = SYS / "ontology" / "target_characteristics.owl"
OVERLAY_TTL = Path(__file__).resolve().parent / "dodaf_overlay.ttl"

DD = Namespace("http://pmtec.example.org/dodaf#")
TC = Namespace("http://pmtec.example.org/tc#")
XSD = Namespace("http://www.w3.org/2001/XMLSchema#")

# 页面/交付工件清单（相对 pmtec_system/，build 时断言文件存在）
VIEW_PAGES = ["output/pmtec_globe.html", "output/pmtec_realtime_display.html",
              "output/dt_dashboard.html", "output/pmtec_spear_timeline.html"]
PROJ_ARTIFACTS = {
    "proj_ci_pipeline": "../.github/workflows",
    "proj_containerization": "Dockerfile",
}

# ---- 公理性映射表：event_type → (UJTL 编号段, 信息实体) ----------------------
EX_MAPPING = {
    "detect":                  ("TA 2", "ent_sensor_track"),
    "kalman_fuse":             ("TA 2", "ent_sensor_track"),
    "live_data_inject":        ("TA 2", "ent_sensor_track"),
    "transfer":                ("TA 2", "ent_sensor_track"),
    "missile_launch":          ("TA 3", "ent_missile_threat"),
    "cyber_attack":            ("TA 6", "ent_missile_threat"),
    "cyber_detected":          ("TA 6", "ent_missile_threat"),
    "ew_jam_start":            ("TA 6", "ent_missile_threat"),
    "intercept_decision":      ("TA 3", "ent_fire_control"),
    "intercept_success":       ("TA 3", "ent_fire_control"),
    "intercept_fail":          ("TA 3", "ent_fire_control"),
    "c2_order":                ("OP 5", "ent_fire_control"),
    "c2_feedback":             ("OP 5", "ent_c2_status"),
    "c2_report":               ("OP 5", "ent_c2_status"),
    "asda_cycle":              ("OP 5", "ent_c2_status"),
    "adapt_summary":           ("OP 5", "ent_c2_status"),
    "political_access_change": ("SN 5", "ent_political_access"),
    "political_grey_zone":     ("SN 5", "ent_political_access"),
    "dqn_dispersal":           ("TA 1", "ent_platform_state"),
    "ma_dqn_decision":         ("TA 1", "ent_platform_state"),
    "sim_start":               ("TA 1", "ent_platform_state"),
    "recover":                 ("TA 4", "ent_platform_state"),
}
ENTITY_NAME = {
    "ent_sensor_track":   "传感器航迹信息",
    "ent_missile_threat": "导弹与网络电磁威胁信息",
    "ent_fire_control":   "拦截火力协同信息",
    "ent_c2_status":      "指挥控制状态信息",
    "ent_political_access": "政治准入状态信息",
    "ent_platform_state": "平台与数字孪生体状态信息",
}
# 信息实体 → tc# 目标特性类（类型系统交叉锚点）
ENTITY_TC_ANCHOR = {
    "ent_sensor_track": "MilitaryInstallation",
    "ent_missile_threat": "MilitaryInstallation",
    "ent_fire_control": "LaunchCapable",
    "ent_c2_status": "AccessDeniedSite",
    "ent_political_access": "AccessState",
    "ent_platform_state": "FacilityPart",
}
# 角色（source 分组）→ 承载系统
ROLE_OF_SOURCE = {
    "ASDA-Engine": "role_asda_engine",
    "ASDA-Adapt": "role_asda_engine",
    "P11-C2Chain": "role_c2_chain",
    "Political-Access-Model": "role_political_access_model",
    "DQN-Agent": "role_dqn_agent",
    "MADDPG (Multi-Agent ": "role_maddpg_agent",
    "LVC-Live": "role_lvc_live",
    "LVC-Fusion": "role_lvc_fusion",
    "hostile": "role_hostile_forces",
    "system": "role_platform_clock",
}  # 未命中且匹配 ^(SEN|JP|AK)- 者归入 role_sensor_grid（友邻与传感网合并观测）
ROLE_NAME = {
    "role_asda_engine": "ASDA 决策引擎",
    "role_c2_chain": "指挥链模型",
    "role_political_access_model": "政治准入模型",
    "role_dqn_agent": "DQN 分散决策智能体",
    "role_maddpg_agent": "MADDPG 多智能体",
    "role_lvc_live": "LVC 实装数据接入",
    "role_lvc_fusion": "LVC 航迹融合",
    "role_hostile_forces": "红方对手兵力",
    "role_sensor_grid": "传感网与友邻单元",
    "role_platform_clock": "平台系统自身",
}
ROLE_SYS = {
    "role_asda_engine": "sys-WarEngine",
    "role_c2_chain": "sys-WarEngine",
    "role_political_access_model": "sys-WarEngine",
    "role_dqn_agent": "sys-WarEngine",
    "role_maddpg_agent": "sys-WarEngine",
    "role_lvc_live": "sys-realtime-ws",
    "role_lvc_fusion": "sys-WarEngine",
    "role_hostile_forces": "sys-WarEngine",
    "role_sensor_grid": "sys-WarEngine",
    "role_platform_clock": "sys-WarEngine",
}
# 应用类别 → 支撑能力段
CATEGORY_CAP = {
    "strike": "OP 3", "defense": "TA 6", "isr": "ST 2",
    "logistics": "TA 4", "analysis": "OP 5", "decision": "OP 5",
}


def slug(raw: str) -> str:
    return re.sub(r"[^0-9a-zA-Z]+", "_", raw.strip()).strip("_").lower()


# ---- 真实产物解析 -------------------------------------------------------------
def load_spear():
    data = json.loads(SPEAR_JSON.read_text(encoding="utf-8"))
    events = data["events"]
    types = collections.Counter(e["event_type"] for e in events)
    type_sources = collections.defaultdict(collections.Counter)
    for e in events:
        type_sources[e["event_type"]][e["source"]] += 1
    return types, type_sources


def load_segments():
    rows = []
    with open(SEGMENTS_CSV, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if not r["层级代码"].strip():
                continue  # 合计行（编号段="合计"，无层级代码）
            rows.append(r)
    return rows


def load_apps():
    """ast 解析 grpc_server.py 中 _init_app_store 的 apps 字面量，不导入引擎"""
    tree = ast.parse(GRPC_SRC.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_init_app_store":
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Assign) and
                        any(getattr(t, "id", "") == "apps" for t in sub.targets)):
                    return ast.literal_eval(sub.value)
    raise RuntimeError("_init_app_store apps 字面量未找到")


def load_grpc_services():
    src = GRPC_SRC.read_text(encoding="utf-8")
    names = re.findall(r"class (\w+?)Servicer\(pb_grpc\.", src)
    return sorted(names)


def read_const(name):
    m = re.search(rf"^{name} = (\d+)", CONFIG_SRC.read_text(encoding="utf-8"), re.M)
    return int(m.group(1))


def load_tc_classes():
    g = Graph()
    g.parse(str(TC_ONT), format="xml")
    return {s.split("#")[-1] for s in g.subjects(RDF.type, OWL.Class)}


# ---- 图构建 -------------------------------------------------------------------
def add_class(g, name, zh, parent=None):
    c = DD[name]
    g.add((c, RDF.type, OWL.Class))
    g.add((c, RDFS.label, Literal(zh, lang="zh")))
    if parent:
        g.add((c, RDFS.subClassOf, DD[parent]))
    return c


def define_schema(g):
    classes = [
        ("ArchitectureDomain", "架构视点域"),
        ("Capability", "作战能力（CV）", "ArchitectureDomain"),
        ("Scenario", "作战场景（CV）", "ArchitectureDomain"),
        ("OperationalActivity", "作战活动/任务（OV-2）", "ArchitectureDomain"),
        ("Role", "作战角色（OV-2）", "ArchitectureDomain"),
        ("InformationExchange", "信息交换（OV-3）", "ArchitectureDomain"),
        ("InformationEntity", "信息实体（DIV 契约）", "ArchitectureDomain"),
        ("ServiceContract", "作战服务契约（SvcV）", "ArchitectureDomain"),
        ("SystemNode", "系统/装备节点（SV）", "ArchitectureDomain"),
        ("StandardBaseline", "标准基线（StdV）", "ArchitectureDomain"),
        ("ProjectActivity", "建设项目（PV）", "ArchitectureDomain"),
    ]
    for spec in classes:
        add_class(g, spec[0], spec[1], spec[2] if len(spec) > 2 else None)
    # 注意：对象属性刻意不写 rdfs:domain/range —— inference="rdfs" 下
    # domain/range 会传染类型标注，污染 SHACL sh:class 判定；语义由形状约束承载。
    for p, zh in [("realizes", "实现/支撑能力"),
                  ("tracesTo", "追溯到活动"),
                  ("aboutEntity", "交换所描述的信息实体"),
                  ("producedBy", "交换由角色产生"),
                  ("providedBy", "服务/系统提供"),
                  ("allocatedTo", "角色/活动配置到系统"),
                  ("verifies", "项目验证系统")]:
        prop = DD[p]
        g.add((prop, RDF.type, OWL.ObjectProperty))
        g.add((prop, RDFS.label, Literal(zh, lang="zh")))
    for p, zh, t in [("observedCount", "实测观测次数", XSD.integer),
                     ("taskCount", "UJTL任务合计数", XSD.integer),
                     ("measureCount", "UJTL衡量指标数", XSD.integer),
                     ("versionInfo", "版本号", XSD.string),
                     ("categoryInfo", "服务类别", XSD.string),
                     ("endpointInfo", "接口端点", XSD.string)]:
        g.add((DD[p], RDF.type, OWL.DatatypeProperty))
        g.add((DD[p], RDFS.label, Literal(zh, lang="zh")))
        g.add((DD[p], RDFS.range, t))


def build_graph():
    types, type_sources = load_spear()
    segments = load_segments()
    apps = load_apps()
    services = load_grpc_services()
    tc_classes = load_tc_classes()

    # 双向完整性校验：映射表 ⇄ 实测事件类型
    unmapped = set(types) - set(EX_MAPPING)
    phantom = set(EX_MAPPING) - set(types)
    if unmapped or phantom:
        raise RuntimeError(f"EX 映射表与实测不符 missing={unmapped} extra={phantom}")
    seg_codes = {r["编号段"] for r in segments}
    bad_caps = {c for c, _ in EX_MAPPING.values() if c not in seg_codes}
    bad_caps |= set(CATEGORY_CAP.values()) - seg_codes
    if bad_caps:
        raise RuntimeError(f"映射到不存在的 UJTL 能力段: {bad_caps}")
    for cls in set(ENTITY_TC_ANCHOR.values()):
        if cls not in tc_classes:
            raise RuntimeError(f"tc#{cls} 不存在，类型系统锚点断裂")

    g = Graph()
    g.bind("dd", DD)
    g.bind("tc", TC)
    g.bind("owl", OWL)
    define_schema(g)

    def ind(cls, sid, label, **props):
        u = DD[sid]
        g.add((u, RDF.type, DD[cls]))
        g.add((u, RDFS.label, Literal(label, lang="zh") if any(
            "\u4e00" <= ch <= "\u9fff" for ch in label) else Literal(label)))
        for k, v in props.items():
            g.add((u, DD[k], Literal(v)))
        return u

    # Capability + OperationalActivity ← UJTL 段（1 段 = 1 能力，段名 = 活动）
    for r in segments:
        code, sc, mc = r["编号段"], int(r["本段任务合计"]), int(r["衡量指标数"])
        cap = ind("Capability", "cap_" + slug(code), r["编号段名称（中文）"],
                  taskCount=sc, measureCount=mc)
        oa = ind("OperationalActivity", "oa_" + slug(code), r["编号段名称（原文）"])
        g.add((oa, DD.tracesTo, cap))

    # InformationEntity（6，类型系统锚到 tc#）
    for eid, name in ENTITY_NAME.items():
        ent = ind("InformationEntity", eid, name)
        g.add((ent, DD.tracesTo, TC[ENTITY_TC_ANCHOR[eid]]))

    # InformationExchange（22）+ producedBy 边（角色×交换 实测共现）
    role_events = collections.Counter()
    for et, n in sorted(types.items(), key=lambda x: -x[1]):
        seg, ent = EX_MAPPING[et]
        ex = ind("InformationExchange", "ex_" + et, et, observedCount=n)
        g.add((ex, DD.tracesTo, DD["oa_" + slug(seg)]))
        g.add((ex, DD.aboutEntity, DD[ent]))
        for src, k in type_sources[et].items():
            rid = ROLE_OF_SOURCE.get(src)
            if rid is None and re.match(r"^(SEN|JP|AK)-", src):
                rid = "role_sensor_grid"
            if rid is None:
                raise RuntimeError(f"事件源角色未归类: {src!r}")
            g.add((ex, DD.producedBy, DD[rid]))
            role_events[rid] += k
    # 观测覆盖率：所有 source 分组都必须被建出角色
    observed_roles = set(role_events)
    if observed_roles != set(ROLE_NAME):
        raise RuntimeError(f"角色覆盖不完整: {set(ROLE_NAME) ^ observed_roles}")

    # Role + allocatedTo
    for rid, name in ROLE_NAME.items():
        ind("Role", rid, name, observedCount=role_events[rid])
        g.add((DD[rid], DD.allocatedTo, DD[ROLE_SYS[rid]]))

    # ServiceContract（6 应用）← ast 解析
    for app_id, name, ver, cat, desc in apps:
        s = ind("ServiceContract", "svc_" + slug(app_id), name,
                versionInfo=ver, categoryInfo=cat)
        g.add((s, DD.realizes, DD["cap_" + slug(CATEGORY_CAP[cat])]))
        g.add((s, DD.providedBy, DD["sys-ApplicationStore"]))

    # SystemNode ← 4 gRPC 服务 + REST/WS + 4 可视化页面
    ports = {"WarEngine": read_const("GRPC_PORT"),
             "ApplicationStore": read_const("GRPC_PORT")}
    grpc_names = {"WarEngine": "战争引擎服务", "BattleNetwork": "作战网络服务",
                  "ApplicationStore": "应用商店服务", "PlugAndPlay": "即插即用服务"}
    for s in services:
        node = ind("SystemNode", "sys-" + s, grpc_names.get(s, s),
                   endpointInfo=f"pmtec://grpc:{ports.get(s, read_const('GRPC_PORT'))}")
        g.add((node, DD.realizes, DD["cap_op_5"]))
    g.add((DD["sys-BattleNetwork"], DD.realizes, DD["cap_ta_6"]))
    ind("SystemNode", "sys-rest-gateway", "数字孪生 REST 网关",
        endpointInfo=f":{read_const('PLATFORM_REST_PORT')}")
    g.add((DD["sys-rest-gateway"], DD.realizes, DD["cap_st_1"]))
    ws_src = (SYS / "realtime" / "websocket_server.py").read_text(encoding="utf-8")
    ws_port = re.search(r"port: int = (\d+)", ws_src).group(1)
    ind("SystemNode", "sys-realtime-ws", "实时态势 WebSocket 服务",
        endpointInfo=f":{ws_port}")
    g.add((DD["sys-realtime-ws"], DD.realizes, DD["cap_ta_2"]))
    for p in VIEW_PAGES:
        if not (SYS / p).exists():
            raise RuntimeError(f"页面工件缺失: {p}")
        sid = "sys-page-" + slug(Path(p).stem)
        ind("SystemNode", sid, Path(p).name, endpointInfo="static://" + p)
        g.add((DD[sid], DD.realizes, DD["cap_op_5"]))

    # ProjectActivity（PV）→ verifies 系统节点
    proj_labels = {"proj_ci_pipeline": "CI/CD 质量门建设",
                   "proj_containerization": "容器化交付建设"}
    for pid, artifact in PROJ_ARTIFACTS.items():
        if not (BASE / "pmtec_system" / artifact).exists() and not (BASE / artifact).exists():
            raise RuntimeError(f"项目工件缺失: {artifact}")
        ind("ProjectActivity", pid, proj_labels[pid])
    for pid in proj_labels:
        for s in services:
            g.add((DD[pid], DD.verifies, DD["sys-" + s]))

    # StdV 声明（标准基线为类级公理，指向真实约束工件）
    std = ind("StandardBaseline", "std_dodaf_projection",
              "DoDAF 2.02 视点投影基线（方法借用，非条款引用）")
    g.add((std, DD.tracesTo, DD["cap_op_5"]))
    g.add((std, DD.tracesTo, DD["ent_political_access"]))
    return g, {"capability": len(segments), "exchange": len(types),
               "role": len(ROLE_NAME), "service": len(apps),
               "entity": len(ENTITY_NAME)}


if __name__ == "__main__":
    g, stats = build_graph()
    OVERLAY_TTL.write_text(g.serialize(format="turtle"), encoding="utf-8")
    print(json.dumps({**stats, "triples": len(g), "artifact": OVERLAY_TTL.name},
                     ensure_ascii=False))
