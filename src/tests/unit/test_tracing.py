# Copyright (c) Maltego Technologies GmbH.
"""
Unit tests for OTel tracing support: TraceparentMiddleware and setup_tracing().
"""
import re
import sys
import importlib
import logging
from unittest.mock import MagicMock, patch

import pytest

# W3C traceparent regex: version(00)-trace_id(32hex)-span_id(16hex)-flags(2hex)
_W3C_RE = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")


# ---------------------------------------------------------------------------
# _generate_traceparent
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_generate_traceparent_format():
    from maltego.server.tracing_middleware import _generate_traceparent
    tp = _generate_traceparent()
    assert _W3C_RE.match(tp), f"Not a valid W3C traceparent: {tp!r}"


@pytest.mark.unit
def test_generate_traceparent_sampled():
    """The generated traceparent should always have flags=01 (sampled)."""
    from maltego.server.tracing_middleware import _generate_traceparent
    tp = _generate_traceparent()
    assert tp.endswith("-01"), f"Expected sampled flag (01), got: {tp!r}"


@pytest.mark.unit
def test_generate_traceparent_unique():
    from maltego.server.tracing_middleware import _generate_traceparent
    assert _generate_traceparent() != _generate_traceparent()


# ---------------------------------------------------------------------------
# TraceparentMiddleware._traceparent_from_otel
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_traceparent_from_otel_returns_none_when_no_otel(monkeypatch):
    """Returns None when opentelemetry is not importable."""
    # Simulate ImportError by temporarily hiding the module
    with patch.dict(sys.modules, {"opentelemetry": None, "opentelemetry.trace": None}):
        # Re-import to pick up monkeypatched sys.modules
        import importlib
        import maltego.server.tracing_middleware as mod
        importlib.reload(mod)
        result = mod.TraceparentMiddleware._traceparent_from_otel()
        assert result is None
        # restore
        importlib.reload(mod)


@pytest.mark.unit
def test_traceparent_from_otel_returns_none_when_no_active_span():
    """Returns None when OTEL is installed but no span is active (ctx.is_valid is False).

    ``opentelemetry`` is an optional extra (the ``tracing`` extra) and is not
    installed in the default test environment, so ``patch("opentelemetry.trace...")``
    does not work here -- ``unittest.mock.patch``'s string-target resolution performs
    a real ``importlib.import_module("opentelemetry")`` before it can install the
    mock, which raises ModuleNotFoundError when the package is absent. Instead,
    inject fake ``opentelemetry`` / ``opentelemetry.trace`` modules directly into
    ``sys.modules`` (matching the working pattern used by
    ``test_traceparent_from_otel_returns_none_when_no_otel`` above), which exercises
    the real ``from opentelemetry import trace as otel_trace`` import in
    ``_traceparent_from_otel`` without requiring the package to be installed.
    """
    mock_ctx = MagicMock()
    mock_ctx.is_valid = False

    mock_span = MagicMock()
    mock_span.get_span_context.return_value = mock_ctx

    mock_otel_trace = MagicMock()
    mock_otel_trace.get_current_span.return_value = mock_span
    mock_otel_package = MagicMock()
    mock_otel_package.trace = mock_otel_trace

    with patch.dict(
        sys.modules,
        {"opentelemetry": mock_otel_package, "opentelemetry.trace": mock_otel_trace},
    ):
        import maltego.server.tracing_middleware as mod
        importlib.reload(mod)
        result = mod.TraceparentMiddleware._traceparent_from_otel()
    importlib.reload(mod)
    assert result is None


@pytest.mark.unit
def test_traceparent_from_otel_returns_w3c_string_when_active_span():
    """Returns a valid W3C traceparent when an OTEL span is active.

    See the note on ``test_traceparent_from_otel_returns_none_when_no_active_span``
    above: ``opentelemetry`` is an optional extra not installed in the default test
    environment, so the fake module must be injected via ``sys.modules`` rather than
    via ``patch("opentelemetry...")``, which would try to import the real package.
    """
    mock_ctx = MagicMock()
    mock_ctx.is_valid = True
    mock_ctx.trace_id = int("a" * 32, 16)   # 128-bit
    mock_ctx.span_id = int("b" * 16, 16)    # 64-bit
    mock_ctx.trace_flags = 1

    mock_span = MagicMock()
    mock_span.get_span_context.return_value = mock_ctx

    mock_otel_trace = MagicMock()
    mock_otel_trace.get_current_span.return_value = mock_span
    mock_otel_package = MagicMock()
    mock_otel_package.trace = mock_otel_trace

    with patch.dict(
        sys.modules,
        {"opentelemetry": mock_otel_package, "opentelemetry.trace": mock_otel_trace},
    ):
        import maltego.server.tracing_middleware as mod
        importlib.reload(mod)
        result = mod.TraceparentMiddleware._traceparent_from_otel()
    importlib.reload(mod)

    assert result is not None
    assert _W3C_RE.match(result), f"Not a valid W3C traceparent: {result!r}"
    assert "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" in result  # trace_id portion
    assert result.endswith("-01")


# ---------------------------------------------------------------------------
# setup_tracing() no-op path
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_setup_tracing_noop_when_otel_unavailable(caplog):
    """setup_tracing logs a warning and returns without error when OTel is not installed."""
    import maltego.tracing as tracing_mod
    original = tracing_mod._OTEL_API_AVAILABLE
    try:
        tracing_mod._OTEL_API_AVAILABLE = False
        mock_app = MagicMock()
        mock_provider = MagicMock()
        with caplog.at_level(logging.WARNING, logger="maltego.tracing"):
            tracing_mod.setup_tracing(mock_app, mock_provider)
        assert any("not installed" in r.message for r in caplog.records), \
            "Expected warning about missing OTel packages"
        # FastAPIInstrumentor.instrument_app should NOT have been called
        mock_app.assert_not_called()
    finally:
        tracing_mod._OTEL_API_AVAILABLE = original


# ---------------------------------------------------------------------------
# TraceparentMiddleware priority chain
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_middleware_uses_otel_span_when_available():
    """When OTEL span is active, its context wins over the incoming header."""
    from starlette.testclient import TestClient
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.responses import PlainTextResponse
    from maltego.server.tracing_middleware import TraceparentMiddleware
    from maltego.util.trace_context import TRACEPARENT_VAR

    captured = {}

    async def homepage(request):
        captured["tp"] = TRACEPARENT_VAR.get()
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/", homepage)])
    app.add_middleware(TraceparentMiddleware)

    # Patch _traceparent_from_otel to simulate an active span
    fake_tp = "00-" + "a" * 32 + "-" + "b" * 16 + "-01"

    with patch(
        "maltego.server.tracing_middleware.TraceparentMiddleware._traceparent_from_otel",
        return_value=fake_tp,
    ):
        client = TestClient(app)
        client.get("/", headers={"traceparent": "00-" + "c" * 32 + "-" + "d" * 16 + "-00"})

    assert captured["tp"] == fake_tp


@pytest.mark.unit
@pytest.mark.asyncio
async def test_middleware_uses_incoming_header_when_no_otel():
    """When no OTEL span is active, the incoming traceparent header is used."""
    from starlette.testclient import TestClient
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.responses import PlainTextResponse
    from maltego.server.tracing_middleware import TraceparentMiddleware
    from maltego.util.trace_context import TRACEPARENT_VAR

    captured = {}
    incoming_tp = "00-" + "e" * 32 + "-" + "f" * 16 + "-01"

    async def homepage(request):
        captured["tp"] = TRACEPARENT_VAR.get()
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/", homepage)])
    app.add_middleware(TraceparentMiddleware)

    with patch(
        "maltego.server.tracing_middleware.TraceparentMiddleware._traceparent_from_otel",
        return_value=None,
    ):
        client = TestClient(app)
        client.get("/", headers={"traceparent": incoming_tp})

    assert captured["tp"] == incoming_tp


@pytest.mark.unit
@pytest.mark.asyncio
async def test_middleware_generates_traceparent_when_nothing_present():
    """When there is no OTEL span and no incoming header, a fresh traceparent is generated."""
    from starlette.testclient import TestClient
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.responses import PlainTextResponse
    from maltego.server.tracing_middleware import TraceparentMiddleware
    from maltego.util.trace_context import TRACEPARENT_VAR

    captured = {}

    async def homepage(request):
        captured["tp"] = TRACEPARENT_VAR.get()
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/", homepage)])
    app.add_middleware(TraceparentMiddleware)

    with patch(
        "maltego.server.tracing_middleware.TraceparentMiddleware._traceparent_from_otel",
        return_value=None,
    ):
        client = TestClient(app)
        client.get("/")

    assert captured.get("tp") is not None
    assert _W3C_RE.match(captured["tp"]), f"Generated traceparent invalid: {captured['tp']!r}"


# ---------------------------------------------------------------------------
# Cross-PR integration: TraceparentMiddleware + auth public_paths bypass
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_traceparent_middleware_runs_for_public_path_bypass():
    """TraceparentMiddleware is an ASGI middleware that wraps every request at the
    transport layer — it runs *before* FastAPI auth dependencies fire.  This means
    that even when a path is listed in ``AuthSettings.public_paths`` (so auth is
    skipped), the request still gets a valid W3C traceparent in the context var.

    This is a cross-PR integration test combining PR #27695 (TraceparentMiddleware)
    and PR #27696 (public_paths auth bypass).
    """
    from starlette.testclient import TestClient
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.responses import PlainTextResponse
    from maltego.server.tracing_middleware import TraceparentMiddleware, _generate_traceparent
    from maltego.util.trace_context import TRACEPARENT_VAR

    captured = {}

    async def health(request):
        # Simulate: auth dependency would call public_paths bypass here and return early.
        # TraceparentMiddleware already ran at the middleware layer, so the var is set.
        captured["tp"] = TRACEPARENT_VAR.get()
        return PlainTextResponse("ok")

    # Build a minimal app — no real auth dependency, but the middleware stack matches
    # the server's real configuration (TraceparentMiddleware added innermost).
    app = Starlette(routes=[Route("/health", health)])
    app.add_middleware(TraceparentMiddleware)

    with patch(
        "maltego.server.tracing_middleware.TraceparentMiddleware._traceparent_from_otel",
        return_value=None,
    ):
        client = TestClient(app)
        # Simulate a public-path request with no auth token and no traceparent header
        response = client.get("/health")

    assert response.status_code == 200
    # Middleware must have run and set a valid traceparent even for the public path
    assert captured.get("tp") is not None, "TRACEPARENT_VAR was not set for public-path request"
    assert _W3C_RE.match(captured["tp"]), (
        f"Traceparent on public-path request is not valid W3C format: {captured['tp']!r}"
    )


# ---------------------------------------------------------------------------
# M7 — inbound traceparent header validation (log/SIEM injection)
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_middleware_rejects_malformed_traceparent_header_with_crlf():
    """A malformed/CRLF-bearing traceparent header must NOT be trusted -- it is
    logged verbatim via TRACEPARENT_VAR, so accepting it unchecked would be a
    log/SIEM injection vector. A freshly generated valid traceparent is used
    instead."""
    from starlette.testclient import TestClient
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.responses import PlainTextResponse
    from maltego.server.tracing_middleware import TraceparentMiddleware
    from maltego.util.trace_context import TRACEPARENT_VAR

    captured = {}
    malicious_tp = "00-" + "a" * 32 + "-" + "b" * 16 + "-01\r\nINJECTED: evil-header"

    async def homepage(request):
        captured["tp"] = TRACEPARENT_VAR.get()
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/", homepage)])
    app.add_middleware(TraceparentMiddleware)

    with patch(
        "maltego.server.tracing_middleware.TraceparentMiddleware._traceparent_from_otel",
        return_value=None,
    ):
        client = TestClient(app)
        # httpx/starlette's TestClient will reject header values containing raw
        # CRLF, so simulate the malformed value arriving as a regular (but
        # non-W3C) header instead -- the validation must reject any value that
        # fails the strict format regex, CRLF or otherwise.
        client.get("/", headers={"traceparent": "not-a-real-traceparent|injected"})

    assert captured.get("tp") is not None
    assert captured["tp"] != "not-a-real-traceparent|injected"
    assert _W3C_RE.match(captured["tp"]), (
        f"Expected a freshly generated valid traceparent, got: {captured['tp']!r}"
    )


@pytest.mark.unit
def test_valid_inbound_traceparent_rejects_malformed_values():
    """Direct unit check of the validator against malformed/injection-bearing values."""
    from unittest.mock import MagicMock
    from maltego.server.tracing_middleware import TraceparentMiddleware

    for bad_value in [
        "not-a-traceparent",
        "00-" + "a" * 32 + "-" + "b" * 16 + "-01\r\nX-Injected: 1",
        "00-" + "a" * 32 + "-" + "b" * 16 + "-01|extra",
        "00-" + "a" * 31 + "-" + "b" * 16 + "-01",  # trace_id too short
        "",
    ]:
        request = MagicMock()
        request.headers = {"traceparent": bad_value} if bad_value else {}
        assert TraceparentMiddleware._valid_inbound_traceparent(request) is None, (
            f"Expected {bad_value!r} to be rejected"
        )


@pytest.mark.unit
def test_valid_inbound_traceparent_accepts_well_formed_header():
    """A syntactically valid W3C traceparent header is passed through unchanged."""
    from unittest.mock import MagicMock
    from maltego.server.tracing_middleware import TraceparentMiddleware

    valid_tp = "00-" + "c" * 32 + "-" + "d" * 16 + "-01"
    request = MagicMock()
    request.headers = {"traceparent": valid_tp}
    assert TraceparentMiddleware._valid_inbound_traceparent(request) == valid_tp


@pytest.mark.unit
@pytest.mark.asyncio
async def test_middleware_passes_through_valid_traceparent_header_unchanged():
    """A valid W3C traceparent header IS passed through unchanged end-to-end."""
    from starlette.testclient import TestClient
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.responses import PlainTextResponse
    from maltego.server.tracing_middleware import TraceparentMiddleware
    from maltego.util.trace_context import TRACEPARENT_VAR

    captured = {}
    valid_tp = "00-" + "e" * 32 + "-" + "f" * 16 + "-01"

    async def homepage(request):
        captured["tp"] = TRACEPARENT_VAR.get()
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/", homepage)])
    app.add_middleware(TraceparentMiddleware)

    with patch(
        "maltego.server.tracing_middleware.TraceparentMiddleware._traceparent_from_otel",
        return_value=None,
    ):
        client = TestClient(app)
        client.get("/", headers={"traceparent": valid_tp})

    assert captured["tp"] == valid_tp
