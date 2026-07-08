# Copyright (c) Maltego Technologies GmbH.
"""Shared authentication validator contracts."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterator, Optional, Protocol, Tuple


class ValidationErrorKind(Enum):
    """Categories of token validation errors for appropriate HTTP status mapping."""

    NO_TOKEN = "no_token"
    """No token was provided (401)"""

    JWKS_UNAVAILABLE = "jwks_unavailable"
    """Provider unreachable or JWKS fetch failed (503)"""

    PROVIDER_UNAVAILABLE = "provider_unavailable"
    """Provider metadata, keys, or trusted signing material unavailable (503)"""

    EXPIRED_TOKEN = "expired_token"
    """JWT/OIDC token exp validation failed (401)"""

    EXPIRED_ASSERTION = "expired_assertion"
    """SAML NotOnOrAfter validation failed (401)"""

    INVALID_TOKEN = "invalid_token"
    """Token signature, format, issuer, audience, or recipient validation failed (401)"""

    INVALID_CLAIMS = "invalid_claims"
    """Custom claims validation failed (403)"""

    INTERNAL_ERROR = "internal_error"
    """Unexpected validation error (500)"""


@dataclass
class AuthValidationSuccess:
    """Normalized successful validation result for built-in and custom validators."""

    identity_claims: Dict[str, Any]
    auth_claims: Dict[str, Any]
    protocol: str
    raw_payload: Any = None

    def __iter__(self) -> Iterator[Any]:
        """Yield the historical success tuple for compatibility."""
        yield None
        yield None
        yield self.auth_claims


@dataclass
class AuthValidationFailure:
    """Structured validation failure result for built-in and custom validators."""

    error_kind: ValidationErrorKind
    error_message: str

    def __iter__(self) -> Iterator[Any]:
        """Yield the historical failure tuple for compatibility."""
        yield self.error_kind
        yield self.error_message
        yield None


ValidationResult = (
    AuthValidationSuccess
    | AuthValidationFailure
    | Tuple[Optional["ValidationErrorKind"], Optional[str], Optional[Dict[str, Any]]]
)


class TokenValidator(Protocol):
    """
    Protocol for token validators.

    Implement this protocol to create custom authentication backends.
    Built-in validators return structured results. Historical tuple-returning
    custom validators remain supported for compatibility.
    """

    async def validate_token(
        self, token: str
    ) -> ValidationResult:
        """
        Validate a token and extract claims.

        Args:
            token: The bearer token to validate

        Returns:
            AuthValidationSuccess, AuthValidationFailure, or the historical
            tuple of (error_kind, error_message, claims):
            - Success: AuthValidationSuccess or (None, None, claims_dict)
            - Failure: AuthValidationFailure or (ValidationErrorKind.*, error_message, None)
        """
        ...

    async def close(self) -> None:
        """Close any resources (HTTP clients, connections, etc.)."""
        ...


def __getattr__(name: str) -> Any:
    """Lazy compatibility exports for validators that import this module."""
    if name == "JWTTokenValidator":
        from maltego.auth.jwt_validator import JWTTokenValidator

        return JWTTokenValidator
    if name == "OIDCTokenValidator":
        from maltego.auth.oidc_validator import OIDCTokenValidator

        return OIDCTokenValidator
    raise AttributeError(name)

__all__ = [
    "AuthValidationFailure",
    "AuthValidationSuccess",
    "JWTTokenValidator",
    "OIDCTokenValidator",
    "TokenValidator",
    "ValidationResult",
    "ValidationErrorKind",
]
