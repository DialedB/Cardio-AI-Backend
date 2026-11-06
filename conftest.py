"""Check local observability services before test modules initialize exporters."""

import os
import socket
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env.local")
load_dotenv(PROJECT_ROOT / "ai" / ".env.local", override=False)
load_dotenv(PROJECT_ROOT / "ai" / ".env", override=False)


def _grafana_is_up():
    health_url = os.getenv(
        "GRAFANA_HEALTH_URL", "http://127.0.0.1:3000/api/health"
    )
    try:
        with urlopen(health_url, timeout=1) as response:
            return response.status == 200
    except (OSError, URLError, TimeoutError, ValueError):
        return False


def _otel_collector_is_up():
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317")
    parsed = urlsplit(endpoint)
    if not parsed.hostname:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 4317)
    try:
        with socket.create_connection((parsed.hostname, port), timeout=1):
            return True
    except (OSError, TimeoutError, ValueError):
        return False


def pytest_sessionstart(session):
    """Probe Grafana and its OTLP intake before tests can import the RAG module."""
    grafana_up = _grafana_is_up()
    collector_up = _otel_collector_is_up()
    explicitly_disabled = os.getenv("CARDIO_RAG_TELEMETRY_DISABLED", "").lower() in {
        "1",
        "true",
        "yes",
    }
    telemetry_enabled = grafana_up and collector_up and not explicitly_disabled
    os.environ["CARDIO_RAG_TELEMETRY_DISABLED"] = "false" if telemetry_enabled else "true"
    session.config._cardio_observability_status = (
        f"Grafana={'up' if grafana_up else 'down'}, "
        f"OTLP Collector={'up' if collector_up else 'down'}, "
        f"telemetry exports={'enabled' if telemetry_enabled else 'disabled'}"
    )


def pytest_report_header(config):
    return getattr(config, "_cardio_observability_status", None)
