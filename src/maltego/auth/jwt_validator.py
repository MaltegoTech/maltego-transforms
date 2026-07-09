# Copyright (c) Maltego Technologies GmbH.
"""Generic JWT token validator."""

import base64
import binascii
import json
import logging
import time
from typing import Any, Dict, Optional

import httpx
from joserfc import errors, jwt
from joserfc.jwk import KeySet
from joserfc.jwt import JWTClaimsRegistry

from maltego.auth.settings import AuthSettings
from maltego.auth.validator import AuthValidationFailure, AuthValidationSuccess, ValidationErrorKind

logger = logging.getLogger(__name__)


class _ClaimsRegistryWithoutTimeValidation(JWTClaimsRegistry):
    def validate_exp(self, value: int) -> None:
        return None

    def validate_iat(self, value: int) -> None:
        return None

    def validate_nbf(self, value: int) -> None:
        return None


class JWTTokenValidator:
    """
    Async JWT validator using a configured JWKS URL.

    This validator intentionally has no OIDC discovery dependency. OIDC-specific
    discovery is implemented by ``OIDCTokenValidator`` and delegates back here.
    """

    protocol = "jwt"

    def __init__(self, settings: AuthSettings):
        self.settings = settings
        self._jwks: Optional[Dict[str, Any]] = None
        self._jwks_fetched_at: float = 0.0
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        return self._http_client

    def _get_jwks_uri(self) -> Optional[str]:
        return self.settings.provider_url

    async def _fetch_jwks(self) -> Optional[Dict[str, Any]]:
        """Fetch JWKS from the configured URI. Returns None on failure."""
        jwks_uri = self._get_jwks_uri()
        if not jwks_uri:
            logger.error("No JWKS URI configured")
            return None

        try:
            client = await self._get_http_client()
            response = await client.get(jwks_uri)
            response.raise_for_status()
            jwks = response.json()
            return self._filter_signing_keys(jwks, jwks_uri)
        except httpx.HTTPError as e:
            logger.error("Failed to fetch JWKS from %s: %s", jwks_uri, e)
            return None
        except Exception as e:
            logger.error("Error processing JWKS from %s: %s", jwks_uri, e)
            return None

    def _filter_signing_keys(self, jwks: Any, jwks_uri: str) -> Optional[Dict[str, Any]]:
        if not isinstance(jwks, dict) or "keys" not in jwks:
            logger.error("Invalid JWKS format from %s", jwks_uri)
            return None

        signing_keys = [k for k in jwks["keys"] if self._is_usable_signing_key(k)]

        if not signing_keys:
            logger.error("No valid signing keys found in JWKS")
            return None

        logger.info("JWKS loaded: %d signing keys", len(signing_keys))
        return {"keys": signing_keys}

    def _is_usable_signing_key(self, key: Dict[str, Any]) -> bool:
        key_use = key.get("use")
        key_algorithm = key.get("alg")
        return (
            (key_use is None or key_use == "sig")
            and (key_algorithm is None or key_algorithm in self.settings.allowed_algorithms)
        )

    async def _get_jwks(self, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """Get cached JWKS with TTL. Returns None if JWKS unavailable."""
        now = time.time()
        expired = (now - self._jwks_fetched_at) > self.settings.jwks_cache_ttl

        if self._jwks is None or force_refresh or expired:
            self._jwks = await self._fetch_jwks()
            self._jwks_fetched_at = now if self._jwks else 0.0

        return self._jwks

    def _expected_issuer(self) -> Optional[str]:
        return self.settings.issuer

    def _expected_audience(self) -> Optional[str]:
        return self.settings.audience

    def _validate_claims(self, claims: Dict[str, Any]) -> None:
        claims_options: Dict[str, Any] = {}

        if self.settings.verify_expiration:
            claims_options["exp"] = {"essential": True}

        expected_issuer = self._expected_issuer()
        if expected_issuer:
            claims_options["iss"] = {"essential": True, "value": expected_issuer}

        expected_audience = self._expected_audience()
        if expected_audience:
            claims_options["aud"] = {"essential": True, "value": expected_audience}

        registry_cls = (
            JWTClaimsRegistry
            if self.settings.verify_expiration
            else _ClaimsRegistryWithoutTimeValidation
        )

        registry_cls(
            leeway=self.settings.token_leeway,
            **claims_options,
        ).validate(claims)

    async def _decode_with_jwks(self, token: str, jwks: Dict[str, Any]) -> Dict[str, Any]:
        key_set = KeySet.import_key_set(jwks)
        decoded = jwt.decode(
            token,
            key_set,
            algorithms=list(self.settings.allowed_algorithms),
        )
        claims = dict(decoded.claims)
        self._validate_claims(claims)
        return claims

    async def _decode_without_signature(self, token: str) -> Dict[str, Any]:
        parts = token.split(".")
        if len(parts) != 3:
            raise errors.DecodeError("Invalid JWT format")
        payload = parts[1]
        padded = payload + "=" * (-len(payload) % 4)
        try:
            claims = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        except (binascii.Error, UnicodeError, ValueError) as e:
            raise errors.DecodeError(f"Invalid JWT payload: {e}") from e
        if not isinstance(claims, dict):
            raise errors.InvalidPayloadError("JWT payload must be an object")
        self._validate_claims(claims)
        return claims

    async def validate_token(
        self, token: str
    ) -> AuthValidationFailure | AuthValidationSuccess:
        if not token:
            return AuthValidationFailure(ValidationErrorKind.NO_TOKEN, "No token provided")

        try:
            if not self.settings.verify_signature:
                # verify_signature=False is an explicit, supported capability choice
                # (permitted in any mode; AuthSettings emits a startup log). Decode
                # claims directly without any cryptographic verification.
                claims = await self._decode_without_signature(token)
                return AuthValidationSuccess(
                    identity_claims=claims,
                    auth_claims=claims,
                    protocol=self.protocol,
                    raw_payload=claims,
                )

            jwks = await self._get_jwks()
            if not jwks:
                return AuthValidationFailure(
                    ValidationErrorKind.JWKS_UNAVAILABLE,
                    "JWKS unavailable, cannot validate token",
                )

            try:
                claims = await self._decode_with_jwks(token, jwks)
            except errors.ExpiredTokenError:
                raise
            except errors.ClaimError:
                raise
            except errors.JoseError:
                logger.debug("JWT decode failed, refreshing JWKS")
                jwks = await self._get_jwks(force_refresh=True)
                if not jwks:
                    return AuthValidationFailure(
                        ValidationErrorKind.JWKS_UNAVAILABLE,
                        "JWKS unavailable after refresh",
                    )
                claims = await self._decode_with_jwks(token, jwks)

            return AuthValidationSuccess(
                identity_claims=claims,
                auth_claims=claims,
                protocol=self.protocol,
                raw_payload=claims,
            )
        except errors.ExpiredTokenError as e:
            return AuthValidationFailure(
                ValidationErrorKind.EXPIRED_TOKEN,
                f"JWT token expired: {e}",
            )
        except errors.JoseError as e:
            return AuthValidationFailure(
                ValidationErrorKind.INVALID_TOKEN,
                f"JWT validation failed: {e}",
            )
        except Exception as e:
            logger.error("Unexpected token validation error: %s", e)
            return AuthValidationFailure(
                ValidationErrorKind.INTERNAL_ERROR,
                "Token validation error",
            )

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
