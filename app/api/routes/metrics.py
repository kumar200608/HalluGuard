"""Metrics endpoint (Prometheus-compatible text format + JSON summary)."""
from __future__ import annotations

import time

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.utils.observability import get_metrics_snapshot

router = APIRouter()

_START_TIME = time.time()


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics_prometheus() -> str:
    snap = get_metrics_snapshot()
    uptime = int(time.time() - _START_TIME)
    lines = [
        "# HELP hallu_guard_requests_total Total verification requests",
        "# TYPE hallu_guard_requests_total counter",
        f"hallu_guard_requests_total {snap['total_requests']}",
        "",
        "# HELP hallu_guard_allowed_total Requests allowed through gate",
        "# TYPE hallu_guard_allowed_total counter",
        f"hallu_guard_allowed_total {snap['allowed']}",
        "",
        "# HELP hallu_guard_blocked_total Requests blocked or repaired",
        "# TYPE hallu_guard_blocked_total counter",
        f"hallu_guard_blocked_total {snap['blocked']}",
        "",
        "# HELP hallu_guard_uptime_seconds Service uptime",
        "# TYPE hallu_guard_uptime_seconds gauge",
        f"hallu_guard_uptime_seconds {uptime}",
    ]
    return "\n".join(lines)


@router.get("/metrics/summary")
async def metrics_summary():
    return get_metrics_snapshot()
