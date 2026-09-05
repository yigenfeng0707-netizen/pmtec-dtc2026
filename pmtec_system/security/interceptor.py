"""
gRPC Auth Interceptor - Enforces JWT + RBAC + Audit on every RPC call.

Intercepts all incoming gRPC calls and:
  1. Extracts JWT from metadata (authorization header)
  2. Verifies the token signature and expiration
  3. Checks RBAC permission for the called method
  4. Logs the operation to the audit trail
  5. Aborts with UNAUTHENTICATED or PERMISSION_DENIED on failure
"""

import grpc


class AuthInterceptor(grpc.ServerInterceptor):
    """gRPC server interceptor for JWT auth, RBAC, and audit logging."""

    def __init__(self, auth_manager, rbac_manager, audit_logger):
        """
        Args:
            auth_manager: AuthManager instance for JWT operations
            rbac_manager: RBACManager instance for permission checks
            audit_logger: AuditLogger instance for audit trail
        """
        self._auth = auth_manager
        self._rbac = rbac_manager
        self._audit = audit_logger

    def intercept_service(self, continuation, handler_call_details):
        """Intercept every gRPC call and enforce authentication."""
        method = handler_call_details.method

        # Health check and reflection are exempt from auth
        if self._rbac.is_exempt(method):
            return continuation(handler_call_details)

        # Extract metadata
        metadata = dict(handler_call_details.invocation_metadata or [])
        token = metadata.get("authorization", "")
        peer = (
            handler_call_details.invocation_metadata
            and self._extract_peer(handler_call_details)
            or "unknown"
        )

        # Parse method for audit logging
        parts = method.split("/")
        service_full = parts[1] if len(parts) > 1 else "unknown"
        method_name = parts[2] if len(parts) > 2 else "unknown"
        service = service_full.split(".")[-1] if "." in service_full else service_full

        # Step 1: Verify JWT token
        try:
            payload = self._auth.verify_token(token)
            user_id = payload.get("user_id", "unknown")
            role_str = payload.get("role", "observer")
            from security.rbac import Role

            role = Role.from_string(role_str)
        except Exception as exc:
            self._audit.log(
                user_id="anonymous",
                role="none",
                service=service,
                method=method_name,
                decision="DENIED",
                peer=peer,
                detail=f"Auth failed: {exc}",
            )
            return self._deny_handler(
                grpc.StatusCode.UNAUTHENTICATED,
                f"Authentication failed: {exc}",
            )

        # Step 2: Check RBAC permission
        if not self._rbac.check_grpc_method(role, method):
            self._audit.log(
                user_id=user_id,
                role=role.value,
                service=service,
                method=method_name,
                decision="DENIED",
                peer=peer,
                detail="RBAC permission denied",
            )
            return self._deny_handler(
                grpc.StatusCode.PERMISSION_DENIED,
                f"Role '{role.value}' cannot access {service}.{method_name}",
            )

        # Step 3: Log allowed access
        self._audit.log(
            user_id=user_id,
            role=role.value,
            service=service,
            method=method_name,
            decision="ALLOWED",
            peer=peer,
        )

        # Continue to the actual service handler
        return continuation(handler_call_details)

    @staticmethod
    def _extract_peer(handler_call_details):
        """Extract client peer address from invocation metadata."""
        if handler_call_details.invocation_metadata:
            for key, value in handler_call_details.invocation_metadata:
                if key == "peer":
                    return value
        return "unknown"

    @staticmethod
    def _deny_handler(status_code, message):
        """Create a handler that aborts the RPC with the given status.

        The handler works for unary and streaming RPCs since the abort
        happens before any message processing.
        """

        def abort(request, context):
            context.abort(status_code, message)

        return grpc.unary_unary_rpc_method_handler(abort)
