import json
from datetime import datetime, timezone
from typing import Any


_ALLOWED_FIELDS = {
    "session_id",
    "task_id",
    "device_id",
    "client_id",
    "round",
    "attempt",
    "action",
    "status",
    "duration_ms",
    "error_type",
}


def log_phase_event(logger, event: str, **fields: Any) -> None:
    """Emit a correlated JSON phase event without request or credential data."""
    payload = {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    payload.update(
        {key: value for key, value in fields.items() if key in _ALLOWED_FIELDS}
    )
    logger.info("phase_event=%s", json.dumps(payload, separators=(",", ":")))