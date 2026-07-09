# Copyright (c) Maltego Technologies GmbH.
"""JWT claim helpers."""

from __future__ import annotations

import base64
import binascii
import json
import re
from typing import Any, Optional

_BASE64URL_SEGMENT = re.compile(r"^[A-Za-z0-9_-]*$")


def _decode_base64url_json(segment: str) -> Optional[Any]:
    if not segment:
        return None
    try:
        padding = "=" * (-len(segment) % 4)
        decoded = base64.urlsafe_b64decode(f"{segment}{padding}".encode("ascii"))
        return json.loads(decoded.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None


def decode_unverified_jwt_claims(token: str) -> Optional[dict[str, Any]]:
    """Decode compact JWT payload claims without signature or claim validation."""
    parts = token.split(".")
    if len(parts) != 3 or any(_BASE64URL_SEGMENT.fullmatch(part) is None for part in parts):
        return None

    header = _decode_base64url_json(parts[0])
    payload = _decode_base64url_json(parts[1])
    if not isinstance(header, dict) or not isinstance(payload, dict):
        return None
    return payload
