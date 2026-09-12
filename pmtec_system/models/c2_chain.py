"""
P11: INDOPACOM 指挥控制组织架构与指挥链模型（Command Chain）

数据来源（CRS IF12175 / CRS R47589，逐条对应见 config/indopacom_c2.json）：
  - 战区级：INDOPACOM（檀香山 Camp H.M. Smith，约 375,000 军事与文职人员）
  - 5 个军种组成司令部：USARPAC / PACFLT / MARFORPAC / PACAF / USSFPAC
  - 3 个下属联合司令部：USFJ（驻日）/ USFK（驻韩）/ SOCPAC（特战）
  - 兵力校准（2023-09 现役）：驻日 53,246 / 驻夏威夷 44,545 /
    驻韩 24,159 / 驻关岛 6,363

设计要点（P11.2 指挥链建模）：
  - 指挥关系树：战区级（INDOPACOM）→ 军种组成/下属联合 → 基地
  - 事件上报（report）：基地传感器/战况沿指挥链逐级上报至 INDOPACOM
  - 命令下发（order）：INDOPACOM 决策沿指挥链逐级下达到基地
  - 跨军种协同（coordination）：源基地 → 上行至最近共同祖先（通常为
    INDOPACOM）→ 决策 → 下行至支援军种司令部 → 目标基地
  - 每条消息记录逐跳时间戳（hop-by-hop latency，可配置）
  - 全链路审计：messages 列表完整保留上报-决策-执行回放轨迹

Maps to DTB Model: WarEngine (指挥决策) + BattleNetwork (命令链路)
Maps to ASDA: Sense (上报) -> Decide (战区决策) -> Act (命令执行) -> Adapt (战果回传)
"""

import json
import os
import time
import uuid
from dataclasses import dataclass, field

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config",
    "indopacom_c2.json",
)

# 军种标准化映射（GeoJSON branch 字符串 → 标准军种码）
BRANCH_NORMALIZE = {
    "us army": "army",
    "army": "army",
    "usn": "navy",
    "navy": "navy",
    "usaf": "usaf",
    "usmc": "usmc",
    "ussf": "ussf",
    "joint": "joint",
    "sof": "sof",
}

# 军种码 → 军种组成司令部（P11.1 规则 R3）
_BRANCH_TO_COMPONENT = {
    "army": "USARPAC",
    "navy": "PACFLT",
    "usmc": "MARFORPAC",
    "usaf": "PACAF",
    "ussf": "USSFPAC",
}


def normalize_branch(branch_str: str) -> list:
    """将 GeoJSON branch 字符串解析为标准军种码列表。

    多军种联合基地（如 "USN/USAF"）返回多元素列表。
    盟友前缀（如 "PAF/US (EDCA)"、"RAAF/USMC"）取美方军种。
    """
    if not branch_str:
        return []
    branches = []
    for part in branch_str.split("/"):
        part = part.strip()
        # 去掉 "US (EDCA)" 中的括号与括号内文字
        part = part.split("(")[0].strip()
        low = part.lower()
        if low in ("us", "us (edca)"):
            branches.append("joint")
        elif low in BRANCH_NORMALIZE and BRANCH_NORMALIZE[low] not in (
            "joint",
            "sof",
        ):
            branches.append(BRANCH_NORMALIZE[low])
        # 盟友军种（RAAF/PAF/PA/Australian Army）不映射为美军种，跳过
    # 去重保序
    seen, out = set(), []
    for b in branches:
        if b not in seen:
            seen.add(b)
            out.append(b)
    # 全 joint（无法识别美军种）时回退空列表，交由规则处理
    return [b for b in out if b != "joint"] if out != ["joint"] else []


@dataclass
class C2Node:
    """指挥链节点：战区 / 军种组成 / 下属联合司令部"""

    node_id: str
    name: str
    node_type: str  # theater | service_component | subordinate_unified
    branch: str  # joint | army | navy | usaf | usmc | ussf | sof
    hq_location: str = ""
    hq_base_id: str = ""
    parent_id: str = ""  # 上级节点（theater 为空）
    country: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "node_type": self.node_type,
            "branch": self.branch,
            "hq_location": self.hq_location,
            "hq_base_id": self.hq_base_id,
            "parent_id": self.parent_id,
            "country": self.country,
        }


@dataclass
class C2Message:
    """指挥链消息：上报 / 命令 / 协同请求 / 协同响应 / 战果回传"""

    message_id: str
    msg_type: str  # report | order | coordination_request | coordination_order | execution_report
    origin: str  # 起始节点/基地
    destination: str  # 目的节点/基地
    hops: list  # [{"node": ..., "time": ..., "action": "relay|decide|execute"}]
    payload: dict = field(default_factory=dict)
    status: str = "delivered"  # delivered | denied
    created_at: float = 0.0
    total_latency_s: float = 0.0

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "msg_type": self.msg_type,
            "origin": self.origin,
            "destination": self.destination,
            "hops": self.hops,
            "payload": self.payload,
            "status": self.status,
            "created_at": self.created_at,
            "total_latency_s": round(self.total_latency_s, 2),
        }


class CommandChain:
    """INDOPACOM 指挥链模型（P11.2）。

    加载 config/indopacom_c2.json 构建指挥关系树，将 67 基地
    按显式指派 + 规则（R1 日本→USFJ / R2 韩国→USFK / R3 军种→组成司令部）
    挂载到指挥链，并提供上报 / 下发 / 跨军种协同的全链路消息记录。
    """

    def __init__(self, config_path: str = None):
        self.config_path = config_path or CONFIG_PATH
        with open(self.config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        self.config = cfg

        # 节点表
        self.nodes: dict[str, C2Node] = {}
        theater = cfg["theater"]
        t = C2Node(
            node_id=theater["node_id"],
            name=theater["name"],
            node_type="theater",
            branch="joint",
            hq_location=theater["hq_location"],
            hq_base_id=theater["hq_base_id"],
        )
        t.notes = theater.get("personnel_note", "")
        self.nodes[t.node_id] = t
        self.theater_id = t.node_id
        self.total_personnel = theater.get("total_personnel", 375000)

        for comp in cfg.get("service_components", []) + cfg.get(
            "subordinate_unified", []
        ):
            node = C2Node(
                node_id=comp["node_id"],
                name=comp["name"],
                node_type=comp["node_type"],
                branch=comp.get("branch", "joint"),
                hq_location=comp.get("hq_location", ""),
                hq_base_id=comp.get("hq_base_id", ""),
                parent_id=self.theater_id,
                country=comp.get("country", ""),
            )
            node.notes = comp.get("hq_note", "")
            self.nodes[node.node_id] = node

        # 兵力校准数据（CRS 权威）
        self.personnel_by_region = cfg.get("personnel_by_region", {})

        # 时延参数
        lat = cfg.get("c2_latency", {})
        self.report_hop_s = lat.get("report_hop_seconds", 0.4)
        self.decision_s = lat.get("decision_seconds", 1.0)
        self.order_hop_s = lat.get("order_hop_seconds", 0.3)

        # gRPC 服务 ↔ 司令部职能映射（P11.4）
        self.grpc_service_mapping = cfg.get("grpc_service_mapping", {})

        # 基地指派
        self._base_command: dict[str, str] = {}      # base_id -> 指挥节点
        self._base_components: dict[str, list] = {}  # base_id -> 军种码列表
        self._base_ally: dict[str, bool] = {}        # base_id -> 盟友东道国站点
        self._command_bases: dict[str, list] = {}    # node_id -> [base_id]
        self._base_info: dict[str, dict] = {}        # base_id -> 原始属性

        # 消息审计
        self.messages: list[C2Message] = []
        self._max_messages = 5000

        self._explicit = cfg.get("base_assignments", {})

    # ------------------------------------------------------------------
    # 基地指派（P11.1 规则 R1/R2/R3 + 显式表）
    # ------------------------------------------------------------------

    def assign_bases(self, bases: list) -> int:
        """将基地列表挂载到指挥链。返回成功指派数量。"""
        assigned = 0
        for base in bases:
            bid = base.get("id")
            if not bid:
                continue
            country = base.get("country", "")
            branch_str = base.get("military_branch", "") or base.get("branch", "")
            self._base_info[bid] = {
                "country": country,
                "branch": branch_str,
                "lat": base.get("lat", 0),
                "lon": base.get("lon", 0),
                "name": base.get("name", bid),
            }

            if bid in self._explicit:
                entry = self._explicit[bid]
                cmd = entry["command"]
                comps = entry.get("components", [])
                self._base_ally[bid] = bool(entry.get("ally_host", False))
            else:
                comps = normalize_branch(branch_str)
                # R1: 日本 → USFJ；R2: 韩国 → USFK；R3: 军种 → 组成司令部
                if country == "Japan":
                    cmd = "USFJ"
                elif country == "South Korea":
                    cmd = "USFK"
                elif comps:
                    cmd = _BRANCH_TO_COMPONENT.get(comps[0], self.theater_id)
                else:
                    cmd = self.theater_id  # 无法识别时直达战区
                self._base_ally[bid] = country not in (
                    "USA",
                    "Japan",
                    "South Korea",
                    "Guam",
                    "CNMI",
                    "Wake Island",
                    "Marshall Islands",
                    "USA (Wake Island)",
                    "British Indian Ocean Territory",
                    "",
                )

            if cmd not in self.nodes:
                cmd = self.theater_id
            self._base_command[bid] = cmd
            self._base_components[bid] = comps
            self._command_bases.setdefault(cmd, []).append(bid)
            assigned += 1
        return assigned

    # ------------------------------------------------------------------
    # 查询接口
    # ------------------------------------------------------------------

    def command_of(self, base_id: str) -> str:
        """基地所属指挥节点。未知基地返回战区节点。"""
        return self._base_command.get(base_id, self.theater_id)

    def bases_of(self, node_id: str) -> list:
        """指挥节点下辖基地列表。"""
        return list(self._command_bases.get(node_id, []))

    def components_of(self, base_id: str) -> list:
        """基地军种组成（RBAC 军种资产校验用）。"""
        return list(self._base_components.get(base_id, []))

    def chain_of_command(self, base_id: str) -> list:
        """基地 → ... → INDOPACOM 完整指挥链。"""
        chain = [base_id]
        node_id = self.command_of(base_id)
        while node_id:
            chain.append(node_id)
            node_id = self.nodes[node_id].parent_id if node_id in self.nodes else ""
        return chain

    def service_components(self) -> list:
        return [
            n.node_id
            for n in self.nodes.values()
            if n.node_type == "service_component"
        ]

    def subordinate_unified(self) -> list:
        return [
            n.node_id
            for n in self.nodes.values()
            if n.node_type == "subordinate_unified"
        ]

    def gRPC_mapping(self) -> dict:
        """P11.4: 四大 gRPC 服务 ↔ 司令部职能映射。"""
        return dict(self.grpc_service_mapping)

    # ------------------------------------------------------------------
    # 消息构造（上报 / 下发 / 跨军种协同）
    # ------------------------------------------------------------------

    def _new_message(self, msg_type: str, origin: str, destination: str, payload: dict) -> C2Message:
        return C2Message(
            message_id=f"C2-{uuid.uuid4().hex[:8].upper()}",
            msg_type=msg_type,
            origin=origin,
            destination=destination,
            hops=[],
            payload=payload,
            created_at=time.time(),
        )

    def _record(self, msg: C2Message) -> C2Message:
        self.messages.append(msg)
        if len(self.messages) > self._max_messages:
            self.messages = self.messages[-self._max_messages:]
        return msg

    def report_event(
        self, base_id: str, event_type: str, payload: dict = None, sim_time: float = 0.0
    ) -> C2Message:
        """事件上报：基地 → 所属司令部 → ... → INDOPACOM。

        每跳累计 report_hop_s 时延；抵达战区后由 TJOC 接收。
        """
        msg = self._new_message(
            "report", base_id, self.theater_id, payload or {}
        )
        msg.payload["event_type"] = event_type
        msg.payload["sim_time"] = sim_time
        t = 0.0
        for node in self.chain_of_command(base_id)[1:]:
            t += self.report_hop_s
            msg.hops.append({"node": node, "time": round(t, 2), "action": "relay"})
        # 抵达战区标记接收
        msg.hops[-1]["action"] = "received" if msg.hops else None
        msg.total_latency_s = t
        return self._record(msg)

    def issue_order(
        self,
        from_node: str,
        base_id: str,
        order_type: str,
        payload: dict = None,
        sim_time: float = 0.0,
    ) -> C2Message:
        """命令下发：from_node（通常 INDOPACOM）→ ... → 基地。

        每跳累计 order_hop_s 时延；末端标记 execute。
        """
        # 下行路径：from_node 到基地的链（取基地链中 from_node 以下部分）
        base_chain = self.chain_of_command(base_id)  # [base, cmd, ..., theater]
        if from_node in base_chain:
            idx = base_chain.index(from_node)
            down_path = list(reversed(base_chain[: idx + 1]))  # [from_node, ..., cmd, base]
        else:
            down_path = [from_node] + list(reversed(base_chain[:-1]))
        msg = self._new_message("order", from_node, base_id, payload or {})
        msg.payload["order_type"] = order_type
        msg.payload["sim_time"] = sim_time
        t = 0.0
        for i, node in enumerate(down_path):
            t += self.order_hop_s
            action = "execute" if i == len(down_path) - 1 else "relay"
            msg.hops.append({"node": node, "time": round(t, 2), "action": action})
        msg.total_latency_s = t
        return self._record(msg)

    def cross_service_coordination(
        self,
        source_base: str,
        target_base: str,
        request_type: str,
        payload: dict = None,
        sim_time: float = 0.0,
    ) -> list:
        """跨军种协同全链路：上报 → 战区决策 → 协同命令下发。

        场景（验收演示）：陆军雷达（Fort Shafter/USARPAC）探测威胁 →
        上报 INDOPACOM → TJOC 决策 → 命令下发 PACAF → Hickam F-22 拦截。

        返回 [report_msg, order_msg] 两条消息，完整还原
        上报-决策-执行链路（ hops 含 decide 节点）。
        """
        msgs = []
        # 1. 上报（源基地 → 战区）
        report = self.report_event(
            source_base,
            request_type,
            payload={"request_type": request_type, **(payload or {})},
            sim_time=sim_time,
        )
        msgs.append(report)

        # 2. 战区决策（时延 decision_s）
        decide_t = report.total_latency_s + self.decision_s
        report.hops.append(
            {"node": self.theater_id, "time": round(decide_t, 2), "action": "decide"}
        )
        report.total_latency_s = decide_t

        # 3. 协同命令下发（战区 → 目标基地，标注跨军种）
        target_cmd = self.command_of(target_base)
        order = self.issue_order(
            self.theater_id,
            target_base,
            f"coordination:{request_type}",
            payload={
                **(payload or {}),
                "source_base": source_base,
                "source_command": self.command_of(source_base),
                "target_command": target_cmd,
                "cross_service": self.command_of(source_base) != target_cmd,
            },
            sim_time=sim_time,
        )
        # 时间轴衔接：命令从决策完成后发出
        order.created_at = report.created_at
        for hop in order.hops:
            hop["time"] = round(hop["time"] + decide_t, 2)
        order.total_latency_s += decide_t
        msgs.append(order)
        return msgs

    # ------------------------------------------------------------------
    # 态势快照
    # ------------------------------------------------------------------

    def command_stats(self) -> list:
        """各指挥节点下辖基地数 + 军种分布（兵力校准视角）。"""
        stats = []
        for node_id, node in self.nodes.items():
            bases = self._command_bases.get(node_id, [])
            branch_count = {}
            for bid in bases:
                for b in self._base_components.get(bid, []):
                    branch_count[b] = branch_count.get(b, 0) + 1
            entry = {
                "node_id": node_id,
                "name": node.name,
                "node_type": node.node_type,
                "branch": node.branch,
                "hq_base_id": node.hq_base_id,
                "bases": len(bases),
                "ally_sites": sum(
                    1 for bid in bases if self._base_ally.get(bid, False)
                ),
                "component_distribution": branch_count,
            }
            # CRS 区域兵力校准（USFJ/USFK 直取权威数字）
            if node_id == "USFJ":
                entry["personnel_crs"] = self.personnel_by_region.get("Japan")
            elif node_id == "USFK":
                entry["personnel_crs"] = self.personnel_by_region.get(
                    "South Korea"
                )
            stats.append(entry)
        return stats

    def snapshot(self) -> dict:
        """态势快照（进入 get_state_dict，供 gRPC/显示层使用）。"""
        return {
            "theater": self.nodes[self.theater_id].to_dict(),
            "total_personnel": self.total_personnel,
            "personnel_by_region": {
                k: v
                for k, v in self.personnel_by_region.items()
                if k != "note"
            },
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "bases_assigned": len(self._base_command),
            "commands": self.command_stats(),
            "grpc_service_mapping": self.grpc_service_mapping,
            "recent_messages": [m.to_dict() for m in self.messages[-20:]],
            "message_count": len(self.messages),
        }
