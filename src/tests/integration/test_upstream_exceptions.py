# Copyright (c) Maltego Technologies GmbH.
# pylint: disable=protected-access
import uuid
from typing import Optional, Sequence
from unittest.mock import MagicMock

import httpx
import pytest

from maltego.middlewares.middlewares import TransformMiddleware
from maltego.model.exception import (
    MaltegoException,
    MaltegoHTTPDataProviderAPIKeyInvalid,
    MaltegoHTTPDataProviderUnavailable,
    MaltegoHTTPUnauthorized,
)
from maltego.model.graph import MaltegoGraph
from maltego.model.transform import MaltegoTransform
from maltego.model.types import ExecutionState, MaltegoSettingTypes
from maltego.runner.transform_execution_context import TransformExecutionContext
from maltego.server import MaltegoContext
from maltego.util import IntegrationClient
from tests.conftest import Phrase

pytestmark = pytest.mark.integration


def _make_context() -> MaltegoContext:
    """Create a fresh MaltegoContext for each test."""
    req = MagicMock()
    req.headers = {}
    return MaltegoContext(MaltegoGraph(), req)


def _make_client_with_mock_response(monkeypatch, status_code, content=b"{}"):
    """Create an IntegrationClient whose httpx client returns a fixed response."""
    client = IntegrationClient(max_calls_per_period=100, period_length_seconds=0.01)

    async def mock_http_request(method, **kwargs):
        return httpx.Response(status_code=status_code, content=content)

    monkeypatch.setattr(client.httpx_client, "request", mock_http_request)
    return client


@pytest.mark.asyncio
async def test_http_status_error_populates_upstream_exceptions(monkeypatch):
    """A 401 response should record exactly one MaltegoHTTPDataProviderAPIKeyInvalid
    on context.upstream_exceptions with the correct identity."""
    client = _make_client_with_mock_response(monkeypatch, status_code=401)
    context = _make_context()

    with pytest.raises(MaltegoHTTPDataProviderAPIKeyInvalid) as exc_info:
        await client.get(url="https://api.example.com/data", context=context)

    assert len(context.upstream_exceptions) == 1
    recorded = context.upstream_exceptions[0]
    assert recorded is exc_info.value  # same object identity
    assert isinstance(recorded, MaltegoHTTPDataProviderAPIKeyInvalid)
    assert "api.example.com" in recorded.message

    client.rate_throttler._leak_task.cancel()


@pytest.mark.asyncio
async def test_connection_error_populates_upstream_exceptions(monkeypatch):
    """An httpx.ConnectError should record a MaltegoHTTPDataProviderUnavailable
    on context.upstream_exceptions."""
    client = IntegrationClient(max_calls_per_period=100, period_length_seconds=0.01)

    async def mock_http_request(method, **kwargs):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(client.httpx_client, "request", mock_http_request)
    context = _make_context()

    with pytest.raises(MaltegoHTTPDataProviderUnavailable) as exc_info:
        await client.get(url="https://api.example.com/data", context=context)

    assert len(context.upstream_exceptions) == 1
    recorded = context.upstream_exceptions[0]
    assert recorded is exc_info.value
    assert isinstance(recorded, MaltegoHTTPDataProviderUnavailable)
    assert "api" in recorded.message.lower()

    client.rate_throttler._leak_task.cancel()


@pytest.mark.asyncio
async def test_success_leaves_upstream_exceptions_empty(monkeypatch):
    """A 200 response should not add anything to context.upstream_exceptions."""
    client = _make_client_with_mock_response(monkeypatch, status_code=200)
    context = _make_context()

    response = await client.get(url="https://api.example.com/data", context=context)

    assert response.status_code == 200
    assert context.upstream_exceptions == []

    client.rate_throttler._leak_task.cancel()


@pytest.mark.asyncio
async def test_multiple_failures_accumulate(monkeypatch):
    """Two failing calls on the same context should accumulate two exceptions."""
    client = IntegrationClient(max_calls_per_period=100, period_length_seconds=0.01)
    context = _make_context()
    call_count = 0

    async def mock_http_request(method, **kwargs):
        nonlocal call_count
        call_count += 1
        # First call: 403, second call: 500
        if call_count == 1:
            return httpx.Response(status_code=403, content=b"{}")
        return httpx.Response(status_code=500, content=b"{}")

    monkeypatch.setattr(client.httpx_client, "request", mock_http_request)

    with pytest.raises(MaltegoHTTPUnauthorized):
        await client.get(url="https://api.example.com/a", context=context)

    with pytest.raises(MaltegoHTTPDataProviderUnavailable):
        await client.get(url="https://api.example.com/b", context=context)

    assert len(context.upstream_exceptions) == 2
    assert isinstance(context.upstream_exceptions[0], MaltegoHTTPUnauthorized)
    assert isinstance(
        context.upstream_exceptions[1], MaltegoHTTPDataProviderUnavailable
    )

    client.rate_throttler._leak_task.cancel()


class SpyMiddleware(TransformMiddleware):
    """Middleware that records what after_transform receives."""

    def __init__(self) -> None:
        self.captured_context: Optional[MaltegoContext] = None
        self.captured_exceptions: Optional[Sequence[Exception]] = None
        self.called = False

    async def before_transform(
        self, transform, transform_input, properties, context, soft_limit, hard_limit
    ):
        pass

    async def after_transform(
        self,
        transform,
        transform_input,
        output_entities,
        context,
        state,
        exceptions=None,
    ):
        self.called = True
        self.captured_context = context
        self.captured_exceptions = exceptions


@pytest.mark.asyncio
async def test_e2e_runner_middleware_sees_upstream_exceptions(monkeypatch):
    """End-to-end
    A transform catches an upstream API error; the middleware's after_transform
    should see context.upstream_exceptions populated, while exceptions param
    is empty"""

    _client = IntegrationClient(max_calls_per_period=100, period_length_seconds=0.01)

    async def mock_http_request(method, **kwargs):
        return httpx.Response(status_code=500, content=b'{"error": "boom"}')

    monkeypatch.setattr(_client.httpx_client, "request", mock_http_request)

    async def transform_that_handles_error(
        input_entity: Phrase, context: MaltegoContext
    ) -> Phrase:
        try:
            await _client.get(url="https://api.example.com/data", context=context)
        except MaltegoException:
            pass  # handled gracefully
        return Phrase("fallback")

    transform = MaltegoTransform(
        impl=transform_that_handles_error,
        name="test.upstream_handled",
        display_name="Test Upstream Handled",
        description="test",
        author="test",
        location_relevance="",
        owner="test",
        settings=[],
        transform_set="test",
        transform_ns="test",
    )

    spy = SpyMiddleware()

    context = _make_context()
    exec_ctx = TransformExecutionContext(
        run_id=str(uuid.uuid4()),
        transform=transform,
        transform_input=Phrase("input"),
        transform_settings={},
        context=context,
        limit=12,
        transform_execution_timeout=30,
        middleware_execution_timeout=30,
        middlewares=[spy],
    )

    await exec_ctx.run()

    assert exec_ctx.result.state == ExecutionState.COMPLETED

    assert spy.called

    assert spy.captured_exceptions == []

    assert len(spy.captured_context.upstream_exceptions) == 1
    assert isinstance(
        spy.captured_context.upstream_exceptions[0], MaltegoHTTPDataProviderUnavailable
    )

    unhandled_ids = set(id(e) for e in spy.captured_exceptions)
    for exc in spy.captured_context.upstream_exceptions:
        source = (
            "upstream_unhandled" if id(exc) in unhandled_ids else "upstream_handled"
        )
        assert source == "upstream_handled"

    _client.rate_throttler._leak_task.cancel()
