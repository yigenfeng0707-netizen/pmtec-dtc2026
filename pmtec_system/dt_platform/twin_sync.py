"""P13 Digital Twin Sync Layer - 虚实同步引擎 (DTC 2026 Level 3).

让 PMTEC 从"仿真系统"升级为真正的数字孪生系统：

  物理域 (Physical)          虚拟域 (Virtual/Twin)
  ─────────────────          ─────────────────────
  基地实体/飞机/传感器   ←→  基地孪生体 (就绪度模型 × 政治准入)
  来袭导弹实体           ←→  威胁孪生体 (拦截概率预测模型)
  战场整体态势           ←→  场景孪生实例 (DTRegistry 注册)

每个孪生体维护：
  - physical: 物理域观测状态（来自仿真引擎）
  - virtual:  虚拟域模型状态（模型预测值）
  - deviation: 虚实偏差（|预测 - 实际|，孪生价值的量化）
  - fidelity:  保真度（1 - 平均偏差，随同步滚动更新）

每 ASDA Adapt 周期同步一次；结果写入 DTRegistry（update_stats）、
get_state_dict（大屏 WebSocket）、LLM 分析上下文（AI 参谋官）。
"""

import time
from collections import deque

try:
    from dt_platform.dt_registry import DTStatus
except ImportError:  # allow standalone import for unit testing
    DTStatus = None

MAX_THREAT_TWINS = 120  # bounded memory for threat twin history
MAX_DEVIATIONS_PER_TWIN = 20


class EntityTwin:
    """单个数字孪生实例：物理镜像 + 虚拟模型 + 虚实偏差追踪."""

    def __init__(self, twin_id: str, kind: str, name: str):
        self.twin_id = twin_id
        self.kind = kind  # "base" | "threat" | "scenario"
        self.name = name
        self.created_at = time.time()
        self.last_sync = None
        self.sync_count = 0
        self.physical: dict = {}  # 物理域观测
        self.virtual: dict = {}  # 虚拟域模型
        self.fidelity = 1.0
        self._deviations: deque = deque(maxlen=MAX_DEVIATIONS_PER_TWIN)

    def record_deviation(self, predicted: float, actual: float):
        """记录一次虚实偏差并滚动更新保真度。"""
        dev = abs(predicted - actual)
        self._deviations.append(dev)
        self.fidelity = 1.0 - (sum(self._deviations) / len(self._deviations))

    @property
    def mean_deviation(self) -> float:
        if not self._deviations:
            return 0.0
        return sum(self._deviations) / len(self._deviations)

    def to_dict(self) -> dict:
        return {
            "twin_id": self.twin_id,
            "kind": self.kind,
            "name": self.name,
            "sync_count": self.sync_count,
            "last_sync": self.last_sync,
            "fidelity": round(self.fidelity, 3),
            "mean_deviation": round(self.mean_deviation, 3),
            "physical": self.physical,
            "virtual": self.virtual,
        }


class TwinSyncManager:
    """数字孪生同步管理器：物理域 → 孪生体 → 注册表 → 大屏/AI."""

    def __init__(self, registry=None):
        self.registry = registry
        self.twins: dict[str, EntityTwin] = {}
        self.sync_count = 0
        self.last_sync_wall = None
        # 虚拟域拦截概率模型：按导弹类型的滚动基线（贝叶斯式更新）
        self._intercept_model: dict[str, dict] = {}
        # P13-2 虚拟域策略模型：(弹型, 拦截策略) -> {success, n}
        # 孪生层用真实交战结局校准各策略对各类导弹的实效，
        # 证据充分时反哺 Decide 环节的策略选择（预测性反哺）
        self._strategy_model: dict[tuple, dict] = {}
        self.strategy_overrides = 0  # 孪生建议覆盖 RL 决策的次数

    # ------------------------------------------------------------------
    # 同步入口（每 ASDA Adapt 周期调用一次）
    # ------------------------------------------------------------------
    def sync(self, engine):
        """从引擎拉取物理域状态，更新全部孪生体。"""
        self.sync_count += 1
        self.last_sync_wall = time.time()

        bases = engine._bases
        entities = engine._entities
        missiles = engine._missiles

        # --- 1. 基地孪生体（盟友基地就绪度：资产 × 政治准入）---
        self._sync_base_twins(engine, bases, entities)
        # --- 2. 威胁孪生体（来袭导弹 + 拦截概率预测）---
        self._sync_threat_twins(missiles)
        # --- 3. 拦截概率虚拟模型更新（用已判定的结局校准预测）---
        self._update_intercept_model()
        # --- 4. 场景级孪生实例状态推进 ---
        self._sync_scenario_instance(engine)
        # --- 5. 回写注册表 ---
        self._publish_to_registry(engine)

    # ------------------------------------------------------------------
    def _sync_base_twins(self, engine, bases, entities):
        pol = engine.political
        pol_sites = {}
        if pol and getattr(pol, "sites", None):
            pol_sites = {
                sid: s.to_dict() for sid, s in pol.sites.items()
            }
        for b in bases:
            tid = f"TWIN-BASE-{b['id']}"
            twin = self.twins.get(tid)
            if twin is None:
                twin = EntityTwin(tid, "base", b.get("name") or b["id"])
                self.twins[tid] = twin
            ac_all = [
                e
                for e in entities
                if isinstance_attr(e, "base_id") and e.base_id == b["id"]
                and not is_sensor(e)
            ]
            ac_active = [e for e in ac_all if e.status == "active"]
            sensors = [
                s for s in engine._sensors if s.base_id == b["id"]
            ]
            sensors_active = [s for s in sensors if s.status == "active"]
            site = pol_sites.get(b["id"])
            access_prob = site["prob"] if site else 1.0

            twin.sync_count += 1
            twin.last_sync = engine.clock.current.sim_seconds
            # 物理域：实际可用资产比例
            avail_physical = len(ac_active) / max(len(ac_all), 1)
            # 虚拟域：模型预测就绪度 = 资产在位 × 政治准入概率
            readiness_virtual = round(avail_physical * access_prob, 3)
            twin.physical = {
                "aircraft_active": len(ac_active),
                "aircraft_total": len(ac_all),
                "sensors_active": len(sensors_active),
                "sensors_total": len(sensors),
                "political_state": (site or {}).get("state", "n/a"),
                "availability": round(avail_physical, 3),
            }
            twin.virtual = {
                "readiness_model": readiness_virtual,
                "access_prob": round(access_prob, 3),
            }
            # 偏差：虚拟就绪度 vs 物理可用性（政治模型失准即偏差）
            twin.record_deviation(readiness_virtual, avail_physical)

    def _sync_threat_twins(self, missiles):
        seen = set()
        for m in missiles:
            tid = f"TWIN-THR-{m.id}"
            seen.add(tid)
            twin = self.twins.get(tid)
            if twin is None:
                twin = EntityTwin(tid, "threat", m.subtype)
                self.twins[tid] = twin
            twin.sync_count += 1
            twin.last_sync = m.timestamp
            model = self._intercept_model.get(m.subtype, {"p": 0.5, "n": 0})
            twin.physical = {
                "lat": round(m.lat, 3),
                "lon": round(m.lon, 3),
                "status": m.status,
            }
            twin.virtual = {
                "predicted_intercept_prob": round(model["p"], 3),
                "model_samples": model["n"],
            }
        # 清理已终结的威胁孪生体（保留最近 N 个）
        done = [tid for tid, t in self.twins.items()
                if t.kind == "threat" and tid not in seen]
        for tid in done:
            twin = self.twins.pop(tid)
            if twin.physical.get("status"):
                self.twins[f"HIST-{tid}"] = twin
        hist = [k for k in self.twins if k.startswith("HIST-")]
        if len(hist) > MAX_THREAT_TWINS:
            for k in hist[: len(hist) - MAX_THREAT_TWINS]:
                self.twins.pop(k, None)

    def _update_intercept_model(self):
        """威胁孪生终结时，用实际结局校准该弹型的预测模型。"""
        for tid in list(self.twins.keys()):
            if not tid.startswith("HIST-TWIN-THR-"):
                continue
            twin = self.twins[tid]
            if twin.virtual.get("model_updated"):
                continue
            status = twin.physical.get("status")
            if status not in ("destroyed", "neutralized"):
                continue
            mtype = twin.name
            actual = 1.0 if twin.physical.get("outcome") == "intercepted" else 0.0
            model = self._intercept_model.setdefault(
                mtype, {"p": 0.5, "n": 0}
            )
            # 指数滚动更新
            alpha = 1.0 / (model["n"] + 2)
            model["p"] = (1 - alpha) * model["p"] + alpha * actual
            model["n"] += 1
            twin.virtual["model_updated"] = True
            # 记录预测 vs 实际偏差
            twin.record_deviation(
                twin.virtual.get("predicted_intercept_prob", 0.5), actual
            )

    def _sync_scenario_instance(self, engine):
        tid = "TWIN-SCENARIO-MAIN"
        twin = self.twins.get(tid)
        if twin is None:
            twin = EntityTwin(tid, "scenario", "PMTEC 场景孪生")
            self.twins[tid] = twin
        twin.sync_count += 1
        twin.last_sync = engine.clock.current.sim_seconds
        twin.physical = {
            "sim_seconds": round(engine.clock.current.sim_seconds, 1),
            "asda_cycle": engine.asda_cycle_count,
            "network_vulnerability": engine._calc_network_vulnerability(),
        }
        twin.virtual = {
            "escalation_level": (
                round(engine.political.escalation_level, 3)
                if engine.political and engine.political.sites
                else None
            ),
            "adversary_aggression": engine.adversary.baseline_aggression,
        }

    def _publish_to_registry(self, engine):
        if not self.registry:
            return
        try:
            inst = self.registry.get_default()
            if inst:
                self.registry.update_stats(
                    inst.instance_id, {"twin_sync": self.summary()}
                )
                if DTStatus is not None and inst.status != DTStatus.RUNNING:
                    self.registry.update_status(inst.instance_id, DTStatus.RUNNING)
        except Exception:
            pass  # twin layer must never break the sim

    # ------------------------------------------------------------------
    def record_threat_outcome(
        self, missile_id: str, intercepted: bool, missile_type: str = None,
        strategy: str = None,
    ):
        """物理域威胁结局回写（引擎在导弹销毁时调用）。

        同时校准两个虚拟域模型：拦截概率基线 + (弹型, 策略) 实效。
        """
        twin = self.twins.get(
            f"HIST-TWIN-THR-{missile_id}"
        ) or self.twins.get(f"TWIN-THR-{missile_id}")
        if twin:
            twin.physical["status"] = "destroyed"
            twin.physical["outcome"] = "intercepted" if intercepted else "impact"
        mtype = missile_type or (twin.name if twin else None)
        if mtype and strategy:
            key = (mtype, strategy)
            m = self._strategy_model.setdefault(key, {"success": 0, "n": 0})
            m["n"] += 1
            if intercepted:
                m["success"] += 1

    def recommend_strategy(
        self, missile_type: str, candidates: list[str], min_samples: int = 3
    ):
        """孪生前推预测：返回证据支持下对该弹型最优的拦截策略。

        返回 (strategy, predicted_prob) 或 (None, 0.0)（证据不足时不干预 RL）。
        Laplace 平滑：rate = (success + 1) / (n + 2)。
        """
        best, best_rate, best_n = None, -1.0, 0
        for strat in candidates:
            m = self._strategy_model.get((missile_type, strat))
            if not m or m["n"] < min_samples:
                continue
            rate = (m["success"] + 1) / (m["n"] + 2)
            if rate > best_rate:
                best, best_rate, best_n = strat, rate, m["n"]
        if best is None:
            return None, 0.0
        return best, round(best_rate, 3)

    def strategy_model_summary(self) -> dict:
        return {
            f"{k[0]}|{k[1]}": {
                "success_rate": round(v["success"] / max(v["n"], 1), 3),
                "n": v["n"],
            }
            for k, v in self._strategy_model.items()
        }

    def summary(self) -> dict:
        by_kind: dict[str, int] = {}
        fid_sum, fid_n = 0.0, 0
        worst = []
        # P13.3-fix: 原子快照，防止与仿真主线程 sync() 增删 twins 的竞态
        for t in list(self.twins.values()):
            by_kind[t.kind] = by_kind.get(t.kind, 0) + 1
            fid_sum += t.fidelity
            fid_n += 1
            if t.mean_deviation > 0.05:
                worst.append(
                    {
                        "twin_id": t.twin_id,
                        "name": t.name,
                        "deviation": round(t.mean_deviation, 3),
                    }
                )
        worst.sort(key=lambda x: -x["deviation"])
        return {
            "total_twins": len(self.twins),
            "by_kind": by_kind,
            "avg_fidelity": round(fid_sum / fid_n, 3) if fid_n else 1.0,
            "engine_syncs": self.sync_count,
            "last_sync_wall": self.last_sync_wall,
            "deviating_twins": worst[:5],
            "intercept_model": {
                k: {"p": round(v["p"], 3), "n": v["n"]}
                for k, v in self._intercept_model.items()
            },
            "strategy_model": self.strategy_model_summary(),
            "strategy_overrides": self.strategy_overrides,
        }

    def top_twins(self, kind: str = None, limit: int = 6) -> list[dict]:
        # P13.3-fix: 原子快照，REST 线程调用时防止与主线程 sync() 增删竞态
        twins = [
            t for t in list(self.twins.values()) if kind is None or t.kind == kind
        ]
        twins.sort(key=lambda t: -t.sync_count)
        return [t.to_dict() for t in twins[:limit]]


# ----------------------------------------------------------------------
def isinstance_attr(obj, attr: str) -> bool:
    return hasattr(obj, attr)


def is_sensor(e) -> bool:
    return hasattr(e, "detection_range_km")
