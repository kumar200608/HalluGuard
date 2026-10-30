"""Observability — structured logging, audit trail, and in-memory metrics."""
from __future__ import annotations

import logging
import logging.config
import time
from collections import defaultdict
from typing import Any

from app.core.config import settings

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
        },
        "standard": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
    },
    "root": {
        "level": settings.log_level,
        "handlers": ["console"],
    },
}


def setup_logging() -> None:
    try:
        logging.config.dictConfig(LOGGING_CONFIG)
    except Exception:
        logging.basicConfig(level=settings.log_level)


# ---------------------------------------------------------------------------
# In-memory metrics (swap for Prometheus client in production)
# ---------------------------------------------------------------------------

_metrics: dict[str, int] = defaultdict(int)
_latencies: list[float] = []


def record_request(allowed: bool, latency_ms: float) -> None:
    _metrics["total_requests"] += 1
    if allowed:
        _metrics["allowed"] += 1
    else:
        _metrics["blocked"] += 1
    _latencies.append(latency_ms)
    # Keep last 1000
    if len(_latencies) > 1000:
        _latencies.pop(0)


def get_metrics_snapshot() -> dict[str, Any]:
    avg_latency = sum(_latencies) / len(_latencies) if _latencies else 0.0
    return {
        "total_requests": _metrics["total_requests"],
        "allowed": _metrics["allowed"],
        "blocked": _metrics["blocked"],
        "avg_latency_ms": round(avg_latency, 1),
        "p95_latency_ms": round(sorted(_latencies)[int(len(_latencies) * 0.95)] if len(_latencies) > 20 else 0, 1),
    }


# ---------------------------------------------------------------------------
# Audit log (async-safe, never logs secrets)
# ---------------------------------------------------------------------------

async def audit_log(request_id: str, event: str, detail: dict[str, Any]) -> None:
    logger = logging.getLogger("hallu_guard.audit")
    logger.info(
        "AUDIT",
        extra={
            "request_id": request_id,
            "event": event,
            **{k: v for k, v in detail.items() if k not in ("api_key", "token", "password", "secret")},
        },
    )
