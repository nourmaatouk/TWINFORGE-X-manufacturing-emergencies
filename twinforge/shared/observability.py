"""
TWINFORGE Observability
OpenTelemetry tracing setup and Prometheus metric definitions.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Prometheus Metrics (lazy imports) ────────────────────────────────────────

_metrics_initialized = False
_REQUEST_COUNTER = None
_REQUEST_DURATION = None
_SECURITY_EVENTS = None


def _init_metrics() -> None:
    """Initialize Prometheus metrics (idempotent)."""
    global _metrics_initialized, _REQUEST_COUNTER, _REQUEST_DURATION, _SECURITY_EVENTS
    if _metrics_initialized:
        return
    try:
        from prometheus_client import Counter, Histogram

        _REQUEST_COUNTER = Counter(
            "twinforge_requests_total",
            "Total requests processed",
            ["agent", "endpoint", "status"],
        )
        _REQUEST_DURATION = Histogram(
            "twinforge_request_duration_seconds",
            "Request processing duration",
            ["agent", "endpoint"],
        )
        _SECURITY_EVENTS = Counter(
            "twinforge_security_events_total",
            "Total security events detected",
            ["agent", "event_type", "severity"],
        )
        _metrics_initialized = True
        logger.info("Prometheus metrics initialized")
    except ImportError:
        logger.warning("prometheus_client not installed, metrics disabled")


def get_request_counter():
    _init_metrics()
    return _REQUEST_COUNTER


def get_request_duration():
    _init_metrics()
    return _REQUEST_DURATION


def get_security_events_counter():
    _init_metrics()
    return _SECURITY_EVENTS


# ─── OpenTelemetry Tracing ────────────────────────────────────────────────────

_tracer = None


def setup_tracing(
    service_name: str,
    otel_endpoint: Optional[str] = None,
) -> None:
    """Set up OpenTelemetry tracing with OTLP exporter."""
    global _tracer
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)

        if otel_endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            exporter = OTLPSpanExporter(endpoint=otel_endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(service_name)
        logger.info("OpenTelemetry tracing configured for %s", service_name)
    except ImportError:
        logger.warning("OpenTelemetry packages not installed, tracing disabled")


def get_tracer():
    """Return the configured tracer or None."""
    return _tracer
