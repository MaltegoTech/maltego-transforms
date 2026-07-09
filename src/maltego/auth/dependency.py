# Copyright (c) Maltego Technologies GmbH.
"""FastAPI dependencies for JWT authentication."""

import logging
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, Optional

import fastapi
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from maltego.auth.claims import decode_unverified_jwt_claims
from maltego.auth.identity import Identity
from maltego.auth.jwt_validator import JWTTokenValidator
from maltego.auth.oidc_validator import OIDCTokenValidator
from maltego.auth.problem import AuthProblemException, build_auth_problem
from maltego.auth.saml_validator import SAMLTokenValidator, decode_unverified_saml_claims
from maltego.auth.settings import AuthMode, AuthProviderType, AuthSettings, AuthTokenOrigin, get_auth_settings
from maltego.auth.validator import (
    AuthValidationFailure,
    AuthValidationSuccess,
    TokenValidator,
    ValidationErrorKind,
)

logger = logging.getLogger(__name__)

# Optional bearer - doesn't fail if no auth header
optional_bearer = HTTPBearer(auto_error=False)

MALTEGO_IDENTITY_AUTHORIZATION_HEADER = "maltego-identity-authorization"
MALTEGO_UPSTREAM_IDENTITY_METHOD_HEADER = "maltego-upstream-identity-method"

# Cached validator instance
_validator: Optional[TokenValidator] = None
_validator_lock = Lock()


@dataclass
class _ValidationAdapterResult:
    error_kind: Optional[ValidationErrorKind]
    error_msg: Optional[str]
    identity_claims: Optional[Dict[str, Any]]
    auth_claims: Optional[Dict[str, Any]]
    raw_payload: Any
    protocol: Optional[str]


@dataclass(frozen=True)
class _SelectedAuthCredential:
    token: Optional[str]
    origin: Optional[str]
    header_name: Optional[str]
    upstream_identity_method: Optional[str]


def _parse_maltego_identity_authorization(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    scheme, _, rest = value.partition(" ")
    if scheme.lower() == "bearer":
        token = rest.strip()
        if not token:
            raise ValueError("maltego-identity-authorization Bearer token is empty")
        return token
    return value


def _normalize_upstream_identity_method(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    method = value.strip().lower()
    if not method:
        return None
    if method not in {"saml", "oidc"}:
        raise ValueError("maltego-upstream-identity-method must be SAML or OIDC")
    return method


def _select_auth_credential(
    settings: AuthSettings,
    bearer_token: Optional[str],
    maltego_identity_token: Optional[str],
    upstream_identity_method: Optional[str] = None,
) -> _SelectedAuthCredential:
    if settings.token_origin == AuthTokenOrigin.MALTEGO_ID or (
        settings.token_origin is None and bearer_token is None and maltego_identity_token is not None
    ):
        return _SelectedAuthCredential(
            token=maltego_identity_token,
            origin=AuthTokenOrigin.MALTEGO_ID.value,
            header_name=MALTEGO_IDENTITY_AUTHORIZATION_HEADER if maltego_identity_token else None,
            upstream_identity_method=None,
        )

    origin = settings.token_origin.value if settings.token_origin else None
    return _SelectedAuthCredential(
        token=bearer_token,
        origin=origin,
        header_name="authorization" if bearer_token else None,
        upstream_identity_method=upstream_identity_method,
    )


def _validate_upstream_identity_method_matches_provider(
    settings: AuthSettings,
    upstream_identity_method: Optional[str],
    require_method: bool = False,
) -> None:
    expected_method_by_provider = {
        AuthProviderType.SAML: "saml",
        AuthProviderType.OIDC: "oidc",
        AuthProviderType.JWT: "oidc",
    }
    expected_method = expected_method_by_provider.get(settings.provider_type)
    if require_method and upstream_identity_method is None:
        raise ValueError("maltego-upstream-identity-method is required")
    if upstream_identity_method and expected_method and upstream_identity_method != expected_method:
        raise ValueError(
            "maltego-upstream-identity-method does not match configured auth provider_type"
        )


def _credential_uses_sso_upstream_identity_method(credential: _SelectedAuthCredential) -> bool:
    return credential.origin == AuthTokenOrigin.SSO.value and credential.token is not None


def _adapt_validation_result(result: Any, settings_provider_type: Optional[AuthProviderType]) -> _ValidationAdapterResult:
    if isinstance(result, AuthValidationSuccess):
        return _ValidationAdapterResult(
            error_kind=None,
            error_msg=None,
            identity_claims=result.identity_claims,
            auth_claims=result.auth_claims,
            raw_payload=result.raw_payload,
            protocol=result.protocol,
        )

    if isinstance(result, AuthValidationFailure):
        return _ValidationAdapterResult(
            error_kind=result.error_kind,
            error_msg=result.error_message,
            identity_claims=None,
            auth_claims=None,
            raw_payload=None,
            protocol=settings_provider_type.value if settings_provider_type else None,
        )

    if not isinstance(result, tuple) or len(result) != 3:
        raise RuntimeError("Invalid auth validation result")

    error_kind, error_msg, claims = result
    protocol = settings_provider_type.value if settings_provider_type else AuthProviderType.JWT.value
    return _ValidationAdapterResult(
        error_kind=error_kind,
        error_msg=error_msg,
        identity_claims=claims,
        auth_claims=claims,
        raw_payload=claims,
        protocol=protocol,
    )


def _create_validator() -> TokenValidator:
    settings = get_auth_settings()
    if settings.validator_factory:
        return settings.validator_factory(settings)
    if settings.provider_type == AuthProviderType.JWT:
        return JWTTokenValidator(settings)
    if settings.provider_type == AuthProviderType.OIDC:
        return OIDCTokenValidator(settings)
    if settings.provider_type == AuthProviderType.SAML:
        return SAMLTokenValidator(settings)
    raise RuntimeError("provider_type is required to create a built-in auth validator")


def _get_validator() -> TokenValidator:
    """Get or create the validator instance (custom or selected built-in)."""
    global _validator
    if _validator is None:
        with _validator_lock:
            if _validator is None:
                _validator = _create_validator()
    return _validator


def _get_client_ip(request: fastapi.Request, forwarded_allow_ips: str = "127.0.0.1") -> str:
    """Best-effort client IP extraction.

    X-Forwarded-For is trusted only when the immediate connection peer is in
    ``forwarded_allow_ips`` (the trusted-proxy list); trusting it from arbitrary
    clients would allow IP spoofing and rate-limit bypass. The default of
    loopback-only means XFF is honored only for connections from the same host.
    """
    # Import here (not at module top) to avoid a circular import:
    # server/__init__.py → maltego.auth → auth/dependency.py → server/util.py is fine,
    # but a top-level import of server/util inside auth would run at import time when
    # server/__init__.py itself is still being initialised.
    from maltego.server.util import is_forwarded_client_allowed  # noqa: PLC0415

    client_host = request.client.host if request.client else None
    xff = request.headers.get("X-Forwarded-For")
    if xff and is_forwarded_client_allowed(client_host, forwarded_allow_ips):
        return xff.split(",")[0].strip()
    return client_host or "unknown"


def _build_rate_limit_key(
    request: fastapi.Request,
    identity: Identity,
    forwarded_allow_ips: str = "127.0.0.1",
) -> str:
    """
    Build rate limit key for throttling.

    Key hierarchy:
    1. Org + real user: org:{org_id}:sub:{sub}
    2. Org + client/app (anonymous): org:{org_id}:azp:{azp}
    3. Real user only: sub:{sub}
    4. Client/app only (anonymous): azp:{azp}

    The forwarded_allow_ips parameter is forwarded to _get_client_ip so that
    X-Forwarded-For is only used when the request arrived from a trusted proxy.
    """
    azp = identity.azp or "unknown-azp"

    if identity.org_id and not identity.is_anonymous:
        key = f"org:{identity.org_id}:sub:{identity.sub}"
    elif identity.org_id:
        key = f"org:{identity.org_id}:azp:{azp}"
    elif not identity.is_anonymous:
        key = f"sub:{identity.sub}"
    else:
        key = f"azp:{azp}"

    # Add IP for additional entropy
    ip = _get_client_ip(request, forwarded_allow_ips)
    if ip != "unknown":
        key = f"{key}:{ip}"

    return key


def _expose_unverified_claims_if_enabled(
    request: fastapi.Request,
    token: Optional[str],
    settings: AuthSettings,
) -> None:
    if not settings.expose_unverified_claims or not token:
        return

    claims: Optional[Dict[str, Any]] = None
    protocol: str = "jwt/oidc or saml"
    if settings.provider_type == AuthProviderType.SAML:
        claims = decode_unverified_saml_claims(token)
        protocol = AuthProviderType.SAML.value
    elif settings.provider_type in (AuthProviderType.JWT, AuthProviderType.OIDC):
        claims = decode_unverified_jwt_claims(token)
        protocol = settings.provider_type.value
    elif settings.enabled:
        logger.debug(
            "Auth is enabled without provider_type; unverified auth claims were not exposed to avoid token-shape inference"
        )
        return
    else:
        claims = decode_unverified_jwt_claims(token)
        if claims is not None:
            protocol = AuthProviderType.JWT.value
        else:
            claims = decode_unverified_saml_claims(token)
            if claims is not None:
                protocol = AuthProviderType.SAML.value

    if claims is None:
        logger.debug("Bearer token was not decodable as %s; unverified auth claims were not exposed", protocol)
        return

    request.state.unverified_auth_claims = claims


async def optional_auth(
    request: fastapi.Request,
    creds: Optional[HTTPAuthorizationCredentials] = fastapi.Depends(optional_bearer),
) -> None:
    """
    Optional JWT authentication dependency.

    When auth is disabled (default):
        - Stores bearer token in request.state.bearer_token
        - No validation performed

    When auth is enabled:
        - Validates JWT token against OIDC provider
        - Builds Identity and stores in request.state.identity
        - Builds rate limit key and stores in request.state.rate_limit_key
        - STRICT mode: raises HTTPException on invalid/missing token
        - WARN mode: logs warning but allows request to proceed
    """
    settings = get_auth_settings()
    bearer_token = creds.credentials if creds else None
    try:
        maltego_identity_token = _parse_maltego_identity_authorization(
            request.headers.get(MALTEGO_IDENTITY_AUTHORIZATION_HEADER)
        )
    except ValueError as exc:
        raise build_auth_problem(
            ValidationErrorKind.INVALID_TOKEN,
            str(exc),
            settings,
            request,
        ) from exc
    selected_credential = _select_auth_credential(
        settings,
        bearer_token,
        maltego_identity_token,
    )
    raw_upstream_identity_method = request.headers.get(MALTEGO_UPSTREAM_IDENTITY_METHOD_HEADER)
    upstream_identity_method = None

    # Always store bearer token (backwards compatibility)
    request.state.bearer_token = bearer_token
    request.state.maltego_identity_token = maltego_identity_token
    request.state.auth_upstream_identity_method = selected_credential.upstream_identity_method

    # If auth is disabled, return
    if not settings.enabled:
        _expose_unverified_claims_if_enabled(request, selected_credential.token, settings)
        return

    # If the path is explicitly whitelisted, skip auth
    if settings.public_paths and request.scope.get("path", "") in settings.public_paths:
        return

    # If a token is provided, validate it
    if selected_credential.token:
        if _credential_uses_sso_upstream_identity_method(selected_credential):
            try:
                upstream_identity_method = _normalize_upstream_identity_method(
                    raw_upstream_identity_method
                )
                _validate_upstream_identity_method_matches_provider(
                    settings,
                    upstream_identity_method,
                    require_method=True,
                )
            except ValueError as exc:
                raise build_auth_problem(
                    ValidationErrorKind.INVALID_TOKEN,
                    str(exc),
                    settings,
                    request,
                ) from exc
            selected_credential = _SelectedAuthCredential(
                token=selected_credential.token,
                origin=selected_credential.origin,
                header_name=selected_credential.header_name,
                upstream_identity_method=upstream_identity_method,
            )
            request.state.auth_upstream_identity_method = upstream_identity_method
        _expose_unverified_claims_if_enabled(request, selected_credential.token, settings)
        try:
            validator = _get_validator()
            validation = _adapt_validation_result(
                await validator.validate_token(selected_credential.token),
                settings.provider_type,
            )
        except AuthProblemException:
            raise
        except Exception:
            logger.exception("Unexpected auth validation error")
            problem = build_auth_problem(
                ValidationErrorKind.INTERNAL_ERROR,
                "Unexpected auth validation error",
                settings,
                request,
            )
            if settings.mode == AuthMode.WARN:
                logger.warning(
                    "Auth (warn): status=%s error_code=%s detail=%s",
                    problem.status_code,
                    problem.problem.error_code.value,
                    "Unexpected auth validation error",
                )
                return

            raise problem

        if validation.error_kind is not None:
            problem = build_auth_problem(
                validation.error_kind,
                validation.error_msg,
                settings,
                request,
            )
            logger.warning(
                "Auth validation failed: status=%s error_code=%s origin=%s provider_type=%s kind=%s",
                problem.status_code,
                problem.problem.error_code.value,
                problem.problem.auth_origin,
                problem.problem.provider_type,
                validation.error_kind.value,
            )
            logger.debug(
                "Auth validation failure detail: status=%s error_code=%s kind=%s detail=%s",
                problem.status_code,
                problem.problem.error_code.value,
                validation.error_kind.value,
                validation.error_msg,
            )
            if settings.mode == AuthMode.WARN:
                # WARN mode is fail-open: requests with bad/expired/missing tokens
                # are allowed through. Intended for non-production or observability-only
                # deployments — do not use on production network-facing servers.
                # A startup warning is emitted by _warn_if_warn_mode_active() to inform operators.
                logger.warning(
                    "Auth (warn) — FAIL-OPEN: request is proceeding despite auth failure. "
                    "status=%s error_code=%s detail=%s",
                    problem.status_code,
                    problem.problem.error_code.value,
                    validation.error_msg,
                )
                return

            raise problem

        # Build and store identity
        identity = Identity.from_claims(validation.identity_claims or {})
        request.state.identity = identity
        app = request.scope.get("app")
        forwarded_allow_ips = getattr(
            getattr(app, "state", None), "forwarded_allow_ips", "127.0.0.1"
        )
        request.state.rate_limit_key = _build_rate_limit_key(
            request, identity, forwarded_allow_ips
        )
        request.state.auth_claims = validation.auth_claims
        request.state.auth_payload = validation.raw_payload
        request.state.auth_token_origin = selected_credential.origin
        request.state.auth_credential_header = selected_credential.header_name
        if validation.protocol in {AuthProviderType.JWT.value, AuthProviderType.OIDC.value}:
            request.state.jwt_claims = validation.auth_claims
        return

    if settings.mode == AuthMode.WARN:
        # WARN mode is fail-open — unauthenticated requests proceed.
        # See the comment in the validation failure block above for rationale.
        problem = build_auth_problem(
            ValidationErrorKind.NO_TOKEN,
            "No Authorization Bearer token",
            settings,
            request,
        )
        logger.warning(
            "Auth (warn) — FAIL-OPEN: unauthenticated request is proceeding. "
            "status=%s error_code=%s detail=%s",
            problem.status_code,
            problem.problem.error_code.value,
            "No Authorization Bearer token",
        )
        return

    raise build_auth_problem(
        ValidationErrorKind.NO_TOKEN,
        "No Authorization Bearer token",
        settings,
        request,
    )


async def close_validator() -> None:
    """Close the validator's HTTP client. Call on app shutdown."""
    global _validator
    with _validator_lock:
        validator = _validator
        _validator = None
    if validator is not None:
        await validator.close()
