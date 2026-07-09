import re
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from maltego.util.trace_context import TRACEPARENT_VAR

# W3C traceparent format: version(2 hex)-trace_id(32 hex)-parent_id(16 hex)-flags(2 hex).
# Inbound headers are validated against this before being trusted, since the value
# is placed into the TRACEPARENT_VAR ContextVar and ends up in log lines — an
# unvalidated header would be a log/SIEM injection vector (e.g. CRLF or pipe
# characters smuggled into structured logs).
_TRACEPARENT_RE = re.compile(r"^[0-9a-f]{2}-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")


class TraceparentMiddleware(BaseHTTPMiddleware):
    """Middleware that stores the W3C traceparent for the current request in a
    ``ContextVar`` so that log formatters can include it.

    Every request is guaranteed to have a traceparent:

    1. When OpenTelemetry is active the OTEL middleware (added outermost by
       :func:`~maltego.tracing.setup_tracing`) will have already created and
       activated a span by the time this middleware runs. The active span's
       context is preferred, ensuring log entries always reflect the same
       trace-id that OTEL reports—including when OTEL generates a brand-new
       trace with no incoming ``traceparent`` header.
    2. When OTEL is not active, the incoming ``traceparent`` header is used.
    3. When neither is present a valid W3C traceparent is generated so that
       every log line for the request carries a consistent trace-id.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        traceparent = (
            self._traceparent_from_otel()
            or self._valid_inbound_traceparent(request)
            or _generate_traceparent()
        )
        TRACEPARENT_VAR.set(traceparent)
        return await call_next(request)

    @staticmethod
    def _valid_inbound_traceparent(request: Request) -> "str | None":
        """Return the inbound ``traceparent`` header only if it matches the strict
        W3C format. Malformed values (including ones carrying CRLF or other
        control/delimiter characters) are rejected so they can never reach log
        lines via ``TRACEPARENT_VAR`` — falling through to a freshly generated
        traceparent instead."""
        header_value = request.headers.get("traceparent")
        if header_value and _TRACEPARENT_RE.match(header_value):
            return header_value
        return None

    @staticmethod
    def _traceparent_from_otel() -> "str | None":
        """Return a W3C traceparent string derived from the active OTEL span,
        or ``None`` when OTEL is not installed / no span is active."""
        try:
            from opentelemetry import trace as otel_trace
            ctx = otel_trace.get_current_span().get_span_context()
            if ctx.is_valid:
                return f"00-{ctx.trace_id:032x}-{ctx.span_id:016x}-{ctx.trace_flags:02x}"
        except ImportError:
            pass
        return None


def _generate_traceparent() -> str:
    """Generate a fresh W3C traceparent (sampled, flags=01)."""
    return f"00-{secrets.token_hex(16)}-{secrets.token_hex(8)}-01"
