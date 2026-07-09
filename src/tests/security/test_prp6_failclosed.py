# Copyright (c) Maltego Technologies GmbH.
"""
Tests for PRP 6 — Fail-closed & info-leak hygiene.

Covers:
  F23  — CORS wildcard+credentials guard
  F40  — SharedSettings fail-closed
  F13  — XFF trusted-proxy gating
  F53  — Paginator SSRF URL validation
  R2-5 — ETag random
  R2-6 — Generic 400 detail
  F33  — transform_id mismatch returns 404
  F25/F70 — Docs gated under auth (structural check)

Covered elsewhere (behaviour lives in a more appropriate layer):
  F21  — TLS fail-closed → unit/test_config.py::TestServerHTTPSettings
  R3-1 — GET returns 200 → contracts/v3/test_v3_transform_execution.py
"""
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import fastapi
import pytest
from starlette.requests import Request

pytestmark = pytest.mark.security


# ---------------------------------------------------------------------------
# F21 — TLS fail-closed: covered in unit/test_config.py::TestServerHTTPSettings
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# F23 — CORS wildcard+credentials guard
# ---------------------------------------------------------------------------

def test_cors_setup_raises_on_wildcard_with_credentials():
    """_setup_cors raises ValueError when allow_origins=['*'] is configured."""
    from maltego.server import MaltegoTransformServer

    app = fastapi.FastAPI()
    server = MaltegoTransformServer.__new__(MaltegoTransformServer)
    server.app = app

    http_settings = MagicMock()
    http_settings.cors_allowed_origins = ["*"]
    http_settings.cors_allowed_origin_regex = None

    server._settings = MagicMock()
    server._settings.http_settings = http_settings

    with pytest.raises(ValueError, match="allow_origins"):
        server._setup_cors()


def test_cors_setup_succeeds_with_explicit_origins():
    """_setup_cors succeeds when explicit origin list is provided."""
    from maltego.server import MaltegoTransformServer

    app = fastapi.FastAPI()
    server = MaltegoTransformServer.__new__(MaltegoTransformServer)
    server.app = app

    http_settings = MagicMock()
    http_settings.cors_allowed_origins = ["https://app.example.com"]
    http_settings.cors_allowed_origin_regex = None

    server._settings = MagicMock()
    server._settings.http_settings = http_settings

    # Should not raise
    server._setup_cors()


@pytest.mark.parametrize("regex", [".*", ".+", "^.*$", "^.+$", "(.*)", "(.+)", "  .*  "])
def test_cors_setup_raises_on_catch_all_regex_with_credentials(regex):
    """A catch-all origin regex is equivalent to a wildcard and must be rejected
    when credentials are allowed (allow_credentials is hardcoded True)."""
    from maltego.server import MaltegoTransformServer

    app = fastapi.FastAPI()
    server = MaltegoTransformServer.__new__(MaltegoTransformServer)
    server.app = app

    http_settings = MagicMock()
    http_settings.cors_allowed_origins = None
    http_settings.cors_allowed_origin_regex = regex

    server._settings = MagicMock()
    server._settings.http_settings = http_settings

    with pytest.raises(ValueError, match="catch-all"):
        server._setup_cors()


def test_cors_setup_succeeds_with_anchored_regex():
    """An anchored regex bound to trusted domains is fine with credentials."""
    from maltego.server import MaltegoTransformServer

    app = fastapi.FastAPI()
    server = MaltegoTransformServer.__new__(MaltegoTransformServer)
    server.app = app

    http_settings = MagicMock()
    http_settings.cors_allowed_origins = None
    http_settings.cors_allowed_origin_regex = r"^https://.*\.example\.com$"

    server._settings = MagicMock()
    server._settings.http_settings = http_settings

    # Should not raise — the regex is anchored to a trusted domain suffix.
    server._setup_cors()


def test_cors_setup_skips_when_no_origins_configured():
    """_setup_cors does nothing when no origins are configured."""
    from maltego.server import MaltegoTransformServer

    app = fastapi.FastAPI()
    server = MaltegoTransformServer.__new__(MaltegoTransformServer)
    server.app = app

    http_settings = MagicMock()
    http_settings.cors_allowed_origins = None
    http_settings.cors_allowed_origin_regex = None

    server._settings = MagicMock()
    server._settings.http_settings = http_settings

    # Should not raise and no middleware added
    before_count = len(app.user_middleware)
    server._setup_cors()
    assert len(app.user_middleware) == before_count


# ---------------------------------------------------------------------------
# F40 — SharedSettings fail-closed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_shared_settings_does_not_inject_none():
    """SharedSettingsMiddleware does NOT overwrite a blank value with None."""
    from maltego.middlewares.shared_settings_middleware import SharedSettingsMiddleware

    middleware = SharedSettingsMiddleware()
    props = {"api_key": ""}

    with patch(
        "maltego.middlewares.shared_settings_middleware.get_shared_setting",
        return_value=None,
    ):
        await middleware.before_transform(
            transform=MagicMock(),
            transform_input=MagicMock(),
            properties=props,
            context=MagicMock(),
            soft_limit=10,
            hard_limit=20,
        )

    # Key should remain "" not be replaced with None
    assert props["api_key"] == ""


@pytest.mark.asyncio
async def test_shared_settings_injects_when_value_found():
    """SharedSettingsMiddleware injects shared setting when one exists."""
    from maltego.middlewares.shared_settings_middleware import SharedSettingsMiddleware

    middleware = SharedSettingsMiddleware()
    props = {"api_key": ""}

    with patch(
        "maltego.middlewares.shared_settings_middleware.get_shared_setting",
        return_value="secret-value",
    ):
        await middleware.before_transform(
            transform=MagicMock(),
            transform_input=MagicMock(),
            properties=props,
            context=MagicMock(),
            soft_limit=10,
            hard_limit=20,
        )

    assert props["api_key"] == "secret-value"


# ---------------------------------------------------------------------------
# F13 — XFF trusted-proxy gating
# ---------------------------------------------------------------------------

def _make_request_with_ip(ip: str, xff: Optional[str] = None) -> MagicMock:
    """Create a mock request with a given client IP and optional XFF header."""
    request = MagicMock(spec=Request)
    request.client = MagicMock()
    request.client.host = ip
    request.headers = {"X-Forwarded-For": xff} if xff else {}
    return request


def test_get_client_ip_ignores_xff_from_untrusted_proxy():
    """XFF header is ignored when the connecting client is not in the allowed list."""
    from maltego.auth.dependency import _get_client_ip

    # Connecting from 10.0.0.1 (not in allow-list)
    request = _make_request_with_ip("10.0.0.1", xff="203.0.113.50")
    ip = _get_client_ip(request, forwarded_allow_ips="127.0.0.1")
    # Must return direct IP, NOT the spoofed XFF
    assert ip == "10.0.0.1"


def test_get_client_ip_trusts_xff_from_loopback():
    """XFF is trusted when the connecting client is 127.0.0.1 (default allow)."""
    from maltego.auth.dependency import _get_client_ip

    request = _make_request_with_ip("127.0.0.1", xff="203.0.113.50, 70.41.3.18")
    ip = _get_client_ip(request, forwarded_allow_ips="127.0.0.1")
    assert ip == "203.0.113.50"


def test_get_client_ip_trusts_xff_from_explicit_trusted_proxy():
    """XFF is trusted when forwarded_allow_ips explicitly allows the proxy."""
    from maltego.auth.dependency import _get_client_ip

    request = _make_request_with_ip("192.168.1.1", xff="203.0.113.50")
    ip = _get_client_ip(request, forwarded_allow_ips="192.168.1.1")
    assert ip == "203.0.113.50"


def test_get_client_ip_direct_connection_no_xff():
    """Direct connection without XFF returns client host."""
    from maltego.auth.dependency import _get_client_ip

    request = _make_request_with_ip("10.0.0.5")
    ip = _get_client_ip(request, forwarded_allow_ips="127.0.0.1")
    assert ip == "10.0.0.5"


def test_build_rate_limit_key_uses_direct_ip_for_untrusted_proxy():
    """Rate-limit key uses direct IP when XFF comes from untrusted proxy."""
    from maltego.auth.dependency import _build_rate_limit_key
    from maltego.auth.identity import Identity

    request = _make_request_with_ip("10.0.0.1", xff="203.0.113.99")
    identity = Identity(sub="user-1")
    key = _build_rate_limit_key(request, identity, forwarded_allow_ips="127.0.0.1")
    # Key should contain the real IP, not the spoofed one
    assert "10.0.0.1" in key
    assert "203.0.113.99" not in key


# ---------------------------------------------------------------------------
# F53 — Paginator SSRF URL validation
# ---------------------------------------------------------------------------

def _make_cursor_paginator(cursor_fn):
    """Create a CursorBasedPaginator with the required base-class args mocked."""
    from maltego.pagination.cursor_based_paginator import CursorBasedPaginator
    from maltego.util import IntegrationClient

    mock_client = MagicMock(spec=IntegrationClient)
    mock_response_to_items = MagicMock()
    mock_response_to_total = MagicMock()

    class _TestPaginator(CursorBasedPaginator):
        def should_fetch_next_page(self, *args, **kwargs):
            return False

    return _TestPaginator(
        response_to_cursor=cursor_fn,
        client=mock_client,
        response_to_items=mock_response_to_items,
        response_to_total_cnt=mock_response_to_total,
        max_pages=10,
    )


def test_cursor_paginator_rejects_non_http_scheme():
    """CursorBasedPaginator raises ValueError for file:// next-page URLs."""
    from maltego.pagination.pagination import PaginationState

    paginator = _make_cursor_paginator(lambda r: "file:///etc/passwd")
    state = PaginationState(url="https://api.example.com/items")

    with pytest.raises(ValueError, match="disallowed scheme"):
        paginator.get_pagination_state_for_next_page(state, MagicMock())


def test_cursor_paginator_rejects_relative_url():
    """CursorBasedPaginator raises ValueError for relative (no netloc) next-page URLs.

    A path-only URL like /next/page parses with an empty scheme, which triggers the
    scheme check before the netloc check.  Either error message proves SSRF prevention.
    """
    from maltego.pagination.pagination import PaginationState

    paginator = _make_cursor_paginator(lambda r: "/next/page?token=abc")
    state = PaginationState(url="https://api.example.com/items")

    with pytest.raises(ValueError, match="disallowed scheme|no host/netloc"):
        paginator.get_pagination_state_for_next_page(state, MagicMock())


def test_cursor_paginator_accepts_https_url():
    """CursorBasedPaginator accepts valid https next-page URL."""
    from maltego.pagination.pagination import PaginationState

    paginator = _make_cursor_paginator(lambda r: "https://api.example.com/items?cursor=page2")
    state = PaginationState(url="https://api.example.com/items")

    result = paginator.get_pagination_state_for_next_page(state, MagicMock())
    assert result.url == "https://api.example.com/items?cursor=page2"


def test_cursor_paginator_accepts_http_url():
    """CursorBasedPaginator accepts valid http next-page URL."""
    from maltego.pagination.pagination import PaginationState

    paginator = _make_cursor_paginator(lambda r: "http://internal.service/items?page=2")
    state = PaginationState(url="http://internal.service/items")

    result = paginator.get_pagination_state_for_next_page(state, MagicMock())
    assert result.url == "http://internal.service/items?page=2"


# ---------------------------------------------------------------------------
# R2-5 — ETag random
# ---------------------------------------------------------------------------

def test_etag_middleware_uses_random_value_not_timestamp():
    """ETagMiddleware sets ETag from os.urandom, not from time.time()."""
    from maltego.server.etag_middleware import ETagMiddleware

    app_mock = MagicMock()
    with patch("maltego.server.etag_middleware.BaseHTTPMiddleware.__init__", return_value=None):
        middleware = ETagMiddleware(app_mock)

    etag = middleware.etag
    # Random hex from 16 bytes = 32 hex chars
    assert len(etag) == 32
    assert all(c in "0123456789abcdef" for c in etag)

    # Two instances must produce different ETags
    with patch("maltego.server.etag_middleware.BaseHTTPMiddleware.__init__", return_value=None):
        middleware2 = ETagMiddleware(app_mock)
    assert middleware.etag != middleware2.etag


# ---------------------------------------------------------------------------
# R2-6 — Generic 400 detail
# ---------------------------------------------------------------------------

def test_build_entity_map_returns_generic_400_on_missing_ids():
    """build_entity_map raises MaltegoHTTPInputEntityMalformed with generic message."""
    from maltego.server.v3 import build_entity_map
    from maltego.model.exception import MaltegoHTTPInputEntityMalformed

    entity_no_id = MagicMock()
    entity_no_id.id = None
    entity_no_id.properties = []

    with pytest.raises(MaltegoHTTPInputEntityMalformed) as exc_info:
        build_entity_map([entity_no_id])

    # Client sees generic message, not internal detail
    assert exc_info.value.detail == "Invalid request: malformed input entities"
    assert "None" not in exc_info.value.detail


def test_build_entity_map_returns_generic_400_on_duplicate_ids():
    """build_entity_map raises MaltegoHTTPInputEntityMalformed with generic message for dupes."""
    from maltego.server.v3 import build_entity_map
    from maltego.model.exception import MaltegoHTTPInputEntityMalformed

    def make_entity(eid):
        e = MagicMock()
        e.id = eid
        e.properties = []
        return e

    entities = [make_entity("id-1"), make_entity("id-1")]

    with pytest.raises(MaltegoHTTPInputEntityMalformed) as exc_info:
        build_entity_map(entities)

    assert exc_info.value.detail == "Invalid request: malformed input entities"
    # Entity ID must NOT be reflected in the client-facing error
    assert "id-1" not in exc_info.value.detail


# ---------------------------------------------------------------------------
# R3-1 — GET routes return 200 not 201: covered behaviourally in
# contracts/v3/test_v3_transform_execution.py
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# F33 — transform_id mismatch returns 404
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_transform_run_results_returns_404_on_transform_id_mismatch():
    """get_transform_run_results returns 404 when run_id belongs to a different transform."""
    from maltego.server.v3 import V3Server
    from maltego.model.types import ExecutionState

    v3 = V3Server.__new__(V3Server)

    # Mock a transform_result
    mock_result = MagicMock()
    mock_result.state = ExecutionState.RUNNING
    mock_result.get_current_duration.return_value = 100

    # Mock execution context that belongs to transform "other.ns.other-transform"
    # F33 check: build full transform ID as "{transform.ns}.{transform.name}" and compare
    mock_exec_ctx = MagicMock()
    mock_exec_ctx.transform.ns = "other.ns"
    mock_exec_ctx.transform.name = "other-transform"

    mock_runner = MagicMock()
    mock_runner.result.return_value = mock_result
    mock_runner.get_execution_context.return_value = mock_exec_ctx

    v3.transform_runner = mock_runner
    v3.transforms = {"my-transform": MagicMock()}
    v3._settings = MagicMock()
    v3._settings.v3_page_size_max = 100

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {}

    with pytest.raises(fastapi.HTTPException) as exc_info:
        await v3.get_transform_run_results(
            transform_id="my-transform",
            run_id="some-run-id",
            response=mock_response,
            event_pointer=0,
            event_limit=0,
            maltego_protocol_version=None,
            maltego_client_capabilities=MagicMock(),
            maltego_client_identifier=None,
            maltego_client_version=None,
            user_agent=None,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Transform run not found"


@pytest.mark.asyncio
async def test_delete_transform_run_returns_404_on_transform_id_mismatch():
    """delete_transform_run returns 404 (not 500) when run_id belongs to a different transform.

    Regression test: the F33 guard raises HTTPException(404) INSIDE the broad try
    block of delete_transform_run. Without an `except fastapi.HTTPException: raise`
    re-raise, the broad `except Exception` masks it as a 500. This asserts the 404
    actually propagates.
    """
    from maltego.server.v3 import V3Server
    from maltego.model.types import ExecutionState

    v3 = V3Server.__new__(V3Server)

    mock_result = MagicMock()
    mock_result.state = ExecutionState.RUNNING

    # Execution context belongs to a DIFFERENT transform than the path transform_id.
    mock_exec_ctx = MagicMock()
    mock_exec_ctx.transform.ns = "other.ns"
    mock_exec_ctx.transform.name = "other-transform"

    mock_runner = MagicMock()
    mock_runner.result.return_value = mock_result
    mock_runner.get_execution_context.return_value = mock_exec_ctx

    v3.transform_runner = mock_runner

    mock_request = MagicMock()
    mock_request.query_params = {}
    mock_response = MagicMock()
    mock_response.headers = {}

    with pytest.raises(fastapi.HTTPException) as exc_info:
        await v3.delete_transform_run(
            transform_id="my-transform",
            run_id="some-run-id",
            request=mock_request,
            response=mock_response,
            maltego_protocol_version=None,
        )

    # Must be the 404 from the F33 guard, NOT a 500 from the broad handler.
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Transform run not found"
    # Guard rejects before any mutating runner calls happen.
    mock_runner.cancel.assert_not_called()
    mock_runner.delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_transform_run_succeeds_on_matching_transform_id():
    """A delete with the correct transform_id for a valid run_id still succeeds."""
    from maltego.server.v3 import V3Server
    from maltego.model.types import ExecutionState

    v3 = V3Server.__new__(V3Server)

    mock_result = MagicMock()
    mock_result.state = ExecutionState.FINISHED
    mock_result.get_duration.return_value = 42

    # Execution context belongs to the SAME transform as the path transform_id.
    mock_exec_ctx = MagicMock()
    mock_exec_ctx.transform.ns = "my.ns"
    mock_exec_ctx.transform.name = "my-transform"

    mock_runner = MagicMock()
    mock_runner.result.return_value = mock_result
    mock_runner.get_execution_context.return_value = mock_exec_ctx
    mock_runner.response_headers.return_value = {}
    mock_runner.output_entities.return_value = []

    v3.transform_runner = mock_runner

    mock_request = MagicMock()
    mock_request.query_params = {}
    mock_response = MagicMock()
    mock_response.headers = {}

    result = await v3.delete_transform_run(
        transform_id="my.ns.my-transform",
        run_id="some-run-id",
        request=mock_request,
        response=mock_response,
        maltego_protocol_version=None,
    )

    assert result.run_id == "some-run-id"
    assert result.state == ExecutionState.FINISHED.value
    mock_runner.cancel.assert_called_once_with("some-run-id")
    mock_runner.delete.assert_called_once_with("some-run-id")


@pytest.mark.asyncio
async def test_cancel_transform_run_returns_404_on_transform_id_mismatch():
    """cancel_transform_run returns 404 (not 500) when run_id belongs to a different transform.

    Regression test: cancel_transform_run must apply the same F33 transform_id<->run_id
    guard as delete_transform_run / get_transform_run_results, with the same
    `except fastapi.HTTPException: raise` re-raise so the 404 isn't masked as a 500.
    """
    from maltego.server.v3 import V3Server
    from maltego.model.types import ExecutionState

    v3 = V3Server.__new__(V3Server)

    mock_result = MagicMock()
    mock_result.state = ExecutionState.RUNNING

    # Execution context belongs to a DIFFERENT transform than the path transform_id.
    mock_exec_ctx = MagicMock()
    mock_exec_ctx.transform.ns = "other.ns"
    mock_exec_ctx.transform.name = "other-transform"

    mock_runner = MagicMock()
    mock_runner.result.return_value = mock_result
    mock_runner.get_execution_context.return_value = mock_exec_ctx

    v3.transform_runner = mock_runner

    mock_request = MagicMock()
    mock_response = MagicMock()
    mock_response.headers = {}

    with pytest.raises(fastapi.HTTPException) as exc_info:
        await v3.cancel_transform_run(
            transform_id="my-transform",
            run_id="some-run-id",
            request=mock_request,
            response=mock_response,
            maltego_protocol_version=None,
            maltego_client_capabilities=MagicMock(),
        )

    # Must be the 404 from the F33 guard, NOT a 500 from the broad handler.
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Could not find transform run with id some-run-id"
    # Guard rejects before any mutating runner calls happen.
    mock_runner.cancel.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_transform_run_succeeds_on_matching_transform_id():
    """A cancel with the correct transform_id for a valid run_id still succeeds,
    and never calls delete (the whole point of the cancel-without-delete endpoint)."""
    from maltego.server.v3 import V3Server
    from maltego.model.types import ExecutionState

    v3 = V3Server.__new__(V3Server)

    mock_result = MagicMock()
    mock_result.state = ExecutionState.RUNNING
    mock_result.get_duration.return_value = 42
    mock_result.atomic_entity_count = 1
    mock_result.composite_entity_count = 0

    # Execution context belongs to the SAME transform as the path transform_id.
    mock_exec_ctx = MagicMock()
    mock_exec_ctx.transform.ns = "my.ns"
    mock_exec_ctx.transform.name = "my-transform"

    mock_runner = MagicMock()
    mock_runner.result.return_value = mock_result
    mock_runner.get_execution_context.return_value = mock_exec_ctx
    mock_runner.response_headers.return_value = {}
    mock_runner.output_entities.return_value = []

    v3.transform_runner = mock_runner

    mock_request = MagicMock()
    mock_response = MagicMock()
    mock_response.headers = {}

    result = await v3.cancel_transform_run(
        transform_id="my.ns.my-transform",
        run_id="some-run-id",
        request=mock_request,
        response=mock_response,
        maltego_protocol_version=None,
        maltego_client_capabilities=MagicMock(),
    )

    assert result.run_id == "some-run-id"
    assert result.state == ExecutionState.CANCELED.value
    mock_runner.cancel.assert_called_once_with("some-run-id")
    mock_runner.delete.assert_not_called()


# ---------------------------------------------------------------------------
# F25/F70 — Docs/OpenAPI auth gating (structural check)
# ---------------------------------------------------------------------------

def _build_real_server(swagger_enabled: bool):
    """Build a real MaltegoTransformServer through the actual setup() path (no
    shortcuts like openapi_url=None) so route registration behaves exactly as
    it does in production. That FastAPI-default-route sidestep was the bug that
    made the old tests give a false pass: it prevented FastAPI from ever
    registering its own unauthenticated /openapi.json route, so the tests could
    not detect whether _configure_openapi actually replaced/stripped it.
    """
    from maltego.model.server import MaltegoServerSettings
    from maltego.server import MaltegoTransformServer

    settings = MaltegoServerSettings(
        server_name="pytest",
        ns="pytest",
        author="pytest",
        swagger_enabled=swagger_enabled,
    )
    server = MaltegoTransformServer(settings=settings)
    server.setup(settings)
    return server


def _find_route(app, path: str):
    for route in app.routes:
        if getattr(route, "path", None) == path:
            return route
    return None


def test_swagger_disabled_by_default_no_openapi_route_resolves():
    """F25/F70 — with swagger_enabled=False (the default), /openapi.json must not
    resolve on the built app at all, including FastAPI's own built-in route."""
    from starlette.testclient import TestClient

    server = _build_real_server(swagger_enabled=False)
    try:
        assert _find_route(server.app, "/openapi.json") is None
        assert _find_route(server.app, "/swagger") is None

        client = TestClient(server.app)
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/swagger").status_code == 404
    finally:
        server.runner.shutdown()


def test_swagger_enabled_registers_openapi_and_swagger_with_auth_dependency():
    """F25/F70 — with swagger_enabled=True, both /openapi.json and /swagger exist
    and carry the optional_auth FastAPI dependency in their dependencies list."""
    from fastapi.routing import APIRoute
    from maltego.auth import optional_auth

    server = _build_real_server(swagger_enabled=True)
    try:
        openapi_route = _find_route(server.app, "/openapi.json")
        swagger_route = _find_route(server.app, "/swagger")

        assert isinstance(openapi_route, APIRoute)
        assert isinstance(swagger_route, APIRoute)

        for route in (openapi_route, swagger_route):
            assert route.dependencies, f"Expected auth dependencies on {route.path}"
            dependency_callables = [dep.dependency for dep in route.dependencies]
            assert optional_auth in dependency_callables, (
                f"Expected optional_auth dependency on {route.path}, got {dependency_callables}"
            )
    finally:
        server.runner.shutdown()
