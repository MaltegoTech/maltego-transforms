#!/usr/bin/env python3
"""Inspect a SAML token/assertion and print whether it is XML-signed.

Examples:
    python src/tests/scripts/inspect_saml_signature.py \
      --token-file /tmp/saml-token.txt

    python src/tests/scripts/inspect_saml_signature.py \
      --token "<base64-saml-assertion>"
"""

from __future__ import annotations

import argparse
import base64
import binascii
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path


SAML_ASSERTION_NS = "urn:oasis:names:tc:SAML:2.0:assertion"
SAML_PROTOCOL_NS = "urn:oasis:names:tc:SAML:2.0:protocol"
XMLDSIG_NS = "http://www.w3.org/2000/09/xmldsig#"
SAML_FORM_FIELDS = ("SAMLResponse", "token", "assertion")


def normalize_saml_token(token: str) -> str:
    text = token.strip()
    for field in SAML_FORM_FIELDS:
        value = extract_form_field(text, field)
        if value:
            text = value
            break

    text = urllib.parse.unquote(text).strip()
    if text.startswith("<"):
        return base64.b64encode(text.encode("utf-8")).decode("ascii")

    text = re.sub(r"\s+", "", text)
    padded = _pad_base64(text)
    if decode_saml_xml_bytes(padded) is not None:
        return padded
    return text


def extract_form_field(value: str, field_name: str) -> str | None:
    for part in value.split("&"):
        key, separator, raw_value = part.partition("=")
        if not separator:
            continue
        if urllib.parse.unquote(key) == field_name and raw_value.strip():
            return urllib.parse.unquote(raw_value).strip()
    return None


def decode_saml_xml_bytes(token: str) -> bytes | None:
    stripped = token.strip()
    if stripped.startswith("<"):
        return stripped.encode("utf-8")
    stripped = re.sub(r"\s+", "", urllib.parse.unquote(stripped))
    if stripped.startswith("<"):
        return stripped.encode("utf-8")
    decoded = _decode_base64_token(stripped)
    if decoded is None:
        return None
    if decoded.lstrip().startswith(b"<"):
        return decoded
    return None


def _decode_base64_token(value: str) -> bytes | None:
    padded = _pad_base64(value)
    try:
        return base64.b64decode(padded, validate=True)
    except (binascii.Error, ValueError):
        try:
            return base64.urlsafe_b64decode(padded)
        except (binascii.Error, ValueError):
            return None


def _pad_base64(value: str) -> str:
    return f"{value}{'=' * (-len(value) % 4)}"


def token_material_kind(token: str) -> str:
    parts = token.split(".")
    if len(parts) == 3 and all(parts):
        return "compact-jwt"
    if decode_saml_xml_bytes(token) is not None:
        return "saml-assertion-or-xml"
    return "opaque-or-raw"


def token_material_shape(token: str) -> str:
    stripped = token.strip()
    has_percent_encoding = bool(re.search(r"%[0-9A-Fa-f]{2}", stripped))
    has_xml_marker = "<" in stripped[:200] or "%3C" in stripped[:200].upper()
    has_saml_response_field = "SAMLResponse" in stripped[:200]
    has_whitespace = any(char.isspace() for char in stripped)
    return (
        f"percent_encoded={has_percent_encoding}, "
        f"xml_marker={has_xml_marker}, "
        f"saml_response_field={has_saml_response_field}, "
        f"has_whitespace={has_whitespace}, "
        f"length_mod4={len(stripped) % 4}"
    )


def _first_text(root: ET.Element, path: str, namespaces: dict[str, str]) -> str | None:
    node = root.find(path, namespaces)
    if node is not None and node.text:
        return node.text.strip() or None
    return None


def _first_attr(root: ET.Element, path: str, attr: str, namespaces: dict[str, str]) -> str | None:
    node = root.find(path, namespaces)
    if node is not None:
        return node.attrib.get(attr)
    return None


def _redact_email(value: str | None) -> str | None:
    if not value or "@" not in value:
        return value
    local, domain = value.split("@", 1)
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def saml_token_summary(token: str) -> dict[str, str | None] | None:
    xml_bytes = decode_saml_xml_bytes(token)
    if xml_bytes is None:
        return None
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None

    ns = {"saml": SAML_ASSERTION_NS}
    return {
        "issuer": _first_text(root, ".//saml:Assertion/saml:Issuer", ns)
        or _first_text(root, "saml:Issuer", ns),
        "audience": _first_text(root, ".//saml:AudienceRestriction/saml:Audience", ns),
        "recipient": _first_attr(root, ".//saml:SubjectConfirmationData", "Recipient", ns),
        "not_on_or_after": _first_attr(root, ".//*[@NotOnOrAfter]", "NotOnOrAfter", ns),
        "name_id": _redact_email(_first_text(root, ".//saml:Subject/saml:NameID", ns)),
    }


def local_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[1]
    return tag


def direct_children(root: ET.Element, namespace: str, name: str) -> list[ET.Element]:
    return [child for child in root if child.tag == f"{{{namespace}}}{name}"]


def find_assertions(root: ET.Element) -> list[ET.Element]:
    if root.tag == f"{{{SAML_ASSERTION_NS}}}Assertion":
        return [root]
    return root.findall(f".//{{{SAML_ASSERTION_NS}}}Assertion")


def signature_report(root: ET.Element) -> dict[str, int | bool | str]:
    assertions = find_assertions(root)
    root_signatures = direct_children(root, XMLDSIG_NS, "Signature")
    assertion_signatures = [
        signature
        for assertion in assertions
        for signature in direct_children(assertion, XMLDSIG_NS, "Signature")
    ]
    all_signatures = root.findall(f".//{{{XMLDSIG_NS}}}Signature")
    certificates = root.findall(f".//{{{XMLDSIG_NS}}}X509Certificate")

    return {
        "root_element": local_name(root.tag),
        "root_is_assertion": root.tag == f"{{{SAML_ASSERTION_NS}}}Assertion",
        "root_is_response": root.tag == f"{{{SAML_PROTOCOL_NS}}}Response",
        "assertion_count": len(assertions),
        "root_direct_signature_count": len(root_signatures),
        "assertion_direct_signature_count": len(assertion_signatures),
        "total_signature_count": len(all_signatures),
        "x509_certificate_count": len(certificates),
    }


def load_token(args: argparse.Namespace) -> tuple[str, str]:
    provided_sources = [
        bool(args.token),
        bool(args.token_file),
    ]
    if sum(provided_sources) != 1:
        raise RuntimeError("Pass exactly one of --token or --token-file.")

    if args.token_file:
        return normalize_saml_token(
            Path(args.token_file).read_text(encoding="utf-8")
        ), f"file: {args.token_file}"

    return normalize_saml_token(args.token), "argument: --token"


def parse_xml(token: str) -> ET.Element:
    xml_bytes = decode_saml_xml_bytes(token)
    if xml_bytes is None:
        raise RuntimeError("Token was not raw XML or base64-encoded SAML XML.")
    try:
        return ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise RuntimeError(f"Decoded SAML XML could not be parsed: {exc}") from exc


def print_report(token: str, source: str, root: ET.Element) -> None:
    report = signature_report(root)
    summary = saml_token_summary(token) or {}
    total_signatures = int(report["total_signature_count"])

    print("SAML Signature Inspection")
    print("=========================")
    print(f"Source: {source}")
    print()
    print("Token material:")
    print(f"  kind: {token_material_kind(token)}")
    print(f"  chars: {len(token)}")
    print(f"  first24: {token[:24]!r}")
    print(f"  shape: {token_material_shape(token)}")
    print()
    print("XML document:")
    print(f"  root_element: {report['root_element']}")
    print(f"  root_is_assertion: {str(report['root_is_assertion']).lower()}")
    print(f"  root_is_response: {str(report['root_is_response']).lower()}")
    print(f"  assertion_count: {report['assertion_count']}")
    for key in ("issuer", "audience", "recipient", "not_on_or_after", "name_id"):
        print(f"  {key}: {summary.get(key)}")
    print()
    print("Signature evidence:")
    print(f"  root_direct_signature_count: {report['root_direct_signature_count']}")
    print(f"  assertion_direct_signature_count: {report['assertion_direct_signature_count']}")
    print(f"  total_signature_count: {total_signatures}")
    print(f"  x509_certificate_count: {report['x509_certificate_count']}")
    print()
    print("Conclusion:")
    if total_signatures == 0:
        print("  UNSIGNED: no XMLDSig Signature element was found in the SAML XML.")
    else:
        print("  SIGNED: at least one XMLDSig Signature element was found.")
        if report["root_is_response"] and report["assertion_direct_signature_count"] == 0:
            print("  Note: the Response may be signed while the nested Assertion is not.")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token", help="Raw XML, base64 SAML XML, or SAMLResponse form value.")
    parser.add_argument("--token-file", help="File containing raw XML, base64 SAML XML, or SAMLResponse form value.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        token, source = load_token(args)
        print_report(token, source, parse_xml(token))
        return 0
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
