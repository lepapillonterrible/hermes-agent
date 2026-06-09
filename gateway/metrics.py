"""Structured gateway metrics logging helpers.

These helpers intentionally emit plain JSON on the existing gateway logger so
operators can build alerting from gateway.log without adding a metrics backend.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from typing import Any, Mapping

logger = logging.getLogger("gateway.metrics")


def _json_safe(value: Any) -> Any:
    """Return a compact JSON-serializable representation for metric fields."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return str(value)


def emit_metric(event: str, /, **fields: Any) -> None:
    """Log one structured gateway metric event.

    Log shape is stable and grep-friendly:

        gateway_metric {"event":"send-failure",...}

    The JSON payload is also standalone parseable for log sinks that split on
    the first ``gateway_metric `` prefix.
    """
    payload = {
        "schema": "hermes.gateway.metric.v1",
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
    }
    payload.update({k: _json_safe(v) for k, v in fields.items() if v is not None})
    logger.info("gateway_metric %s", json.dumps(payload, sort_keys=True, separators=(",", ":")))


def exception_summary(exc: BaseException) -> dict[str, Any]:
    """Summarize an exception, including ExceptionGroup sub-exceptions."""
    summary: dict[str, Any] = {
        "type": type(exc).__name__,
        "message": str(exc)[:500],
    }
    exceptions = getattr(exc, "exceptions", None)
    if exceptions:
        summary["sub_exceptions"] = [
            {"type": type(sub).__name__, "message": str(sub)[:300]}
            for sub in list(exceptions)[:10]
        ]
        summary["sub_exception_count"] = len(exceptions)
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        summary["status_code"] = status_code
    return summary
