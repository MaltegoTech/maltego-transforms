# Copyright (c) Maltego Technologies GmbH.

import pytest
import sys

from maltego.auth import AuthMode, AuthProviderType, AuthSettings, AuthTokenOrigin

pytestmark = pytest.mark.security


def test_auth_settings_accepts_jwt_provider_model():
    settings = AuthSettings(
        enabled=True,
        token_origin="sso",
        provider_type="jwt",
        provider_url="https://id.example/jwks",
    )

    assert settings.token_origin == AuthTokenOrigin.SSO
    assert settings.provider_type == AuthProviderType.JWT
    assert settings.provider_url == "https://id.example/jwks"


def test_auth_settings_accepts_maltego_id_origin_with_oidc_provider_model():
    settings = AuthSettings(
        enabled=True,
        token_origin="maltego_id",
        provider_type="oidc",
        provider_url="https://auth.maltego.example/realms/maltego",
    )

    assert settings.token_origin == AuthTokenOrigin.MALTEGO_ID
    assert settings.provider_type == AuthProviderType.OIDC


def test_auth_settings_reads_token_origin_from_cli(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["maltego", "--auth-token-origin", "sso"])

    assert AuthSettings().token_origin == AuthTokenOrigin.SSO


def test_auth_settings_accepts_warn_mode():
    settings = AuthSettings(mode="warn")

    assert settings.mode == AuthMode.WARN
    assert settings.mode.value == "warn"


def test_auth_settings_maps_deprecated_log_only_mode():
    with pytest.warns(DeprecationWarning, match="log_only"):
        settings = AuthSettings(mode="log_only")

    assert settings.mode == AuthMode.WARN


def test_auth_mode_maps_deprecated_log_only_value():
    with pytest.warns(DeprecationWarning, match="log_only"):
        mode = AuthMode("log_only")

    assert mode == AuthMode.WARN


def test_auth_settings_reads_warn_mode_from_cli(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["maltego", "--auth-mode", "warn"])

    assert AuthSettings().mode == AuthMode.WARN


def test_auth_settings_preserves_jwt_provider_url_trailing_slash():
    settings = AuthSettings(
        enabled=True,
        token_origin="sso",
        provider_type="jwt",
        provider_url="https://id.example/jwks/",
    )

    assert settings.provider_url == "https://id.example/jwks/"


def test_auth_settings_accepts_saml_provider_model():
    settings = AuthSettings(
        enabled=True,
        token_origin="sso",
        provider_type="saml",
        provider_url="https://id.example/metadata",
    )

    assert settings.provider_type == AuthProviderType.SAML
    assert settings.provider_url == "https://id.example/metadata"


def test_auth_settings_accepts_saml_without_signing_material():
    # SAML requires an anchored issuer (R2-2), but does NOT require a signing
    # cert or provider_url — those are optional (signing cert can come from
    # metadata, or verify_signature=False may be used for testing).
    settings = AuthSettings(
        enabled=True,
        token_origin="sso",
        provider_type="saml",
        issuer="https://idp.example/metadata",
    )

    assert settings.provider_type == AuthProviderType.SAML
    assert settings.verify_signature is True
    assert settings.provider_url is None
    assert settings.saml_idp_cert is None
    assert settings.issuer == "https://idp.example/metadata"


def test_auth_settings_preserves_saml_provider_url_trailing_slash():
    settings = AuthSettings(
        enabled=True,
        token_origin="sso",
        provider_type="saml",
        provider_url="https://id.example/metadata/",
    )

    assert settings.provider_url == "https://id.example/metadata/"


def test_auth_settings_requires_token_origin_when_enabled_without_custom_validator():
    with pytest.raises(ValueError, match="token_origin"):
        AuthSettings(enabled=True, provider_type="oidc", provider_url="https://id.example")


def test_auth_settings_rejects_maltego_id_saml_combination():
    with pytest.raises(ValueError, match="maltego_id.*saml"):
        AuthSettings(
            enabled=True,
            token_origin="maltego_id",
            provider_type="saml",
            provider_url="https://id.example/metadata",
        )


def test_auth_settings_maps_deprecated_oidc_issuer_url():
    with pytest.warns(DeprecationWarning, match="oidc_issuer_url"):
        settings = AuthSettings(
            enabled=True,
            token_origin="sso",
            oidc_issuer_url="https://id.example/realms/test",
        )

    assert settings.provider_type == AuthProviderType.OIDC
    assert settings.provider_url == "https://id.example/realms/test"


def test_auth_settings_rejects_conflicting_deprecated_audience():
    with pytest.raises(ValueError, match="oidc_audience"):
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="oidc",
            provider_url="https://id.example/realms/test",
            oidc_audience="old",
            audience="new",
        )


def test_auth_settings_warns_clearly_for_deprecated_jwks_alias_with_oidc_provider():
    with pytest.warns(DeprecationWarning, match="provider_type=oidc and provider_url"):
        settings = AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="oidc",
            provider_url="https://id.example/realms/test",
            oidc_jwks_uri="https://id.example/realms/test/protocol/openid-connect/certs",
        )

    assert settings.provider_type == AuthProviderType.OIDC
    assert settings.provider_url == "https://id.example/realms/test"


def test_auth_settings_normalizes_oidc_provider_url():
    settings = AuthSettings(
        enabled=True,
        token_origin="sso",
        provider_type="oidc",
        provider_url="https://id.example/realms/test/.well-known/openid-configuration",
    )

    assert settings.provider_url == "https://id.example/realms/test"


def test_auth_settings_custom_validator_does_not_require_provider_type():
    settings = AuthSettings(
        enabled=True,
        validator_factory=lambda auth_settings: object(),
    )

    assert settings.provider_type is None
    assert settings.provider_url is None
