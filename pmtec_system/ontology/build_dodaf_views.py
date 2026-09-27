# -*- coding: utf-8 -*-
"""P16-D4: DoDAF 2.02 八视点架构说明文档生成器

输入只有两个机器产物：dodaf_overlay.ttl（覆盖层本体）与
dodaf_validation_report.json（SHACL 追溯链校验结果）。
文档中每一张表的每一行都可由脚本回溯到仓库真实工件（SPEAR 报告 /
UJTL CSV / grpc_server.py / config.py / 页面文件），无任何手工誊写行。
重跑本脚本即可再生，内容随真实产物自动演进。

用法: python build_dodaf_views.py  → docs/PMTEC-DoDAF视点架构说明.md
"""
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import rdflib
from rdflib import RDF, Namespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dodaf_build  # noqa: E402

DD = Namespace("http://pmtec.example.org/dodaf#")
TC = Namespace("http://pmtec.example.org/tc#")
OVERLAY = dodaf_build.OVERLAY_TTL
REPORT = HERE / "dodaf_validation_report.json"
OUT_MD = dodaf_build.BASE / "docs" / "PMTEC-DoDAF视点架构说明.md"

TIER = {"OP": "战役层", "SN": "战略—国家层", "ST": "战略—战区层", "TA": "战术层"}


def zh(g, subj):
    for o in g.objects(subj, rdflib.RDFS.label):
        return str(o)
    return str(subj).split("#")[-1]


def main():
    g = rdflib.Graph()
    g.parse(str(OVERLAY), format="turtle")
    rep = json.loads(REPORT.read_text(encoding="utf-8"))

    def subjects(cls):
        return sorted(g.subjects(RDF.type, DD[cls]), key=str)

    def prop(s, p, default=""):
        vals = list(g.objects(s, DD[p]))
        return str(vals[0]) if vals else default

    def objs(s, p):
        return sorted(g.objects(s, p), key=str)

    L = []
    add = L.append
    add("# PMTEC 政治韧性数字孪生体系 — DoDAF 2.02 视点架构说明")
    add("")
    add(f"> 生成日期：{date.today().isoformat()}（由 `pmtec_system/ontology/build_dodaf_views.py` 自动导出，重跑可再生）  ")
    add("> 方法声明：本文借用 DoDAF 2.02 公开视点框架（AV/CV/OV/DIV/SvcV/SV/StdV/PV）"
       "与追溯链范式；全部内容针对 PMTEC 自有体系独立建模，所有矩阵行由脚本从仓库"
       "真实工件（SPEAR 实跑报告、UJTL 数据集、gRPC 服务源码、配置文件、页面文件）推导，"
       "无人工誊写行。  ")
    sc = rep["class_counts"]
    add(f"> 追溯链校验：SHACL `conforms={rep['shacl']['conforms']}`，"
       f"违规 {rep['shacl']['violation_count']} 条，跨本体锚点断裂 "
       f"{len(rep['cross_ontology']['broken_anchors'])} 处。")
    add("")

    # ---- AV 全局视点 ----
    add("## 1. AV 全局视点（视角总纲）")
    add("")
    add("**体系**：PMTEC 政治韧性数字孪生试验床——以政治准入模型为一等公民的"
        "INDOPACOM 基地群数字孪生与推演体系。")
    add("")
    add("**视角投影总表**（每行 = 覆盖层一个类，个体数机器统计）：")
    add("")
    add("| DoDAF 视点 | 覆盖层类 | 个体数 | 真实工件来源 |")
    add("|---|---|---:|---|")
    view_rows = [
        ("CV 能力", "Capability", "data/ujtl/ujtl_segments.csv（UJTL 编号段）"),
        ("OV-2 活动", "OperationalActivity", "同上（段名即活动）"),
        ("OV-2 角色", "Role", "output/pmtec_spear_report.json 事件 source 分组"),
        ("OV-3 交换", "InformationExchange", "同上，22 事件类型 × 观测计数"),
        ("DIV 信息实体", "InformationEntity", "引擎状态语义 + tc# 本体类型锚定"),
        ("SvcV 服务", "ServiceContract", "services/grpc_server.py _init_app_store（ast 解析）"),
        ("SV 系统", "SystemNode", "grpc_server.py Servicer 类 + config.py 端口 + 页面文件"),
        ("PV 项目", "ProjectActivity", ".github/workflows + Dockerfile"),
    ]
    for view, cls, src in view_rows:
        add(f"| {view} | `dd:{cls}` | {sc[cls]} | {src} |")
    add("")
    add("追溯主链：`CAP ← OA ← EX → ENT`（能力—活动—交换—实体），"
        "旁链 `Role →allocatedTo→ SYS`、`SER →realizes→ CAP`、`SYS →realizes→ CAP`、"
        "`PRO →verifies→ SYS`，全部由 SHACL 形状强制无悬空。")
    add("")

    # ---- CV 能力视点 ----
    add("## 2. CV 能力视点")
    add("")
    add(f"能力基线取自 UJTL（通用联合任务清单）{sc['Capability']} 个编号段，"
        "任务/指标计数为数据集实测值：")
    add("")
    add("| 能力代码 | 能力名称 | 层级 | UJTL任务数 | 衡量指标数 |")
    add("|---|---|---|---:|---:|")
    caps = subjects("Capability")
    for c in caps:
        cid = str(c).split("#")[-1].replace("cap_", "").upper().replace("_", " ")
        tier = TIER.get(cid.split()[0], cid.split()[0])
        add(f"| {cid} | {zh(g, c)} | {tier} | {prop(c, 'taskCount')} | {prop(c, 'measureCount')} |")
    add("")

    # ---- OV-2 ----
    add("## 3. OV-2 作战活动与角色")
    add("")
    add("### 3.1 作战角色（事件源实测分组）")
    add("")
    add("| 角色 | 名称 | 观测事件数 | 配置系统 |")
    add("|---|---|---:|---|")
    for r in subjects("Role"):
        sysn = ", ".join(str(x).split("#")[-1] for x in objs(r, DD.allocatedTo))
        add(f"| `{str(r).split('#')[-1]}` | {zh(g, r)} | {prop(r, 'observedCount')} | {sysn} |")
    add("")
    add("### 3.2 作战活动")
    add("")
    add(f"与能力一一对应（{sc['OperationalActivity']} 项，段名原文即活动名），"
        "此处仅列各活动被哪些信息交换触达：")
    add("")
    oa_hits = defaultdict(list)
    for e in subjects("InformationExchange"):
        for oa in objs(e, DD.tracesTo):
            oa_hits[str(oa)].append(str(e).split("#")[-1])
    rows = []
    for oa in subjects("OperationalActivity"):
        hits = oa_hits.get(str(oa), [])
        if hits:
            rows.append((zh(g, oa), len(hits),
                         ", ".join(h[3:] for h in hits)))
    add("| 作战活动（原文） | 触达交换数 | 交换（事件类型） |")
    add("|---|---:|---|")
    for name, n, lst in sorted(rows, key=lambda x: -x[1]):
        add(f"| {name} | {n} | {lst} |")
    add("")

    # ---- OV-3 ----
    add("## 4. OV-3 信息交换矩阵")
    add("")
    add(f"全部 {sc['InformationExchange']} 行由 SPEAR 实跑报告事件流聚合生成，"
        "观测计数 = 该事件类型在一次完整推演中的出现次数：")
    add("")
    add("| 交换（事件类型） | 观测次数 | 追溯到活动 | 信息实体 | 产生角色 |")
    add("|---|---:|---|---|---|")
    for e in sorted(subjects("InformationExchange"),
                    key=lambda x: -int(prop(x, "observedCount", "0"))):
        eid = str(e).split("#")[-1]
        oa = ", ".join(zh(g, x) for x in objs(e, DD.tracesTo))
        ent = ", ".join(zh(g, x) for x in objs(e, DD.aboutEntity))
        roles = ", ".join(zh(g, x) for x in objs(e, DD.producedBy))
        add(f"| `{eid[3:]}` | {prop(e, 'observedCount')} | {oa} | {ent} | {roles} |")
    add("")

    # ---- DIV ----
    add("## 5. DIV 数据/信息视点（信息实体契约）")
    add("")
    add("| 信息实体 | 名称 | 锚定的目标特性本体类型 |")
    add("|---|---|---|")
    for ent in subjects("InformationEntity"):
        anchors = ", ".join(f"`tc:{str(x).split('#')[-1]}`" for x in objs(ent, DD.tracesTo))
        add(f"| `{str(ent).split('#')[-1]}` | {zh(g, ent)} | {anchors} |")
    add("")
    add("信息实体是 OV-3 交换与目标特性本体（TO 五元组）之间的类型契约：交换必须"
        "aboutEntity 到实体、实体必须锚定 tc# 已声明类，跨本体悬空由 dodaf_check.py 拦截。")
    add("")

    # ---- SvcV ----
    add("## 6. SvcV 服务视点")
    add("")
    add("| 服务契约 | 名称 | 版本 | 类别 | 支撑能力 | 提供方 |")
    add("|---|---|---|---|---|---|")
    for s in subjects("ServiceContract"):
        caps_ = ", ".join(zh(g, x) for x in objs(s, DD.realizes))
        prov = ", ".join(str(x).split("#")[-1] for x in objs(s, DD.providedBy))
        add(f"| `{str(s).split('#')[-1]}` | {zh(g, s)} | {prop(s, 'versionInfo')} "
            f"| {prop(s, 'categoryInfo')} | {caps_} | {prov} |")
    add("")

    # ---- SV ----
    add("## 7. SV 系统视点")
    add("")
    add("| 系统节点 | 名称 | 接口/工件端点 | 支撑能力 |")
    add("|---|---|---|---|")
    for n in subjects("SystemNode"):
        caps_ = ", ".join(zh(g, x) for x in objs(n, DD.realizes))
        add(f"| `{str(n).split('#')[-1]}` | {zh(g, n)} | {prop(n, 'endpointInfo')} | {caps_} |")
    add("")

    # ---- StdV ----
    add("## 8. StdV 标准视点")
    add("")
    for std in subjects("StandardBaseline"):
        add(f"- **{zh(g, std)}**（`{str(std).split('#')[-1]}`）：视点方法与追溯链遵循 "
            "DoDAF 2.02 公开框架；数据侧遵循既有基线——UJTL/CJCSI 3500.02D 任务清单口径、"
            "PROV-O 溯源、OWL 2 DL + HermiT 一致性（tc 基线本体）、SHACL 形状校验、"
            "军用不在场（纯公开资料研究建模，无任何侦察采集能力）。")
    add("")

    # ---- PV ----
    add("## 9. PV 项目视点")
    add("")
    add("| 建设项目 | 验证的系统节点 | 真实工件 |")
    add("|---|---|---|")
    for p in subjects("ProjectActivity"):
        pid = str(p).split("#")[-1]
        vs = ", ".join(str(x).split("#")[-1] for x in objs(p, DD.verifies))
        add(f"| {zh(g, p)} | {vs} | `{dodaf_build.PROJ_ARTIFACTS[pid]}` |")
    add("")

    # ---- 追溯矩阵 + 校验 ----
    add("## 10. 全链路追溯与机器校验")
    add("")
    add("抽一条链走读（机器遍历）：")
    add("")
    ex = DD["ex_intercept_decision"]
    chain = []
    for oa in objs(ex, DD.tracesTo):
        for cap in objs(oa, DD.tracesTo):
            chain.append(f"EX(intercept_decision, {prop(ex, 'observedCount')} 次观测) "
                         f"→ OA({zh(g, oa)}) → CAP({zh(g, cap)})")
    for ent in objs(ex, DD.aboutEntity):
        anchors = ", ".join(f"tc:{str(x).split('#')[-1]}" for x in objs(ent, DD.tracesTo))
        chain.append(f"EX → ENT({zh(g, ent)}) → {anchors}")
    for r in objs(ex, DD.producedBy):
        for sn in objs(r, DD.allocatedTo):
            chain.append(f"EX ← Role({zh(g, r)}) → SYS({str(sn).split('#')[-1]})")
    for line in chain:
        add(f"- {line}")
    add("")
    add("**校验结论**（`dodaf_check.py` 输出，报告落盘 "
        "`pmtec_system/ontology/dodaf_validation_report.json`）：")
    add("")
    add(f"- SHACL 追溯链（9 个形状，覆盖 {sum(sc.values())} 个体）：conforms = "
        f"**{rep['shacl']['conforms']}**，违规 {rep['shacl']['violation_count']} 条")
    add(f"- 跨本体锚点（dd:InformationEntity → tc# 类）：断裂 "
        f"{len(rep['cross_ontology']['broken_anchors'])} 处")
    add("- 基线本体（target_characteristics.owl）HermiT 一致性由既有 "
        "`reason_check.py` 守护；覆盖层为个体投影层，判定程序为 SHACL。")
    add("")
    add("---")
    add("*本文档为脚本生成物：修改任何真实工件后重跑 "
        "`dodaf_build.py → dodaf_check.py → build_dodaf_views.py` 即自动同步。*")

    OUT_MD.parent.mkdir(exist_ok=True)
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"OK: {OUT_MD.relative_to(dodaf_build.BASE)} {len(L)} 行, "
          f"{OUT_MD.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
