# Copyright (c) Maltego Technologies GmbH.

import base64
import datetime as dt
import os
import re
import textwrap
import urllib.parse
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from lxml import etree
from signxml import XMLSigner, methods

from maltego.auth import AuthSettings
from maltego.auth.saml_validator import SAMLTokenValidator
from maltego.auth.validator import AuthValidationSuccess, ValidationErrorKind

pytestmark = pytest.mark.security


SAML_NS = "urn:oasis:names:tc:SAML:2.0:assertion"
DS_NS = "http://www.w3.org/2000/09/xmldsig#"
KEYCLOAK_SAML_EXAMPLE_PATH_ENV = "MALTEGO_AUTH_KEYCLOAK_SAML_EXAMPLE_PATH"
KEYCLOAK_SAML_IDP_CERT_ENV = "MALTEGO_AUTH_KEYCLOAK_SAML_IDP_CERT"
KEYCLOAK_SAML_IDP_CERT_PATH_ENV = "MALTEGO_AUTH_KEYCLOAK_SAML_IDP_CERT_PATH"
KEYCLOAK_SAML_ISSUER_ENV = "MALTEGO_AUTH_KEYCLOAK_SAML_ISSUER"
KEYCLOAK_SAML_AUDIENCE_ENV = "MALTEGO_AUTH_KEYCLOAK_SAML_AUDIENCE"
KEYCLOAK_SAML_RECIPIENT_ENV = "MALTEGO_AUTH_KEYCLOAK_SAML_RECIPIENT"
KEYCLOAK_SAML_EMAIL_ENV = "MALTEGO_AUTH_KEYCLOAK_SAML_EMAIL"


def _cert_pair(common_name: str = "Test IdP"):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(dt.datetime.now(dt.UTC) - dt.timedelta(days=1))
        .not_valid_after(dt.datetime.now(dt.UTC) + dt.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return (
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode(),
        cert.public_bytes(serialization.Encoding.PEM).decode(),
    )


def _assertion_xml(
    assertion_id: str = "_test-assertion",
    issuer: str = "https://idp.example/metadata",
    audience: str = "https://transform.example",
    recipient: str = "https://transform.example/run",
    name_id: str = "user@example.com",
    not_before: dt.datetime | None = None,
    not_on_or_after: dt.datetime | None = None,
    include_time_bounds: bool = True,
) -> etree._Element:
    now = dt.datetime.now(dt.UTC)
    if include_time_bounds:
        not_before = not_before or (now - dt.timedelta(minutes=1))
        not_on_or_after = not_on_or_after or (now + dt.timedelta(minutes=5))
    assertion = etree.Element(
        f"{{{SAML_NS}}}Assertion",
        nsmap={None: SAML_NS},
        ID=assertion_id,
        Version="2.0",
        IssueInstant=now.isoformat().replace("+00:00", "Z"),
    )
    etree.SubElement(assertion, f"{{{SAML_NS}}}Issuer").text = issuer
    subject = etree.SubElement(assertion, f"{{{SAML_NS}}}Subject")
    etree.SubElement(
        subject,
        f"{{{SAML_NS}}}NameID",
        Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
    ).text = name_id
    confirmation = etree.SubElement(
        subject,
        f"{{{SAML_NS}}}SubjectConfirmation",
        Method="urn:oasis:names:tc:SAML:2.0:cm:bearer",
    )
    etree.SubElement(
        confirmation,
        f"{{{SAML_NS}}}SubjectConfirmationData",
        Recipient=recipient,
        **(
            {"NotOnOrAfter": not_on_or_after.isoformat().replace("+00:00", "Z")}
            if not_on_or_after
            else {}
        ),
    )
    condition_attrs = {}
    if not_before:
        condition_attrs["NotBefore"] = not_before.isoformat().replace("+00:00", "Z")
    if not_on_or_after:
        condition_attrs["NotOnOrAfter"] = not_on_or_after.isoformat().replace("+00:00", "Z")
    conditions = etree.SubElement(
        assertion,
        f"{{{SAML_NS}}}Conditions",
        **condition_attrs,
    )
    restriction = etree.SubElement(conditions, f"{{{SAML_NS}}}AudienceRestriction")
    etree.SubElement(restriction, f"{{{SAML_NS}}}Audience").text = audience
    attrs = etree.SubElement(assertion, f"{{{SAML_NS}}}AttributeStatement")
    attr = etree.SubElement(
        attrs,
        f"{{{SAML_NS}}}Attribute",
        Name="http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
    )
    etree.SubElement(attr, f"{{{SAML_NS}}}AttributeValue").text = name_id
    return assertion


def _signed_assertion_element(private_key: str, cert: str, **kwargs) -> etree._Element:
    assertion_id = kwargs.get("assertion_id", "_test-assertion")
    return XMLSigner(method=methods.enveloped).sign(
        _assertion_xml(**kwargs),
        key=private_key,
        cert=cert,
        reference_uri=f"#{assertion_id}",
        id_attribute="ID",
    )


def _signed_assertion_token(private_key: str, cert: str, **kwargs) -> str:
    signed = _signed_assertion_element(private_key, cert, **kwargs)
    xml = etree.tostring(signed, xml_declaration=True, encoding="utf-8")
    return base64.b64encode(xml).decode()


def _saml_time(value: dt.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _add_subject_confirmation(
    assertion: etree._Element,
    *,
    recipient: str,
    not_on_or_after: dt.datetime | None,
    method: str = "urn:oasis:names:tc:SAML:2.0:cm:bearer",
) -> None:
    subject = assertion.find(f".//{{{SAML_NS}}}Subject")
    confirmation = etree.SubElement(
        subject,
        f"{{{SAML_NS}}}SubjectConfirmation",
        Method=method,
    )
    etree.SubElement(
        confirmation,
        f"{{{SAML_NS}}}SubjectConfirmationData",
        Recipient=recipient,
        **({"NotOnOrAfter": _saml_time(not_on_or_after)} if not_on_or_after else {}),
    )


def _signed_assertion_token_from_element(private_key: str, cert: str, assertion: etree._Element) -> str:
    signed = XMLSigner(method=methods.enveloped).sign(
        assertion,
        key=private_key,
        cert=cert,
        reference_uri="#_test-assertion",
        id_attribute="ID",
    )
    return base64.b64encode(etree.tostring(signed, xml_declaration=True, encoding="utf-8")).decode()


def _signed_response_token(private_key: str, cert: str, assertion: etree._Element) -> str:
    response = etree.Element(
        "{urn:oasis:names:tc:SAML:2.0:protocol}Response",
        nsmap={"samlp": "urn:oasis:names:tc:SAML:2.0:protocol"},
        ID="_test-response",
        Version="2.0",
        IssueInstant=dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
    )
    response.append(assertion)
    signed = XMLSigner(method=methods.enveloped).sign(
        response,
        key=private_key,
        cert=cert,
        reference_uri="#_test-response",
        id_attribute="ID",
    )
    return base64.b64encode(etree.tostring(signed, xml_declaration=True, encoding="utf-8")).decode()


def _cert_body(cert: str) -> str:
    return "".join(line for line in cert.splitlines() if "CERTIFICATE" not in line)


def _token_from_keycloak_saml_example_path() -> str:
    path = os.environ.get(KEYCLOAK_SAML_EXAMPLE_PATH_ENV)
    if not path:
        pytest.skip(f"{KEYCLOAK_SAML_EXAMPLE_PATH_ENV} is not set")

    content = Path(path).read_text(encoding="utf-8").strip()
    match = re.search(r"```text\s*(<\?xml.*?</samlp:Response>)\s*```", content, re.DOTALL)
    if match:
        content = match.group(1).strip()

    if content.startswith("<?xml") or content.startswith("<"):
        return base64.b64encode(content.encode("utf-8")).decode()
    return content


def _keycloak_saml_idp_cert() -> str | None:
    if os.environ.get(KEYCLOAK_SAML_IDP_CERT_ENV):
        return os.environ[KEYCLOAK_SAML_IDP_CERT_ENV]
    cert_path = os.environ.get(KEYCLOAK_SAML_IDP_CERT_PATH_ENV)
    if cert_path:
        return Path(cert_path).read_text(encoding="utf-8")
    return None


def _required_keycloak_saml_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} is not set")
    return value


def _metadata_xml(entity_id: str, signing_cert: str, encryption_cert: str | None = None) -> etree._Element:
    root = etree.Element(
        "{urn:oasis:names:tc:SAML:2.0:metadata}EntityDescriptor",
        nsmap={"md": "urn:oasis:names:tc:SAML:2.0:metadata", "ds": DS_NS},
        entityID=entity_id,
    )
    idp = etree.SubElement(root, "{urn:oasis:names:tc:SAML:2.0:metadata}IDPSSODescriptor")
    for use, cert in (("encryption", encryption_cert), ("signing", signing_cert)):
        if not cert:
            continue
        key_descriptor = etree.SubElement(
            idp,
            "{urn:oasis:names:tc:SAML:2.0:metadata}KeyDescriptor",
            use=use,
        )
        key_info = etree.SubElement(key_descriptor, f"{{{DS_NS}}}KeyInfo")
        x509_data = etree.SubElement(key_info, f"{{{DS_NS}}}X509Data")
        etree.SubElement(x509_data, f"{{{DS_NS}}}X509Certificate").text = _cert_body(cert)
    return root


def _metadata_entities_xml(*entities: etree._Element) -> etree._Element:
    root = etree.Element(
        "{urn:oasis:names:tc:SAML:2.0:metadata}EntitiesDescriptor",
        nsmap={"md": "urn:oasis:names:tc:SAML:2.0:metadata", "ds": DS_NS},
    )
    for entity in entities:
        root.append(entity)
    return root


@pytest.mark.asyncio
@pytest.mark.slow
async def test_saml_validator_handles_real_keycloak_broker_saml_example():
    token = _token_from_keycloak_saml_example_path()
    idp_cert = _keycloak_saml_idp_cert()
    issuer = _required_keycloak_saml_env(KEYCLOAK_SAML_ISSUER_ENV)
    audience = _required_keycloak_saml_env(KEYCLOAK_SAML_AUDIENCE_ENV)
    recipient = _required_keycloak_saml_env(KEYCLOAK_SAML_RECIPIENT_ENV)
    email = _required_keycloak_saml_env(KEYCLOAK_SAML_EMAIL_ENV)
    validator = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            saml_idp_cert=idp_cert,
            issuer=issuer,
            audience=audience,
            recipient=recipient,
            verify_signature=bool(idp_cert),
            verify_expiration=False,
        )
    )

    error_kind, error_msg, claims = await validator.validate_token(token)

    assert error_kind is None, error_msg
    assert claims["iss"] == validator.settings.issuer
    assert claims["aud"] == validator.settings.audience
    assert claims["saml_recipient"] == validator.settings.recipient
    assert claims["sub"] == email
    assert claims["email"] == email


@pytest.mark.asyncio
async def test_saml_validator_accepts_signed_assertion_with_configured_cert():
    private_key, cert = _cert_pair()
    validator = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            saml_idp_cert=cert,
            issuer="https://idp.example/metadata",
            audience="https://transform.example",
            recipient="https://transform.example/run",
        ),
    )

    result = await validator.validate_token(
        _signed_assertion_token(private_key, cert)
    )
    error_kind, error_msg, claims = result

    assert isinstance(result, AuthValidationSuccess)
    assert result.protocol == "saml"
    assert result.identity_claims == {
        "iss": "https://idp.example/metadata",
        "sub": "user@example.com",
        "email": "user@example.com",
        "aud": "https://transform.example",
    }
    assert "saml_assertion_id" not in result.auth_claims
    assert result.raw_payload["saml_assertion_id"]
    assert result.raw_payload["saml_recipients"] == ["https://transform.example/run"]
    assert error_kind is None
    assert error_msg is None
    assert claims["iss"] == "https://idp.example/metadata"
    assert claims["sub"] == "user@example.com"
    assert claims["email"] == "user@example.com"
    assert claims["aud"] == "https://transform.example"


@pytest.mark.asyncio
async def test_saml_validator_rejects_unsigned_assertion_when_verify_signature_is_true():
    """F1 (CRIT): unsigned assertion must be rejected when verify_signature=True (the default)."""
    token = base64.b64encode(
        etree.tostring(_assertion_xml(), xml_declaration=True, encoding="utf-8")
    ).decode()
    validator = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            issuer="https://idp.example/metadata",
            audience="https://transform.example",
            recipient="https://transform.example/run",
        ),
    )

    error_kind, error_msg, claims = await validator.validate_token(token)

    assert error_kind == ValidationErrorKind.INVALID_TOKEN
    assert "unsigned" in error_msg.lower()
    assert claims is None


@pytest.mark.asyncio
async def test_saml_validator_accepts_unsigned_assertion_when_verify_signature_false():
    """
    Simplification: the old require_signature=False 'verify if present, tolerate
    absent' combo no longer exists. verify_signature=False (explicit choice) skips
    signature checks entirely; verify_signature=True always requires a signature.
    """
    token = base64.b64encode(
        etree.tostring(_assertion_xml(), xml_declaration=True, encoding="utf-8")
    ).decode()
    validator = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            issuer="https://idp.example/metadata",
            audience="https://transform.example",
            recipient="https://transform.example/run",
            verify_signature=False,
        ),
    )

    error_kind, error_msg, claims = await validator.validate_token(token)

    assert error_kind is None, error_msg
    assert claims["iss"] == "https://idp.example/metadata"
    assert claims["sub"] == "user@example.com"
    assert claims["aud"] == "https://transform.example"


@pytest.mark.asyncio
async def test_saml_validator_verifies_signed_response_with_unsigned_assertion():
    private_key, cert = _cert_pair()
    token = _signed_response_token(private_key, cert, _assertion_xml())
    validator = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            saml_idp_cert=cert,
            issuer="https://idp.example/metadata",
            audience="https://transform.example",
            recipient="https://transform.example/run",
        ),
    )

    error_kind, error_msg, claims = await validator.validate_token(token)

    assert error_kind is None, error_msg
    assert claims["iss"] == "https://idp.example/metadata"
    assert claims["sub"] == "user@example.com"
    assert claims["aud"] == "https://transform.example"


@pytest.mark.asyncio
async def test_saml_validator_rejects_embedded_keyinfo_without_trusted_cert():
    private_key, cert = _cert_pair()
    validator = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            verify_signature=True,
            saml_idp_cert=None,
            provider_url="https://idp.example/metadata",
        ),
    )

    error_kind, error_msg, claims = await validator.validate_token(
        _signed_assertion_token(private_key, cert)
    )

    assert error_kind == ValidationErrorKind.PROVIDER_UNAVAILABLE
    assert "trusted" in error_msg
    assert claims is None


@pytest.mark.asyncio
async def test_saml_validator_returns_invalid_token_for_malformed_xml():
    token = base64.b64encode(b"<not-xml").decode()
    validator = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            issuer="https://idp.example/metadata",
            verify_signature=False,
        ),
    )

    error_kind, error_msg, claims = await validator.validate_token(token)

    assert error_kind == ValidationErrorKind.INVALID_TOKEN
    assert "SAML XML" in error_msg
    assert claims is None


@pytest.mark.asyncio
async def test_saml_issuer_audience_and_recipient_are_conditional():
    """R2-2: issuer must be anchored; audience/recipient remain optional (warn-only)."""
    private_key, cert = _cert_pair()
    token = _signed_assertion_token(
        private_key,
        cert,
        issuer="https://actual-idp.example",
        audience="actual-audience",
        recipient="actual-recipient",
    )

    # Issuer-anchored but no audience/recipient configured → allowed, claims accepted
    relaxed = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            saml_idp_cert=cert,
            issuer="https://actual-idp.example",
        ),
    )
    error_kind, _, claims = await relaxed.validate_token(token)
    assert error_kind is None
    assert claims["iss"] == "https://actual-idp.example"

    strict = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            saml_idp_cert=cert,
            issuer="https://expected-idp.example",
            audience="expected-audience",
            recipient="expected-recipient",
        ),
    )
    error_kind, error_msg, claims = await strict.validate_token(token)
    assert error_kind == ValidationErrorKind.INVALID_TOKEN
    assert "Issuer" in error_msg
    assert claims is None


@pytest.mark.asyncio
async def test_saml_expired_assertion_rejects_when_time_validation_enabled():
    private_key, cert = _cert_pair()
    token = _signed_assertion_token(
        private_key,
        cert,
        not_before=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=10),
        not_on_or_after=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=5),
    )
    validator = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            saml_idp_cert=cert,
            issuer="https://idp.example/metadata",
        ),
    )

    error_kind, error_msg, claims = await validator.validate_token(token)

    assert error_kind == ValidationErrorKind.EXPIRED_ASSERTION
    assert "expired" in error_msg.lower()
    assert claims is None


@pytest.mark.asyncio
async def test_saml_validator_ignores_expired_subject_confirmation_for_different_recipient():
    private_key, cert = _cert_pair()
    assertion = _assertion_xml(
        recipient="expired-recipient",
        not_on_or_after=dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5),
    )
    expired_confirmation_data = assertion.find(f".//{{{SAML_NS}}}SubjectConfirmationData")
    expired_confirmation_data.attrib["NotOnOrAfter"] = _saml_time(
        dt.datetime.now(dt.UTC) - dt.timedelta(minutes=5)
    )
    _add_subject_confirmation(
        assertion,
        recipient="expected-recipient",
        not_on_or_after=dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5),
    )
    token = _signed_assertion_token_from_element(private_key, cert, assertion)
    validator = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            saml_idp_cert=cert,
            issuer="https://idp.example/metadata",
            recipient="expected-recipient",
        ),
    )

    error_kind, error_msg, claims = await validator.validate_token(token)

    assert error_kind is None
    assert error_msg is None
    assert claims["saml_recipient"] == "expected-recipient"


@pytest.mark.asyncio
async def test_saml_validator_uses_any_valid_subject_confirmation_when_recipient_unconfigured():
    private_key, cert = _cert_pair()
    assertion = _assertion_xml(
        recipient="expired-recipient",
        not_on_or_after=dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5),
    )
    expired_confirmation_data = assertion.find(f".//{{{SAML_NS}}}SubjectConfirmationData")
    expired_confirmation_data.attrib["NotOnOrAfter"] = _saml_time(
        dt.datetime.now(dt.UTC) - dt.timedelta(minutes=5)
    )
    _add_subject_confirmation(
        assertion,
        recipient="valid-recipient",
        not_on_or_after=dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5),
    )
    token = _signed_assertion_token_from_element(private_key, cert, assertion)
    validator = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            saml_idp_cert=cert,
            issuer="https://idp.example/metadata",
        ),
    )

    error_kind, error_msg, claims = await validator.validate_token(token)

    assert error_kind is None
    assert error_msg is None
    assert claims["saml_recipient"] == "valid-recipient"


@pytest.mark.asyncio
async def test_saml_validator_prefers_bounded_valid_subject_confirmation():
    private_key, cert = _cert_pair()
    assertion = _assertion_xml(recipient="unbounded-recipient", include_time_bounds=False)
    _add_subject_confirmation(
        assertion,
        recipient="valid-recipient",
        not_on_or_after=dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5),
    )
    token = _signed_assertion_token_from_element(private_key, cert, assertion)
    validator = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            saml_idp_cert=cert,
            issuer="https://idp.example/metadata",
        ),
    )

    error_kind, error_msg, claims = await validator.validate_token(token)

    assert error_kind is None
    assert error_msg is None
    assert claims["saml_recipient"] == "valid-recipient"


@pytest.mark.asyncio
async def test_saml_validator_ignores_non_bearer_subject_confirmation_timing():
    private_key, cert = _cert_pair()
    assertion = _assertion_xml(
        recipient="expected-recipient",
        not_on_or_after=dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5),
    )
    bearer_confirmation_data = assertion.find(f".//{{{SAML_NS}}}SubjectConfirmationData")
    bearer_confirmation_data.attrib["NotOnOrAfter"] = _saml_time(
        dt.datetime.now(dt.UTC) - dt.timedelta(minutes=5)
    )
    _add_subject_confirmation(
        assertion,
        recipient="expected-recipient",
        not_on_or_after=dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5),
        method="urn:oasis:names:tc:SAML:2.0:cm:holder-of-key",
    )
    token = _signed_assertion_token_from_element(private_key, cert, assertion)
    validator = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            saml_idp_cert=cert,
            issuer="https://idp.example/metadata",
            recipient="expected-recipient",
        ),
    )

    error_kind, error_msg, claims = await validator.validate_token(token)

    assert error_kind == ValidationErrorKind.EXPIRED_ASSERTION
    assert "expired" in error_msg.lower()
    assert claims is None


@pytest.mark.asyncio
async def test_saml_validator_rejects_future_conditions_even_when_subject_confirmation_valid():
    private_key, cert = _cert_pair()
    assertion = _assertion_xml(
        not_before=dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5),
        not_on_or_after=dt.datetime.now(dt.UTC) + dt.timedelta(minutes=10),
    )
    token = _signed_assertion_token_from_element(private_key, cert, assertion)
    validator = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            saml_idp_cert=cert,
            issuer="https://idp.example/metadata",
        ),
    )

    error_kind, error_msg, claims = await validator.validate_token(token)

    assert error_kind == ValidationErrorKind.INVALID_TOKEN
    assert "not yet valid" in error_msg.lower()
    assert claims is None


@pytest.mark.asyncio
async def test_saml_validator_accepts_conditions_time_bounds_without_subject_confirmation():
    private_key, cert = _cert_pair()
    assertion = _assertion_xml()
    for node in assertion.findall(f".//{{{SAML_NS}}}SubjectConfirmation"):
        node.getparent().remove(node)
    token = _signed_assertion_token_from_element(private_key, cert, assertion)
    validator = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            saml_idp_cert=cert,
            issuer="https://idp.example/metadata",
        ),
    )

    error_kind, error_msg, claims = await validator.validate_token(token)

    assert error_kind is None
    assert error_msg is None
    assert claims["sub"] == "user@example.com"


@pytest.mark.asyncio
async def test_saml_validator_rejects_expired_conditions_even_when_subject_confirmation_valid():
    private_key, cert = _cert_pair()
    assertion = _assertion_xml(
        not_before=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=10),
        not_on_or_after=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=5),
    )
    confirmation_data = assertion.find(f".//{{{SAML_NS}}}SubjectConfirmationData")
    confirmation_data.attrib["NotOnOrAfter"] = _saml_time(
        dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5)
    )
    token = _signed_assertion_token_from_element(private_key, cert, assertion)
    validator = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            saml_idp_cert=cert,
            issuer="https://idp.example/metadata",
        ),
    )

    error_kind, error_msg, claims = await validator.validate_token(token)

    assert error_kind == ValidationErrorKind.EXPIRED_ASSERTION
    assert "expired" in error_msg.lower()
    assert claims is None


@pytest.mark.asyncio
async def test_saml_signed_assertion_without_validity_bounds_rejects_when_time_validation_enabled():
    private_key, cert = _cert_pair()
    token = _signed_assertion_token(private_key, cert, include_time_bounds=False)
    validator = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            saml_idp_cert=cert,
            issuer="https://idp.example/metadata",
        ),
    )

    error_kind, error_msg, claims = await validator.validate_token(token)

    assert error_kind == ValidationErrorKind.INVALID_TOKEN
    assert "validity" in error_msg.lower()
    assert claims is None


@pytest.mark.asyncio
async def test_saml_validator_accepts_json_wrapped_payloads():
    private_key, cert = _cert_pair()
    for i, fmt in enumerate(('{{"token": "{}"}}', '{{"assertion": "{}"}}')):
        token = _signed_assertion_token(private_key, cert, assertion_id=f"_test-json-{i}")
        validator = SAMLTokenValidator(
            AuthSettings(
                enabled=True,
                token_origin="sso",
                provider_type="saml",
                saml_idp_cert=cert,
                issuer="https://idp.example/metadata",
            ),
        )
        payload = fmt.format(token)
        error_kind, _, claims = await validator.validate_token(payload)
        assert error_kind is None
        assert claims["sub"] == "user@example.com"


@pytest.mark.asyncio
async def test_saml_validator_accepts_raw_xml_form_encoded_and_wrapped_base64_payloads():
    private_key, cert = _cert_pair()
    # Exercise each payload format with its own token.
    payloads = []
    for i in range(6):
        tok = _signed_assertion_token(private_key, cert, assertion_id=f"_test-fmt-{i}")
        payloads.append(tok)
    xml_payloads = [base64.b64decode(t).decode("utf-8") for t in payloads]

    test_cases = [
        xml_payloads[0],
        urllib.parse.quote(xml_payloads[1]),
        f"SAMLResponse={urllib.parse.quote_plus(payloads[2])}",
        "\n".join(textwrap.wrap(payloads[3], 64)),
        payloads[4].rstrip("="),
        base64.urlsafe_b64encode(base64.b64decode(payloads[5])).decode("ascii").rstrip("="),
    ]

    for payload in test_cases:
        validator = SAMLTokenValidator(
            AuthSettings(
                enabled=True,
                token_origin="sso",
                provider_type="saml",
                saml_idp_cert=cert,
                issuer="https://idp.example/metadata",
            ),
        )
        error_kind, error_msg, claims = await validator.validate_token(payload)
        assert error_kind is None, error_msg
        assert claims["sub"] == "user@example.com"


@pytest.mark.asyncio
async def test_saml_validator_preserves_literal_plus_in_form_encoded_base64():
    # Build a minimal SAML assertion whose base64 encoding contains a '+'.
    # We keep the issuer in the XML so R2-2 issuer-anchor check passes, and
    # turn off signature + expiration so we're only testing the '+' handling.
    xml_bytes = (
        b'<saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">'
        b"<saml:Issuer>https://idp.example/metadata</saml:Issuer>"
        b"</saml:Assertion>"
    )
    token = base64.b64encode(xml_bytes).decode("ascii")
    # Guarantee '+' appears in the base64; if the specific bytes above don't
    # produce one, pad the issuer slightly until it does (this loop exits quickly).
    suffix = b""
    while "+" not in token:
        suffix += b" "
        xml_bytes = (
            b'<saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">'
            b"<saml:Issuer>https://idp.example/metadata</saml:Issuer>"
            + suffix
            + b"</saml:Assertion>"
        )
        token = base64.b64encode(xml_bytes).decode("ascii")
    assert "+" in token
    validator = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            issuer="https://idp.example/metadata",
            verify_signature=False,
            verify_expiration=False,
        ),
    )

    error_kind, error_msg, _ = await validator.validate_token(f"SAMLResponse={token}")

    assert error_kind is None, error_msg


@pytest.mark.asyncio
async def test_saml_validator_extracts_claims_from_signed_assertion_only():
    private_key, cert = _cert_pair()
    unsigned = _assertion_xml(
        assertion_id="_unsigned",
        issuer="https://evil.example",
        audience="evil-audience",
        recipient="evil-recipient",
        name_id="attacker@example.com",
    )
    signed = _signed_assertion_element(
        private_key,
        cert,
        assertion_id="_signed",
        issuer="https://idp.example/metadata",
        audience="https://transform.example",
        recipient="https://transform.example/run",
        name_id="user@example.com",
    )
    response = etree.Element("Response")
    response.append(unsigned)
    response.append(signed)
    token = base64.b64encode(etree.tostring(response, xml_declaration=True, encoding="utf-8")).decode()
    validator = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            saml_idp_cert=cert,
            issuer="https://idp.example/metadata",
        ),
    )

    error_kind, error_msg, claims = await validator.validate_token(token)

    assert error_kind is None
    assert error_msg is None
    assert claims["iss"] == "https://idp.example/metadata"
    assert claims["sub"] == "user@example.com"
    assert claims["aud"] == "https://transform.example"


@pytest.mark.asyncio
async def test_saml_validator_uses_metadata_signing_cert_not_encryption_cert():
    signing_key, signing_cert = _cert_pair("Signing")
    _, encryption_cert = _cert_pair("Encryption")
    token = _signed_assertion_token(signing_key, signing_cert)
    validator = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            provider_url="https://idp.example/metadata",
            issuer="https://idp.example/metadata",
        ),
    )
    validator._metadata_xml = _metadata_xml(
        entity_id="https://idp.example/metadata",
        signing_cert=signing_cert,
        encryption_cert=encryption_cert,
    )

    error_kind, error_msg, claims = await validator.validate_token(token)

    assert error_kind is None
    assert error_msg is None
    assert claims["sub"] == "user@example.com"


@pytest.mark.asyncio
async def test_saml_validator_requires_issuer_for_multi_entity_metadata():
    signing_key, signing_cert = _cert_pair("Signing")
    _, other_cert = _cert_pair("Other")
    token = _signed_assertion_token(signing_key, signing_cert)
    validator = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            provider_url="https://idp.example/metadata",
        ),
    )
    validator._metadata_xml = _metadata_entities_xml(
        _metadata_xml("https://idp.example/metadata", signing_cert),
        _metadata_xml("https://other-idp.example/metadata", other_cert),
    )

    error_kind, error_msg, claims = await validator.validate_token(token)

    assert error_kind == ValidationErrorKind.INVALID_TOKEN
    assert "multiple" in error_msg.lower()
    assert "issuer" in error_msg.lower()
    assert claims is None


@pytest.mark.asyncio
async def test_saml_validator_accepts_matching_audience_and_recipient_among_multiple_values():
    private_key, cert = _cert_pair()
    assertion = _assertion_xml()
    restriction = assertion.find(f".//{{{SAML_NS}}}AudienceRestriction")
    etree.SubElement(restriction, f"{{{SAML_NS}}}Audience").text = "second-audience"
    subject = assertion.find(f".//{{{SAML_NS}}}Subject")
    confirmation = etree.SubElement(
        subject,
        f"{{{SAML_NS}}}SubjectConfirmation",
        Method="urn:oasis:names:tc:SAML:2.0:cm:bearer",
    )
    etree.SubElement(
        confirmation,
        f"{{{SAML_NS}}}SubjectConfirmationData",
        Recipient="second-recipient",
        NotOnOrAfter=(dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
    )
    signed = XMLSigner(method=methods.enveloped).sign(
        assertion,
        key=private_key,
        cert=cert,
        reference_uri="#_test-assertion",
        id_attribute="ID",
    )
    token = base64.b64encode(etree.tostring(signed, xml_declaration=True, encoding="utf-8")).decode()
    validator = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            saml_idp_cert=cert,
            issuer="https://idp.example/metadata",
            audience="second-audience",
            recipient="second-recipient",
        ),
    )

    error_kind, error_msg, claims = await validator.validate_token(token)

    assert error_kind is None
    assert error_msg is None
    assert claims["aud"] == "second-audience"
    assert claims["saml_recipient"] == "second-recipient"


# ---------------------------------------------------------------------------
# New tests for PRP 2 — SAML hardening (F1, R2-2, F2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_f1_verify_signature_true_rejects_unsigned_assertion():
    """
    F1 (CRIT) regression guard: verify_signature=True (default) must reject an
    assertion with no <Signature>, unconditionally -- independent of any
    require_signature flag (removed; folded into verify_signature=True meaning
    "signature required").
    """
    token = base64.b64encode(
        etree.tostring(_assertion_xml(), xml_declaration=True, encoding="utf-8")
    ).decode()
    validator = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            issuer="https://idp.example/metadata",
            # verify_signature defaults to True -> signature is unconditionally required
        ),
    )

    error_kind, error_msg, claims = await validator.validate_token(token)

    assert error_kind == ValidationErrorKind.INVALID_TOKEN
    assert "unsigned" in error_msg.lower()
    assert claims is None


@pytest.mark.asyncio
async def test_f1_signed_assertion_with_trusted_cert_accepted():
    """F1: properly signed assertion with verify_signature=True is accepted."""
    private_key, cert = _cert_pair()
    validator = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            saml_idp_cert=cert,
            issuer="https://idp.example/metadata",
        ),
    )

    error_kind, error_msg, claims = await validator.validate_token(
        _signed_assertion_token(private_key, cert)
    )

    assert error_kind is None, error_msg
    assert claims["iss"] == "https://idp.example/metadata"


@pytest.mark.asyncio
async def test_f1_verify_signature_false_still_decodes_unsigned_assertion():
    """F1: verify_signature=False (loose mode) continues to decode unsigned assertions."""
    token = base64.b64encode(
        etree.tostring(_assertion_xml(), xml_declaration=True, encoding="utf-8")
    ).decode()
    validator = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            issuer="https://idp.example/metadata",
            verify_signature=False,
        ),
    )

    error_kind, error_msg, claims = await validator.validate_token(token)

    assert error_kind is None, error_msg
    assert claims["iss"] == "https://idp.example/metadata"


@pytest.mark.asyncio
async def test_r2_2_unconfigured_issuer_fails_closed():
    """R2-2: constructing AuthSettings with SAML and no issuer/provider_url must fail closed."""
    import pytest as _pytest
    from pydantic import ValidationError

    with _pytest.raises(ValidationError, match="anchored issuer"):
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            saml_idp_cert="some-cert",
            # No issuer, no provider_url
        )


@pytest.mark.asyncio
async def test_r2_2_configured_issuer_mismatch_rejected():
    """R2-2: token issuer that doesn't match configured issuer is rejected."""
    private_key, cert = _cert_pair()
    token = _signed_assertion_token(
        private_key,
        cert,
        issuer="https://actual-idp.example",
    )
    validator = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            saml_idp_cert=cert,
            issuer="https://expected-idp.example",
        ),
    )

    error_kind, error_msg, claims = await validator.validate_token(token)

    assert error_kind == ValidationErrorKind.INVALID_TOKEN
    assert "issuer" in error_msg.lower()
    assert claims is None


@pytest.mark.asyncio
async def test_r2_2_configured_issuer_matching_accepted():
    """R2-2: token with matching issuer is accepted."""
    private_key, cert = _cert_pair()
    validator = SAMLTokenValidator(
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            saml_idp_cert=cert,
            issuer="https://idp.example/metadata",
        ),
    )

    error_kind, error_msg, claims = await validator.validate_token(
        _signed_assertion_token(private_key, cert, assertion_id="_r22-match")
    )

    assert error_kind is None, error_msg
    assert claims["iss"] == "https://idp.example/metadata"


@pytest.mark.asyncio
async def test_r2_2_startup_warns_on_unconfigured_audience(caplog):
    """R2-2: startup warning is emitted for each unconfigured SAML claim field."""
    import logging

    with caplog.at_level(logging.WARNING, logger="maltego.auth.settings"):
        AuthSettings(
            enabled=True,
            token_origin="sso",
            provider_type="saml",
            issuer="https://idp.example/metadata",
            # audience and recipient not configured → should warn
        )

    warning_messages = " ".join(caplog.messages)
    assert "audience" in warning_messages.lower()
    assert "recipient" in warning_messages.lower()

