# Copyright (c) Maltego Technologies GmbH.
"""SAML assertion validator."""

import base64
import binascii
import datetime as dt
import json
import logging
import re
import urllib.parse
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx
from lxml import etree
from signxml import XMLVerifier
from signxml.exceptions import InvalidSignature

from maltego.auth.settings import AuthSettings
from maltego.auth.validator import AuthValidationFailure, AuthValidationSuccess, ValidationErrorKind

logger = logging.getLogger(__name__)

SAML_NS = "urn:oasis:names:tc:SAML:2.0:assertion"
MD_NS = "urn:oasis:names:tc:SAML:2.0:metadata"
DS_NS = "http://www.w3.org/2000/09/xmldsig#"
NS = {
    "saml": SAML_NS,
    "md": MD_NS,
    "ds": DS_NS,
}
_SAML_FORM_FIELDS = ("SAMLResponse", "token", "assertion")
_SAML_BEARER_CONFIRMATION_METHOD = "urn:oasis:names:tc:SAML:2.0:cm:bearer"


@dataclass(frozen=True)
class _SubjectConfirmationValidation:
    recipient: Optional[str]
    has_validity_bound: bool
    has_expiration_bound: bool


class _SAMLAssertionExpired(ValueError):
    """SAML assertion is past NotOnOrAfter."""


def decode_unverified_saml_claims(token: str) -> Optional[Dict[str, Any]]:
    """Best-effort SAML assertion decoding without trust validation."""
    try:
        validator = SAMLTokenValidator(AuthSettings())
        saml_b64 = validator._extract_saml_b64(token)
        xml_bytes = _decode_base64_token(saml_b64)
        if xml_bytes is None:
            return None
        root = validator._parse_xml(xml_bytes)
        assertion = _select_assertion(root)
        return _saml_payload_from_assertion(assertion, has_signature=_has_signature(root))
    except Exception:
        logger.debug("Failed to decode unverified SAML claims.", exc_info=True)
        return None


class SAMLTokenValidator:
    """Validate base64/XML SAML assertions against trusted IdP signing material."""

    protocol = "saml"

    def __init__(
        self,
        settings: AuthSettings,
    ):
        self.settings = settings
        self._http_client: Optional[httpx.AsyncClient] = None
        self._metadata_xml: Optional[etree._Element] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        return self._http_client

    def _extract_saml_b64(self, payload_text: str) -> str:
        text = payload_text.strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None

        if isinstance(parsed, str):
            text = parsed.strip()
        elif isinstance(parsed, dict):
            token = parsed.get("token") or parsed.get("assertion")
            if isinstance(token, str) and token.strip():
                text = token.strip()
            else:
                raise ValueError("Could not extract SAML payload")

        for field in _SAML_FORM_FIELDS:
            value = _extract_form_field(text, field)
            if value:
                text = value
                break

        text = urllib.parse.unquote(text).strip()
        if text.startswith("<"):
            return base64.b64encode(text.encode("utf-8")).decode("ascii")

        return re.sub(r"\s+", "", text)

    def _parse_xml(self, xml_bytes: bytes) -> etree._Element:
        parser = etree.XMLParser(resolve_entities=False, no_network=True, remove_blank_text=True)
        return etree.fromstring(xml_bytes, parser=parser)

    async def _fetch_metadata_xml(self) -> Optional[etree._Element]:
        if not self.settings.provider_url:
            return None
        try:
            client = await self._get_http_client()
            response = await client.get(self.settings.provider_url)
            response.raise_for_status()
            return self._parse_xml(response.content)
        except httpx.HTTPError as e:
            logger.error("Failed to fetch SAML metadata from %s: %s", self.settings.provider_url, e)
            return None
        except Exception as e:
            logger.error("Error processing SAML metadata: %s", e)
            return None

    async def _get_metadata_xml(self) -> Optional[etree._Element]:
        if self._metadata_xml is None:
            self._metadata_xml = await self._fetch_metadata_xml()
        return self._metadata_xml

    async def _trusted_cert(self) -> Optional[str]:
        certs = await self._trusted_certs()
        return certs[0] if certs else None

    async def _trusted_certs(self) -> list[str]:
        if self.settings.saml_idp_cert:
            return [self.settings.saml_idp_cert]

        metadata = await self._get_metadata_xml()
        if metadata is None:
            return []

        entity = await self._metadata_entity()
        if entity is None:
            return []

        certs: list[str] = []
        key_descriptors = entity.findall(".//md:IDPSSODescriptor/md:KeyDescriptor", namespaces=NS)
        for key_descriptor in key_descriptors:
            use = key_descriptor.attrib.get("use")
            if use and use != "signing":
                continue
            for cert in key_descriptor.findall(".//ds:X509Certificate", namespaces=NS):
                if cert.text:
                    certs.append(_pem_from_cert_text(cert.text))
        return certs

    async def _metadata_entity(self) -> Optional[etree._Element]:
        metadata = await self._get_metadata_xml()
        if metadata is None:
            return None

        entities = _metadata_entities(metadata)
        if self.settings.issuer:
            for entity in entities:
                if entity.attrib.get("entityID") == self.settings.issuer:
                    return entity
            raise ValueError(
                f"SAML metadata does not contain configured issuer {self.settings.issuer!r}"
            )
        if len(entities) > 1:
            raise ValueError(
                "SAML metadata contains multiple EntityDescriptor elements; configure issuer"
            )
        return entities[0] if entities else None

    async def _metadata_issuer(self) -> Optional[str]:
        entity = await self._metadata_entity()
        if entity is not None:
            return entity.attrib.get("entityID")
        return None

    async def validate_token(
        self, token: str
    ) -> AuthValidationFailure | AuthValidationSuccess:
        if not token:
            return AuthValidationFailure(ValidationErrorKind.NO_TOKEN, "No token provided")

        try:
            saml_b64 = self._extract_saml_b64(token)
            try:
                xml_bytes = _decode_base64_token(saml_b64)
                if xml_bytes is None:
                    raise ValueError("Only base64 data is allowed")
            except (binascii.Error, ValueError) as e:
                return AuthValidationFailure(ValidationErrorKind.INVALID_TOKEN, f"Invalid SAML payload: {e}")

            try:
                root = self._parse_xml(xml_bytes)
            except etree.XMLSyntaxError as e:
                return AuthValidationFailure(ValidationErrorKind.INVALID_TOKEN, f"Invalid SAML XML: {e}")

            verified_root = root
            if self.settings.verify_signature and _has_signature(root):
                trusted_certs = await self._trusted_certs()
                if not trusted_certs:
                    if self.settings.provider_url and not self.settings.saml_idp_cert:
                        return AuthValidationFailure(
                            ValidationErrorKind.PROVIDER_UNAVAILABLE,
                            "SAML trusted IdP signing material unavailable",
                        )
                    return AuthValidationFailure(
                        ValidationErrorKind.INVALID_TOKEN,
                        "SAML signature validation requires trusted IdP metadata or saml_idp_cert",
                    )
                last_error: Optional[Exception] = None
                for trusted_cert in trusted_certs:
                    try:
                        verify_result = XMLVerifier().verify(root, x509_cert=trusted_cert, id_attribute="ID")
                        verified_root = verify_result.signed_xml
                        break
                    except InvalidSignature as e:
                        last_error = e
                else:
                    raise InvalidSignature(str(last_error) if last_error else "No trusted certificate matched")
            elif self.settings.verify_signature:
                # No <Signature> element found but signature verification is enabled.
                # verify_signature=True now unconditionally means "a valid signature is
                # required" — falling through would let an attacker bypass verification
                # simply by stripping the signature. Reject unconditionally.
                return AuthValidationFailure(
                    ValidationErrorKind.INVALID_TOKEN,
                    "SAML token is unsigned; a signature is required when verify_signature=True",
                )

            token_has_signature = _has_signature(root)
            assertion = _select_assertion(verified_root)
            raw_payload = await self._extract_and_validate_claims(
                assertion,
                token_has_signature=token_has_signature,
            )
            identity_claims = _identity_claims_from_saml_payload(raw_payload)
            auth_claims = _auth_claims_from_saml_payload(raw_payload)
            return AuthValidationSuccess(
                identity_claims=identity_claims,
                auth_claims=auth_claims,
                protocol=self.protocol,
                raw_payload=raw_payload,
            )
        except InvalidSignature as e:
            return AuthValidationFailure(
                ValidationErrorKind.INVALID_TOKEN,
                f"SAML signature validation failed: {e}",
            )
        except _SAMLAssertionExpired as e:
            return AuthValidationFailure(ValidationErrorKind.EXPIRED_ASSERTION, str(e))
        except ValueError as e:
            return AuthValidationFailure(ValidationErrorKind.INVALID_TOKEN, str(e))
        except Exception as e:
            logger.error("Unexpected SAML validation error: %s", e)
            return AuthValidationFailure(ValidationErrorKind.INTERNAL_ERROR, "SAML validation error")

    async def _extract_and_validate_claims(
        self,
        root: etree._Element,
        *,
        token_has_signature: bool,
    ) -> Dict[str, Any]:
        raw_payload = _saml_payload_from_assertion(root, has_signature=token_has_signature)
        issuer = raw_payload["iss"]
        audiences = raw_payload["saml_audiences"]
        recipients = raw_payload["saml_recipients"]

        # Require an anchored issuer — fail closed if neither settings.issuer
        # nor a metadata-derived entityID is available.
        expected_issuer = self.settings.issuer or await self._metadata_issuer()
        if not expected_issuer:
            raise ValueError(
                "SAML issuer is not anchored: set issuer or provide IdP metadata "
                "so the token issuer can be verified"
            )
        if issuer != expected_issuer:
            raise ValueError(f"Issuer mismatch: expected {expected_issuer!r}, got {issuer!r}")

        audience = _select_expected_or_first(audiences, self.settings.audience, "Audience")

        configured_recipient = self.settings.recipient
        recipient = _select_expected_or_first(recipients, configured_recipient, "Recipient")

        if self.settings.verify_expiration:
            recipient = self._validate_time_conditions(root, configured_recipient) or recipient

        raw_payload["aud"] = audience
        raw_payload["saml_recipient"] = recipient
        return raw_payload

    def _validate_time_conditions(self, root: etree._Element, recipient: Optional[str]) -> Optional[str]:
        """Validate assertion and bearer-confirmation time windows.

        ``saml:Conditions`` is assertion-wide: if its ``NotBefore`` or
        ``NotOnOrAfter`` bounds are present, they must be valid for the
        assertion as a whole. A valid ``SubjectConfirmationData`` window does
        not override expired or not-yet-valid ``Conditions``.

        ``SubjectConfirmationData`` is bearer-confirmation-specific. When a
        recipient is configured, only confirmation data for that exact
        recipient is considered. When no recipient is configured, any
        confirmation data can satisfy the timing check; the recipient returned
        here is the one from the selected valid confirmation, if it has one.

        The assertion must have both a validity bound and an expiration bound
        from either ``Conditions`` or an applicable confirmation. Returning a
        recipient does not mean recipient matching was enforced; it records
        which valid confirmation supplied the timing information so callers can
        expose it in claims.
        """
        now = dt.datetime.now(dt.UTC)
        leeway = dt.timedelta(seconds=self.settings.token_leeway)
        has_validity_bound = False
        has_expiration_bound = False
        for node in root.findall(".//saml:Conditions", namespaces=NS):
            not_before = _parse_saml_time(node.attrib.get("NotBefore"))
            not_on_or_after = _parse_saml_time(node.attrib.get("NotOnOrAfter"))
            has_validity_bound = has_validity_bound or bool(not_before or not_on_or_after)
            has_expiration_bound = has_expiration_bound or bool(not_on_or_after)
            if not_before and now + leeway < not_before:
                raise ValueError("SAML assertion is not yet valid")
            if not_on_or_after and now - leeway >= not_on_or_after:
                raise _SAMLAssertionExpired("SAML assertion has expired")

        valid_recipient = self._validate_subject_confirmation_data(root, recipient, now, leeway)
        has_validity_bound = has_validity_bound or valid_recipient.has_validity_bound
        has_expiration_bound = has_expiration_bound or valid_recipient.has_expiration_bound

        if not has_validity_bound or not has_expiration_bound:
            raise ValueError("SAML assertion must include validity bounds")
        return valid_recipient.recipient or recipient

    def _validate_subject_confirmation_data(
        self,
        root: etree._Element,
        recipient: Optional[str],
        now: dt.datetime,
        leeway: dt.timedelta,
    ) -> "_SubjectConfirmationValidation":
        nodes = root.findall(".//saml:SubjectConfirmationData", namespaces=NS)
        applicable_nodes = [
            node
            for node in nodes
            if _is_bearer_subject_confirmation_data(node)
            and (recipient is None or node.attrib.get("Recipient") == recipient)
        ]
        has_validity_bound = False
        has_expiration_bound = False
        saw_not_yet_valid = False
        saw_expired = False
        first_valid = None
        for node in applicable_nodes:
            not_before = _parse_saml_time(node.attrib.get("NotBefore"))
            not_on_or_after = _parse_saml_time(node.attrib.get("NotOnOrAfter"))
            node_has_validity_bound = bool(not_before or not_on_or_after)
            node_has_expiration_bound = bool(not_on_or_after)
            has_validity_bound = has_validity_bound or node_has_validity_bound
            has_expiration_bound = has_expiration_bound or node_has_expiration_bound
            if not_before and now + leeway < not_before:
                saw_not_yet_valid = True
                continue
            if not_on_or_after and now - leeway >= not_on_or_after:
                saw_expired = True
                continue
            valid = _SubjectConfirmationValidation(
                recipient=node.attrib.get("Recipient"),
                has_validity_bound=node_has_validity_bound,
                has_expiration_bound=node_has_expiration_bound,
            )
            if valid.has_expiration_bound:
                return valid
            if first_valid is None:
                first_valid = valid

        if first_valid is not None:
            return first_valid

        if applicable_nodes and saw_not_yet_valid:
            raise ValueError("SAML assertion is not yet valid")
        if applicable_nodes and saw_expired:
            raise _SAMLAssertionExpired("SAML assertion has expired")
        return _SubjectConfirmationValidation(
            recipient=None,
            has_validity_bound=has_validity_bound,
            has_expiration_bound=has_expiration_bound,
        )

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


def _is_bearer_subject_confirmation_data(node: etree._Element) -> bool:
    parent = node.getparent()
    return (
        parent is not None
        and etree.QName(parent).localname == "SubjectConfirmation"
        and parent.attrib.get("Method") == _SAML_BEARER_CONFIRMATION_METHOD
    )


def _text(node: Optional[etree._Element]) -> Optional[str]:
    if node is None or node.text is None:
        return None
    return node.text.strip() or None


def _looks_like_email(value: Optional[str]) -> bool:
    return bool(value and "@" in value)


def _extract_saml_email(root: etree._Element) -> Optional[str]:
    email_names = {
        "email",
        "mail",
        "emailaddress",
        "upn",
        "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
        "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
    }
    for attr in root.findall(".//saml:Attribute", namespaces=NS):
        name = (attr.attrib.get("Name") or "").strip().lower()
        if name not in email_names:
            continue
        value = attr.find(".//saml:AttributeValue", namespaces=NS)
        text = _text(value)
        if text:
            return text
    return None


def _saml_payload_from_assertion(root: etree._Element, *, has_signature: bool) -> Dict[str, Any]:
    issuer = _text(root.find("saml:Issuer", namespaces=NS))
    name_id = _text(root.find(".//saml:Subject/saml:NameID", namespaces=NS))
    audiences = [
        audience
        for audience in (
            _text(node)
            for node in root.findall(".//saml:AudienceRestriction/saml:Audience", namespaces=NS)
        )
        if audience
    ]
    recipients = [
        recipient
        for recipient in (
            node.attrib.get("Recipient")
            for node in root.findall(".//saml:SubjectConfirmationData", namespaces=NS)
        )
        if recipient
    ]
    email = _extract_saml_email(root) or (name_id if _looks_like_email(name_id) else None)
    return {
        "iss": issuer,
        "sub": name_id,
        "email": email,
        "aud": audiences[0] if audiences else None,
        "saml_recipient": recipients[0] if recipients else None,
        "saml_assertion_id": root.attrib.get("ID"),
        "saml_audiences": audiences,
        "saml_recipients": recipients,
        "saml_document_has_signature": has_signature,
    }


def _identity_claims_from_saml_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: payload[key]
        for key in ("iss", "sub", "aud", "email")
        if payload.get(key) is not None
    }


def _auth_claims_from_saml_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    claims = _identity_claims_from_saml_payload(payload)
    if payload.get("saml_recipient") is not None:
        claims["saml_recipient"] = payload["saml_recipient"]
    return claims


def _parse_saml_time(value: Optional[str]) -> Optional[dt.datetime]:
    if not value:
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    parsed = dt.datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def _pem_from_cert_text(cert_text: str) -> str:
    stripped = "".join(cert_text.strip().split())
    lines = [stripped[i : i + 64] for i in range(0, len(stripped), 64)]
    return "-----BEGIN CERTIFICATE-----\n" + "\n".join(lines) + "\n-----END CERTIFICATE-----\n"


def _extract_form_field(value: str, field_name: str) -> Optional[str]:
    for part in value.split("&"):
        key, separator, raw_value = part.partition("=")
        if not separator:
            continue
        if urllib.parse.unquote(key) == field_name and raw_value.strip():
            return urllib.parse.unquote(raw_value).strip()
    return None


def _pad_base64(value: str) -> str:
    return f"{value}{'=' * (-len(value) % 4)}"


def _decode_base64_token(value: str) -> bytes | None:
    padded = _pad_base64(value)
    try:
        return base64.b64decode(padded, validate=True)
    except (binascii.Error, ValueError):
        try:
            return base64.urlsafe_b64decode(padded)
        except (binascii.Error, ValueError):
            return None


def _metadata_entities(metadata: etree._Element) -> list[etree._Element]:
    if etree.QName(metadata).localname == "EntityDescriptor":
        return [metadata]
    return metadata.findall("md:EntityDescriptor", namespaces=NS)


def _has_signature(root: etree._Element) -> bool:
    return root.find(".//ds:Signature", namespaces=NS) is not None


def _select_assertion(root: etree._Element) -> etree._Element:
    if etree.QName(root).localname == "Assertion":
        return root
    assertion = root.find(".//saml:Assertion", namespaces=NS)
    if assertion is None:
        raise ValueError("No signed SAML assertion found")
    return assertion


def _select_expected_or_first(values: list[str], expected: Optional[str], field_name: str) -> Optional[str]:
    if expected:
        if expected not in values:
            raise ValueError(f"{field_name} mismatch: expected {expected!r}, got {values!r}")
        return expected
    return values[0] if values else None
