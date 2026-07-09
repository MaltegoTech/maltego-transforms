# Copyright (c) Maltego Technologies GmbH.

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from starlette.requests import Request

from maltego.auth import (
    AuthMode,
    AuthProviderType,
    AuthSettings,
    Identity,
    get_auth_settings,
    reset_auth_settings,
    set_auth_settings,
)
from maltego.auth.dependency import (
    _build_rate_limit_key,
    close_validator,
    optional_auth,
)
from maltego.auth.validator import OIDCTokenValidator, ValidationErrorKind

pytestmark = pytest.mark.security


def _make_mock_validator(validate_result=None):
    """Create a mock validator."""
    mock = AsyncMock(spec=OIDCTokenValidator)
    if validate_result is None:
        # Default: return invalid token error
        validate_result = (ValidationErrorKind.INVALID_TOKEN, "Mocked error", None)
    mock.validate_token.return_value = validate_result
    return mock


def test_identity_from_claims_basic():
    """Identity parses standard JWT claims."""
    claims = {
        "iss": "https://id.maltego.com/realms/maltego",
        "sub": "user-123",
        "azp": "maltego-client",
        "sid": "session-456",
        "scope": "openid profile email",
    }
    identity = Identity.from_claims(claims)

    assert identity.iss == "https://id.maltego.com/realms/maltego"
    assert identity.sub == "user-123"
    assert identity.azp == "maltego-client"
    assert identity.scopes == ["openid", "profile", "email"]
    assert not identity.is_anonymous


def test_identity_from_claims_with_roles():
    """Identity parses Keycloak realm and client roles."""
    claims = {
        "sub": "user-123",
        "realm_access": {"roles": ["admin", "user"]},
        "resource_access": {
            "my-client": {"roles": ["read", "write"]},
            "other-client": {"roles": ["view"]},
        },
    }
    identity = Identity.from_claims(claims)

    assert identity.realm_roles == ["admin", "user"]
    assert identity.client_roles == {
        "my-client": ["read", "write"],
        "other-client": ["view"],
    }


def test_identity_from_claims_with_org():
    """Identity parses organization ID from Keycloak claims."""
    claims = {
        "sub": "user-123",
        "organization": {"id": "org-789", "name": "Acme Corp"},
    }
    identity = Identity.from_claims(claims)
    assert identity.org_id == "org-789"


def test_identity_is_anonymous():
    """Identity detects anonymous/placeholder subjects."""
    assert Identity(sub=None).is_anonymous
    assert Identity(sub="00000000-0000-0000-0000-000000000000").is_anonymous
    assert not Identity(sub="real-user-id").is_anonymous


def _make_request_with_ip(ip: str, xff: str = None) -> MagicMock:
    """Helper to create mock request with IP."""
    request = MagicMock(spec=Request)
    request.client = MagicMock()
    request.client.host = ip
    request.headers = {"X-Forwarded-For": xff} if xff else {}
    return request


def test_build_rate_limit_key_org_and_user():
    """Rate limit key: org + real user."""
    request = _make_request_with_ip("10.0.0.1")
    identity = Identity(sub="user-123", org_id="org-456")

    key = _build_rate_limit_key(request, identity)
    assert key == "org:org-456:sub:user-123:10.0.0.1"


def test_build_rate_limit_key_org_anonymous():
    """Rate limit key: org + anonymous (uses azp)."""
    request = _make_request_with_ip("10.0.0.1")
    identity = Identity(sub=None, org_id="org-456", azp="my-client")

    key = _build_rate_limit_key(request, identity)
    assert key == "org:org-456:azp:my-client:10.0.0.1"


def test_build_rate_limit_key_user_only():
    """Rate limit key: real user without org."""
    request = _make_request_with_ip("10.0.0.1")
    identity = Identity(sub="user-123")

    key = _build_rate_limit_key(request, identity)
    assert key == "sub:user-123:10.0.0.1"


def test_build_rate_limit_key_anonymous_only():
    """Rate limit key: anonymous without org."""
    request = _make_request_with_ip("10.0.0.1")
    identity = Identity(sub=None, azp="my-client")

    key = _build_rate_limit_key(request, identity)
    assert key == "azp:my-client:10.0.0.1"


def test_auth_settings_defaults():
    """Auth settings have sensible defaults."""
    settings = AuthSettings()

    assert settings.enabled is False
    assert settings.mode == AuthMode.STRICT
    assert settings.provider_type is None
    assert settings.provider_url is None
    assert settings.oidc_issuer_url is None  # No default - must be set when enabled
    assert settings.verify_signature is True
    assert settings.verify_expiration is True
    assert "RS256" in settings.allowed_algorithms


def test_auth_settings_normalizes_issuer_url():
    """Issuer URL strips .well-known suffix."""
    with pytest.warns(DeprecationWarning, match="oidc_issuer_url"):
        settings = AuthSettings(
            token_origin="sso",
            oidc_issuer_url="https://id.example.com/realms/test/.well-known/openid-configuration"
        )
    assert settings.oidc_issuer_url == "https://id.example.com/realms/test"
    assert settings.provider_type == AuthProviderType.OIDC
    assert settings.provider_url == "https://id.example.com/realms/test"


def test_set_and_get_auth_settings():
    """Programmatic auth settings work."""
    reset_auth_settings()
    custom = AuthSettings(
        enabled=True,
        token_origin="sso",
        mode=AuthMode.WARN,
        oidc_issuer_url="https://test.example.com/realms/test",
    )
    set_auth_settings(custom)

    retrieved = get_auth_settings()
    assert retrieved.enabled is True
    assert retrieved.mode == AuthMode.WARN

    reset_auth_settings()


def test_auth_settings_requires_token_origin_when_enabled():
    """Auth enabled requires token origin unless a custom validator is configured."""
    with pytest.raises(ValueError, match="token_origin is required when auth is enabled"):
        AuthSettings(enabled=True, provider_type="oidc", provider_url="https://test.example.com/realms/test")


@pytest.mark.asyncio
async def test_validator_no_token():
    """Validator returns NO_TOKEN error for empty token."""
    settings = AuthSettings(enabled=True, token_origin="sso", oidc_issuer_url="https://test.example.com/realms/test")
    validator = OIDCTokenValidator(settings)

    error_kind, _, claims = await validator.validate_token("")

    assert error_kind == ValidationErrorKind.NO_TOKEN
    assert claims is None
    await validator.close()


@pytest.mark.asyncio
async def test_validator_jwks_unavailable():
    """Validator returns JWKS_UNAVAILABLE when OIDC discovery fails."""
    settings = AuthSettings(enabled=True, token_origin="sso", oidc_issuer_url="https://invalid.example.com")
    validator = OIDCTokenValidator(settings)

    # Mock HTTP client to fail
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("Network error"))
    validator._http_client = mock_client

    error_kind, _, claims = await validator.validate_token("some.jwt.token")

    assert error_kind == ValidationErrorKind.JWKS_UNAVAILABLE
    assert claims is None
    await validator.close()


@pytest.fixture
def mock_request():
    """Create mock FastAPI request."""
    scope = {"type": "http", "headers": [(b"user-agent", b"test")]}
    request = Request(scope)
    request.state.bearer_token = None
    request.state.identity = None
    request.state.rate_limit_key = None
    return request


@pytest_asyncio.fixture
async def auth_cleanup():
    """Fixture that resets auth state and mocks validator (no network calls)."""
    reset_auth_settings()
    mock_validator = _make_mock_validator()
    with patch("maltego.auth.dependency._get_validator", return_value=mock_validator):
        yield mock_validator
    await close_validator()
    reset_auth_settings()


@pytest.mark.asyncio
async def test_optional_auth_disabled(mock_request, auth_cleanup):
    """When auth disabled, token stored but not validated."""
    set_auth_settings(AuthSettings(enabled=False))

    creds = MagicMock()
    creds.credentials = "some-token"

    await optional_auth(mock_request, creds)

    assert mock_request.state.bearer_token == "some-token"
    assert (
        not hasattr(mock_request.state, "identity")
        or mock_request.state.identity is None
    )
    # Validator should not be called when auth is disabled
    auth_cleanup.validate_token.assert_not_called()


@pytest.mark.asyncio
async def test_optional_auth_warn_invalid_token(mock_request, auth_cleanup):
    """WARN mode logs but doesn't reject invalid tokens."""
    set_auth_settings(AuthSettings(
        enabled=True,
        mode=AuthMode.WARN,
        token_origin="sso",
        oidc_issuer_url="https://test.example.com/realms/test",
    ))

    creds = MagicMock()
    creds.credentials = "invalid-token"
    mock_request.headers._list.append((b"maltego-upstream-identity-method", b"OIDC"))

    # Should not raise, just log
    await optional_auth(mock_request, creds)

    assert mock_request.state.bearer_token == "invalid-token"
    # Validator was called with the token
    auth_cleanup.validate_token.assert_called_once_with("invalid-token")


@pytest.mark.asyncio
async def test_optional_auth_strict_no_token(mock_request, auth_cleanup):
    """STRICT mode rejects missing token with 401."""
    from maltego.auth.problem import AuthProblemException

    set_auth_settings(AuthSettings(
        enabled=True,
        mode=AuthMode.STRICT,
        token_origin="sso",
        oidc_issuer_url="https://test.example.com/realms/test",
    ))

    with pytest.raises(AuthProblemException) as exc_info:
        await optional_auth(mock_request, None)

    assert exc_info.value.status_code == 401
    assert exc_info.value.problem.error_code.value == "auth.credentials_missing"
    # Validator not called - rejected before validation
    auth_cleanup.validate_token.assert_not_called()


@pytest.mark.asyncio
async def test_optional_auth_strict_validator_exception_maps_to_internal_problem(mock_request):
    """Unexpected validator exceptions return auth Problem Details in strict mode."""
    from maltego.auth.problem import AuthProblemException

    reset_auth_settings()
    mock_validator = _make_mock_validator()
    mock_validator.validate_token.side_effect = RuntimeError("custom validator failed")
    set_auth_settings(
        AuthSettings(
            enabled=True,
            mode=AuthMode.STRICT,
            token_origin="sso",
            provider_type="jwt",
            provider_url="https://test.example.com/jwks",
        )
    )

    creds = MagicMock()
    creds.credentials = "some-token"
    mock_request.headers._list.append((b"maltego-upstream-identity-method", b"OIDC"))

    with patch("maltego.auth.dependency._get_validator", return_value=mock_validator):
        with pytest.raises(AuthProblemException) as exc_info:
            await optional_auth(mock_request, creds)

    assert exc_info.value.status_code == 500
    assert exc_info.value.problem.type == "urn:maltego-transforms:problem:auth:internal-error"
    assert exc_info.value.problem.error_code.value == "auth.internal_error"
    assert "custom validator failed" not in exc_info.value.problem.detail
    reset_auth_settings()


@pytest.mark.asyncio
async def test_optional_auth_strict_validator_factory_exception_maps_to_internal_problem(mock_request):
    """Unexpected validator factory exceptions return auth Problem Details in strict mode."""
    from maltego.auth.problem import AuthProblemException

    reset_auth_settings()

    def broken_validator_factory(settings):
        raise RuntimeError("validator factory failed")

    set_auth_settings(
        AuthSettings(
            enabled=True,
            mode=AuthMode.STRICT,
            token_origin="sso",
            validator_factory=broken_validator_factory,
        )
    )

    creds = MagicMock()
    creds.credentials = "some-token"
    mock_request.headers._list.append((b"maltego-upstream-identity-method", b"OIDC"))

    with pytest.raises(AuthProblemException) as exc_info:
        await optional_auth(mock_request, creds)

    assert exc_info.value.status_code == 500
    assert exc_info.value.problem.type == "urn:maltego-transforms:problem:auth:internal-error"
    assert exc_info.value.problem.error_code.value == "auth.internal_error"
    assert "validator factory failed" not in exc_info.value.problem.detail
    await close_validator()
    reset_auth_settings()


@pytest.mark.asyncio
async def test_optional_auth_rejects_api_key_only(mock_request, auth_cleanup):
    """API-key-only request must be REJECTED under STRICT (auth bypass removed)."""
    from maltego.auth.problem import AuthProblemException

    set_auth_settings(AuthSettings(
        enabled=True,
        mode=AuthMode.STRICT,
        token_origin="sso",
        oidc_issuer_url="https://test.example.com/realms/test",
    ))

    # Add API key header but no Bearer token
    mock_request.headers._list.append((b"maltego-api-key", b"some-key"))

    # Must raise — API key no longer bypasses auth
    with pytest.raises(AuthProblemException) as exc_info:
        await optional_auth(mock_request, None)

    assert exc_info.value.status_code == 401
    assert exc_info.value.problem.error_code.value == "auth.credentials_missing"
    # Validator not called — rejected before validation (no bearer token present)
    auth_cleanup.validate_token.assert_not_called()


@pytest.mark.asyncio
async def test_optional_auth_warns_api_key_only_in_warn_mode(mock_request, auth_cleanup):
    """API-key-only request is WARNED (not rejected) under WARN mode."""
    set_auth_settings(AuthSettings(
        enabled=True,
        mode=AuthMode.WARN,
        token_origin="sso",
        oidc_issuer_url="https://test.example.com/realms/test",
    ))

    # Add API key header but no Bearer token
    mock_request.headers._list.append((b"maltego-api-key", b"some-key"))

    # Must not raise — WARN mode lets the request through
    await optional_auth(mock_request, None)
    # Validator not called — no bearer token to validate
    auth_cleanup.validate_token.assert_not_called()


@pytest.mark.asyncio
async def test_valid_jwt_passes_with_api_key_header_present(mock_request, auth_cleanup):
    """Valid JWT is still accepted in STRICT mode when Maltego-API-Key header is also present."""
    from maltego.auth.validator import AuthValidationSuccess

    set_auth_settings(AuthSettings(
        enabled=True,
        mode=AuthMode.STRICT,
        token_origin="sso",
        oidc_issuer_url="https://test.example.com/realms/test",
    ))

    # Simulate a valid JWT validation result
    auth_cleanup.validate_token.return_value = AuthValidationSuccess(
        identity_claims={"sub": "user-123", "iss": "https://id.maltego.com/realms/maltego"},
        auth_claims={"sub": "user-123"},
        raw_payload=None,
        protocol="oidc",
    )

    creds = MagicMock()
    creds.credentials = "valid-jwt-token"
    mock_request.headers._list.append((b"maltego-upstream-identity-method", b"OIDC"))
    # Also add legacy API key header — must be ignored
    mock_request.headers._list.append((b"maltego-api-key", b"some-legacy-key"))

    # Must not raise — JWT is valid
    await optional_auth(mock_request, creds)
    auth_cleanup.validate_token.assert_called_once_with("valid-jwt-token")


@pytest.mark.asyncio
async def test_valid_jwt_passes_without_api_key_header(mock_request, auth_cleanup):
    """Valid JWT is accepted in STRICT mode with no Maltego-API-Key header."""
    from maltego.auth.validator import AuthValidationSuccess

    set_auth_settings(AuthSettings(
        enabled=True,
        mode=AuthMode.STRICT,
        token_origin="sso",
        oidc_issuer_url="https://test.example.com/realms/test",
    ))

    auth_cleanup.validate_token.return_value = AuthValidationSuccess(
        identity_claims={"sub": "user-456", "iss": "https://id.maltego.com/realms/maltego"},
        auth_claims={"sub": "user-456"},
        raw_payload=None,
        protocol="oidc",
    )

    creds = MagicMock()
    creds.credentials = "valid-jwt-token"
    mock_request.headers._list.append((b"maltego-upstream-identity-method", b"OIDC"))

    # Must not raise — JWT is valid even without the legacy header
    await optional_auth(mock_request, creds)
    auth_cleanup.validate_token.assert_called_once_with("valid-jwt-token")
