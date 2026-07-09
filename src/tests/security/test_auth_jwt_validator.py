# Copyright (c) Maltego Technologies GmbH.

import time

import pytest
from joserfc import jwk, jwt

from maltego.auth import AuthSettings
from maltego.auth.jwt_validator import JWTTokenValidator
from maltego.auth.validator import AuthValidationFailure, AuthValidationSuccess, ValidationErrorKind

pytestmark = pytest.mark.security


def _rsa_key():
    return jwk.generate_key("RSA", 2048, {"kid": "test-key", "alg": "RS256", "use": "sig"})


def _rsa_public_key(**overrides):
    key = jwk.generate_key("RSA", 2048, {"kid": "test-key"})
    public_key = key.as_dict(private=False)
    public_key.update(overrides)
    return public_key


def _token(key, claims):
    payload = {
        "sub": "user-123",
        "exp": int(time.time()) + 300,
        **claims,
    }
    return jwt.encode({"alg": "RS256", "kid": "test-key"}, payload, key)


def _validator(settings, jwks):
    validator = JWTTokenValidator(settings)
    validator._jwks = jwks
    validator._jwks_fetched_at = time.time()
    return validator


@pytest.mark.asyncio
async def test_jwt_validator_validates_signed_token_with_configured_jwks():
    key = _rsa_key()
    settings = AuthSettings(
        enabled=True,
        token_origin="sso",
        provider_type="jwt",
        provider_url="https://id.example/jwks",
        issuer="https://issuer.example",
        audience="transform-server",
    )
    validator = _validator(settings, {"keys": [key.as_dict(private=False)]})

    result = await validator.validate_token(
        _token(key, {"iss": "https://issuer.example", "aud": "transform-server"})
    )
    error_kind, error_msg, claims = result

    assert isinstance(result, AuthValidationSuccess)
    assert result.protocol == "jwt"
    assert result.identity_claims == result.auth_claims
    assert result.raw_payload == result.auth_claims
    assert error_kind is None
    assert error_msg is None
    assert claims["sub"] == "user-123"
    assert claims["iss"] == "https://issuer.example"


@pytest.mark.parametrize(
    "key_params",
    [
        {"use": "enc", "alg": "RS256"},
        {"use": "enc"},
    ],
)
def test_jwt_validator_filters_out_encryption_keys(key_params):
    validator = JWTTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="jwt",
            provider_url="https://id.example/jwks",
        )
    )

    assert validator._filter_signing_keys({"keys": [_rsa_public_key(**key_params)]}, "test") is None


@pytest.mark.parametrize(
    "key_params",
    [
        {"use": "sig", "alg": "RS256"},
        {"use": "sig"},
        {"alg": "RS256"},
        {},
    ],
)
def test_jwt_validator_keeps_keys_that_can_be_used_for_signatures(key_params):
    key = _rsa_public_key(**key_params)
    validator = JWTTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="jwt",
            provider_url="https://id.example/jwks",
        )
    )

    assert validator._filter_signing_keys({"keys": [key]}, "test") == {"keys": [key]}


@pytest.mark.asyncio
async def test_jwt_issuer_is_validated_only_when_configured():
    key = _rsa_key()
    token = _token(key, {"iss": "https://actual.example"})

    no_issuer_validator = _validator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="jwt",
            provider_url="https://id.example/jwks",
        ),
        {"keys": [key.as_dict(private=False)]},
    )
    error_kind, _, claims = await no_issuer_validator.validate_token(token)
    assert error_kind is None
    assert claims["iss"] == "https://actual.example"

    issuer_validator = _validator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="jwt",
            provider_url="https://id.example/jwks",
            issuer="https://expected.example",
        ),
        {"keys": [key.as_dict(private=False)]},
    )
    result = await issuer_validator.validate_token(token)
    error_kind, error_msg, claims = result
    assert isinstance(result, AuthValidationFailure)
    assert error_kind == ValidationErrorKind.INVALID_TOKEN
    assert "iss" in error_msg
    assert claims is None


@pytest.mark.asyncio
async def test_jwt_audience_is_validated_only_when_configured():
    key = _rsa_key()
    token = _token(key, {"aud": "actual-audience"})

    no_audience_validator = _validator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="jwt",
            provider_url="https://id.example/jwks",
        ),
        {"keys": [key.as_dict(private=False)]},
    )
    error_kind, _, claims = await no_audience_validator.validate_token(token)
    assert error_kind is None
    assert claims["aud"] == "actual-audience"

    audience_validator = _validator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="jwt",
            provider_url="https://id.example/jwks",
            audience="expected-audience",
        ),
        {"keys": [key.as_dict(private=False)]},
    )
    error_kind, error_msg, claims = await audience_validator.validate_token(token)
    assert error_kind == ValidationErrorKind.INVALID_TOKEN
    assert "aud" in error_msg
    assert claims is None


@pytest.mark.asyncio
async def test_jwt_validator_skips_jwks_when_signature_verification_disabled():
    key = _rsa_key()
    # verify_signature=False is a first-class capability choice, permitted in
    # any mode with no opt-in flag required (two-axis model).
    settings = AuthSettings(
        enabled=True,
        mode="warn",
        token_origin="sso",
        provider_type="jwt",
        verify_signature=False,
        issuer="https://issuer.example",
        audience="transform-server",
    )
    validator = JWTTokenValidator(settings)

    error_kind, error_msg, claims = await validator.validate_token(
        _token(key, {"iss": "https://issuer.example", "aud": "transform-server"})
    )

    assert error_kind is None
    assert error_msg is None
    assert claims["sub"] == "user-123"


@pytest.mark.asyncio
async def test_jwt_validator_skips_jwks_when_signature_verification_disabled_in_strict_mode():
    """verify_signature is a capability axis independent of mode: STRICT + verify_signature=False
    decodes-without-verify directly, with no ValueError at settings construction and no gate
    in the validator (two-axis model)."""
    key = _rsa_key()
    settings = AuthSettings(
        enabled=True,
        mode="strict",
        token_origin="sso",
        provider_type="jwt",
        verify_signature=False,
        issuer="https://issuer.example",
        audience="transform-server",
    )
    validator = JWTTokenValidator(settings)

    error_kind, error_msg, claims = await validator.validate_token(
        _token(key, {"iss": "https://issuer.example", "aud": "transform-server"})
    )

    assert error_kind is None
    assert error_msg is None
    assert claims["sub"] == "user-123"


@pytest.mark.asyncio
async def test_jwt_validator_returns_invalid_token_for_unreadable_unsigned_payload():
    # verify_signature=False is permitted with no opt-in flag required (two-axis model).
    validator = JWTTokenValidator(
        AuthSettings(
            enabled=True,
            mode="warn",
            token_origin="sso",
            provider_type="jwt",
            verify_signature=False,
        )
    )

    error_kind, error_msg, claims = await validator.validate_token("header.not-json.signature")

    assert error_kind == ValidationErrorKind.INVALID_TOKEN
    assert "JWT validation failed" in error_msg
    assert claims is None


@pytest.mark.asyncio
async def test_jwt_expired_exp_passes_when_expiration_verification_disabled():
    key = _rsa_key()
    settings = AuthSettings(
        enabled=True,
        token_origin="sso",
        provider_type="jwt",
        provider_url="https://id.example/jwks",
        issuer="https://issuer.example",
        audience="transform-server",
        verify_expiration=False,
    )
    validator = _validator(settings, {"keys": [key.as_dict(private=False)]})

    error_kind, error_msg, claims = await validator.validate_token(
        _token(
            key,
            {
                "iss": "https://issuer.example",
                "aud": "transform-server",
                "exp": int(time.time()) - 300,
            },
        )
    )

    assert error_kind is None
    assert error_msg is None
    assert claims["sub"] == "user-123"


@pytest.mark.asyncio
async def test_jwt_expired_exp_returns_expired_token_when_time_validation_enabled():
    key = _rsa_key()
    settings = AuthSettings(
        enabled=True,
        token_origin="sso",
        provider_type="jwt",
        provider_url="https://id.example/jwks",
        issuer="https://issuer.example",
        audience="transform-server",
    )
    validator = _validator(settings, {"keys": [key.as_dict(private=False)]})

    error_kind, error_msg, claims = await validator.validate_token(
        _token(
            key,
            {
                "iss": "https://issuer.example",
                "aud": "transform-server",
                "exp": int(time.time()) - 300,
            },
        )
    )

    assert error_kind == ValidationErrorKind.EXPIRED_TOKEN
    assert "expired" in error_msg.lower()
    assert claims is None


@pytest.mark.asyncio
async def test_jwt_future_nbf_passes_when_expiration_verification_disabled():
    key = _rsa_key()
    settings = AuthSettings(
        enabled=True,
        token_origin="sso",
        provider_type="jwt",
        provider_url="https://id.example/jwks",
        issuer="https://issuer.example",
        audience="transform-server",
        verify_expiration=False,
    )
    validator = _validator(settings, {"keys": [key.as_dict(private=False)]})

    error_kind, error_msg, claims = await validator.validate_token(
        _token(
            key,
            {
                "iss": "https://issuer.example",
                "aud": "transform-server",
                "nbf": int(time.time()) + 300,
            },
        )
    )

    assert error_kind is None
    assert error_msg is None
    assert claims["sub"] == "user-123"
