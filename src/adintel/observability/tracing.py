"""OpenTelemetry tracing. A no-op tracer unless ``ADINTEL_OTEL_ENDPOINT`` is set (Jaeger locally)."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode

from adintel.observability import context

_configured = False


def configure_tracing(service_name: str, endpoint: str | None) -> None:
    global _configured
    if _configured or not endpoint:
        return
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces")))
    trace.set_tracer_provider(provider)
    _configured = True


def tracer() -> trace.Tracer:
    return trace.get_tracer("adintel")


@contextlib.contextmanager
def span(name: str, **attributes: Any) -> Iterator[Span]:
    attrs = {
        **{f"adintel.{k}": v for k, v in context.current().items()},
        **{k: v for k, v in attributes.items() if v is not None},
    }
    with tracer().start_as_current_span(name, attributes={k: str(v) for k, v in attrs.items()}) as s:
        try:
            yield s
        except Exception as exc:
            s.set_status(Status(StatusCode.ERROR, str(exc)[:200]))
            raise


def current_trace_id() -> str | None:
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx.is_valid else None
