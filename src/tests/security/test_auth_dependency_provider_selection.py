# Copyright (c) Maltego Technologies GmbH.

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request

from maltego.auth import AuthProviderType, AuthSettings, set_auth_settings, reset_auth_settings
from maltego.auth.dependency import _get_validator, close_validator, optional_auth
from maltego.auth.jwt_validator import JWTTokenValidator
from maltego.auth.oidc_validator import OIDCTokenValidator
from maltego.auth.problem import AuthProblemException
from maltego.auth.saml_validator import SAMLTokenValidator
from maltego.auth.validator import AuthValidationFailure, AuthValidationSuccess, ValidationErrorKind

pytestmark = pytest.mark.security


def _reset_validator_cache():
    import maltego.auth.dependency as dependency

    dependency._validator = None


def _set_validator_cache(value):
    import maltego.auth.dependency as dependency

    dependency._validator = value


def test_get_validator_selects_jwt_validator():
    reset_auth_settings()
    _reset_validator_cache()
    set_auth_settings(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type=AuthProviderType.JWT,
            provider_url="https://id.example/jwks",
        )
    )

    validator = _get_validator()

    assert isinstance(validator, JWTTokenValidator)


def test_get_validator_selects_oidc_validator():
    reset_auth_settings()
    _reset_validator_cache()
    set_auth_settings(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type=AuthProviderType.OIDC,
            provider_url="https://id.example/realms/test",
        )
    )

    validator = _get_validator()

    assert isinstance(validator, OIDCTokenValidator)


def test_get_validator_selects_saml_validator():
    reset_auth_settings()
    _reset_validator_cache()
    set_auth_settings(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type=AuthProviderType.SAML,
            saml_idp_cert="-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n",
            issuer="https://idp.example/metadata",
        )
    )

    validator = _get_validator()

    assert isinstance(validator, SAMLTokenValidator)


def test_get_validator_initializes_single_instance_under_threaded_concurrency():
    reset_auth_settings()
    _reset_validator_cache()
    created = []

    class FakeValidator:
        async def validate_token(self, token):
            return None, None, {"sub": token}

        async def close(self):
            return None

    def factory(settings):
        created.append(object())
        time.sleep(0.01)
        return FakeValidator()

    set_auth_settings(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            validator_factory=factory,
        )
    )
    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            validators = list(executor.map(lambda _: _get_validator(), range(20)))

        assert len({id(validator) for validator in validators}) == 1
        assert len(created) == 1
    finally:
        _reset_validator_cache()
        reset_auth_settings()


@pytest.mark.asyncio
async def test_close_validator_is_idempotent_under_concurrent_calls():
    reset_auth_settings()
    _reset_validator_cache()
    close_calls = 0
    entered_close = asyncio.Event()
    release_close = asyncio.Event()

    class FakeValidator:
        async def validate_token(self, token):
            return None, None, {"sub": token}

        async def close(self):
            nonlocal close_calls
            close_calls += 1
            if close_calls == 1:
                entered_close.set()
                await release_close.wait()
            return None

    def factory(settings):
        return FakeValidator()

    set_auth_settings(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            validator_factory=factory,
        )
    )
    _set_validator_cache(_get_validator())
    try:
        first_close = asyncio.create_task(close_validator())
        await entered_close.wait()
        second_close = asyncio.create_task(close_validator())
        release_close.set()
        await first_close
        await second_close

        assert close_calls == 1
    finally:
        _reset_validator_cache()
        reset_auth_settings()


async def _cleanup_validator():
    await close_validator()
    reset_auth_settings()


def _mock_request(upstream_identity_method: bytes | None = b"OIDC"):
    headers = [(b"user-agent", b"test")]
    if upstream_identity_method is not None:
        headers.append((b"maltego-upstream-identity-method", upstream_identity_method))
    scope = {"type": "http", "headers": headers}
    request = Request(scope)
    request.state.bearer_token = None
    request.state.identity = None
    request.state.rate_limit_key = None
    return request


@pytest.mark.asyncio
async def test_optional_auth_stores_generic_and_jwt_claims_for_jwt():
    reset_auth_settings()
    set_auth_settings(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type=AuthProviderType.JWT,
            provider_url="https://id.example/jwks",
        )
    )
    request = _mock_request()
    creds = MagicMock()
    creds.credentials = "jwt-token"
    validator = AsyncMock()
    validator.validate_token.return_value = (None, None, {"sub": "user-123"})

    with patch("maltego.auth.dependency._get_validator", return_value=validator):
        await optional_auth(request, creds)

    assert request.state.auth_claims == {"sub": "user-123"}
    assert request.state.jwt_claims == {"sub": "user-123"}
    await _cleanup_validator()


@pytest.mark.asyncio
async def test_optional_auth_sso_origin_uses_authorization_not_maltego_identity_header():
    reset_auth_settings()
    set_auth_settings(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type=AuthProviderType.OIDC,
            provider_url="https://id.example/realms/test",
        )
    )
    request = Request(
        {
            "type": "http",
            "headers": [
                (b"authorization", b"Bearer sso-token"),
                (b"maltego-identity-authorization", b"maltego-token"),
                (b"maltego-upstream-identity-method", b"OIDC"),
            ],
        }
    )
    creds = MagicMock()
    creds.credentials = "sso-token"
    validator = AsyncMock()
    validator.validate_token.return_value = AuthValidationSuccess(
        identity_claims={"sub": "sso-user"},
        auth_claims={"sub": "sso-user"},
        protocol="oidc",
        raw_payload={"sub": "sso-user"},
    )

    with patch("maltego.auth.dependency._get_validator", return_value=validator):
        await optional_auth(request, creds)

    validator.validate_token.assert_awaited_once_with("sso-token")
    assert request.state.bearer_token == "sso-token"
    assert request.state.maltego_identity_token == "maltego-token"
    assert request.state.auth_token_origin == "sso"
    assert request.state.auth_credential_header == "authorization"
    assert request.state.auth_upstream_identity_method == "oidc"
    await _cleanup_validator()


@pytest.mark.asyncio
async def test_optional_auth_maltego_id_origin_uses_maltego_identity_header_without_authorization():
    reset_auth_settings()
    set_auth_settings(
        AuthSettings(
            enabled=True,
            token_origin="maltego_id",
            provider_type=AuthProviderType.OIDC,
            provider_url="https://id.example/realms/test",
        )
    )
    request = Request(
        {
            "type": "http",
            "headers": [
                (b"maltego-identity-authorization", b"Bearer maltego-token"),
            ],
        }
    )
    validator = AsyncMock()
    validator.validate_token.return_value = AuthValidationSuccess(
        identity_claims={"sub": "maltego-user"},
        auth_claims={"sub": "maltego-user"},
        protocol="oidc",
        raw_payload={"sub": "maltego-user"},
    )

    with patch("maltego.auth.dependency._get_validator", return_value=validator):
        await optional_auth(request, None)

    validator.validate_token.assert_awaited_once_with("maltego-token")
    assert request.state.bearer_token is None
    assert request.state.maltego_identity_token == "maltego-token"
    assert request.state.auth_token_origin == "maltego_id"
    assert request.state.auth_credential_header == "maltego-identity-authorization"
    assert request.state.auth_upstream_identity_method is None
    await _cleanup_validator()


@pytest.mark.asyncio
async def test_optional_auth_stores_generic_claims_without_jwt_claims_for_saml():
    reset_auth_settings()
    set_auth_settings(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type=AuthProviderType.SAML,
            saml_idp_cert="-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n",
            issuer="https://idp.example/metadata",
        )
    )
    request = _mock_request(b"SAML")
    creds = MagicMock()
    creds.credentials = "saml-token"
    validator = AsyncMock()
    validator.validate_token.return_value = (None, None, {"sub": "user@example.com", "email": "user@example.com"})

    with patch("maltego.auth.dependency._get_validator", return_value=validator):
        await optional_auth(request, creds)

    assert request.state.auth_claims == {"sub": "user@example.com", "email": "user@example.com"}
    assert not hasattr(request.state, "jwt_claims")
    await _cleanup_validator()


@pytest.mark.asyncio
async def test_optional_auth_accepts_auth_validation_success_result():
    reset_auth_settings()
    set_auth_settings(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type=AuthProviderType.SAML,
            saml_idp_cert="-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n",
            issuer="https://idp.example/metadata",
        )
    )
    request = _mock_request(b"SAML")
    creds = MagicMock()
    creds.credentials = "saml-token"
    validator = AsyncMock()
    validator.validate_token.return_value = AuthValidationSuccess(
        identity_claims={"sub": "user@example.com", "email": "user@example.com"},
        auth_claims={"external_id": "user@example.com"},
        protocol="saml",
        raw_payload={"assertion_id": "_test-assertion"},
    )

    with patch("maltego.auth.dependency._get_validator", return_value=validator):
        await optional_auth(request, creds)

    assert request.state.identity.sub == "user@example.com"
    assert request.state.auth_claims == {"external_id": "user@example.com"}
    assert request.state.auth_payload == {"assertion_id": "_test-assertion"}
    assert not hasattr(request.state, "jwt_claims")
    await _cleanup_validator()


@pytest.mark.asyncio
async def test_optional_auth_accepts_auth_validation_failure_result():
    reset_auth_settings()
    set_auth_settings(
        AuthSettings(
            enabled=True,
            mode="warn",
            token_origin="sso",
            provider_type=AuthProviderType.JWT,
            provider_url="https://id.example/jwks",
        )
    )
    request = _mock_request()
    creds = MagicMock()
    creds.credentials = "jwt-token"
    validator = AsyncMock()
    validator.validate_token.return_value = AuthValidationFailure(
        ValidationErrorKind.INVALID_CLAIMS,
        "Tenant not allowed",
    )

    with patch("maltego.auth.dependency._get_validator", return_value=validator):
        await optional_auth(request, creds)

    assert not hasattr(request.state, "auth_claims")
    assert not hasattr(request.state, "jwt_claims")
    await _cleanup_validator()


@pytest.mark.asyncio
async def test_optional_auth_logs_validation_failure_detail_in_strict_mode(caplog):
    reset_auth_settings()
    set_auth_settings(
        AuthSettings(
            enabled=True,
            mode="strict",
            token_origin="sso",
            provider_type=AuthProviderType.SAML,
            saml_idp_cert="-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n",
            issuer="https://idp.example/metadata",
        )
    )
    request = _mock_request(b"SAML")
    creds = MagicMock()
    creds.credentials = "saml-token"
    validator = AsyncMock()
    validator.validate_token.return_value = AuthValidationFailure(
        ValidationErrorKind.INVALID_TOKEN,
        "SAML signature validation failed: bad signature",
    )

    caplog.set_level(logging.DEBUG, logger="maltego.auth.dependency")
    with patch("maltego.auth.dependency._get_validator", return_value=validator):
        with pytest.raises(AuthProblemException):
            await optional_auth(request, creds)

    assert "Auth validation failed" in caplog.text
    assert "provider_type=saml" in caplog.text
    assert "kind=invalid_token" in caplog.text
    assert "Auth validation failure detail" in caplog.text
    assert "SAML signature validation failed: bad signature" in caplog.text
    await _cleanup_validator()


@pytest.mark.asyncio
async def test_optional_auth_maps_malformed_custom_validator_result_to_internal_problem():
    reset_auth_settings()
    set_auth_settings(
        AuthSettings(
            enabled=True,
            validator_factory=lambda settings: object(),
        )
    )
    request = _mock_request()
    creds = MagicMock()
    creds.credentials = "jwt-token"
    validator = AsyncMock()
    validator.validate_token.return_value = object()

    with patch("maltego.auth.dependency._get_validator", return_value=validator):
        with pytest.raises(AuthProblemException) as exc_info:
            await optional_auth(request, creds)

    assert exc_info.value.status_code == 500
    assert exc_info.value.problem.error_code.value == "auth.internal_error"
    await _cleanup_validator()


@pytest.mark.asyncio
async def test_optional_auth_preserves_jwt_claims_for_legacy_custom_validator_without_provider_type():
    reset_auth_settings()
    set_auth_settings(
        AuthSettings(
            enabled=True,
            validator_factory=lambda settings: object(),
        )
    )
    request = _mock_request()
    creds = MagicMock()
    creds.credentials = "legacy-token"
    validator = AsyncMock()
    validator.validate_token.return_value = (None, None, {"sub": "legacy-user"})

    with patch("maltego.auth.dependency._get_validator", return_value=validator):
        await optional_auth(request, creds)

    assert request.state.auth_claims == {"sub": "legacy-user"}
    assert request.state.jwt_claims == {"sub": "legacy-user"}
    await _cleanup_validator()


@pytest.mark.asyncio
async def test_optional_auth_maltego_id_origin_rejects_missing_maltego_identity_header():
    reset_auth_settings()
    set_auth_settings(
        AuthSettings(
            enabled=True,
            token_origin="maltego_id",
            provider_type=AuthProviderType.OIDC,
            provider_url="https://id.example/realms/test",
        )
    )
    request = Request({"type": "http", "headers": []})

    with pytest.raises(AuthProblemException) as exc_info:
        await optional_auth(request, None)

    assert exc_info.value.status_code == 401
    assert exc_info.value.problem.error_code.value == "auth.credentials_missing"
    assert exc_info.value.problem.auth_origin == "maltego_id"
    await _cleanup_validator()


@pytest.mark.asyncio
async def test_optional_auth_rejects_missing_upstream_identity_method_for_sso_token_before_validator_selection():
    reset_auth_settings()
    set_auth_settings(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type=AuthProviderType.OIDC,
            provider_url="https://id.example/realms/test",
        )
    )
    request = Request(
        {
            "type": "http",
            "headers": [(b"authorization", b"Bearer sso-token")],
        }
    )
    creds = MagicMock()
    creds.credentials = "sso-token"

    with patch("maltego.auth.dependency._get_validator") as get_validator:
        with pytest.raises(AuthProblemException) as exc_info:
            await optional_auth(request, creds)

    assert exc_info.value.status_code == 401
    assert exc_info.value.problem.error_code.value == "auth.credentials_invalid"
    assert exc_info.value.problem.provider_type == "oidc"
    get_validator.assert_not_called()
    await _cleanup_validator()


@pytest.mark.asyncio
async def test_optional_auth_allows_missing_upstream_identity_method_for_maltego_identity_token():
    reset_auth_settings()
    set_auth_settings(
        AuthSettings(
            enabled=True,
            token_origin="maltego_id",
            provider_type=AuthProviderType.OIDC,
            provider_url="https://id.example/realms/test",
        )
    )
    request = Request(
        {
            "type": "http",
            "headers": [(b"maltego-identity-authorization", b"maltego-token")],
        }
    )
    validator = AsyncMock()
    validator.validate_token.return_value = AuthValidationSuccess(
        identity_claims={"sub": "maltego-user"},
        auth_claims={"sub": "maltego-user"},
        protocol="oidc",
        raw_payload={"sub": "maltego-user"},
    )

    with patch("maltego.auth.dependency._get_validator", return_value=validator):
        await optional_auth(request, None)

    validator.validate_token.assert_awaited_once_with("maltego-token")
    assert request.state.auth_token_origin == "maltego_id"
    assert request.state.auth_credential_header == "maltego-identity-authorization"
    assert request.state.auth_upstream_identity_method is None
    await _cleanup_validator()


@pytest.mark.asyncio
async def test_optional_auth_rejects_missing_upstream_identity_method_for_custom_validator_before_validator_selection():
    reset_auth_settings()
    set_auth_settings(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            validator_factory=lambda settings: object(),
        )
    )
    request = Request(
        {
            "type": "http",
            "headers": [(b"authorization", b"Bearer custom-token")],
        }
    )
    creds = MagicMock()
    creds.credentials = "custom-token"

    with patch("maltego.auth.dependency._get_validator") as get_validator:
        with pytest.raises(AuthProblemException) as exc_info:
            await optional_auth(request, creds)

    assert exc_info.value.status_code == 401
    assert exc_info.value.problem.error_code.value == "auth.credentials_invalid"
    get_validator.assert_not_called()
    await _cleanup_validator()


@pytest.mark.asyncio
async def test_optional_auth_allows_missing_upstream_identity_method_without_configured_token_origin():
    reset_auth_settings()
    set_auth_settings(
        AuthSettings(
            enabled=True,
            validator_factory=lambda settings: object(),
        )
    )
    request = Request(
        {
            "type": "http",
            "headers": [(b"authorization", b"Bearer custom-token")],
        }
    )
    creds = MagicMock()
    creds.credentials = "custom-token"
    validator = AsyncMock()
    validator.validate_token.return_value = AuthValidationSuccess(
        identity_claims={"sub": "custom-user"},
        auth_claims={"sub": "custom-user"},
        protocol="debug",
        raw_payload={"sub": "custom-user"},
    )

    with patch("maltego.auth.dependency._get_validator", return_value=validator):
        await optional_auth(request, creds)

    validator.validate_token.assert_awaited_once_with("custom-token")
    assert request.state.auth_token_origin is None
    assert request.state.auth_credential_header == "authorization"
    assert request.state.auth_upstream_identity_method is None
    await _cleanup_validator()


@pytest.mark.asyncio
async def test_optional_auth_without_configured_token_origin_accepts_maltego_identity_header():
    reset_auth_settings()
    set_auth_settings(
        AuthSettings(
            enabled=True,
            validator_factory=lambda settings: object(),
        )
    )
    request = Request(
        {
            "type": "http",
            "headers": [(b"maltego-identity-authorization", b"maltego-token")],
        }
    )
    validator = AsyncMock()
    validator.validate_token.return_value = AuthValidationSuccess(
        identity_claims={"sub": "maltego-user"},
        auth_claims={"sub": "maltego-user"},
        protocol="debug",
        raw_payload={"sub": "maltego-user"},
    )

    with patch("maltego.auth.dependency._get_validator", return_value=validator):
        await optional_auth(request, None)

    validator.validate_token.assert_awaited_once_with("maltego-token")
    assert request.state.bearer_token is None
    assert request.state.maltego_identity_token == "maltego-token"
    assert request.state.auth_token_origin == "maltego_id"
    assert request.state.auth_credential_header == "maltego-identity-authorization"
    assert request.state.auth_upstream_identity_method is None
    await _cleanup_validator()


@pytest.mark.asyncio
async def test_optional_auth_rejects_empty_maltego_identity_bearer_value():
    reset_auth_settings()
    set_auth_settings(
        AuthSettings(
            enabled=True,
            token_origin="maltego_id",
            provider_type=AuthProviderType.OIDC,
            provider_url="https://id.example/realms/test",
        )
    )
    request = Request(
        {
            "type": "http",
            "headers": [(b"maltego-identity-authorization", b"Bearer ")],
        }
    )

    with pytest.raises(AuthProblemException) as exc_info:
        await optional_auth(request, None)

    assert exc_info.value.status_code == 401
    assert exc_info.value.problem.error_code.value == "auth.credentials_invalid"
    await _cleanup_validator()


@pytest.mark.asyncio
async def test_optional_auth_rejects_unknown_upstream_identity_method():
    reset_auth_settings()
    set_auth_settings(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type=AuthProviderType.OIDC,
            provider_url="https://id.example/realms/test",
        )
    )
    request = Request(
        {
            "type": "http",
            "headers": [
                (b"authorization", b"Bearer oidc-token"),
                (b"maltego-upstream-identity-method", b"LDAP"),
            ],
        }
    )
    creds = MagicMock()
    creds.credentials = "oidc-token"

    with pytest.raises(AuthProblemException) as exc_info:
        await optional_auth(request, creds)

    assert exc_info.value.status_code == 401
    assert exc_info.value.problem.error_code.value == "auth.credentials_invalid"
    await _cleanup_validator()


@pytest.mark.asyncio
async def test_optional_auth_rejects_method_header_conflicting_with_configured_provider_type():
    reset_auth_settings()
    set_auth_settings(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type=AuthProviderType.SAML,
            saml_idp_cert="-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n",
            issuer="https://idp.example/metadata",
        )
    )
    request = Request(
        {
            "type": "http",
            "headers": [
                (b"authorization", b"Bearer saml-token"),
                (b"maltego-upstream-identity-method", b"OIDC"),
            ],
        }
    )
    creds = MagicMock()
    creds.credentials = "saml-token"

    with patch("maltego.auth.dependency._get_validator") as get_validator:
        with pytest.raises(AuthProblemException) as exc_info:
            await optional_auth(request, creds)

    assert exc_info.value.status_code == 401
    assert exc_info.value.problem.error_code.value == "auth.credentials_invalid"
    assert exc_info.value.problem.provider_type == "saml"
    get_validator.assert_not_called()
    await _cleanup_validator()


@pytest.mark.asyncio
async def test_optional_auth_rejects_saml_method_header_for_configured_jwt_provider_before_validator_selection():
    reset_auth_settings()
    set_auth_settings(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type=AuthProviderType.JWT,
            provider_url="https://id.example/jwks",
        )
    )
    request = Request(
        {
            "type": "http",
            "headers": [
                (b"authorization", b"Bearer jwt-token"),
                (b"maltego-upstream-identity-method", b"SAML"),
            ],
        }
    )
    creds = MagicMock()
    creds.credentials = "jwt-token"

    with patch("maltego.auth.dependency._get_validator") as get_validator:
        with pytest.raises(AuthProblemException) as exc_info:
            await optional_auth(request, creds)

    assert exc_info.value.status_code == 401
    assert exc_info.value.problem.error_code.value == "auth.credentials_invalid"
    assert exc_info.value.problem.provider_type == "jwt"
    get_validator.assert_not_called()
    await _cleanup_validator()


@pytest.mark.asyncio
async def test_optional_auth_public_paths_bypass_auth_when_enabled():
    reset_auth_settings()
    set_auth_settings(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type=AuthProviderType.JWT,
            provider_url="https://id.example/jwks",
            public_paths={"/health"},
        )
    )
    scope = {"type": "http", "headers": [], "path": "/health"}
    request = Request(scope)
    request.state.bearer_token = None
    request.state.identity = None
    request.state.rate_limit_key = None

    # No token, no validator call — should pass because path is whitelisted
    await optional_auth(request, None)
    await _cleanup_validator()


@pytest.mark.asyncio
async def test_optional_auth_public_paths_does_not_bypass_non_listed_paths():
    reset_auth_settings()
    set_auth_settings(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type=AuthProviderType.JWT,
            provider_url="https://id.example/jwks",
            public_paths={"/health"},
        )
    )
    scope = {"type": "http", "headers": [], "path": "/transform"}
    request = Request(scope)
    request.state.bearer_token = None
    request.state.identity = None
    request.state.rate_limit_key = None

    # STRICT mode (default) with no token on a non-public path → 401
    with pytest.raises(AuthProblemException):
        await optional_auth(request, None)
    await _cleanup_validator()
