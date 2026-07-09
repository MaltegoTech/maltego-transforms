# Copyright (c) Maltego Technologies GmbH.
import inspect
import sys
from unittest.mock import MagicMock

import pytest

from maltego.auth import AuthContext, Identity
from maltego.model.context import MaltegoContext
from maltego.model.graph import MaltegoGraph
from tests.conftest import Phrase

pytestmark = pytest.mark.security


def _context(**kwargs):
    request = MagicMock()
    request.headers = {"user-agent": "Maltego Desktop/test"}
    return MaltegoContext(MaltegoGraph(), request, remote_ip="127.0.0.1", **kwargs)


@pytest.fixture
def transform_identity_info(mock_server_example):
    del mock_server_example
    return sys.modules["tests.example.transforms.transforms"].transform_identity_info


@pytest.mark.asyncio
async def test_debug_auth_context_transform_accepts_phrase_only(transform_identity_info):
    signature = inspect.signature(transform_identity_info)

    assert signature.parameters["input_entity"].annotation is Phrase


@pytest.mark.asyncio
async def test_debug_auth_context_transform_outputs_auth_context(transform_identity_info):
    context = _context(
        auth_context=AuthContext(
            identity=Identity(
                iss="https://idp.example",
                sub="user-123",
                aud="maltego",
                org_id="org-456",
                email="user@example.com",
                realm_roles=["analyst"],
                client_roles={"hub": ["runner"]},
            ),
            rate_limit_key="org:org-456:sub:user-123",
            auth_claims={
                "sub": "user-123",
                "organization": {"id": "org-456", "name": "Example Org"},
            },
            auth_payload={"assertion_id": "_assertion-123"},
            unverified_auth_claims={"debug": True},
        ),
    )

    output = await transform_identity_info(Phrase("input value"), context)
    values = [entity.value for entity in output]

    assert "Auth Available: true" in values
    assert any(value.startswith("Input Entity: ") and "input value" in value for value in values)
    assert any(value.startswith("Organization: ") and "org-456" in value for value in values)
    assert any(value.startswith("Identity: ") and "user@example.com" in value for value in values)
    assert any(value.startswith("Auth Claims: ") and "Example Org" in value for value in values)
    assert any(value.startswith("Auth Payload: ") and "_assertion-123" in value for value in values)
    assert any(value.startswith("Unverified Auth Claims: ") and "debug" in value for value in values)
    assert "Rate Limit Key: org:org-456:sub:user-123" in values
    assert "Remote IP: 127.0.0.1" in values


@pytest.mark.asyncio
async def test_debug_auth_context_transform_outputs_auth_absent(transform_identity_info):
    output = await transform_identity_info(Phrase("input value"), _context())
    values = [entity.value for entity in output]

    assert "Auth Available: false" in values
    assert "Identity: null" in values
    assert "Auth Claims: null" in values
    assert "Auth Payload: null" in values
    assert "Unverified Auth Claims: null" in values
