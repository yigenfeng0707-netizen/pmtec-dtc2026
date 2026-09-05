"""
PMTEC Security Package - P0-A Production-grade Authentication & Authorization.

Components:
  - auth: JWT token issuance, verification, and refresh
  - rbac: Three-tier role-based access control (Commander / Operator / Observer)
  - audit: Hash-chained audit logging with SQLite persistence
  - cert_manager: mTLS certificate generation, loading, and auto-renewal
  - interceptor: gRPC server interceptor enforcing JWT + RBAC + audit on every call
"""

from security.auth import AuthManager, AuthError
from security.rbac import RBACManager, Role, Permission
from security.audit import AuditLogger
from security.cert_manager import CertificateManager
from security.interceptor import AuthInterceptor

__all__ = [
    "AuthManager",
    "AuthError",
    "RBACManager",
    "Role",
    "Permission",
    "AuditLogger",
    "CertificateManager",
    "AuthInterceptor",
]
