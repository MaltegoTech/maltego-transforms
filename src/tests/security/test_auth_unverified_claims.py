# Copyright (c) Maltego Technologies GmbH.

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request

from maltego.auth import AuthContext
from maltego.auth.claims import decode_unverified_jwt_claims
from maltego.auth.dependency import optional_auth
from maltego.auth.problem import AuthProblemException
from maltego.auth.saml_validator import decode_unverified_saml_claims
from maltego.auth.settings import (
    AuthMode,
    AuthProviderType,
    AuthSettings,
    reset_auth_settings,
    set_auth_settings,
)
from maltego.auth.validator import AuthValidationSuccess, ValidationErrorKind
from maltego.model.context import MaltegoContext, ResolvedCapabilitiesSet
from maltego.model.graph import MaltegoGraph
from maltego.protocol.v3.execution.transform_run import TransformRunRequest
from maltego.server.v3 import V3Server

pytestmark = pytest.mark.security


def _b64url_json(value):
    data = json.dumps(value, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _jwt(payload):
    return f"{_b64url_json({'alg': 'none'})}.{_b64url_json(payload)}.signature"


def _saml_token(
    issuer="https://idp.example/metadata",
    audience="https://transform.example",
    recipient="https://transform.example/run",
    name_id="user@example.com",
    wrap_response=False,
    response_signature=False,
):
    assertion = f"""
    <saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" ID="_test-assertion">
      <saml:Issuer>{issuer}</saml:Issuer>
      <saml:Subject>
        <saml:NameID>{name_id}</saml:NameID>
        <saml:SubjectConfirmation>
          <saml:SubjectConfirmationData Recipient="{recipient}" />
        </saml:SubjectConfirmation>
      </saml:Subject>
      <saml:Conditions>
        <saml:AudienceRestriction>
          <saml:Audience>{audience}</saml:Audience>
        </saml:AudienceRestriction>
      </saml:Conditions>
    </saml:Assertion>
    """
    if wrap_response:
        signature = ""
        if response_signature:
            signature = '<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#" />'
        xml = f"""
        <samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol">
          {signature}
          {assertion}
        </samlp:Response>
        """
    else:
        xml = assertion
    return base64.b64encode(xml.encode("utf-8")).decode("ascii")


def _request(headers=None):
    encoded_headers = []
    for name, value in (headers or {}).items():
        encoded_headers.append((name.lower().encode("latin-1"), value.encode("latin-1")))
    return Request({"type": "http", "headers": encoded_headers})


def _creds(token):
    creds = MagicMock()
    creds.credentials = token
    return creds


@pytest.fixture(autouse=True)
def cleanup_auth_settings():
    reset_auth_settings()
    yield
    reset_auth_settings()


def test_decode_unverified_jwt_claims_decodes_compact_jwt_payload():
    claims = {"sub": "user-123", "roles": ["analyst"]}

    assert decode_unverified_jwt_claims(_jwt(claims)) == claims


@pytest.mark.parametrize(
    "token",
    [
        "not-a-jwt",
        "one.two",
        "one.two.three.four",
        "not-base64.%%%bad%%%.signature",
        f"{_b64url_json({'alg': 'none'})}.{_b64url_json({'sub': 'user'})}.not+a+base64url+segment",
        f"{_b64url_json({'alg': 'none'})}.{_b64url_json(['not', 'an', 'object'])}.signature",
    ],
)
def test_decode_unverified_jwt_claims_returns_none_for_malformed_tokens(token):
    assert decode_unverified_jwt_claims(token) is None


def test_decode_unverified_saml_claims_decodes_saml_assertion_payload():
    claims = decode_unverified_saml_claims(_saml_token())

    assert claims == {
        "iss": "https://idp.example/metadata",
        "sub": "user@example.com",
        "email": "user@example.com",
        "aud": "https://transform.example",
        "saml_recipient": "https://transform.example/run",
        "saml_assertion_id": "_test-assertion",
        "saml_audiences": ["https://transform.example"],
        "saml_recipients": ["https://transform.example/run"],
        "saml_document_has_signature": False,
    }


def test_decode_unverified_saml_claims_detects_response_signature_wrapper():
    claims = decode_unverified_saml_claims(_saml_token(wrap_response=True, response_signature=True))

    assert claims["sub"] == "user@example.com"
    assert claims["saml_document_has_signature"] is True


def test_auth_settings_does_not_expose_unverified_claims_by_default():
    assert AuthSettings().expose_unverified_claims is False


def test_auth_settings_reads_expose_unverified_claims_from_environment(monkeypatch):
    monkeypatch.setenv("MALTEGO_SERVER_AUTH_EXPOSE_UNVERIFIED_CLAIMS", "true")

    assert AuthSettings().expose_unverified_claims is True


def test_auth_settings_reads_expose_unverified_claims_from_cli(monkeypatch):
    import sys

    monkeypatch.setattr(sys, "argv", ["maltego", "--auth-expose-unverified-claims"])

    assert AuthSettings().expose_unverified_claims is True


@pytest.mark.asyncio
async def test_optional_auth_disabled_does_not_decode_unverified_claims_by_default():
    token = _jwt({"sub": "untrusted-user"})
    request = _request()
    set_auth_settings(AuthSettings(enabled=False))

    await optional_auth(request, _creds(token))

    assert request.state.bearer_token == token
    assert not hasattr(request.state, "unverified_auth_claims")


@pytest.mark.asyncio
async def test_optional_auth_disabled_exposes_unverified_claims_when_opted_in():
    claims = {"sub": "untrusted-user", "tenant": "untrusted-tenant"}
    request = _request()
    set_auth_settings(AuthSettings(enabled=False, expose_unverified_claims=True))

    await optional_auth(request, _creds(_jwt(claims)))

    assert request.state.unverified_auth_claims == claims
    assert not hasattr(request.state, "identity")
    assert not hasattr(request.state, "rate_limit_key")


@pytest.mark.asyncio
async def test_optional_auth_disabled_auto_detects_unverified_saml_claims_when_opted_in():
    request = _request()
    set_auth_settings(AuthSettings(enabled=False, expose_unverified_claims=True))

    await optional_auth(request, _creds(_saml_token()))

    assert request.state.unverified_auth_claims["sub"] == "user@example.com"
    assert request.state.unverified_auth_claims["saml_assertion_id"] == "_test-assertion"


@pytest.mark.asyncio
async def test_optional_auth_disabled_exposes_unverified_saml_claims_with_saml_config():
    request = _request()
    set_auth_settings(
        AuthSettings(
            enabled=False,
            provider_type=AuthProviderType.SAML,
            expose_unverified_claims=True,
        )
    )

    await optional_auth(request, _creds(_saml_token()))

    assert request.state.unverified_auth_claims["sub"] == "user@example.com"
    assert request.state.unverified_auth_claims["saml_assertion_id"] == "_test-assertion"


@pytest.mark.asyncio
async def test_optional_auth_exposes_unverified_claims_on_warn_failure():
    claims = {"sub": "untrusted-user"}
    request = _request({"maltego-upstream-identity-method": "OIDC"})
    validator = AsyncMock()
    validator.validate_token.return_value = (
        ValidationErrorKind.INVALID_TOKEN,
        "bad token",
        None,
    )
    set_auth_settings(
        AuthSettings(
            enabled=True,
            mode=AuthMode.WARN,
            token_origin="sso",
            provider_type=AuthProviderType.JWT,
            provider_url="https://id.example/jwks",
            expose_unverified_claims=True,
        )
    )

    with patch("maltego.auth.dependency._get_validator", return_value=validator):
        await optional_auth(request, _creds(_jwt(claims)))

    assert request.state.unverified_auth_claims == claims
    assert not hasattr(request.state, "identity")
    assert not hasattr(request.state, "rate_limit_key")


@pytest.mark.asyncio
async def test_optional_auth_enabled_without_provider_type_does_not_infer_unverified_saml_claims_from_shape():
    request = _request({"maltego-upstream-identity-method": "SAML"})
    set_auth_settings(
        AuthSettings(
            enabled=True,
            validator_factory=lambda settings: object(),
            expose_unverified_claims=True,
        )
    )
    validator = AsyncMock()
    validator.validate_token.return_value = AuthValidationSuccess(
        identity_claims={"sub": "trusted-user"},
        auth_claims={"sub": "trusted-user"},
        protocol=None,
        raw_payload={"sub": "trusted-user"},
    )

    with patch("maltego.auth.dependency._get_validator", return_value=validator):
        await optional_auth(request, _creds(_saml_token()))

    assert not hasattr(request.state, "unverified_auth_claims")


@pytest.mark.asyncio
async def test_optional_auth_enabled_without_provider_type_does_not_infer_unverified_jwt_claims_from_shape():
    request = _request({"maltego-upstream-identity-method": "OIDC"})
    set_auth_settings(
        AuthSettings(
            enabled=True,
            validator_factory=lambda settings: object(),
            expose_unverified_claims=True,
        )
    )
    validator = AsyncMock()
    validator.validate_token.return_value = AuthValidationSuccess(
        identity_claims={"sub": "trusted-user"},
        auth_claims={"sub": "trusted-user"},
        protocol=None,
        raw_payload={"sub": "trusted-user"},
    )

    with patch("maltego.auth.dependency._get_validator", return_value=validator):
        await optional_auth(request, _creds(_jwt({"sub": "shape-guessed-user"})))

    assert not hasattr(request.state, "unverified_auth_claims")


@pytest.mark.asyncio
async def test_optional_auth_strict_failure_rejects_before_context_use():
    request = _request({"maltego-upstream-identity-method": "OIDC"})
    validator = AsyncMock()
    validator.validate_token.return_value = (
        ValidationErrorKind.INVALID_TOKEN,
        "bad token",
        None,
    )
    set_auth_settings(
        AuthSettings(
            enabled=True,
            mode=AuthMode.STRICT,
            token_origin="sso",
            provider_type=AuthProviderType.JWT,
            provider_url="https://id.example/jwks",
            expose_unverified_claims=True,
        )
    )

    with patch("maltego.auth.dependency._get_validator", return_value=validator):
        with pytest.raises(AuthProblemException) as exc_info:
            await optional_auth(request, _creds(_jwt({"sub": "untrusted-user"})))

    assert exc_info.value.status_code == 401
    assert exc_info.value.problem.error_code.value == "auth.credentials_invalid"


@pytest.mark.asyncio
async def test_optional_auth_keeps_identity_and_rate_limit_key_from_verified_claims():
    # F13: XFF is only trusted when the connecting client host is in the
    # forwarded_allow_ips list. This request has no client.host set (the ASGI
    # scope has no 'client' key), so XFF is ignored and the rate-limit key
    # is built without an IP suffix.
    request = _request({
        "X-Forwarded-For": "203.0.113.1",
        "maltego-upstream-identity-method": "OIDC",
    })
    validator = AsyncMock()
    validator.validate_token.return_value = (
        None,
        None,
        {"sub": "trusted-user", "organization": {"id": "trusted-org"}},
    )
    set_auth_settings(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type=AuthProviderType.JWT,
            provider_url="https://id.example/jwks",
            expose_unverified_claims=True,
        )
    )

    with patch("maltego.auth.dependency._get_validator", return_value=validator):
        await optional_auth(request, _creds(_jwt({"sub": "attacker", "organization": {"id": "attacker-org"}})))

    assert request.state.unverified_auth_claims == {"sub": "attacker", "organization": {"id": "attacker-org"}}
    assert request.state.identity.sub == "trusted-user"
    assert request.state.identity.org_id == "trusted-org"
    # F13: XFF ignored because client.host is None (no trusted proxy in scope).
    # Rate-limit key has no IP suffix when client IP is unavailable.
    assert request.state.rate_limit_key == "org:trusted-org:sub:trusted-user"


def test_maltego_context_exposes_optional_unverified_claims():
    claims = {"sub": "untrusted-user"}
    context = MaltegoContext(
        MaltegoGraph(),
        _request(),
        unverified_auth_claims=claims,
    )

    assert context.unverified_auth_claims == claims
    assert context.auth_context.unverified_auth_claims == claims


def test_maltego_context_exposes_validated_auth_data():
    auth_claims = {"tenant": "trusted-tenant", "groups": ["analyst"]}
    auth_payload = {"assertion_id": "_trusted-assertion"}
    context = MaltegoContext(
        MaltegoGraph(),
        _request(),
        auth_context=AuthContext(auth_claims=auth_claims, auth_payload=auth_payload),
    )

    assert context.auth_claims == auth_claims
    assert context.auth_payload == auth_payload


def test_maltego_context_exposes_selected_auth_metadata():
    auth_context = AuthContext(
        token_origin="maltego_id",
        credential_header="maltego-identity-authorization",
        upstream_identity_method="oidc",
    )
    context = MaltegoContext(
        MaltegoGraph(),
        _request(),
        auth_context=auth_context,
    )

    assert context.auth_context is auth_context
    assert context.auth_token_origin == "maltego_id"
    assert context.auth_credential_header == "maltego-identity-authorization"
    assert context.auth_upstream_identity_method == "oidc"


def test_v3_schedule_transform_passes_unverified_claims_to_context():
    request = _request()
    request.state.unverified_auth_claims = {"sub": "untrusted-user"}
    request.state.auth_claims = {"tenant": "trusted-tenant", "groups": ["analyst"]}
    request.state.auth_payload = {"assertion_id": "_trusted-assertion"}
    request.state.auth_token_origin = "maltego_id"
    request.state.auth_credential_header = "maltego-identity-authorization"
    request.state.auth_upstream_identity_method = "oidc"
    server = object.__new__(V3Server)
    server.transform_runner = MagicMock()
    server.transform_runner.schedule_transform.return_value = "run-id"
    transform = MagicMock()
    transform.name = "test-transform"
    transform_run_request = TransformRunRequest(
        input={
            "metadata": {"entities_types_stat": {}, "entities_total_count": 0},
            "graph": {"entities": [], "links": []},
        },
        transformSettings=[],
    )

    with (
        patch.object(V3Server, "_V3Server__parse_transform_run_request", return_value=({}, 12, 12, None)),
        patch("maltego.server.v3.get_transform_inputs", return_value=("input",)),
    ):
        run_id = server._V3Server__schedule_transform(
            transform_run_request,
            transform,
            request,
            "api-key",
            ResolvedCapabilitiesSet(set()),
        )

    assert run_id == "run-id"
    scheduled_context = server.transform_runner.schedule_transform.call_args.args[4]
    assert scheduled_context.unverified_auth_claims == {"sub": "untrusted-user"}
    assert scheduled_context.auth_claims == {"tenant": "trusted-tenant", "groups": ["analyst"]}
    assert scheduled_context.auth_payload == {"assertion_id": "_trusted-assertion"}
    assert scheduled_context.auth_context.token_origin == "maltego_id"
    assert scheduled_context.auth_token_origin == "maltego_id"
    assert scheduled_context.auth_credential_header == "maltego-identity-authorization"
    assert scheduled_context.auth_upstream_identity_method == "oidc"
    assert scheduled_context.identity is None
