# Copyright (c) Maltego Technologies GmbH.
"""RFC 9457 Problem Details for auth failures."""

from enum import Enum
from typing import Any, Optional

import fastapi

from maltego.model.exception import MaltegoTransformProblemDetail
from maltego.auth.settings import AuthSettings
from maltego.auth.validator import ValidationErrorKind

AUTH_PROBLEM_TYPE_PREFIX = "urn:maltego-transforms:problem:auth:"


class MaltegoAuthErrorCode(str, Enum):
    """Stable auth error codes for machine-readable client handling."""

    CREDENTIALS_MISSING = "auth.credentials_missing"
    TOKEN_EXPIRED = "auth.token_expired"
    ASSERTION_EXPIRED = "auth.assertion_expired"
    CREDENTIALS_INVALID = "auth.credentials_invalid"
    ACCESS_DENIED = "auth.access_denied"
    PROVIDER_UNAVAILABLE = "auth.provider_unavailable"
    INTERNAL_ERROR = "auth.internal_error"


class MaltegoAuthProblemDetail(MaltegoTransformProblemDetail):
    """RFC 9457 auth problem body plus SDK auth extension members."""

    error_code: MaltegoAuthErrorCode
    auth_origin: Optional[str] = None
    provider_type: Optional[str] = None
    reason: str
    refresh_required: bool
    retryable: bool


class AuthProblemException(Exception):
    """Exception carrying an auth Problem Details response."""

    def __init__(self, problem: MaltegoAuthProblemDetail, headers: Optional[dict[str, str]] = None):
        super().__init__(problem.detail)
        self.problem = problem
        self.headers = headers or {}
        self.status_code = problem.status


def _type(name: str) -> str:
    return f"{AUTH_PROBLEM_TYPE_PREFIX}{name}"


def _request_instance(request: Any) -> str:
    if request is None:
        return ""
    scope = getattr(request, "scope", None)
    if isinstance(scope, dict):
        path = scope.get("path")
        if path:
            return str(path)
        return ""
    try:
        url = getattr(request, "url", None)
        if url is not None and getattr(url, "path", None):
            return url.path
    except (KeyError, RuntimeError):
        return ""
    return ""


def _settings_value(value: Any) -> Optional[str]:
    return value.value if hasattr(value, "value") else value


def build_auth_problem(
    error_kind: ValidationErrorKind,
    error_message: Optional[str],
    settings: AuthSettings,
    request: Any,
) -> AuthProblemException:
    """Map a validator failure to an auth problem."""
    del error_message  # Raw validator messages are logged separately, not exposed.

    auth_origin = _settings_value(settings.token_origin)
    provider_type = _settings_value(settings.provider_type)
    headers: dict[str, str] = {}

    if error_kind == ValidationErrorKind.NO_TOKEN:
        problem = MaltegoAuthProblemDetail(
            type=_type("credentials-missing"),
            title="Authentication credentials missing",
            status=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="No accepted authentication credential was provided.",
            instance=_request_instance(request),
            error_code=MaltegoAuthErrorCode.CREDENTIALS_MISSING,
            auth_origin=auth_origin,
            provider_type=provider_type,
            reason="missing",
            refresh_required=False,
            retryable=False,
        )
        headers["WWW-Authenticate"] = "Bearer"
    elif error_kind == ValidationErrorKind.EXPIRED_TOKEN:
        problem = MaltegoAuthProblemDetail(
            type=_type("token-expired"),
            title="Authentication token expired",
            status=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="The authentication token has expired. Obtain a fresh SSO credential and retry the request.",
            instance=_request_instance(request),
            error_code=MaltegoAuthErrorCode.TOKEN_EXPIRED,
            auth_origin=auth_origin,
            provider_type=provider_type,
            reason="expired",
            refresh_required=True,
            retryable=False,
        )
        headers["WWW-Authenticate"] = (
            'Bearer error="invalid_token", error_description="The access token expired"'
        )
    elif error_kind == ValidationErrorKind.EXPIRED_ASSERTION:
        problem = MaltegoAuthProblemDetail(
            type=_type("assertion-expired"),
            title="SAML assertion expired",
            status=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="The SAML assertion has expired. Re-authenticate through the upstream SSO provider and retry the request.",
            instance=_request_instance(request),
            error_code=MaltegoAuthErrorCode.ASSERTION_EXPIRED,
            auth_origin=auth_origin,
            provider_type=provider_type,
            reason="expired",
            refresh_required=True,
            retryable=False,
        )
        headers["WWW-Authenticate"] = (
            'Bearer error="invalid_token", error_description="The SAML assertion expired"'
        )
    elif error_kind == ValidationErrorKind.INVALID_CLAIMS:
        problem = MaltegoAuthProblemDetail(
            type=_type("access-denied"),
            title="Access denied",
            status=fastapi.status.HTTP_403_FORBIDDEN,
            detail="The authenticated principal is not allowed to access this transform.",
            instance=_request_instance(request),
            error_code=MaltegoAuthErrorCode.ACCESS_DENIED,
            auth_origin=auth_origin,
            provider_type=provider_type,
            reason="access_denied",
            refresh_required=False,
            retryable=False,
        )
    elif error_kind in {
        ValidationErrorKind.JWKS_UNAVAILABLE,
        ValidationErrorKind.PROVIDER_UNAVAILABLE,
    }:
        problem = MaltegoAuthProblemDetail(
            type=_type("provider-unavailable"),
            title="Authentication provider unavailable",
            status=fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The authentication provider could not be reached. Retry the request later.",
            instance=_request_instance(request),
            error_code=MaltegoAuthErrorCode.PROVIDER_UNAVAILABLE,
            auth_origin=auth_origin,
            provider_type=provider_type,
            reason="provider_unavailable",
            refresh_required=False,
            retryable=True,
        )
    elif error_kind == ValidationErrorKind.INTERNAL_ERROR:
        problem = MaltegoAuthProblemDetail(
            type=_type("internal-error"),
            title="Authentication error",
            status=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal authentication error occurred.",
            instance=_request_instance(request),
            error_code=MaltegoAuthErrorCode.INTERNAL_ERROR,
            auth_origin=auth_origin,
            provider_type=provider_type,
            reason="internal_error",
            refresh_required=False,
            retryable=False,
        )
    else:
        problem = MaltegoAuthProblemDetail(
            type=_type("credentials-invalid"),
            title="Invalid authentication credentials",
            status=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="The authentication credential is invalid for this transform server.",
            instance=_request_instance(request),
            error_code=MaltegoAuthErrorCode.CREDENTIALS_INVALID,
            auth_origin=auth_origin,
            provider_type=provider_type,
            reason="invalid",
            refresh_required=False,
            retryable=False,
        )
        headers["WWW-Authenticate"] = 'Bearer error="invalid_token"'

    return AuthProblemException(problem=problem, headers=headers)
