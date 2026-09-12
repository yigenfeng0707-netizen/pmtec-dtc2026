"""
JWT Token Management - Issue, verify, and refresh authentication tokens.

Uses PyJWT (HS256) for token signing. Tokens carry user_id, role, and
expiration. Supports refresh within a grace window before expiry.
"""

import os
import time
import jwt
from dataclasses import dataclass


class AuthError(Exception):
    """Raised when token operations fail."""

    pass


@dataclass
class TokenInfo:
    token: str
    user_id: str
    role: str
    expires_at: int
    issued_at: int


class AuthManager:
    """Manages JWT token lifecycle: issuance, verification, refresh."""

    def __init__(self, secret: str = None, expiration_hours: int = 24):
        self._secret = secret or os.environ.get(
            "PMTEC_JWT_SECRET", self._generate_secret()
        )
        self._expiration_seconds = expiration_hours * 3600
        self._algorithm = "HS256"

    @staticmethod
    def _generate_secret() -> str:
        import secrets

        return secrets.token_urlsafe(48)

    @property
    def secret(self) -> str:
        return self._secret

    def issue_token(self, user_id: str, role: str, branch: str = None) -> TokenInfo:
        """Issue a JWT token for the given user and role.

        P11.3: optional branch claim scopes the role to a service branch
        (e.g. "usaf" -> PACAF-Operator can only operate Air Force assets).
        Empty/absent branch = joint (unrestricted, backward compatible).
        """
        now = int(time.time())
        payload = {
            "user_id": user_id,
            "role": role,
            "iat": now,
            "exp": now + self._expiration_seconds,
            "iss": "PMTEC-Auth",
        }
        if branch:
            payload["branch"] = branch
        token = jwt.encode(payload, self._secret, algorithm=self._algorithm)
        return TokenInfo(
            token=token,
            user_id=user_id,
            role=role,
            expires_at=payload["exp"],
            issued_at=now,
        )

    def verify_token(self, token: str) -> dict:
        """Verify a JWT token and return the decoded payload.

        Raises AuthError if the token is invalid, expired, or malformed.
        """
        if not token:
            raise AuthError("Empty token")
        token = token.replace("Bearer ", "").strip()
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                issuer="PMTEC-Auth",
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise AuthError("Token has expired")
        except jwt.InvalidTokenError as exc:
            raise AuthError(f"Invalid token: {exc}")

    def refresh_token(self, token: str) -> TokenInfo:
        """Refresh an expired or near-expiry token.

        The token must be within the refresh window (expired < 2 hours).
        Returns a new TokenInfo with a fresh token.
        """
        token = token.replace("Bearer ", "").strip()
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                issuer="PMTEC-Auth",
                options={"verify_exp": False},
            )
        except jwt.InvalidTokenError as exc:
            raise AuthError(f"Cannot refresh invalid token: {exc}")

        now = int(time.time())
        if payload.get("exp", 0) + 7200 < now:
            raise AuthError("Token too old to refresh (exceeded 2-hour grace window)")

        return self.issue_token(payload["user_id"], payload["role"])

    def authenticate(
        self, user_id: str, password: str, role: str, branch: str = None
    ) -> TokenInfo:
        """Authenticate a user and return a token.

        In production, password verification would be against an identity
        provider (LDAP/Active Directory/OAuth). For competition deployment,
        a simple credential store is used.

        P11.3: optional branch validates the service-branch scope
        (army/navy/usmc/usaf/ussf/joint per INDOPACOM components).
        """
        valid = self._check_credentials(user_id, password)
        if not valid:
            raise AuthError("Invalid credentials")
        if role not in ("commander", "operator", "observer"):
            raise AuthError(f"Unknown role: {role}")
        if branch:
            from security.rbac import VALID_BRANCHES

            if branch.strip().lower() not in VALID_BRANCHES:
                raise AuthError(f"Unknown branch: {branch}")
        return self.issue_token(user_id, role, branch)

    @staticmethod
    def _check_credentials(user_id: str, password: str) -> bool:
        """Check credentials against a simple store.

        Production would integrate with LDAP/AD/OAuth.
        For competition demo, accept any non-empty password.
        """
        return bool(user_id and password)
