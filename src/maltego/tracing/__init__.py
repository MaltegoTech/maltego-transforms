# Copyright (c) Maltego Technologies GmbH.
"""
Generic OpenTelemetry tracing support for Maltego transform servers.

This module provides a provider-agnostic tracing setup. You supply a configured
``TracerProvider`` (with your chosen exporter) and this module handles:

- Setting it as the global OTEL provider
- Registering W3C TraceContext, B3 and W3C Baggage propagators
- Instrumenting the FastAPI app with OTEL HTTP spans

Requires the ``tracing`` optional extra::

    pip install maltego-transforms[tracing]

Example usage with an OTLP exporter::

    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))

    run_server(settings=..., tracer_provider=provider)

Example usage with Azure Monitor::

    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter

    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(AzureMonitorTraceExporter()))

    run_server(settings=..., tracer_provider=provider)
"""
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import fastapi
    from opentelemetry.sdk.trace import TracerProvider

logger = logging.getLogger(__name__)

try:
    from opentelemetry import trace
    from opentelemetry.baggage.propagation import W3CBaggagePropagator
    from opentelemetry.propagate import set_global_textmap
    from opentelemetry.propagators.composite import CompositePropagator
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    _OTEL_API_AVAILABLE = True
except ImportError:
    _OTEL_API_AVAILABLE = False


def setup_tracing(
    app: "fastapi.FastAPI",
    tracer_provider: "TracerProvider",
    excluded_urls: Optional[str] = None,
) -> None:
    """Configure OpenTelemetry tracing for a Maltego transform server.

    Sets the given provider as the global OTEL tracer provider, registers
    W3C TraceContext, W3C Baggage and B3 propagators, and instruments the
    FastAPI application so that every HTTP request produces a span.

    This function is a no-op (with a warning) when the ``tracing`` extra is
    not installed.

    :param app: The FastAPI application instance to instrument.
    :type app: fastapi.FastAPI
    :param tracer_provider: A fully-configured ``TracerProvider``.
        Add your ``SpanProcessor`` / exporter to it before passing it here.
    :type tracer_provider: opentelemetry.sdk.trace.TracerProvider
    :param excluded_urls: Comma-separated list of URL patterns to exclude from
        tracing (forwarded to the FastAPI instrumentor). Example:
        ``"/health,/metrics"``.
    :type excluded_urls: str, optional
    """
    if not _OTEL_API_AVAILABLE:
        logger.warning(
            "tracer_provider was provided but the OpenTelemetry packages are not "
            "installed. Install maltego-transforms[tracing] to enable OTEL support."
        )
        return

    # Register the provider globally so any library using `opentelemetry.trace`
    # will automatically pick it up.
    trace.set_tracer_provider(tracer_provider)

    # Build composite propagator: W3C TraceContext + W3C Baggage are always
    # registered. B3 is added when its package is available (common in
    # environments that mix Zipkin/Jaeger tooling with W3C).
    propagators = [
        TraceContextTextMapPropagator(),
        W3CBaggagePropagator(),
    ]
    try:
        from opentelemetry.propagators.b3 import B3MultiFormat
        propagators.append(B3MultiFormat())
        logger.debug("OpenTelemetry: B3 propagator registered")
    except ImportError:
        logger.debug(
            "opentelemetry-propagator-b3 not installed; B3 propagation disabled"
        )

    set_global_textmap(CompositePropagator(propagators))

    # Instrument FastAPI — creates a span per HTTP request automatically.
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls=excluded_urls,
            tracer_provider=tracer_provider,
        )
        logger.info(
            "OpenTelemetry tracing enabled: provider=%s%s",
            type(tracer_provider).__name__,
            f", excluded_urls={excluded_urls!r}" if excluded_urls else "",
        )
    except ImportError:
        logger.warning(
            "opentelemetry-instrumentation-fastapi not installed; "
            "HTTP spans will not be created. "
            "Install maltego-transforms[tracing] for full instrumentation."
        )


__all__ = ["setup_tracing"]
