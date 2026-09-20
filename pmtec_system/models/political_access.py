"""
P10: 政治准入模型（Political Access Model）
盟友基地准入不确定性的状态机 + 概率演化建模。

数据/观点来源：
  - RAND RRA967-2: U.S. Major Combat Operations in the Indo-Pacific:
    Partner and Ally Views（盟友政治意愿不确定性、冲突升级风险、
    被卷入主动挑衅、联盟承诺可信度、主权与国内政治压力）
  - CRS R47589: 基地准入的政治约束（EDCA 框架、MRF-D 轮换、战时使用谈判）

设计要点：
  - 三态准入状态机：FULL（全面准入）/ RESTRICTED（有限准入）/ DENIED（准入被拒）
  - 每站点维护动态准入概率 current_prob，事件驱动演化：
      * 对手灰色地带挑衅 → provocation_response × 冲击
      * 冲突升级（导弹活动/盟友本土临近打击）→ escalation_sensitivity × 冲击
      * 联盟信誉行动（前推部署/军援/联合演训）→ credibility_weight 增益
      * 国内政治摇摆 → 随机小幅扰动
  - 状态转移含迟滞（恢复阈值高于降级阈值），防止抖动
  - 与实体模型解耦：引擎通过 base_id 查询准入状态
  - MRF-D 六个月轮换周期建模（战时冻结需付政治成本）
  - 日韩战时使用谈判延迟：Decide → Act 之间的政治时延

Maps to DTB Model: Battle Network (政治态势输入) + War Engine (决策约束)
Maps to ASDA: Decide (政治成本评估) + Adapt (准入状态反馈)
"""

import json
import os
import random
from dataclasses import dataclass, field
from enum import Enum

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config",
    "political_access.json",
)


class AccessState(Enum):
    """基地准入三态（P10.1）"""

    FULL = "full"            # 全面准入：战斗行动可用
    RESTRICTED = "restricted"  # 有限准入：仅轮换/补给/后勤，容量折减
    DENIED = "denied"        # 准入被拒：不可用

    @property
    def capacity_factor(self) -> float:
        return {"full": 1.0, "restricted": 0.5, "denied": 0.0}[self.value]

    @property
    def political_cost(self) -> float:
        """使用该基地的政治成本（Decide 环节惩罚项）"""
        return {"full": 0.0, "restricted": 0.5, "denied": 1.0}[self.value]


# 事件类型（RAND 观点映射）
EVENT_GREY_ZONE = "grey_zone_provocation"      # 对手灰色地带行动（菲海警冲撞/东海防空识别区压迫等）
EVENT_ESCALATION = "conflict_escalation"      # 冲突升级（本土临近打击/封锁）
EVENT_REASSURANCE = "alliance_reassurance"    # 联盟信誉行动（前推部署/军援/联合演训）
EVENT_DOMESTIC = "domestic_political_shift"   # 东道国国内政治摇摆（选举/政党轮替）
EVENT_SOVEREIGN_STRIKE = "sovereign_territory_strike"  # 盟友主权领土/专属经济区被打击

EVENT_IMPACT = {
    EVENT_GREY_ZONE: 0.12,      # 基准冲击（配置可覆盖）
    EVENT_ESCALATION: 0.18,
    EVENT_REASSURANCE: 0.08,
    EVENT_DOMESTIC: 0.06,
    EVENT_SOVEREIGN_STRIKE: 0.28,
}


@dataclass
class PoliticalEvent:
    """一次政治事件（可由对手智能体/想定注入）"""

    event_type: str            # 见 EVENT_*
    target_country: str        # 受影响东道国
    intensity: float = 1.0     # 事件强度 0~1
    source: str = "scenario"   # adversary / scenario / analyst
    note: str = ""
    cycle: int = 0


@dataclass
class AllySiteAccess:
    """单个盟友站点的准入状态机（P10.1 + P10.2）"""

    base_id: str
    country: str
    baseline_prob: float
    escalation_sensitivity: float
    provocation_response: float
    credibility_weight: float
    domestic_pressure: float
    wartime_negotiation_delay_h: int
    current_prob: float
    state: AccessState = AccessState.FULL
    state_history: list = field(default_factory=list)
    last_transition_cycle: int = -1
    notes: str = ""

    def _classify(self, recovering: bool) -> AccessState:
        """迟滞分类：降级阈值 vs 恢复阈值分离，防止边界抖动。"""
        th = self._thresholds
        if recovering:
            # 恢复路径需要更高概率才升回上一级
            if self.current_prob >= th.get("recovery_full", 0.75):
                return AccessState.FULL
            if self.current_prob >= th.get("recovery_denied", 0.45):
                return AccessState.RESTRICTED
            return AccessState.DENIED
        else:
            if self.current_prob >= th.get("full", 0.60):
                return AccessState.FULL
            if self.current_prob >= th.get("restricted", 0.30):
                return AccessState.RESTRICTED
            return AccessState.DENIED

    _thresholds: dict = field(default_factory=dict)

    def apply_event(self, event: PoliticalEvent, cycle: int = 0) -> float:
        """应用政治事件 → 概率冲击。返回概率变化量。"""
        base_impact = EVENT_IMPACT.get(event.event_type, 0.05)
        if event.event_type == EVENT_GREY_ZONE:
            # 盟友对挑衅的反应越强（回应意愿）→ 对手行为越能左右准入
            # 但注意方向：对手挑衅使盟友更谨慎（怕被卷入）→ 准入下降
            delta = -base_impact * event.intensity * (
                0.5 + self.provocation_response
            )
        elif event.event_type in (EVENT_ESCALATION, EVENT_SOVEREIGN_STRIKE):
            delta = -base_impact * event.intensity * (
                0.5 + self.escalation_sensitivity
            )
        elif event.event_type == EVENT_REASSURANCE:
            delta = base_impact * event.intensity * self.credibility_weight
        else:  # domestic
            # 国内压力方向随机（执政党更亲美或更疏美）
            direction = 1.0 if random.random() > self.domestic_pressure else -1.0
            delta = direction * base_impact * event.intensity * self.domestic_pressure

        old = self.current_prob
        self.current_prob = max(0.0, min(1.0, self.current_prob + delta))
        return self.current_prob - old

    def transition(self, cycle: int) -> dict | None:
        """按迟滞阈值重判状态；变更时返回转移记录。"""
        recovering = self.current_prob > self.baseline_prob * 0.98
        # 概率显著高于基线视为恢复路径（迟滞）；低于/等于基线走降级路径
        new_state = self._classify(recovering)
        if new_state != self.state:
            record = {
                "base_id": self.base_id,
                "country": self.country,
                "from": self.state.value,
                "to": new_state.value,
                "prob": round(self.current_prob, 4),
                "cycle": cycle,
            }
            self.state_history.append(record)
            self.state = new_state
            self.last_transition_cycle = cycle
            return record
        return None

    def recover(self, per_cycle: float):
        """无事件时缓慢回归基线（政治有惯性，但不永久）。"""
        if self.current_prob < self.baseline_prob:
            self.current_prob = min(
                self.baseline_prob, self.current_prob + per_cycle
            )
        else:
            self.current_prob = max(
                self.baseline_prob, self.current_prob - per_cycle * 0.5
            )

    def to_dict(self) -> dict:
        return {
            "base_id": self.base_id,
            "country": self.country,
            "state": self.state.value,
            "prob": round(self.current_prob, 4),
            "baseline": round(self.baseline_prob, 4),
        }


class MRFDRotation:
    """
    P10.3: 海军陆战队达尔文轮换部队（MRF-D）建模
    六个月轮换周期；换防窗口期内能力下降；
    战时可冻结轮换（assume 激活）但付出政治成本。
    """

    def __init__(self, rotation_days: int = 180, changeover_window: int = 30,
                 freeze_cost: float = 0.35, seed: int = 42):
        self.rotation_days = rotation_days
        self.changeover_window = changeover_window
        self.freeze_cost = freeze_cost
        self.day = 0
        self.frozen = False
        self._rng = random.Random(seed)
        # 随机起始相位（真实轮换时间表不公开）
        self.day = self._rng.randint(0, rotation_days - 1)

    def advance(self, days: float):
        self.day = (self.day + days) % self.rotation_days

    def readiness(self) -> float:
        """MRF-D 战备系数：换防窗口期约 60%，其余 100%。"""
        if self.frozen:
            return 1.0
        in_changeover = (
            self.day < self.changeover_window / 2
            or self.day > self.rotation_days - self.changeover_window / 2
        )
        return 0.6 if in_changeover else 1.0

    def freeze_wartime(self) -> dict:
        """战时冻结轮换（假设式激活）：立即满战备，付出政治成本。"""
        self.frozen = True
        return {
            "action": "mrfd_wartime_freeze",
            "readiness": 1.0,
            "political_cost": self.freeze_cost,
            "note": "MRF-D rotation frozen under wartime assumption "
                    "(bilateral activation at political cost)",
        }

    def to_dict(self) -> dict:
        return {
            "rotation_day": round(self.day, 1),
            "cycle_progress": round(self.day / self.rotation_days, 3),
            "readiness": self.readiness(),
            "frozen": self.frozen,
        }


class PoliticalAccessModel:
    """
    P10 核心：盟友准入模型管理器。
    - from_bases(): 从基地字典列表构建（引擎 load_bases 后调用）
    - inject_event(): 注入政治事件（对手灰色地带行动/想定）
    - update_cycle(): 每 ASDA 周期演化（恢复 + 冲突升级度）
    - available_bases() / political_risk_exposure(): 决策接口
    """

    def __init__(self, config_path: str = None, seed: int = 42):
        self._rng = random.Random(seed)
        self.config_path = config_path or CONFIG_PATH
        self.config = self._load_config()
        self.sites: dict[str, AllySiteAccess] = {}
        self.events_log: list[PoliticalEvent] = []
        self.transitions_log: list[dict] = []
        dyn = self.config.get("dynamics", {})
        self.mrfd = MRFDRotation(
            rotation_days=dyn.get("mrfd_rotation_days", 180),
            changeover_window=dyn.get("mrfd_changeover_window_days", 30),
            freeze_cost=dyn.get("mrfd_wartime_freeze_cost", 0.35),
        )
        self.escalation_level = 0.0  # 全局冲突升级度 0~1
        self.ally_countries: set = set()

    # ---------------- 初始化 ----------------

    def _load_config(self) -> dict:
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {"countries": {}, "defaults": {}, "thresholds": {},
                    "dynamics": {}}

    def _country_params(self, country: str) -> dict:
        c = self.config.get("countries", {}).get(country)
        d = self.config.get("defaults", {})
        if not c:
            c = {}
        merged = {k: c.get(k, d.get(k, 0.7)) for k in (
            "baseline_access_prob", "escalation_sensitivity",
            "provocation_response", "credibility_weight",
            "domestic_pressure", "wartime_negotiation_delay_h")}
        merged["notes"] = c.get("notes", "")
        return merged

    @classmethod
    def from_bases(cls, bases: list[dict], config_path: str = None,
                   seed: int = 42) -> "PoliticalAccessModel":
        """从引擎基地列表构建。

        v2 数据用 access_uncertainty == "host_nation" 精确标记东道国站点；
        v1 数据缺失该字段时，回退为"国家在 political_access.json 配置中出现
        即视为东道国站点"的推断（不含 US 本土/属地）。
        """
        model = cls(config_path=config_path, seed=seed)
        th = model.config.get("thresholds", {})
        known_countries = set(model.config.get("countries", {}).keys())
        for b in bases:
            unc = b.get("access_uncertainty")
            if unc is None:
                # P13-fix: v1 兜底——配置里有的国家即东道国（排除 USA）
                country = b.get("country", "")
                if not country or country not in known_countries:
                    continue
            elif unc != "host_nation":
                continue
            p = model._country_params(b.get("country", ""))
            site = AllySiteAccess(
                base_id=b["id"],
                country=b.get("country", ""),
                baseline_prob=p["baseline_access_prob"],
                escalation_sensitivity=p["escalation_sensitivity"],
                provocation_response=p["provocation_response"],
                credibility_weight=p["credibility_weight"],
                domestic_pressure=p["domestic_pressure"],
                wartime_negotiation_delay_h=p["wartime_negotiation_delay_h"],
                current_prob=p["baseline_access_prob"],
                notes=p.get("notes", ""),
            )
            site._thresholds = th
            site.state = site._classify(recovering=False)
            model.sites[b["id"]] = site
            model.ally_countries.add(b.get("country", ""))
        return model

    # ---------------- 事件与演化 ----------------

    def inject_event(self, event: PoliticalEvent):
        """注入政治事件，作用于目标国家的全部站点。立即应用概率冲击。"""
        self.events_log.append(event)
        for site in self.sites.values():
            if site.country == event.target_country:
                site.apply_event(event, event.cycle)

    def update_cycle(
        self,
        cycle: int,
        missile_activity: float = 0.0,
        events: list[PoliticalEvent] = None,
    ) -> list[dict]:
        """
        每 ASDA 周期演化一次（Adapt 环节调用）。
        missile_activity: 本周期对手导弹活动强度 0~1（冲突升级度输入）
        events: 本周期新注入事件（已 inject 的不重复）
        返回本周期发生的状态转移记录列表。
        """
        dyn = self.config.get("dynamics", {})
        # 全局冲突升级度：导弹活动驱动，缓慢衰减
        self.escalation_level = max(
            0.0,
            min(1.0, self.escalation_level * 0.95
                + missile_activity * dyn.get("escalation_per_missile_cycle", 0.05)),
        )

        for ev in (events or []):
            self.inject_event(ev)

        transitions = []
        for site in self.sites.values():
            # 冲突升级对每个站点的持续压力
            if self.escalation_level > 0.05:
                site.apply_event(PoliticalEvent(
                    event_type=EVENT_ESCALATION,
                    target_country=site.country,
                    intensity=self.escalation_level * 0.3,  # 每周期小幅
                    source="dynamics", cycle=cycle,
                ), cycle)
            else:
                site.recover(dyn.get("recovery_per_cycle", 0.015))
            record = site.transition(cycle)
            if record:
                transitions.append(record)
                self.transitions_log.append(record)

        # MRF-D 轮换推进（ASDA 周期 ≈ 10 秒仿真时间）
        self.mrfd.advance(10.0 / 86400.0)
        return transitions

    # ---------------- 决策接口 ----------------

    def access_state(self, base_id: str) -> AccessState:
        site = self.sites.get(base_id)
        if site is None:
            return AccessState.FULL  # 美国主权/领地站点无准入约束
        return site.state

    def available_bases(self, all_base_ids: list[str]) -> list[str]:
        """可用基地集合：非盟友站点 + FULL/RESTRICTED 盟友站点。"""
        return [
            bid for bid in all_base_ids
            if self.access_state(bid) != AccessState.DENIED
        ]

    def political_cost(self, base_id: str) -> float:
        return self.access_state(base_id).political_cost

    def negotiation_delay_h(self, base_id: str) -> float:
        """战时使用谈判延迟（小时）：主权站点 0，盟友按国家参数。"""
        site = self.sites.get(base_id)
        return float(site.wartime_negotiation_delay_h) if site else 0.0

    def political_risk_exposure(
        self, assets_by_base: dict[str, float]
    ) -> float:
        """
        政治风险敞口：Σ 资产价值 × (1 - 准入系数)。
        衡量部署方案中可能被政治拒止困住的能力比重（Pareto 新目标）。
        """
        risk = 0.0
        for bid, value in assets_by_base.items():
            if value <= 0:
                continue
            risk += value * (1.0 - self.access_state(bid).capacity_factor)
        return risk

    def snapshot(self) -> dict:
        by_country = {}
        for site in self.sites.values():
            by_country.setdefault(site.country, []).append(site.to_dict())
        return {
            "ally_sites": len(self.sites),
            "ally_countries": sorted(self.ally_countries),
            "escalation_level": round(self.escalation_level, 3),
            "by_country": by_country,
            "mrfd": self.mrfd.to_dict(),
            "recent_transitions": self.transitions_log[-10:],
            "events_count": len(self.events_log),
        }

    # ---------------- 敏感性分析支持（P10.2） ----------------

    def perturb_baselines(self, sigma: float = 0.10, seed: int = None):
        """蒙特卡洛敏感性分析：国家基线准入概率 ± 正态扰动。"""
        rng = random.Random(seed if seed is not None else self._rng.randint(0, 99999))
        for site in self.sites.values():
            delta = rng.gauss(0.0, sigma)
            site.baseline_prob = max(0.05, min(0.99, site.baseline_prob + delta))
            site.current_prob = site.baseline_prob
            site.state = site._classify(recovering=False)
