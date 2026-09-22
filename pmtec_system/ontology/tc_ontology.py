# -*- coding: utf-8 -*-
"""目标特性本体 TO = <E, A, R, F, Ax>（OWL 2 DL）

E/A/R/F/Ax 五元组落盘，输入为一级交付物 indopacom_bases_v2.geojson（67 实体）。
遵循最小完备性：仅建回答"评审三问"所需的最简类公理集，不做层级堆砌。
"""
import json
from pathlib import Path

from owlready2 import (Not, Thing, DataProperty, FunctionalProperty,
                       ObjectProperty, TransitiveProperty, get_ontology)
from owlready2.disjoint import AllDisjoint

REPO_ROOT = Path(__file__).resolve().parents[2]
GEOJSON_PATH = REPO_ROOT / "过程脚本归档" / "indopacom_bases_v2.geojson"
ONTOLOGY_DIR = Path(__file__).resolve().parent
ONTOLOGY_IRI = "http://pmtec.example.org/tc"
ONTOLOGY_FILE = ONTOLOGY_DIR / "target_characteristics.owl"

# 上层本体对齐声明（BFO: 独立实体/依附实体），复用而非自造类别体系
BFO_ALIGNMENT = ("BFO-independent-continuant: MilitaryInstallation; "
                 "BFO-dependent-continuant: FacilityPart, AccessState")


def _ind_name(raw_id: str) -> str:
    return "base_" + raw_id.replace("-", "_").replace("/", "_").replace(" ", "_")


def build_ontology():
    onto = get_ontology(ONTOLOGY_IRI + ".owl")
    onto._default_namespace = ENTITY_NS

    with onto:

        class MilitaryInstallation(Thing):
            """E-实体集：基地类（BFO 独立实体）"""

        class AirBase(MilitaryInstallation):
            pass

        class NavalBase(MilitaryInstallation):
            pass

        class LandBase(MilitaryInstallation):
            pass

        class SupportSite(MilitaryInstallation):
            pass

        AllDisjoint([AirBase, NavalBase, LandBase, SupportSite])  # 互斥；完备性由 populate_abox 分类规则保证

        class FacilityPart(Thing):
            """E-实体集：设施部件类（BFO 依附实体）"""

        class Runway(FacilityPart):
            pass

        class Hangar(FacilityPart):
            pass

        class FuelDepot(FacilityPart):
            pass

        class RadarSite(FacilityPart):
            pass

        class DefensePosition(FacilityPart):
            pass

        class Aircraft(Thing):
            pass

        class AccessState(Thing):
            """F-行为函数的状态域：政治准入三态"""

        class OpenState(AccessState):
            pass

        class RestrictedState(AccessState):
            pass

        class DeniedState(AccessState):
            pass

        AllDisjoint([OpenState, RestrictedState, DeniedState])

        # A-属性集：可观测特性 = 直接数据属性；功能/状态/脆弱性见下
        class observableProperty(DataProperty):
            pass

        class runwayLengthM(observableProperty, FunctionalProperty):
            domain = [Runway]
            range = [float]

        class personnelCount(observableProperty, FunctionalProperty):
            domain = [MilitaryInstallation]
            range = [int]

        class areaAcres(observableProperty, FunctionalProperty):
            domain = [MilitaryInstallation]
            range = [float]

        class latitude(observableProperty, FunctionalProperty):
            domain = [MilitaryInstallation]
            range = [float]

        class longitude(observableProperty, FunctionalProperty):
            domain = [MilitaryInstallation]
            range = [float]

        class tierLevel(observableProperty, FunctionalProperty):
            domain = [MilitaryInstallation]
            range = [int]

        class branchCode(observableProperty, FunctionalProperty):
            domain = [MilitaryInstallation]
            range = [str]

        class accessUncertainty(observableProperty, FunctionalProperty):
            """可观测但跨源口径歧义：host_nation/sovereign/territory——不可推断属性，见失效边界"""
            domain = [MilitaryInstallation]
            range = [str]

        class countryName(observableProperty, FunctionalProperty):
            domain = [MilitaryInstallation]
            range = [str]

        class regionName(observableProperty, FunctionalProperty):
            domain = [MilitaryInstallation]
            range = [str]

        class basedAircraft(observableProperty, FunctionalProperty):
            """驻防机型清单（自由文本，杀伤网 Match Effector 查询输入）"""
            domain = [MilitaryInstallation]
            range = [str]

        class singleRunwayDependency(DataProperty, FunctionalProperty):
            """脆弱性特性：推断规则"跑道数==1 => 单点依赖"导出（规则实现见 populate_abox）"""
            domain = [MilitaryInstallation]
            range = [bool]

        class hasAccessState(ObjectProperty):
            """状态特性：随外部条件演化"""
            domain = [MilitaryInstallation]
            range = [AccessState]

        # R-关系集：从属（传闭）与支撑
        class hasPart(ObjectProperty, TransitiveProperty):
            domain = [MilitaryInstallation]
            range = [FacilityPart]

        class partOf(ObjectProperty):
            pass

        partOf.inverse_property = hasPart

        # Ax-公理集
        state_open = OpenState("state_open")
        RestrictedState("state_restricted")
        state_denied = DeniedState("state_denied")

        AirBase.equivalent_to = [hasPart.some(Runway)]  # Ax1: 航空基地 ≡ 至少有一条跑道的基地

        Runway.is_a = [partOf.some(MilitaryInstallation)]  # Ax2: 跑道必从属于某基地

        class LaunchCapable(Thing):
            """可战性判定 Judge(e, c0)：准入态非 Denied 即判定可出击"""
            equivalent_to = [hasAccessState.some(OpenState | RestrictedState)]

        class AccessDeniedSite(Thing):
            """Ax3 翻转条件形式化：Denied => 非可战（∃c: Judge(e,c) != Judge(e,c0)）"""
            equivalent_to = [hasAccessState.value(state_denied)]
            is_a = [Not(LaunchCapable)]

        onto.public_comment = BFO_ALIGNMENT
        return onto


def populate_abox(onto, geojson_path=GEOJSON_PATH):
    data = json.loads(geojson_path.read_text(encoding="utf-8"))
    state_open = onto.OpenState("state_open")
    onto.RestrictedState("state_restricted")
    onto.DeniedState("state_denied")

    count = 0
    for feat in data["features"]:
        p = feat["properties"]
        branch = str(p.get("branch", ""))
        if p.get("runway_m"):
            cls = onto.AirBase
        elif "USN" in branch:
            cls = onto.NavalBase
        elif any(b in branch for b in ("Army", "USMC")):
            cls = onto.LandBase
        else:
            cls = onto.SupportSite

        ind = cls(_ind_name(p["id"]))
        ind.label = [p.get("name", p["id"])]
        if p.get("runway_m"):
            rw = onto.Runway(_ind_name(p["id"]) + "_rwy01")
            rw.runwayLengthM = float(p["runway_m"])
            ind.hasPart.append(rw)
            ind.singleRunwayDependency = True  # 推断规则：数据集中每基地至多一条跑道记录
        if p.get("personnel") is not None:
            ind.personnelCount = int(p["personnel"])
        if p.get("fy24_total_acres") is not None:
            ind.areaAcres = float(p["fy24_total_acres"])
        ind.longitude = float(feat["geometry"]["coordinates"][0])
        ind.latitude = float(feat["geometry"]["coordinates"][1])
        if p.get("tier") is not None:
            ind.tierLevel = int(p["tier"])
        ind.branchCode = branch
        ind.accessUncertainty = str(p.get("access_uncertainty", ""))
        ind.countryName = str(p.get("country", ""))
        ind.regionName = str(p.get("region", ""))
        if p.get("aircraft"):
            ind.basedAircraft = str(p["aircraft"])
        ind.hasAccessState.append(state_open)  # 基准条件 c0：和平时期全开放
        count += 1
    return count


ENTITY_NS = ONTOLOGY_IRI + "#"


def export(onto, path=ONTOLOGY_FILE):
    onto.save(file=str(path), format="rdfxml")
    # 实体命名空间统一锚定为 tc#（owlready2 默认以文档 IRI 为 base，导出相对 IRI 会落在 tc.owl#）
    text = path.read_text(encoding="utf-8")
    text = text.replace(f'xml:base="{ONTOLOGY_IRI}.owl#"', f'xml:base="{ENTITY_NS}"')
    text = text.replace(f'xml:base="{ONTOLOGY_IRI}.owl"', f'xml:base="{ENTITY_NS}"')
    # 相对 IRI "#x" 对以 # 结尾的 base 解析有歧义（出现 tc##x），统一改写为绝对 IRI
    text = text.replace('rdf:about="#', f'rdf:about="{ENTITY_NS}')
    text = text.replace('rdf:resource="#', f'rdf:resource="{ENTITY_NS}')
    text = text.replace(f'xmlns="{ONTOLOGY_IRI}.owl#"', f'xmlns="{ENTITY_NS}"')
    path.write_text(text, encoding="utf-8")
    return path


if __name__ == "__main__":
    onto = build_ontology()
    n = populate_abox(onto)
    out = export(onto)
    print(f"OK: {n} installations, {len(list(onto.individuals()))} individuals -> {out.name}")
