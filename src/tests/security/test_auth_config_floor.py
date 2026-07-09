# Copyright (c) Maltego Technologies GmbH.
"""
PRP 3 — Auth config floor tests (F16, F5, F15, F6, F8).

Covers each security invariant introduced by the auth-config-floor hardening:

  F16  minimum-security floor in settings
  F5   verify_signature=False is a first-class capability choice (two-axis
       model: verify_signature=capability, mode=failure-handling), permitted
       in any mode with no startup reject; a startup WARNING is still emitted.
  F15  env cannot silently downgrade a programmatically-set security setting
  F6   missing aud/iss warns loudly at startup for JWT/OIDC
  F8   WARN mode is documented/gated; startup warning is emitted
"""

import os
import logging

import pytest

from maltego.auth.settings import (
    AuthMode,
    AuthProviderType,
    AuthSettings,
    AuthTokenOrigin,
    get_auth_settings,
    reset_auth_settings,
    set_auth_settings,
)

pytestmark = pytest.mark.security


# ── Helpers ──────────────────────────────────────────────────────────────────


def _jwt_settings(**kwargs) -> AuthSettings:
    """Minimal valid JWT settings with sensible defaults."""
    defaults = dict(
        enabled=True,
        token_origin="sso",
        provider_type="jwt",
        provider_url="https://id.example/jwks",
        issuer="https://issuer.example",
        audience="my-service",
    )
    defaults.update(kwargs)
    return AuthSettings(**defaults)


def _oidc_settings(**kwargs) -> AuthSettings:
    """Minimal valid OIDC settings."""
    defaults = dict(
        enabled=True,
        token_origin="sso",
        provider_type="oidc",
        provider_url="https://id.example/realms/test",
        audience="my-service",
    )
    defaults.update(kwargs)
    return AuthSettings(**defaults)


# ── F16: minimum-security floor ───────────────────────────────────────────────


class TestF16MinimumSecurityFloor:
    def test_strict_allows_verify_signature_false_for_jwt(self):
        """
        verify_signature is a capability axis independent of mode: STRICT no
        longer rejects verify_signature=False for JWT (two-axis model).
        """
        s = AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="jwt",
            provider_url="https://id.example/jwks",
            mode="strict",
            verify_signature=False,
        )
        assert s.verify_signature is False
        assert s.mode == AuthMode.STRICT

    def test_strict_allows_verify_signature_false_for_oidc(self):
        """STRICT mode permits OIDC decode-without-verify (capability vs failure-handling)."""
        s = AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="oidc",
            provider_url="https://id.example/realms/test",
            mode="strict",
            verify_signature=False,
        )
        assert s.verify_signature is False
        assert s.mode == AuthMode.STRICT

    def test_none_algorithm_rejected_for_jwt(self):
        """'none' algorithm must be rejected for JWT."""
        with pytest.raises(ValueError, match="insecure algorithm"):
            AuthSettings(
                enabled=True,
                token_origin="sso",
                provider_type="jwt",
                provider_url="https://id.example/jwks",
                allowed_algorithms={"none"},
            )

    def test_hs256_rejected_for_jwt(self):
        """HS256 (symmetric) must be rejected for JWT asymmetric provider."""
        with pytest.raises(ValueError, match="insecure algorithm"):
            AuthSettings(
                enabled=True,
                token_origin="sso",
                provider_type="jwt",
                provider_url="https://id.example/jwks",
                allowed_algorithms={"HS256"},
            )

    def test_hs384_rejected_for_jwt(self):
        """HS384 (symmetric) must be rejected for JWT asymmetric provider."""
        with pytest.raises(ValueError, match="insecure algorithm"):
            AuthSettings(
                enabled=True,
                token_origin="sso",
                provider_type="jwt",
                provider_url="https://id.example/jwks",
                allowed_algorithms={"HS384"},
            )

    def test_hs512_rejected_for_jwt(self):
        """HS512 (symmetric) must be rejected for JWT asymmetric provider."""
        with pytest.raises(ValueError, match="insecure algorithm"):
            AuthSettings(
                enabled=True,
                token_origin="sso",
                provider_type="jwt",
                provider_url="https://id.example/jwks",
                allowed_algorithms={"HS512"},
            )

    def test_none_algorithm_rejected_for_oidc(self):
        """'none' algorithm must be rejected for OIDC."""
        with pytest.raises(ValueError, match="insecure algorithm"):
            AuthSettings(
                enabled=True,
                token_origin="sso",
                provider_type="oidc",
                provider_url="https://id.example/realms/test",
                allowed_algorithms={"none"},
            )

    def test_rs256_allowed_for_jwt(self):
        """RS256 (asymmetric) is the standard and must be accepted."""
        s = _jwt_settings(allowed_algorithms={"RS256"})
        assert "RS256" in s.allowed_algorithms

    def test_rs256_and_es256_allowed_for_jwt(self):
        """Multiple asymmetric algorithms are accepted."""
        s = _jwt_settings(allowed_algorithms={"RS256", "ES256"})
        assert s.allowed_algorithms == {"RS256", "ES256"}

    def test_insecure_algos_not_checked_for_disabled_auth(self):
        """Security floor doesn't fire when auth is disabled."""
        s = AuthSettings(
            enabled=False,
            allowed_algorithms={"none"},
        )
        assert "none" in s.allowed_algorithms

    def test_insecure_algos_not_checked_for_saml(self):
        """HS256 algo restriction only applies to JWT/OIDC, not SAML."""
        s = AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            issuer="https://idp.example.com",
            allowed_algorithms={"HS256"},
        )
        assert "HS256" in s.allowed_algorithms

    def test_mixed_algos_with_insecure_rejected(self):
        """Mixed set containing an insecure algo is rejected for JWT."""
        with pytest.raises(ValueError, match="insecure algorithm"):
            AuthSettings(
                enabled=True,
                token_origin="sso",
                provider_type="jwt",
                provider_url="https://id.example/jwks",
                allowed_algorithms={"RS256", "HS256"},
            )


# ── F5/simplification: verify_signature=False is a first-class capability choice ──


class TestF5VerifySignatureCapabilityAxis:
    def test_jwt_verify_signature_false_starts_successfully_in_strict_mode(self):
        """verify_signature=False constructs/starts successfully in STRICT (no ValueError)."""
        s = AuthSettings(
            enabled=True,
            mode="strict",
            token_origin="sso",
            provider_type="jwt",
            provider_url="https://id.example/jwks",
            verify_signature=False,
        )
        assert s.verify_signature is False
        assert s.mode == AuthMode.STRICT

    def test_jwt_verify_signature_false_starts_successfully_in_warn_mode(self):
        """verify_signature=False constructs/starts successfully in WARN (no ValueError)."""
        s = AuthSettings(
            enabled=True,
            mode="warn",
            token_origin="sso",
            provider_type="jwt",
            provider_url="https://id.example/jwks",
            verify_signature=False,
        )
        assert s.verify_signature is False
        assert s.mode == AuthMode.WARN

    def test_oidc_verify_signature_false_starts_successfully_in_strict_mode(self):
        """OIDC verify_signature=False is permitted in STRICT with no opt-in flag needed."""
        s = AuthSettings(
            enabled=True,
            mode="strict",
            token_origin="sso",
            provider_type="oidc",
            provider_url="https://id.example/realms/test",
            verify_signature=False,
        )
        assert s.verify_signature is False

    def test_verify_signature_false_not_checked_for_saml(self):
        """verify_signature=False for SAML starts successfully (PRP 2 scope)."""
        s = AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            issuer="https://idp.example.com",
            verify_signature=False,
        )
        assert s.verify_signature is False

    def test_verify_signature_true_is_the_default(self):
        """Default verify_signature=True path requires no extra flags."""
        s = _jwt_settings(verify_signature=True)
        assert s.verify_signature is True

    def test_verify_signature_false_not_checked_when_auth_disabled(self):
        """When auth is disabled, verify_signature=False is not validated."""
        s = AuthSettings(
            enabled=False,
            provider_type="jwt",
            verify_signature=False,
        )
        assert s.verify_signature is False

    def test_startup_warning_emitted_for_verify_signature_false(self, caplog):
        """A startup WARNING is logged when verify_signature=False, with no opt-in flag needed."""
        with caplog.at_level(logging.WARNING, logger="maltego.auth.settings"):
            AuthSettings(
                enabled=True,
                mode="warn",
                token_origin="sso",
                provider_type="jwt",
                provider_url="https://id.example/jwks",
                verify_signature=False,
            )
        assert any(
            "verify_signature=False" in r.message and "SECURITY WARNING" in r.message
            for r in caplog.records
        )

    def test_startup_warning_emitted_for_verify_signature_false_in_strict_mode(self, caplog):
        """The WARNING fires regardless of mode -- it's independent of failure-handling."""
        with caplog.at_level(logging.WARNING, logger="maltego.auth.settings"):
            AuthSettings(
                enabled=True,
                mode="strict",
                token_origin="sso",
                provider_type="jwt",
                provider_url="https://id.example/jwks",
                verify_signature=False,
            )
        assert any(
            "verify_signature=False" in r.message and "SECURITY WARNING" in r.message
            for r in caplog.records
        )


# ── public_paths + STRICT mode notice ───────────────────────────────────────────


class TestPublicPathsStrictModeWarning:
    def test_warning_emitted_when_public_paths_set_in_strict_mode(self, caplog):
        """A startup WARNING fires when public_paths is non-empty AND mode=strict,
        since those exact paths bypass auth even though STRICT is otherwise enforced."""
        with caplog.at_level(logging.WARNING, logger="maltego.auth.settings"):
            AuthSettings(
                enabled=True,
                mode="strict",
                token_origin="sso",
                provider_type="jwt",
                provider_url="https://id.example/jwks",
                issuer="https://issuer.example",
                audience="my-service",
                public_paths={"/openapi.json", "/swagger"},
            )
        assert any(
            "public_paths" in r.message and "SECURITY WARNING" in r.message
            for r in caplog.records
        )

    def test_no_warning_when_public_paths_empty_in_strict_mode(self, caplog):
        """No public_paths warning when public_paths is empty, even in STRICT mode."""
        with caplog.at_level(logging.WARNING, logger="maltego.auth.settings"):
            AuthSettings(
                enabled=True,
                mode="strict",
                token_origin="sso",
                provider_type="jwt",
                provider_url="https://id.example/jwks",
                issuer="https://issuer.example",
                audience="my-service",
            )
        assert not any(
            "public_paths" in r.message and "SECURITY WARNING" in r.message
            for r in caplog.records
        )

    def test_no_warning_when_public_paths_set_in_warn_mode(self, caplog):
        """No public_paths/STRICT warning fires when mode is not STRICT."""
        with caplog.at_level(logging.WARNING, logger="maltego.auth.settings"):
            AuthSettings(
                enabled=True,
                mode="warn",
                token_origin="sso",
                provider_type="jwt",
                provider_url="https://id.example/jwks",
                issuer="https://issuer.example",
                audience="my-service",
                public_paths={"/openapi.json"},
            )
        assert not any(
            "public_paths" in r.message and "SECURITY WARNING" in r.message
            for r in caplog.records
        )


# ── F15: env cannot silently downgrade programmatic security settings ──────────


class TestF15SecurityFloor:
    def test_env_cannot_downgrade_verify_signature_from_true_to_false(self, monkeypatch):
        """
        If code sets verify_signature=True and env says False, the programmatic
        value (True) must be preserved and an ERROR must be logged.

        Note: for JWT/OIDC in STRICT mode, the model_validator fires first and
        raises a ValidationError — the floor is a secondary guard.  For non-STRICT
        or SAML, the floor itself kicks in.
        """
        monkeypatch.setenv("MALTEGO_SERVER_AUTH_VERIFY_SIGNATURE", "false")
        # Use SAML so the STRICT validator doesn't pre-empt the floor check
        s = AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            issuer="https://idp.example.com",
            verify_signature=True,
        )
        assert s.verify_signature is True

    def test_env_cannot_downgrade_verify_signature_for_saml_logs_error(self, monkeypatch, caplog):
        """An ERROR is logged when env attempts to downgrade verify_signature."""
        monkeypatch.setenv("MALTEGO_SERVER_AUTH_VERIFY_SIGNATURE", "false")
        with caplog.at_level(logging.ERROR, logger="maltego.auth.settings"):
            AuthSettings(
                enabled=True,
                token_origin="sso",
                provider_type="saml",
                issuer="https://idp.example.com",
                verify_signature=True,
            )
        assert any(
            "downgrade" in r.message.lower() and "verify_signature" in r.message
            for r in caplog.records
        )

    def test_env_cannot_downgrade_mode_from_strict_to_warn(self, monkeypatch):
        """If code sets mode=strict and env says warn, STRICT must be preserved."""
        monkeypatch.setenv("MALTEGO_SERVER_AUTH_MODE", "warn")
        s = AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="jwt",
            provider_url="https://id.example/jwks",
            issuer="https://issuer.example",
            audience="my-service",
            mode="strict",
        )
        assert s.mode == AuthMode.STRICT

    def test_env_cannot_downgrade_mode_logs_error(self, monkeypatch, caplog):
        """An ERROR is logged when env attempts to downgrade mode."""
        monkeypatch.setenv("MALTEGO_SERVER_AUTH_MODE", "warn")
        with caplog.at_level(logging.ERROR, logger="maltego.auth.settings"):
            AuthSettings(
                enabled=True,
                token_origin="sso",
                provider_type="jwt",
                provider_url="https://id.example/jwks",
                issuer="https://issuer.example",
                audience="my-service",
                mode="strict",
            )
        assert any(
            "downgrade" in r.message.lower() and "mode" in r.message.lower()
            for r in caplog.records
        )

    def test_env_setting_security_from_scratch_is_allowed(self, monkeypatch):
        """
        When no programmatic value was provided, env/dotenv settings are fine —
        the floor only protects explicitly-set programmatic values.
        """
        monkeypatch.setenv("MALTEGO_SERVER_AUTH_MODE", "warn")
        s = AuthSettings()  # no mode kwarg
        assert s.mode == AuthMode.WARN  # env value accepted because no programmatic baseline

    def test_env_cannot_downgrade_verify_expiration_from_true_to_false(self, monkeypatch, caplog):
        """Env cannot silently disable expiration checks that code enabled."""
        monkeypatch.setenv("MALTEGO_SERVER_AUTH_VERIFY_EXPIRATION", "false")
        with caplog.at_level(logging.ERROR, logger="maltego.auth.settings"):
            # SAML so the STRICT JWT/OIDC validator doesn't pre-empt the floor.
            s = AuthSettings(
                enabled=True,
                token_origin="sso",
                provider_type="saml",
                issuer="https://idp.example.com",
                verify_expiration=True,
            )
        assert s.verify_expiration is True
        assert any(
            "downgrade" in r.message.lower() and "verify_expiration" in r.message
            for r in caplog.records
        )

    def test_env_cannot_broaden_allowed_algorithms(self, monkeypatch, caplog):
        """
        Env cannot add algorithms outside the code-set allow-list (e.g. HS256/none).
        Auth is left disabled here to isolate the floor from the N10 algorithm
        validator (which independently hard-rejects none/HS* for enabled JWT/OIDC).
        """
        monkeypatch.setenv("MALTEGO_SERVER_AUTH_ALLOWED_ALGORITHMS", '["RS256", "HS256"]')
        with caplog.at_level(logging.ERROR, logger="maltego.auth.settings"):
            s = AuthSettings(allowed_algorithms={"RS256"})
        assert set(s.allowed_algorithms) == {"RS256"}
        assert "HS256" not in s.allowed_algorithms
        assert any("allowed_algorithms" in r.message for r in caplog.records)

    def test_env_may_narrow_allowed_algorithms(self, monkeypatch):
        """Narrowing the code-set allow-list via env is permitted (not a downgrade)."""
        monkeypatch.setenv("MALTEGO_SERVER_AUTH_ALLOWED_ALGORITHMS", '["RS256"]')
        s = AuthSettings(allowed_algorithms={"RS256", "RS384"})
        assert set(s.allowed_algorithms) == {"RS256"}


# ── F6: missing aud/iss startup warnings ─────────────────────────────────────


class TestF6AudIssWarnings:
    def test_missing_audience_warns_for_jwt(self, caplog):
        """A WARNING is logged when JWT auth has no audience configured."""
        with caplog.at_level(logging.WARNING, logger="maltego.auth.settings"):
            AuthSettings(
                enabled=True,
                token_origin="sso",
                provider_type="jwt",
                provider_url="https://id.example/jwks",
                # No audience set
            )
        assert any(
            "audience" in r.message.lower() and "SECURITY WARNING" in r.message
            for r in caplog.records
        )

    def test_missing_issuer_warns_for_jwt(self, caplog):
        """A WARNING is logged when JWT auth has no issuer configured."""
        with caplog.at_level(logging.WARNING, logger="maltego.auth.settings"):
            AuthSettings(
                enabled=True,
                token_origin="sso",
                provider_type="jwt",
                provider_url="https://id.example/jwks",
                audience="my-service",
                # No issuer set
            )
        assert any(
            "issuer" in r.message.lower() and "SECURITY WARNING" in r.message
            for r in caplog.records
        )

    def test_no_warning_when_audience_and_issuer_set_for_jwt(self, caplog):
        """No security warning emitted when both aud and iss are configured."""
        with caplog.at_level(logging.WARNING, logger="maltego.auth.settings"):
            _jwt_settings()  # has both issuer and audience
        security_warnings = [
            r for r in caplog.records
            if "SECURITY WARNING" in r.message
            and ("audience" in r.message.lower() or "issuer" in r.message.lower())
        ]
        assert not security_warnings

    def test_missing_audience_warns_for_oidc(self, caplog):
        """A WARNING is logged when OIDC auth has no audience configured."""
        with caplog.at_level(logging.WARNING, logger="maltego.auth.settings"):
            AuthSettings(
                enabled=True,
                token_origin="sso",
                provider_type="oidc",
                provider_url="https://id.example/realms/test",
                # No audience
            )
        assert any(
            "audience" in r.message.lower() and "SECURITY WARNING" in r.message
            for r in caplog.records
        )

    def test_issuer_warning_not_emitted_for_oidc(self, caplog):
        """
        OIDC derives the issuer from discovery metadata; a missing issuer in
        settings is not a warning for OIDC (only for bare JWT).
        """
        with caplog.at_level(logging.WARNING, logger="maltego.auth.settings"):
            _oidc_settings()  # has audience but no explicit issuer kwarg
        # No "issuer" SECURITY WARNING should appear (audience is set)
        issuer_warnings = [
            r for r in caplog.records
            if "SECURITY WARNING" in r.message and "issuer" in r.message.lower()
        ]
        assert not issuer_warnings

    def test_aud_iss_warnings_suppressed_when_auth_disabled(self, caplog):
        """No startup warnings when auth is not enabled."""
        with caplog.at_level(logging.WARNING, logger="maltego.auth.settings"):
            AuthSettings(enabled=False, provider_type="jwt")
        security_warnings = [
            r for r in caplog.records if "SECURITY WARNING" in r.message
        ]
        assert not security_warnings

    def test_aud_iss_warnings_suppressed_for_saml(self, caplog):
        """aud/iss warnings only apply to JWT/OIDC, not SAML."""
        with caplog.at_level(logging.WARNING, logger="maltego.auth.settings"):
            AuthSettings(
                enabled=True,
                token_origin="sso",
                provider_type="saml",
                issuer="https://idp.example.com",
                # No audience configured
            )
        audience_warnings = [
            r for r in caplog.records
            if "SECURITY WARNING" in r.message and "audience" in r.message.lower()
        ]
        assert not audience_warnings


# ── F8: WARN mode documentation and startup warning ──────────────────────────


class TestF8WarnMode:
    def setup_method(self):
        reset_auth_settings()

    def teardown_method(self):
        reset_auth_settings()

    def test_startup_warning_emitted_when_warn_mode_set_via_get_auth_settings(
        self, monkeypatch, caplog
    ):
        """get_auth_settings() emits a startup WARNING when auth is in WARN mode."""
        monkeypatch.setenv("MALTEGO_SERVER_AUTH_ENABLED", "true")
        monkeypatch.setenv("MALTEGO_SERVER_AUTH_MODE", "warn")
        monkeypatch.setenv("MALTEGO_SERVER_AUTH_TOKEN_ORIGIN", "sso")
        monkeypatch.setenv("MALTEGO_SERVER_AUTH_PROVIDER_TYPE", "jwt")
        monkeypatch.setenv("MALTEGO_SERVER_AUTH_PROVIDER_URL", "https://id.example/jwks")

        with caplog.at_level(logging.WARNING, logger="maltego.auth.settings"):
            get_auth_settings()

        assert any(
            "WARN" in r.message and "fail-open" in r.message.lower()
            for r in caplog.records
        ), f"Expected WARN mode startup warning. Got: {[r.message for r in caplog.records]}"

    def test_startup_warning_emitted_when_warn_mode_set_via_set_auth_settings(
        self, caplog
    ):
        """set_auth_settings() emits a startup WARNING when auth is in WARN mode."""
        settings = AuthSettings(
            enabled=True,
            mode="warn",
            token_origin="sso",
            provider_type="jwt",
            provider_url="https://id.example/jwks",
            issuer="https://issuer.example",
            audience="my-service",
        )
        with caplog.at_level(logging.WARNING, logger="maltego.auth.settings"):
            set_auth_settings(settings)

        assert any(
            "WARN" in r.message and "fail-open" in r.message.lower()
            for r in caplog.records
        )

    def test_no_warn_mode_startup_warning_for_strict_mode(self, caplog):
        """No WARN-mode startup warning when mode is STRICT (the default)."""
        settings = _jwt_settings(mode="strict")
        with caplog.at_level(logging.WARNING, logger="maltego.auth.settings"):
            set_auth_settings(settings)
        warn_mode_messages = [
            r for r in caplog.records
            if "fail-open" in r.message.lower()
        ]
        assert not warn_mode_messages

    def test_no_warn_mode_startup_warning_when_auth_disabled(self, caplog):
        """No WARN-mode startup warning when auth is disabled."""
        settings = AuthSettings(enabled=False, mode="warn")
        with caplog.at_level(logging.WARNING, logger="maltego.auth.settings"):
            set_auth_settings(settings)
        warn_mode_messages = [
            r for r in caplog.records
            if "fail-open" in r.message.lower()
        ]
        assert not warn_mode_messages
