# Copyright (c) Maltego Technologies GmbH.
"""OIDC discovery-backed JWT token validator."""

import logging
from typing import Any, Dict, Optional

import httpx
from authlib.oidc.discovery import OpenIDProviderMetadata, get_well_known_url
from joserfc import errors

from maltego.auth.jwt_validator import JWTTokenValidator
from maltego.auth.settings import AuthSettings, _normalize_oidc_url

logger = logging.getLogger(__name__)


class OIDCTokenValidator(JWTTokenValidator):
    """
    Async OIDC token validator.

    Handles OIDC discovery, then delegates JWT signature and claim validation to
    ``JWTTokenValidator``.
    """

    protocol = "oidc"

    def __init__(self, settings: AuthSettings):
        super().__init__(settings)
        self._metadata: Optional[Dict[str, Any]] = None

    def _get_issuer_url(self) -> Optional[str]:
        return self.settings.provider_url or self.settings.oidc_issuer_url

    async def _fetch_oidc_metadata(self) -> Optional[Dict[str, Any]]:
        """Fetch OIDC discovery document. Returns None on failure."""
        issuer_url = self._get_issuer_url()
        if not issuer_url:
            logger.error("No OIDC issuer URL configured")
            return None

        try:
            discovery_url = (
                issuer_url
                if issuer_url.rstrip("/").endswith("/.well-known/openid-configuration")
                else get_well_known_url(issuer_url, external=True)
            )
            client = await self._get_http_client()
            response = await client.get(discovery_url)
            response.raise_for_status()

            metadata = OpenIDProviderMetadata(response.json())
            discovered_issuer = metadata.get("issuer")
            if not discovered_issuer:
                logger.error("OIDC metadata from %s does not include issuer", issuer_url)
                return None

            if not self.settings.issuer:
                configured_issuer = _normalize_oidc_url(issuer_url)
                normalized_discovered_issuer = str(discovered_issuer).rstrip("/")
                if normalized_discovered_issuer != configured_issuer:
                    logger.error(
                        "OIDC discovery issuer mismatch: configured provider URL %s "
                        "(normalized: %s) does not match discovered issuer %s. "
                        "Rejecting metadata to prevent trusting an unauthorized issuer/jwks_uri.",
                        issuer_url,
                        configured_issuer,
                        discovered_issuer,
                    )
                    return None

            logger.info("OIDC discovery complete: issuer=%s", discovered_issuer)
            return dict(metadata)
        except httpx.HTTPError as e:
            logger.error("Failed to fetch OIDC metadata from %s: %s", issuer_url, e)
            return None
        except Exception as e:
            logger.error("Error processing OIDC metadata: %s", e)
            return None

    async def _get_metadata(self) -> Optional[Dict[str, Any]]:
        """Get cached OIDC metadata. Returns None if unavailable."""
        if self._metadata is None:
            self._metadata = await self._fetch_oidc_metadata()
        return self._metadata

    async def _fetch_jwks(self) -> Optional[Dict[str, Any]]:
        """Fetch JWKS from the discovered URI. Returns None on failure."""
        metadata = await self._get_metadata()
        if not metadata:
            logger.error("OIDC metadata not available")
            return None

        jwks_uri = metadata.get("jwks_uri")
        if not jwks_uri:
            logger.error("No jwks_uri in OIDC metadata")
            return None

        try:
            client = await self._get_http_client()
            response = await client.get(jwks_uri)
            response.raise_for_status()
            return self._filter_signing_keys(response.json(), jwks_uri)
        except httpx.HTTPError as e:
            logger.error("Failed to fetch JWKS: %s", e)
            return None
        except Exception as e:
            logger.error("Error processing JWKS: %s", e)
            return None

    def _expected_issuer(self) -> Optional[str]:
        if self.settings.issuer:
            return self.settings.issuer
        if self._metadata:
            issuer = self._metadata.get("issuer")
            if not issuer:
                raise errors.MissingClaimError("issuer", "OIDC discovery metadata is missing issuer")
            return issuer
        return None
