"""
RBAC - Role-Based Access Control for PMTEC gRPC services.

Three tiers:
  Commander  - Full access to all services and methods
  Operator   - Operational access (start/stop sim, view data; no registration/config)
  Observer   - Read-only access (view all; no mutations)

Permission matrix maps each (service, method) pair to the set of roles
allowed to invoke it.
"""

from enum import Enum


class Role(Enum):
    """Three-tier role hierarchy for PMTEC battlefield operations."""

    COMMANDER = "commander"
    OPERATOR = "operator"
    OBSERVER = "observer"

    @classmethod
    def from_string(cls, role_str: str) -> "Role":
        """Parse a role string into a Role enum value."""
        normalized = (role_str or "").strip().lower()
        for member in cls:
            if member.value == normalized:
                return member
        raise ValueError(f"Unknown role: {role_str}")


class Permission:
    """Permission constants for each gRPC method."""

    # WarEngine service
    START_SIM = ("WarEngine", "StartSimulation")
    STOP_SIM = ("WarEngine", "StopSimulation")
    GET_STATE = ("WarEngine", "GetState")
    INJECT_EVENT = ("WarEngine", "InjectEvent")
    GET_SPEAR = ("WarEngine", "GetSpearReport")
    GET_EW = ("WarEngine", "GetEWThreats")
    GET_CYBER = ("WarEngine", "GetCyberThreats")
    GET_THREAT_SUM = ("WarEngine", "GetThreatSummary")

    # BattleNetwork service
    GET_TRACK = ("BattleNetwork", "GetTrackFeed")
    GET_ENTITY = ("BattleNetwork", "GetEntityStatus")
    GET_NET = ("BattleNetwork", "GetNetworkState")
    GET_LIVE = ("BattleNetwork", "GetLiveFeed")
    GET_LVC = ("BattleNetwork", "GetLVCStatus")

    # ApplicationStore service
    LIST_APPS = ("ApplicationStore", "ListApps")
    DEPLOY_APP = ("ApplicationStore", "DeployApp")
    QUERY_CAP = ("ApplicationStore", "QueryCapability")
    DQN_INFER = ("ApplicationStore", "DQNInfer")
    GET_DQN = ("ApplicationStore", "GetDQNStatus")

    # PlugAndPlay service
    REGISTER_COMP = ("PlugAndPlay", "RegisterComponent")
    DISCOVER = ("PlugAndPlay", "DiscoverServices")
    HEALTH_CHECK = ("PlugAndPlay", "HealthCheck")
    LIST_PLUGINS = ("PlugAndPlay", "ListPlugins")
    LIST_DT_INST = ("PlugAndPlay", "ListDTInstances")
    REGISTER_DT = ("PlugAndPlay", "RegisterDTInstance")


# Permission matrix: maps each (service, method) to allowed roles.
# Methods not listed here are denied for all roles (deny by default).
_PERMISSION_MATRIX = {
    # --- WarEngine ---
    Permission.START_SIM: {Role.COMMANDER, Role.OPERATOR},
    Permission.STOP_SIM: {Role.COMMANDER, Role.OPERATOR},
    Permission.GET_STATE: {Role.COMMANDER, Role.OPERATOR, Role.OBSERVER},
    Permission.INJECT_EVENT: {Role.COMMANDER},
    Permission.GET_SPEAR: {Role.COMMANDER, Role.OPERATOR, Role.OBSERVER},
    Permission.GET_EW: {Role.COMMANDER, Role.OPERATOR, Role.OBSERVER},
    Permission.GET_CYBER: {Role.COMMANDER, Role.OPERATOR, Role.OBSERVER},
    Permission.GET_THREAT_SUM: {Role.COMMANDER, Role.OPERATOR, Role.OBSERVER},
    # --- BattleNetwork (all roles can read) ---
    Permission.GET_TRACK: {Role.COMMANDER, Role.OPERATOR, Role.OBSERVER},
    Permission.GET_ENTITY: {Role.COMMANDER, Role.OPERATOR, Role.OBSERVER},
    Permission.GET_NET: {Role.COMMANDER, Role.OPERATOR, Role.OBSERVER},
    Permission.GET_LIVE: {Role.COMMANDER, Role.OPERATOR, Role.OBSERVER},
    Permission.GET_LVC: {Role.COMMANDER, Role.OPERATOR, Role.OBSERVER},
    # --- ApplicationStore ---
    Permission.LIST_APPS: {Role.COMMANDER, Role.OPERATOR, Role.OBSERVER},
    Permission.DEPLOY_APP: {Role.COMMANDER, Role.OPERATOR},
    Permission.QUERY_CAP: {Role.COMMANDER, Role.OPERATOR, Role.OBSERVER},
    Permission.DQN_INFER: {Role.COMMANDER, Role.OPERATOR},
    Permission.GET_DQN: {Role.COMMANDER, Role.OPERATOR, Role.OBSERVER},
    # --- PlugAndPlay ---
    Permission.REGISTER_COMP: {Role.COMMANDER},
    Permission.DISCOVER: {Role.COMMANDER, Role.OPERATOR, Role.OBSERVER},
    Permission.HEALTH_CHECK: {Role.COMMANDER, Role.OPERATOR, Role.OBSERVER},
    Permission.LIST_PLUGINS: {Role.COMMANDER, Role.OPERATOR, Role.OBSERVER},
    Permission.LIST_DT_INST: {Role.COMMANDER, Role.OPERATOR, Role.OBSERVER},
    Permission.REGISTER_DT: {Role.COMMANDER},
}


# Methods exempt from authentication (health probes, internal)
_EXEMPT_METHODS = {"/dtb_model.PlugAndPlay/HealthCheck"}


class RBACManager:
    """Checks user roles against the permission matrix."""

    def __init__(self):
        self._matrix = dict(_PERMISSION_MATRIX)
        self._exempt = set(_EXEMPT_METHODS)

    def is_exempt(self, grpc_method: str) -> bool:
        """Check if a full gRPC method path is exempt from auth."""
        return grpc_method in self._exempt

    def check_permission(self, role: Role, service: str, method: str) -> bool:
        """Check if the given role can invoke (service, method).

        Returns True if permitted, False otherwise.
        Unknown methods are denied by default.
        """
        key = (service, method)
        allowed = self._matrix.get(key)
        if allowed is None:
            return False
        return role in allowed

    def check_grpc_method(self, role: Role, grpc_method: str) -> bool:
        """Check permission using the full gRPC method path.

        Path format: /dtb_model.{Service}/{Method}
        """
        if self.is_exempt(grpc_method):
            return True
        parts = grpc_method.split("/")
        if len(parts) < 3:
            return False
        service_full = parts[1]  # e.g., "dtb_model.WarEngine"
        method = parts[2]  # e.g., "StartSimulation"
        # Strip package prefix
        service = service_full.split(".")[-1] if "." in service_full else service_full
        return self.check_permission(role, service, method)

    def get_role_permissions(self, role: Role) -> list:
        """Return all (service, method) pairs the role can access."""
        return [perm for perm, roles in self._matrix.items() if role in roles]
