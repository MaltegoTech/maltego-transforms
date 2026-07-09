# Copyright (c) Maltego Technologies GmbH.
import pytest
from starlette.requests import Request

from maltego.auth import AuthSettings
from maltego.auth.problem import MaltegoAuthErrorCode, MaltegoAuthProblemDetail, build_auth_problem
from maltego.model.exception import MaltegoTransformProblemDetail
from maltego.auth.validator import ValidationErrorKind

pytestmark = pytest.mark.security


def _request(path: str = "/v3/transforms/acme.example/run") -> Request:
    return Request({"type": "http", "path": path, "headers": []})


def test_expired_oidc_token_maps_to_401_problem_details():
    settings = AuthSettings(
        enabled=True,
        token_origin="sso",
        provider_type="oidc",
        provider_url="https://id.example/realms/customer",
    )

    exc = build_auth_problem(
        ValidationErrorKind.EXPIRED_TOKEN,
        "raw validator message must not leak",
        settings,
        _request(),
    )

    assert exc.status_code == 401
    assert isinstance(exc.problem, MaltegoAuthProblemDetail)
    assert isinstance(exc.problem, MaltegoTransformProblemDetail)
    assert exc.headers["WWW-Authenticate"] == (
        'Bearer error="invalid_token", error_description="The access token expired"'
    )
    assert exc.problem.type == "urn:maltego-transforms:problem:auth:token-expired"
    assert exc.problem.status == 401
    assert exc.problem.error_code == MaltegoAuthErrorCode.TOKEN_EXPIRED
    assert exc.problem.auth_origin == "sso"
    assert exc.problem.provider_type == "oidc"
    assert exc.problem.reason == "expired"
    assert exc.problem.refresh_required is True
    assert exc.problem.retryable is False
    assert "raw validator" not in exc.problem.detail


def test_auth_problem_details_serializes_only_rfc_members_and_defined_extensions():
    problem = MaltegoAuthProblemDetail(
        type="urn:maltego-transforms:problem:auth:credentials-invalid",
        title="Invalid authentication credentials",
        status=401,
        detail="The authentication credential is invalid for this transform server.",
        instance="/v3/transforms/acme.example/run",
        error_code=MaltegoAuthErrorCode.CREDENTIALS_INVALID,
        auth_origin="sso",
        provider_type="jwt",
        reason="invalid",
        refresh_required=False,
        retryable=False,
    )

    assert problem.model_dump(mode="json") == {
        "type": "urn:maltego-transforms:problem:auth:credentials-invalid",
        "title": "Invalid authentication credentials",
        "status": 401,
        "detail": "The authentication credential is invalid for this transform server.",
        "instance": "/v3/transforms/acme.example/run",
        "error_code": "auth.credentials_invalid",
        "auth_origin": "sso",
        "provider_type": "jwt",
        "reason": "invalid",
        "refresh_required": False,
        "retryable": False,
    }


def test_auth_problem_detail_declares_only_auth_extensions():
    assert set(MaltegoAuthProblemDetail.__annotations__) == {
        "error_code",
        "auth_origin",
        "provider_type",
        "reason",
        "refresh_required",
        "retryable",
    }


def test_expired_saml_assertion_maps_to_401_problem_details():
    settings = AuthSettings(
        enabled=True,
        token_origin="sso",
        provider_type="saml",
        provider_url="https://idp.example/metadata",
    )

    exc = build_auth_problem(
        ValidationErrorKind.EXPIRED_ASSERTION,
        "SAML assertion has expired",
        settings,
        _request(),
    )

    assert exc.status_code == 401
    assert exc.headers["WWW-Authenticate"] == (
        'Bearer error="invalid_token", error_description="The SAML assertion expired"'
    )
    assert exc.problem.type == "urn:maltego-transforms:problem:auth:assertion-expired"
    assert exc.problem.status == 401
    assert exc.problem.error_code == MaltegoAuthErrorCode.ASSERTION_EXPIRED
    assert exc.problem.auth_origin == "sso"
    assert exc.problem.provider_type == "saml"
    assert exc.problem.reason == "expired"
    assert exc.problem.refresh_required is True


def test_provider_unavailable_maps_to_503_retryable_problem_details():
    settings = AuthSettings(
        enabled=True,
        token_origin="sso",
        provider_type="oidc",
        provider_url="https://id.example/realms/customer",
    )

    exc = build_auth_problem(
        ValidationErrorKind.PROVIDER_UNAVAILABLE,
        "metadata URL must not leak",
        settings,
        _request(),
    )

    assert exc.status_code == 503
    assert exc.problem.type == "urn:maltego-transforms:problem:auth:provider-unavailable"
    assert exc.problem.status == 503
    assert exc.problem.error_code == MaltegoAuthErrorCode.PROVIDER_UNAVAILABLE
    assert exc.problem.reason == "provider_unavailable"
    assert exc.problem.refresh_required is False
    assert exc.problem.retryable is True
    assert "metadata URL" not in exc.problem.detail


def test_invalid_credentials_map_to_401_without_refresh_required():
    settings = AuthSettings(
        enabled=True,
        token_origin="sso",
        provider_type="jwt",
        provider_url="https://id.example/jwks",
    )

    exc = build_auth_problem(
        ValidationErrorKind.INVALID_TOKEN,
        "bad signature internals",
        settings,
        _request(),
    )

    assert exc.status_code == 401
    assert exc.problem.type == "urn:maltego-transforms:problem:auth:credentials-invalid"
    assert exc.problem.status == 401
    assert exc.problem.error_code == MaltegoAuthErrorCode.CREDENTIALS_INVALID
    assert exc.problem.reason == "invalid"
    assert exc.problem.refresh_required is False
    assert exc.problem.retryable is False


def test_custom_policy_denial_maps_to_403_problem_details():
    settings = AuthSettings(
        enabled=True,
        token_origin="sso",
        provider_type="oidc",
        provider_url="https://id.example/realms/customer",
    )

    exc = build_auth_problem(
        ValidationErrorKind.INVALID_CLAIMS,
        "custom policy message",
        settings,
        _request("/v3/transforms/private/run"),
    )

    assert exc.status_code == 403
    assert exc.problem.type == "urn:maltego-transforms:problem:auth:access-denied"
    assert exc.problem.status == 403
    assert exc.problem.error_code == MaltegoAuthErrorCode.ACCESS_DENIED
    assert exc.problem.instance == "/v3/transforms/private/run"
