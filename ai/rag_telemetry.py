"""OpenTelemetry setup and helpers for the standalone RAG pipeline."""

import json
import logging
import os
import time
import traceback
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.parse import urlsplit

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode

resource = Resource.create(
    {
        "service.name": os.getenv("OTEL_SERVICE_NAME", "cardio-rag"),
        "service.version": os.getenv("APP_VERSION", "unknown"),
        "app.environment": os.getenv("APP_ENVIRONMENT", os.getenv("APP_ENV", "dev")),
        "app.owner": "AI-Team",
        "telemetry.sdk.language": "python",
        "telemetry.sdk.name": "opentelemetry",
    }
)
OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317")
OTLP_INSECURE = urlsplit(OTLP_ENDPOINT).scheme == "http"
TELEMETRY_EXPORTS_ENABLED = os.getenv("CARDIO_RAG_TELEMETRY_DISABLED", "").lower() not in {
    "1",
    "true",
    "yes",
}

tracer_provider = TracerProvider(resource=resource)
trace.set_tracer_provider(tracer_provider)
tracer = trace.get_tracer(__name__)
if TELEMETRY_EXPORTS_ENABLED:
    trace_exporter = OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=OTLP_INSECURE)
    tracer_provider.add_span_processor(BatchSpanProcessor(trace_exporter))

metric_readers = []
if TELEMETRY_EXPORTS_ENABLED:
    metric_exporter = OTLPMetricExporter(endpoint=OTLP_ENDPOINT, insecure=OTLP_INSECURE)
    metric_readers.append(
        PeriodicExportingMetricReader(
            metric_exporter,
            export_interval_millis=int(os.getenv("OTEL_METRIC_EXPORT_INTERVAL_MS", "5000")),
        )
    )
meter_provider = MeterProvider(resource=resource, metric_readers=metric_readers)
metrics.set_meter_provider(meter_provider)
meter = metrics.get_meter(__name__)

request_counter = meter.create_counter(
    "rag.requests", unit="{request}", description="RAG requests by terminal result"
)
request_duration = meter.create_histogram(
    "rag.request.duration", unit="ms", description="End-to-end RAG request duration"
)
operation_duration = meter.create_histogram(
    "rag.operation.duration", unit="ms", description="Duration of RAG operations"
)
retrieved_documents_counter = meter.create_counter(
    "rag.retrieved.documents",
    unit="{document}",
    description=(
        "Search result documents returned across all query variations; documents may repeat"
    ),
)
fused_documents_counter = meter.create_counter(
    "rag.fused.documents", unit="{document}", description="Unique documents after rank fusion"
)
selected_documents_counter = meter.create_counter(
    "rag.selected.documents", unit="{document}", description="Documents selected for answer context"
)
llm_request_counter = meter.create_counter(
    "rag.llm.requests", unit="{request}", description="LLM requests by operation"
)
llm_input_tokens = meter.create_counter(
    "rag.llm.input.tokens", unit="{token}", description="Input tokens reported by the LLM provider"
)
llm_output_tokens = meter.create_counter(
    "rag.llm.output.tokens",
    unit="{token}",
    description="Output tokens reported by the LLM provider",
)
operation_error_counter = meter.create_counter(
    "rag.operation.errors", unit="{error}", description="RAG operations that raised an exception"
)
request_result_context = ContextVar("rag_request_result", default="answered")


@contextmanager
def observe_operation(span_name: str, operation: str, *, is_llm: bool = False):
    """Trace an operation and record latency and failures on every exit path."""
    started = time.perf_counter()
    attributes = {"operation": operation}
    with tracer.start_as_current_span(span_name) as span:
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, f"{operation} failed"))
            operation_error_counter.add(1, attributes)
            raise
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            span.set_attribute("operation.duration_ms", duration_ms)
            operation_duration.record(duration_ms, attributes)
            if is_llm:
                llm_request_counter.add(1, attributes)


def record_llm_usage(result, operation: str) -> None:
    """Record provider-reported usage when the result exposes it."""
    usage = getattr(result, "usage_metadata", None) or {}
    if not isinstance(usage, dict):
        return
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if isinstance(input_tokens, int) and input_tokens >= 0:
        llm_input_tokens.add(input_tokens, {"operation": operation})
    if isinstance(output_tokens, int) and output_tokens >= 0:
        llm_output_tokens.add(output_tokens, {"operation": operation})


def set_request_result(result: str) -> None:
    request_result_context.set(result)


def mark_span_error(span, description: str) -> None:
    """Set the OpenTelemetry error status on a span."""
    span.set_status(Status(StatusCode.ERROR, description))


logger_provider = LoggerProvider(resource=resource)
if TELEMETRY_EXPORTS_ENABLED:
    log_exporter = OTLPLogExporter(endpoint=OTLP_ENDPOINT, insecure=True)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))


class JSONFormatter(logging.Formatter):
    def format(self, record):
        span_context = trace.get_current_span().get_span_context()
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": span_context.trace_id if span_context.is_valid else None,
            "span_id": span_context.span_id if span_context.is_valid else None,
        }
        standard_fields = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName", "processName",
            "process", "message", "asctime",
        }
        log_record.update(
            {
                key: value
                for key, value in record.__dict__.items()
                if key not in standard_fields and not key.startswith("_")
            }
        )
        if record.exc_info:
            exception_type = record.exc_info[0]
            log_record["exception_type"] = (
                exception_type.__name__ if exception_type else "Exception"
            )
            log_record["exception_stacktrace"] = "".join(
                traceback.format_exception(*record.exc_info)
            )
        return json.dumps(log_record, default=str)


otel_handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
console_handler = logging.StreamHandler()
console_handler.setFormatter(JSONFormatter())
logger = logging.getLogger("cardio-rag")
logger.setLevel(logging.INFO)
logger.propagate = False
if not any(isinstance(handler, LoggingHandler) for handler in logger.handlers):
    logger.addHandler(otel_handler)
if not any(getattr(handler, "_cardio_rag_json", False) for handler in logger.handlers):
    console_handler._cardio_rag_json = True
    logger.addHandler(console_handler)


def shutdown_telemetry() -> None:
    """Flush and stop exporters after the interactive application exits."""
    for provider in (meter_provider, tracer_provider, logger_provider):
        try:
            provider.shutdown()
        except Exception:
            logger.exception("OpenTelemetry provider shutdown failed")
