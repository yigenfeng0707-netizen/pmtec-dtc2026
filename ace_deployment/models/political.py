"""
P10: ACE 政治准入约束模型（Level 2 自包含轻量版）
盟友基地准入不确定性进入 ACE 分布式部署与紧急转移决策。

数据/观点来源（与 pmtec_system/models/political_access.py 同源）：
  - RAND RRA967-2: 盟友政治意愿不确定性、冲突升级风险、联盟可信度
  - CRS R47589: EDCA 框架、基地准入政治约束

设计（相对 pmtec_system 完整版的简化，保持 Level 2 交付物独立运行）：
  - PoliticalConstraint: 每站点三态准入 + 容量折减 + 政治成本 + 谈判延迟
  - 初始状态由国家基线准入概率确定性导出（可复现）
  - 三场景接口（P10 验收）：FULL 准入 / 演化准入 / 全拒
  - DeploymentOptimizer/TransferPlanner/Optimizer 的政治约束集成
    见各算法文件（DENIED 排除、RESTRICTED 打折、风险敞口目标）

Maps to DTB Model: Battle Network (准入态势) + War Engine (部署约束)
Maps to ASDA: Decide (政治成本权衡) + Adapt (准入场景重优化)
"""

# 国家基线准入概率与参数（RAND 观点量化近似；与 pmtec_system 配置一致）
COUNTRY_PARAMS = {
    "Japan": {"prob": 0.85, "delay_h": 12},
    "South Korea": {"prob": 0.80, "delay_h": 24},
    "Philippines": {"prob": 0.65, "delay_h": 6},
    "Australia": {"prob": 0.92, "delay_h": 4},
    "Singapore": {"prob": 0.55, "delay_h": 8},
    "Marshall Islands": {"prob": 0.88, "delay_h": 2},
    "British Indian Ocean Territory": {"prob": 0.90, "delay_h": 3},
}
DEFAULT_PARAMS = {"prob": 0.70, "delay_h": 12}

# 三态准入参数
CAPACITY_FACTOR = {"full": 1.0, "restricted": 0.5, "denied": 0.0}
POLITICAL_COST = {"full": 0.0, "restricted": 0.5, "denied": 1.0}

# 状态判定阈值（同 pmtec_system thresholds）
TH_FULL = 0.60
TH_RESTRICTED = 0.30

SCENARIO_FULL = "full_access"        # 政治无约束基线（原 P1-P8 行为）
SCENARIO_EVOLVED = "evolved_access"  # 演化准入（国家基线概率导出）
SCENARIO_DENIED = "all_denied"      # 全部盟友站点被拒（最坏情形压力测试）


class PoliticalConstraint:
    """
    站点级政治准入约束（ACE 侧）。

    用法：
        pc = PoliticalConstraint.from_geojson_props(props_list)  # 演化场景
        pc.set_scenario(SCENARIO_DENIED)                          # 场景切换
        pc.accessible("PH-BASA")  -> bool
        pc.capacity_factor(bid)   -> 0.0~1.0
    """

    def __init__(self):
        # base_id -> {state, prob, delay_h, country}
        self._sites: dict[str, dict] = {}
        self.scenario = SCENARIO_EVOLVED

    # ---------------- 构建 ----------------

    @classmethod
    def from_geojson_props(cls, props_list: list[dict]) -> "PoliticalConstraint":
        """从 GeoJSON properties 列表构建（access_uncertainty=host_nation 的站点受约束）。"""
        pc = cls()
        for p in props_list:
            if p.get("access_uncertainty") != "host_nation":
                continue
            country = p.get("country", "")
            params = COUNTRY_PARAMS.get(country, DEFAULT_PARAMS)
            prob = params["prob"]
            state = (
                "full" if prob >= TH_FULL
                else "restricted" if prob >= TH_RESTRICTED
                else "denied"
            )
            pc._sites[p.get("id", "")] = {
                "state": state,
                "prob": prob,
                "delay_h": params["delay_h"],
                "country": country,
            }
        return pc

    def set_scenario(self, scenario: str):
        """三场景切换（P10 验收：Full / 演化 / 全拒）。"""
        self.scenario = scenario
        if scenario == SCENARIO_FULL:
            for s in self._sites.values():
                s["state"] = "full"
        elif scenario == SCENARIO_DENIED:
            for s in self._sites.values():
                s["state"] = "denied"
        elif scenario == SCENARIO_EVOLVED:
            for s in self._sites.values():
                s["state"] = (
                    "full" if s["prob"] >= TH_FULL
                    else "restricted" if s["prob"] >= TH_RESTRICTED
                    else "denied"
                )
        else:
            raise ValueError(f"Unknown political scenario: {scenario}")

    def apply_event(self, base_id: str, prob_delta: float):
        """注入概率冲击（灰色地带/升级/信誉事件），重判状态。"""
        site = self._sites.get(base_id)
        if not site:
            return
        site["prob"] = max(0.0, min(1.0, site["prob"] + prob_delta))
        site["state"] = (
            "full" if site["prob"] >= TH_FULL
            else "restricted" if site["prob"] >= TH_RESTRICTED
            else "denied"
        )

    # ---------------- 查询 ----------------

    def constrained_ids(self) -> set:
        return set(self._sites.keys())

    def state(self, base_id: str) -> str:
        site = self._sites.get(base_id)
        return site["state"] if site else "full"

    def accessible(self, base_id: str) -> bool:
        """DENIED 不可用；full/restricted 可用（restricted 容量打折）。"""
        return self.state(base_id) != "denied"

    def capacity_factor(self, base_id: str) -> float:
        return CAPACITY_FACTOR[self.state(base_id)]

    def political_cost(self, base_id: str) -> float:
        return POLITICAL_COST[self.state(base_id)]

    def negotiation_delay_h(self, base_id: str) -> float:
        site = self._sites.get(base_id)
        return site["delay_h"] if site else 0.0

    def political_risk_exposure(self, assets_by_base: dict[str, float]) -> float:
        """政治风险敞口：Σ 资产价值 × (1 - 准入系数)（Pareto 目标 6）。"""
        risk = 0.0
        for bid, value in assets_by_base.items():
            if value > 0:
                risk += value * (1.0 - self.capacity_factor(bid))
        return risk

    def snapshot(self) -> dict:
        by_state = {"full": 0, "restricted": 0, "denied": 0}
        for s in self._sites.values():
            by_state[s["state"]] += 1
        return {
            "scenario": self.scenario,
            "constrained_sites": len(self._sites),
            "by_state": by_state,
            "countries": sorted({s["country"] for s in self._sites.values()}),
        }
