# Copyright (c) Maltego Technologies GmbH.

import time

import httpx
import pytest
from joserfc import jwk, jwt

from maltego.auth import AuthSettings
from maltego.auth.oidc_validator import OIDCTokenValidator
from maltego.auth.validator import ValidationErrorKind

pytestmark = pytest.mark.security


def _rsa_key():
    return jwk.generate_key("RSA", 2048, {"kid": "oidc-key", "alg": "RS256", "use": "sig"})


def _token(key, claims):
    payload = {
        "sub": "user-123",
        "aud": "transform-server",
        "exp": int(time.time()) + 300,
        **claims,
    }
    return jwt.encode({"alg": "RS256", "kid": "oidc-key"}, payload, key)


def _validator(settings, key, metadata):
    validator = OIDCTokenValidator(settings)
    validator._metadata = metadata
    validator._jwks = {"keys": [key.as_dict(private=False)]}
    validator._jwks_fetched_at = time.time()
    return validator


@pytest.mark.asyncio
async def test_oidc_validator_uses_discovery_issuer_by_default():
    key = _rsa_key()
    settings = AuthSettings(
        enabled=True,
        token_origin="sso",
        provider_type="oidc",
        provider_url="https://id.example/realms/test",
        audience="transform-server",
    )
    validator = _validator(
        settings,
        key,
        {
            "issuer": "https://id.example/realms/test",
            "jwks_uri": "https://id.example/realms/test/jwks",
        },
    )

    error_kind, _, claims = await validator.validate_token(
        _token(key, {"iss": "https://id.example/realms/test"})
    )

    assert error_kind is None
    assert claims["iss"] == "https://id.example/realms/test"


@pytest.mark.asyncio
async def test_oidc_validator_explicit_issuer_overrides_discovery_issuer():
    key = _rsa_key()
    settings = AuthSettings(
        enabled=True,
        token_origin="sso",
        provider_type="oidc",
        provider_url="https://id.example/realms/test",
        issuer="https://explicit.example",
        audience="transform-server",
    )
    validator = _validator(
        settings,
        key,
        {
            "issuer": "https://id.example/realms/test",
            "jwks_uri": "https://id.example/realms/test/jwks",
        },
    )

    error_kind, error_msg, claims = await validator.validate_token(
        _token(key, {"iss": "https://id.example/realms/test"})
    )

    assert error_kind == ValidationErrorKind.INVALID_TOKEN
    assert "iss" in error_msg
    assert claims is None


@pytest.mark.asyncio
async def test_oidc_validator_does_not_infer_issuer_from_provider_url():
    key = _rsa_key()
    settings = AuthSettings(
        enabled=True,
        token_origin="sso",
        provider_type="oidc",
        provider_url="https://id.example/realms/test",
        audience="transform-server",
    )
    validator = _validator(
        settings,
        key,
        {
            "jwks_uri": "https://id.example/realms/test/jwks",
        },
    )

    error_kind, error_msg, claims = await validator.validate_token(
        _token(key, {"iss": "https://id.example/realms/test"})
    )

    assert error_kind == ValidationErrorKind.INVALID_TOKEN
    assert "issuer" in error_msg.lower()
    assert claims is None


def _mock_transport(discovery_response):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json=discovery_response)
        raise AssertionError(f"Unexpected request to {request.url}")

    return httpx.MockTransport(handler)


def _validator_with_transport(settings, transport):
    validator = OIDCTokenValidator(settings)
    validator._http_client = httpx.AsyncClient(transport=transport, timeout=10.0)
    return validator


@pytest.mark.asyncio
async def test_fetch_oidc_metadata_accepts_matching_discovered_issuer():
    """Discovered issuer equal to the configured provider URL is accepted (MF2)."""
    settings = AuthSettings(
        enabled=True,
        token_origin="sso",
        provider_type="oidc",
        provider_url="https://id.example/realms/test",
        audience="transform-server",
    )
    transport = _mock_transport(
        {
            "issuer": "https://id.example/realms/test",
            "jwks_uri": "https://id.example/realms/test/jwks",
        }
    )
    validator = _validator_with_transport(settings, transport)

    metadata = await validator._fetch_oidc_metadata()

    assert metadata is not None
    assert metadata["issuer"] == "https://id.example/realms/test"


@pytest.mark.asyncio
async def test_fetch_oidc_metadata_rejects_mismatched_discovered_issuer(caplog):
    """A discovery doc declaring a different issuer than configured must fail closed (MF2)."""
    settings = AuthSettings(
        enabled=True,
        token_origin="sso",
        provider_type="oidc",
        provider_url="https://id.example/realms/test",
        audience="transform-server",
    )
    transport = _mock_transport(
        {
            "issuer": "https://attacker.example/evil",
            "jwks_uri": "https://attacker.example/evil/jwks",
        }
    )
    validator = _validator_with_transport(settings, transport)

    with caplog.at_level("ERROR"):
        metadata = await validator._fetch_oidc_metadata()

    assert metadata is None
    assert any(
        "https://id.example/realms/test" in record.getMessage()
        and "https://attacker.example/evil" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_fetch_oidc_metadata_explicit_issuer_override_skips_mismatch_check():
    """When settings.issuer is explicitly set, discovery issuer need not match provider_url (MF2)."""
    settings = AuthSettings(
        enabled=True,
        token_origin="sso",
        provider_type="oidc",
        provider_url="https://id.example/realms/test",
        issuer="https://explicit.example",
        audience="transform-server",
    )
    transport = _mock_transport(
        {
            "issuer": "https://id.example/realms/test",
            "jwks_uri": "https://id.example/realms/test/jwks",
        }
    )
    validator = _validator_with_transport(settings, transport)

    metadata = await validator._fetch_oidc_metadata()

    assert metadata is not None
    assert metadata["issuer"] == "https://id.example/realms/test"
    assert validator._expected_issuer() == "https://explicit.example"


@pytest.mark.asyncio
async def test_fetch_oidc_metadata_missing_issuer_returns_none():
    """Discovery metadata without an issuer is still rejected (unchanged behavior)."""
    settings = AuthSettings(
        enabled=True,
        token_origin="sso",
        provider_type="oidc",
        provider_url="https://id.example/realms/test",
        audience="transform-server",
    )
    transport = _mock_transport({"jwks_uri": "https://id.example/realms/test/jwks"})
    validator = _validator_with_transport(settings, transport)

    metadata = await validator._fetch_oidc_metadata()

    assert metadata is None
