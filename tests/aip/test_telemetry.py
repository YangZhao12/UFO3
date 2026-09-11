import json
import logging

from aip.telemetry import log_phase_event


def test_phase_event_logs_only_allowed_fields(caplog):
    logger = logging.getLogger("test.phase_event")

    with caplog.at_level(logging.INFO, logger=logger.name):
        log_phase_event(
            logger,
            "task_send",
            session_id="session-1",
            task_id="task-1",
            token="secret-token",
            request="sensitive request",
        )

    payload = json.loads(caplog.records[-1].message.removeprefix("phase_event="))
    assert payload["event"] == "task_send"
    assert payload["session_id"] == "session-1"
    assert "token" not in payload
    assert "request" not in payload