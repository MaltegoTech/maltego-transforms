# Copyright (c) Maltego Technologies GmbH.
"""Auth identity model for JWT claims."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Identity:
    """
    Normalized auth identity extracted from JWT claims.

    Provides a stable, consistent structure for downstream middleware and transforms.
    Built from Keycloak/OIDC JWT claims.
    """

    iss: Optional[str] = None  # Issuer
    sub: Optional[str] = None  # Subject
    azp: Optional[str] = None  # Authorized party
    sid: Optional[str] = None  # Session ID
    aud: Optional[Any] = None  # Audience
    org_id: Optional[str] = None  # Organization ID
    scopes: List[str] = field(default_factory=list)
    realm_roles: List[str] = field(default_factory=list)
    client_roles: Dict[str, List[str]] = field(default_factory=dict)
    use_credits: Optional[bool] = None
    maltego_id: Optional[str] = None  # Maltego ID
    email: Optional[str] = None  # Email

    @classmethod
    def from_claims(cls, claims: Dict[str, Any]) -> "Identity":
        """Build Identity from JWT claims."""
        scopes = (claims.get("scope") or "").split()
        realm_access = claims.get("realm_access") or {}
        realm_roles = realm_access.get("roles") or []
        resource_access = claims.get("resource_access") or {}

        client_roles: Dict[str, List[str]] = {}
        for client, data in resource_access.items():
            roles = (data or {}).get("roles") or []
            if roles:
                client_roles[client] = roles

        org = claims.get("organization") or {}
        org_id = org.get("id")

        return cls(
            iss=claims.get("iss"),
            sub=claims.get("sub"),
            azp=claims.get("azp"),
            sid=claims.get("sid"),
            aud=claims.get("aud"),
            org_id=org_id,
            scopes=scopes,
            realm_roles=realm_roles,
            client_roles=client_roles,
            use_credits=claims.get("use_credits"),
            maltego_id=claims.get("maltego_id"),
            email=claims.get("email"),
        )

    @property
    def is_anonymous(self) -> bool:
        """Detect placeholder/shared subjects."""
        return not self.sub or self.sub == "00000000-0000-0000-0000-000000000000"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "iss": self.iss,
            "sub": self.sub,
            "azp": self.azp,
            "sid": self.sid,
            "aud": self.aud,
            "org_id": self.org_id,
            "scopes": self.scopes,
            "realm_roles": self.realm_roles,
            "client_roles": self.client_roles,
            "use_credits": self.use_credits,
            "maltego_id": self.maltego_id,
            "email": self.email,
        }


@dataclass
class AuthContext:
    """Auth data attached to a transform execution context."""

    identity: Optional[Identity] = None
    rate_limit_key: Optional[str] = None
    auth_claims: Optional[Dict[str, Any]] = None
    auth_payload: Any = None
    unverified_auth_claims: Optional[Dict[str, Any]] = None
    token_origin: Optional[str] = None
    credential_header: Optional[str] = None
    upstream_identity_method: Optional[str] = None

    @classmethod
    def from_request_state(cls, state: Any) -> "AuthContext":
        """Build auth context from FastAPI request state."""
        return cls(
            identity=getattr(state, "identity", None),
            rate_limit_key=getattr(state, "rate_limit_key", None),
            auth_claims=getattr(state, "auth_claims", None),
            auth_payload=getattr(state, "auth_payload", None),
            unverified_auth_claims=getattr(state, "unverified_auth_claims", None),
            token_origin=getattr(state, "auth_token_origin", None),
            credential_header=getattr(state, "auth_credential_header", None),
            upstream_identity_method=getattr(state, "auth_upstream_identity_method", None),
        )
