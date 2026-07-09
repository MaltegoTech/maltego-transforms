# Copyright (c) Maltego Technologies GmbH.
"""Authentication settings for JWT/OIDC token validation."""

import argparse
import logging
import sys
import warnings
from enum import Enum
from typing import Annotated, Any, Callable, Optional, Set, Tuple, Type

from pydantic import BeforeValidator, Field, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from maltego.model.server import MALTEGO_ENV_PREFIX

logger = logging.getLogger(__name__)


def _parse_comma_separated_set(v: Any) -> Set[str]:
    """Parse comma-separated string or collection into a Set."""
    if isinstance(v, str):
        return {item.strip() for item in v.split(",") if item.strip()}
    if isinstance(v, (list, set, frozenset)):
        return set(v)
    return v


# Custom type for Set[str] fields parsed from comma-separated strings
CommaSeparatedSet = Annotated[Set[str], BeforeValidator(_parse_comma_separated_set)]


class AuthMode(str, Enum):
    """Authentication mode determining how validation failures are handled.

    - STRICT: Invalid/missing tokens result in 401/403 response
    - WARN: Invalid tokens are logged but requests proceed
    """

    STRICT = "strict"
    WARN = "warn"
    LOG_ONLY = "warn"  # Deprecated alias. Use WARN.

    @classmethod
    def _missing_(cls, value: object) -> Optional["AuthMode"]:
        if isinstance(value, str) and value.lower() == "log_only":
            _warn_deprecated_setting("mode=log_only", "mode=warn")
            return cls.WARN
        return None


class AuthProviderType(str, Enum):
    """Authentication provider/token type."""

    JWT = "jwt"
    OIDC = "oidc"
    SAML = "saml"


class AuthTokenOrigin(str, Enum):
    """Semantic origin of the authentication credential."""

    SSO = "sso"
    MALTEGO_ID = "maltego_id"


def _normalize_oidc_url(v: Optional[str]) -> Optional[str]:
    if not isinstance(v, str):
        return v
    v = v.rstrip("/")
    well_known_suffix = "/.well-known/openid-configuration"
    if v.endswith(well_known_suffix):
        return v[: -len(well_known_suffix)]
    return v


def _warn_deprecated_setting(old_name: str, replacement: str) -> None:
    message = f"{old_name} is deprecated. Use {replacement} instead."
    warnings.warn(message, DeprecationWarning, stacklevel=2)
    logger.warning(message)


def _create_auth_arg_parser() -> argparse.ArgumentParser:
    """Create argument parser for auth CLI arguments."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--auth-enabled", action="store_true", default=None)
    parser.add_argument("--no-auth-enabled", dest="auth_enabled", action="store_false")
    parser.add_argument("--auth-mode", type=str)
    parser.add_argument("--auth-token-origin", type=str, choices=["sso", "maltego_id"])
    parser.add_argument("--auth-provider-type", type=str, choices=["jwt", "oidc", "saml"])
    parser.add_argument("--auth-provider-url", type=str)
    parser.add_argument("--auth-issuer", type=str)
    parser.add_argument("--auth-audience", type=str)
    parser.add_argument("--auth-recipient", type=str)
    parser.add_argument("--auth-token-leeway", type=int)
    parser.add_argument("--auth-saml-idp-cert", type=str)
    parser.add_argument("--auth-oidc-issuer-url", type=str)
    parser.add_argument("--auth-oidc-jwks-uri", type=str)
    parser.add_argument("--auth-oidc-audience", type=str)
    parser.add_argument("--auth-verify-signature", action="store_true", default=None)
    parser.add_argument("--no-auth-verify-signature", dest="auth_verify_signature", action="store_false")
    parser.add_argument("--auth-verify-expiration", action="store_true", default=None)
    parser.add_argument("--no-auth-verify-expiration", dest="auth_verify_expiration", action="store_false")
    parser.add_argument("--auth-expose-unverified-claims", action="store_true", default=None)
    parser.add_argument(
        "--no-auth-expose-unverified-claims",
        dest="auth_expose_unverified_claims",
        action="store_false",
    )
    parser.add_argument("--auth-allowed-algorithms", type=str)
    parser.add_argument("--auth-jwks-cache-ttl", type=int)
    parser.add_argument("--auth-jwt-leeway", type=int)
    parser.add_argument("--auth-public-paths", type=str)
    return parser


class CliSettingsSource(PydanticBaseSettingsSource):
    """Settings source that reads from CLI arguments."""

    def __init__(self, settings_cls: Type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        self._parsed: Optional[argparse.Namespace] = None

    def _parse_args(self) -> argparse.Namespace:
        if self._parsed is None:
            parser = _create_auth_arg_parser()
            self._parsed, _ = parser.parse_known_args(sys.argv[1:])
        return self._parsed

    def get_field_value(
        self, field: Any, field_name: str
    ) -> Tuple[Any, str, bool]:
        args = self._parse_args()
        # Map field names to CLI arg names
        cli_map = {
            "enabled": "auth_enabled",
            "mode": "auth_mode",
            "token_origin": "auth_token_origin",
            "provider_type": "auth_provider_type",
            "provider_url": "auth_provider_url",
            "issuer": "auth_issuer",
            "audience": "auth_audience",
            "recipient": "auth_recipient",
            "token_leeway": "auth_token_leeway",
            "saml_idp_cert": "auth_saml_idp_cert",
            "oidc_issuer_url": "auth_oidc_issuer_url",
            "oidc_jwks_uri": "auth_oidc_jwks_uri",
            "oidc_audience": "auth_oidc_audience",
            "verify_signature": "auth_verify_signature",
            "verify_expiration": "auth_verify_expiration",
            "expose_unverified_claims": "auth_expose_unverified_claims",
            "allowed_algorithms": "auth_allowed_algorithms",
            "jwks_cache_ttl": "auth_jwks_cache_ttl",
            "jwt_leeway": "auth_jwt_leeway",
            "public_paths": "auth_public_paths",
        }
        cli_name = cli_map.get(field_name)
        if cli_name:
            value = getattr(args, cli_name, None)
            if value is not None:
                return value, field_name, False
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for field_name in self.settings_cls.model_fields:
            value, _, _ = self.get_field_value(None, field_name)
            if value is not None:
                result[field_name] = value
        return result


# Security-relevant fields that must not be silently downgraded by env/dotenv.
# Defined at module level so __init__ can reference it without pydantic intercepting it.
_SECURITY_FLOOR_FIELDS: frozenset = frozenset({
    "verify_signature",
    "verify_expiration",
    "mode",
    "allowed_algorithms",
})


class AuthSettings(BaseSettings):
    """
    Authentication settings for JWT/OIDC/SAML token validation.

    All settings can be overridden via environment variables with ``MALTEGO_SERVER_AUTH_`` prefix.

    Example::

        MALTEGO_SERVER_AUTH_ENABLED=true
        MALTEGO_SERVER_AUTH_MODE=strict
        MALTEGO_SERVER_AUTH_PROVIDER_TYPE=oidc
        MALTEGO_SERVER_AUTH_PROVIDER_URL=https://your-keycloak/realms/your-realm

    :param enabled: Master switch to enable/disable authentication (default: False)
    :param mode: How to handle validation failures (strict or warn)
    :param provider_type: Token/provider type (jwt, oidc, saml)
    :param provider_url: Provider configuration URL (JWKS, OIDC issuer/discovery, or SAML metadata)
    :param issuer: Expected issuer (optional)
    :param audience: Expected audience (optional)
    :param recipient: Expected SAML recipient/ACS URL (optional)
    :param verify_signature: Whether to cryptographically verify signatures (JWT/OIDC and SAML).
        When True, a valid signature is required; unsigned/unverifiable credentials are rejected.
        When False, no signature check is performed — an explicit, supported choice permitted in
        any mode (see the loud startup log emitted by server startup).
    :param verify_expiration: Whether to verify token expiration
    :param expose_unverified_claims: Expose syntactically decoded JWT/SAML claims on context
    :param allowed_algorithms: Set of allowed JWT signing algorithms
    :param jwks_cache_ttl: How long to cache JWKS keys in seconds
    :param token_leeway: Time tolerance for time-based validation in seconds
    :param saml_idp_cert: Trusted SAML IdP signing certificate material
    :param validator_factory: Custom validator factory (programmatic only, not from env)
    """

    enabled: bool = Field(
        default=False,  # Disabled by default
        description="Master switch to enable/disable authentication",
    )

    mode: AuthMode = Field(
        default=AuthMode.STRICT,
        description="How to handle validation failures",
    )

    provider_type: Optional[AuthProviderType] = Field(
        default=None,
        description="Token/provider type (jwt, oidc, saml)",
    )

    token_origin: Optional[AuthTokenOrigin] = Field(
        default=None,
        description="Semantic credential origin (sso or maltego_id)",
    )

    provider_url: Optional[str] = Field(
        default=None,
        description="Provider configuration URL (JWKS, OIDC issuer/discovery, or SAML metadata)",
    )

    issuer: Optional[str] = Field(
        default=None,
        description="Expected issuer",
    )

    audience: Optional[str] = Field(
        default=None,
        description="Expected audience",
    )

    recipient: Optional[str] = Field(
        default=None,
        description="Expected SAML recipient/ACS URL",
    )

    token_leeway: int = Field(
        default=60,
        description="Time tolerance in seconds for validating time-based token/assertion claims",
    )

    saml_idp_cert: Optional[str] = Field(
        default=None,
        description="Trusted SAML IdP signing certificate material",
    )

    oidc_issuer_url: Optional[str] = Field(
        default=None,
        description="Deprecated. Use provider_type=oidc and provider_url instead.",
    )

    oidc_jwks_uri: Optional[str] = Field(
        default=None,
        description="Deprecated. Use provider_type=jwt and provider_url instead.",
    )

    oidc_audience: Optional[str] = Field(
        default=None,
        description="Deprecated. Use audience instead.",
    )

    verify_signature: bool = Field(
        default=True,
        description=(
            "Whether to cryptographically verify signatures. True (default): a valid "
            "signature is required (JWT/OIDC compact signature; SAML XML signature) and "
            "unsigned/unverifiable credentials are rejected. False: no signature check is "
            "performed at all — an explicit, supported choice permitted in any mode. Setting "
            "this to False emits a startup WARNING (ERROR if the server binds to a "
            "non-loopback address)."
        ),
    )

    verify_expiration: bool = Field(
        default=True,
        description="Whether to verify token expiration",
    )

    expose_unverified_claims: bool = Field(
        default=False,
        description="Expose syntactically decoded bearer JWT/SAML claims on request state and context",
    )

    allowed_algorithms: CommaSeparatedSet = Field(
        default_factory=lambda: {"RS256"},
        description="Set of allowed JWT signing algorithms",
    )

    public_paths: CommaSeparatedSet = Field(
        default_factory=set,
        description=(
            "Comma-separated list of request paths that bypass authentication entirely, "
            "even when auth is enabled. Example: /swagger,/openapi.json. "
            "Env var: MALTEGO_SERVER_AUTH_PUBLIC_PATHS"
        ),
    )

    jwks_cache_ttl: int = Field(
        default=180,
        description="How long to cache JWKS keys in seconds",
    )

    jwt_leeway: int = Field(
        default=60,
        description="Deprecated. Use token_leeway instead.",
    )

    # Programmatic only - not configurable via env vars
    # Type is Callable[[AuthSettings], TokenValidator] but using Any to avoid circular imports
    validator_factory: Optional[Callable[..., Any]] = Field(
        default=None,
        exclude=True,  # Exclude from serialization/env parsing
        description="Custom validator factory for alternative auth backends",
    )

    model_config = SettingsConfigDict(
        env_prefix=f"{MALTEGO_ENV_PREFIX}AUTH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        env_ignore_empty=True,
    )

    def __init__(self, **data: Any) -> None:
        # Capture which security settings were explicitly set programmatically
        # BEFORE pydantic-settings merges env/dotenv on top.
        programmatic_security = {
            k: v for k, v in data.items() if k in _SECURITY_FLOOR_FIELDS
        }
        super().__init__(**data)
        # Apply security floor: if env/dotenv downgraded a programmatic setting,
        # restore the programmatic (stronger) value and log at ERROR.
        self._enforce_security_floor(programmatic_security)

    def _enforce_security_floor(self, programmatic: dict) -> None:
        """
        Ensure env/dotenv cannot silently downgrade programmatically-set
        security settings. Called after __init__ merges all sources.
        """
        changed = False

        if "verify_signature" in programmatic:
            prog_val = programmatic["verify_signature"]
            if prog_val is True and self.verify_signature is False:
                logger.error(
                    "SECURITY: env/dotenv attempted to downgrade verify_signature from True to False. "
                    "Restoring programmatic value (True). "
                    "Set verify_signature=False explicitly in code to permit this."
                )
                self.verify_signature = True
                changed = True

        if "mode" in programmatic:
            prog_val = programmatic["mode"]
            # Normalise both to AuthMode for comparison
            try:
                prog_mode = AuthMode(prog_val) if isinstance(prog_val, str) else prog_val
            except ValueError:
                prog_mode = None
            if prog_mode == AuthMode.STRICT and self.mode == AuthMode.WARN:
                logger.error(
                    "SECURITY: env/dotenv attempted to downgrade auth mode from STRICT to WARN. "
                    "Restoring programmatic value (STRICT)."
                )
                self.mode = AuthMode.STRICT
                changed = True

        if "verify_expiration" in programmatic:
            prog_val = programmatic["verify_expiration"]
            if prog_val is True and self.verify_expiration is False:
                logger.error(
                    "SECURITY: env/dotenv attempted to downgrade verify_expiration from True to False. "
                    "Restoring programmatic value (True). "
                    "Set verify_expiration=False explicitly in code to permit this."
                )
                self.verify_expiration = True
                changed = True

        if "allowed_algorithms" in programmatic:
            prog_val = programmatic["allowed_algorithms"]
            # env/dotenv may narrow the code-set allow-list but must not broaden it
            # (e.g. inject HS*/none). If env introduced algorithms the code did not
            # sanction, restore the programmatic allow-list.
            try:
                prog_set = set(prog_val) if prog_val is not None else None
            except TypeError:
                prog_set = None
            if prog_set is not None and not set(self.allowed_algorithms) <= prog_set:
                introduced = set(self.allowed_algorithms) - prog_set
                logger.error(
                    "SECURITY: env/dotenv attempted to broaden allowed_algorithms with %s "
                    "beyond the programmatic allow-list. Restoring programmatic value.",
                    sorted(introduced),
                )
                self.allowed_algorithms = prog_set
                changed = True

        if changed:
            logger.error(
                "SECURITY FLOOR: one or more security settings were restored to their "
                "programmatic values because env/dotenv attempted a downgrade. "
                "Review your environment variables."
            )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        """
        Configure settings source priority (highest to lowest):
        1. Environment variables
        2. .env file
        3. CLI arguments
        4. Code (init kwargs)
        5. Secrets files

        Note: env outranks init in this order. Security-relevant settings
        are protected by a floor applied in __init__/_enforce_security_floor:
        if env/dotenv would downgrade a programmatically-hardened value the
        programmatic value is restored and an ERROR is logged.
        """
        return (
            env_settings,
            dotenv_settings,
            CliSettingsSource(settings_cls),
            init_settings,
            file_secret_settings,
        )

    @field_validator("oidc_issuer_url", mode="before")
    @classmethod
    def normalize_oidc_issuer_url(cls, v: Any) -> str:
        """Normalize deprecated OIDC issuer URL inputs."""
        return _normalize_oidc_url(v)

    @field_validator("mode", mode="before")
    @classmethod
    def parse_mode(cls, v: Any) -> AuthMode:
        """Parse mode from string or AuthMode enum."""
        if isinstance(v, AuthMode):
            return v
        if isinstance(v, str):
            return AuthMode(v.lower())
        return v

    @field_validator("provider_type", mode="before")
    @classmethod
    def parse_provider_type(cls, v: Any) -> Optional[AuthProviderType]:
        """Parse provider type from string or AuthProviderType enum."""
        if v is None or isinstance(v, AuthProviderType):
            return v
        if isinstance(v, str):
            return AuthProviderType(v.lower())
        return v

    @field_validator("token_origin", mode="before")
    @classmethod
    def parse_token_origin(cls, v: Any) -> Optional[AuthTokenOrigin]:
        """Parse token origin from string or AuthTokenOrigin enum."""
        if v is None or isinstance(v, AuthTokenOrigin):
            return v
        if isinstance(v, str):
            return AuthTokenOrigin(v.lower())
        return v

    @model_validator(mode="after")
    def map_deprecated_settings_and_validate(self) -> "AuthSettings":
        """Map deprecated OIDC settings to the provider-neutral model."""
        explicit_fields = self.model_fields_set

        if self.oidc_audience:
            if self.audience and self.audience != self.oidc_audience:
                raise ValueError("oidc_audience conflicts with audience")
            _warn_deprecated_setting(
                "oidc_audience",
                "audience",
            )
            self.audience = self.oidc_audience

        if "jwt_leeway" in explicit_fields:
            if "token_leeway" in explicit_fields and self.token_leeway != self.jwt_leeway:
                raise ValueError("jwt_leeway conflicts with token_leeway")
            _warn_deprecated_setting(
                "jwt_leeway",
                "token_leeway",
            )
            self.token_leeway = self.jwt_leeway

        if self.oidc_issuer_url:
            oidc_issuer_url = _normalize_oidc_url(self.oidc_issuer_url)
            if self.provider_type and self.provider_type != AuthProviderType.OIDC:
                raise ValueError("oidc_issuer_url conflicts with provider_type")
            if self.provider_url and _normalize_oidc_url(self.provider_url) != oidc_issuer_url:
                raise ValueError("oidc_issuer_url conflicts with provider_url")
            _warn_deprecated_setting(
                "oidc_issuer_url",
                "provider_type=oidc and provider_url",
            )
            self.provider_type = AuthProviderType.OIDC
            self.provider_url = oidc_issuer_url
            self.oidc_issuer_url = oidc_issuer_url

        if self.oidc_jwks_uri:
            if self.provider_type is None:
                _warn_deprecated_setting(
                    "oidc_jwks_uri",
                    "provider_type=jwt and provider_url",
                )
                self.provider_type = AuthProviderType.JWT
                self.provider_url = self.oidc_jwks_uri
            elif self.provider_type == AuthProviderType.JWT:
                if self.provider_url and self.provider_url != self.oidc_jwks_uri:
                    raise ValueError("oidc_jwks_uri conflicts with provider_url")
                _warn_deprecated_setting(
                    "oidc_jwks_uri",
                    "provider_url",
                )
                self.provider_url = self.oidc_jwks_uri
            elif self.provider_type != AuthProviderType.OIDC:
                raise ValueError("oidc_jwks_uri conflicts with provider_type")
            else:
                _warn_deprecated_setting(
                    "oidc_jwks_uri",
                    "provider_type=oidc and provider_url",
                )

        if self.provider_type == AuthProviderType.OIDC and self.provider_url:
            self.provider_url = _normalize_oidc_url(self.provider_url)
            if self.oidc_issuer_url is None:
                self.oidc_issuer_url = self.provider_url

        # ── Minimum-security floor ─────────────────────────────────────────────
        _SYMMETRIC_ALGOS = frozenset({
            "HS256", "HS384", "HS512",
        })
        _INSECURE_ALGOS = frozenset({"none"}) | _SYMMETRIC_ALGOS

        is_asymmetric_provider = self.provider_type in (
            AuthProviderType.JWT, AuthProviderType.OIDC
        )

        if self.enabled and not self.validator_factory:
            # Reject "none" and symmetric algorithms for JWT/OIDC asymmetric providers
            if is_asymmetric_provider:
                bad_algos = self.allowed_algorithms & _INSECURE_ALGOS
                if bad_algos:
                    raise ValueError(
                        f"allowed_algorithms contains insecure algorithm(s) {bad_algos!r} "
                        "which are not permitted for asymmetric JWT/OIDC providers. "
                        "Remove 'none' and HS* algorithms from allowed_algorithms."
                    )

        # ── verify_signature=False notice ───────────────────────────────────────
        # verify_signature=False is a valid choice — warn, don't block. Same
        # WARNING regardless of mode or bind address (0.0.0.0 behind a proxy is
        # a normal deployment).
        if self.enabled and not self.validator_factory and not self.verify_signature:
            logger.warning(
                "SECURITY WARNING: verify_signature=False is active for %s. "
                "Signatures will not be cryptographically verified. This is an explicit, "
                "supported choice, but must only be used in trusted-network / "
                "auth-terminating-gateway / custom-validator / dev setups.",
                self.provider_type.value if self.provider_type else "auth",
            )

        # ── public_paths + STRICT mode notice ──────────────────────────────────
        # public_paths bypasses auth entirely for the listed paths regardless of
        # mode. Under STRICT this is easy to misread as "fully enforced auth" --
        # warn so operators know those exact paths remain unauthenticated.
        if self.enabled and self.public_paths and self.mode == AuthMode.STRICT:
            logger.warning(
                "SECURITY WARNING: auth.public_paths is set (%s) while mode=strict. "
                "Requests to these exact paths bypass authentication entirely, even "
                "though STRICT mode is enforced for all other paths.",
                sorted(self.public_paths),
            )

        # ── Missing aud/iss warning for JWT/OIDC ───────────────────────────────
        if self.enabled and not self.validator_factory and is_asymmetric_provider and self.verify_signature:
            if not self.audience:
                logger.warning(
                    "SECURITY WARNING: auth.audience is not configured for provider_type=%s. "
                    "Without an expected audience, tokens issued for other services can be "
                    "replayed against this server. Set auth.audience to the expected audience value.",
                    self.provider_type.value if self.provider_type else "unknown",
                )
            # For JWT (not OIDC), also warn on missing issuer since OIDC derives issuer from
            # discovery metadata automatically.
            if self.provider_type == AuthProviderType.JWT and not self.issuer:
                logger.warning(
                    "SECURITY WARNING: auth.issuer is not configured for provider_type=jwt. "
                    "Without an expected issuer, tokens from any issuer will be accepted. "
                    "Set auth.issuer to the expected issuer value.",
                )

        if not self.enabled:
            return self

        if self.validator_factory:
            return self

        if not self.token_origin:
            raise ValueError("token_origin is required when auth is enabled")

        if not self.provider_type:
            raise ValueError("provider_type is required when auth is enabled")

        if (
            self.token_origin == AuthTokenOrigin.MALTEGO_ID
            and self.provider_type == AuthProviderType.SAML
        ):
            raise ValueError("token_origin=maltego_id cannot be used with provider_type=saml")

        if self.provider_type == AuthProviderType.OIDC and not self.provider_url:
            raise ValueError("provider_url is required when provider_type=oidc")

        if (
            self.provider_type == AuthProviderType.JWT
            and self.verify_signature
            and not self.provider_url
        ):
            raise ValueError("provider_url is required when provider_type=jwt and verify_signature=True")

        if self.provider_type == AuthProviderType.SAML:
            # Warn operators about any unconfigured SAML claim fields so they
            # understand the loosened posture for optional fields.
            if not self.issuer and not self.provider_url:
                raise ValueError(
                    "SAML requires an anchored issuer: set issuer or provider_url "
                    "(so the IdP entityID can be resolved from metadata)"
                )
            for field_name in ("audience", "recipient"):
                if not getattr(self, field_name):
                    logger.warning(
                        "SAML %s is not configured; any value in the assertion will be accepted. "
                        "Consider setting auth_%s for a stricter posture.",
                        field_name,
                        field_name,
                    )

        return self


# Global singleton instance
_auth_settings: Optional[AuthSettings] = None


def _warn_if_warn_mode_active(settings: AuthSettings) -> None:
    """
    Emit a startup-time WARNING when auth is enabled in WARN (fail-open) mode.

    WARN mode allows requests to proceed even when token validation fails (bad
    signature, expired, missing token). Do not use on a production network-facing
    server. This warning is emitted at startup so operators are informed.
    """
    if settings.enabled and settings.mode == AuthMode.WARN:
        logger.warning(
            "SECURITY WARNING: auth is enabled in WARN (fail-open) mode. "
            "Requests with invalid, expired, or missing tokens will be ALLOWED THROUGH. "
            "This mode is intended for non-production / observability deployments only. "
            "Set mode=strict for production network-facing servers."
        )


def get_auth_settings() -> AuthSettings:
    """Get the global auth settings instance."""
    global _auth_settings
    if _auth_settings is None:
        _auth_settings = AuthSettings()
        logger.info(
            "Auth settings loaded: enabled=%s, mode=%s, token_origin=%s, provider_type=%s, provider_url=%s",
            _auth_settings.enabled,
            str(_auth_settings.mode),
            _auth_settings.token_origin,
            _auth_settings.provider_type,
            _auth_settings.provider_url,
        )
        _warn_if_warn_mode_active(_auth_settings)
    return _auth_settings


def set_auth_settings(settings: AuthSettings) -> None:
    """
    Set the global auth settings instance.

    Prefer using run_server(auth_settings=...) instead of calling this directly.
    Called internally by run_server when auth_settings is provided.
    """
    global _auth_settings
    _auth_settings = settings
    logger.info(
        "Auth settings set programmatically: enabled=%s, mode=%s, token_origin=%s, provider_type=%s, provider_url=%s",
        settings.enabled,
        str(settings.mode),
        settings.token_origin,
        settings.provider_type,
        settings.provider_url,
    )
    _warn_if_warn_mode_active(settings)


def reset_auth_settings() -> None:
    """Reset the global auth settings (useful for testing)."""
    global _auth_settings
    _auth_settings = None
