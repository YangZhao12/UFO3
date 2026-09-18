import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest

from aip.messages import ServerMessage, ServerMessageType, TaskStatus
from ufo.client.websocket import UFOWebSocketClient


def test_with_api_key_adds_encoded_token():
    connection_url = UFOWebSocketClient._with_api_key(
        "ws://localhost:5000/ws", "key with/+symbols"
    )

    assert parse_qs(urlsplit(connection_url).query) == {
        "token": ["key with/+symbols"]
    }


def test_with_api_key_preserves_query_and_replaces_token():
    connection_url = UFOWebSocketClient._with_api_key(
        "ws://localhost:5000/ws?mode=local&token=old", "new"
    )

    assert parse_qs(urlsplit(connection_url).query) == {
        "mode": ["local"],
        "token": ["new"],
    }


def test_with_api_key_leaves_url_unchanged_without_key():
    ws_url = "ws://localhost:5000/ws?mode=local"

    assert UFOWebSocketClient._with_api_key(ws_url, None) == ws_url


@pytest.mark.asyncio
async def test_handle_commands_starts_recording_before_executing_action(
    monkeypatch, tmp_path
):
    events = []
    script_path = tmp_path / "record_automation.py"
    script_path.touch()
    recording_process = SimpleNamespace(returncode=None)

    async def create_subprocess_exec(*args, **kwargs):
        events.append(("record", args, kwargs))
        return recording_process

    ufo_client = SimpleNamespace(
        client_id="windows_device_2",
        execute_step=AsyncMock(side_effect=lambda response: events.append(("execute",))),
    )
    ws_client = UFOWebSocketClient("ws://localhost/ws", ufo_client)
    ws_client.task_protocol = SimpleNamespace(send_task_result=AsyncMock())
    server_response = SimpleNamespace(
        response_id="response-1",
        status=TaskStatus.CONTINUE,
        session_id="session-1",
    )

    monkeypatch.setattr(
        "ufo.client.websocket.Path",
        lambda value: SimpleNamespace(
            resolve=lambda: SimpleNamespace(
                parents=[None, None, tmp_path],
            )
        ),
    )
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_subprocess_exec)

    await ws_client.handle_commands(server_response)

    assert [event[0] for event in events] == ["record", "execute"]
    assert events[0][1] == (sys.executable, str(script_path))
    assert events[0][2] == {
        "cwd": str(tmp_path),
        "stdin": asyncio.subprocess.PIPE,
    }
    assert ws_client._recording_process is recording_process
    assert ws_client._recording_sessions == {"session-1"}


@pytest.mark.asyncio
async def test_trigger_recording_does_not_start_another_running_recording(
    monkeypatch,
):
    running_process = SimpleNamespace(returncode=None)
    ufo_client = SimpleNamespace(client_id="windows_device_2")
    ws_client = UFOWebSocketClient("ws://localhost/ws", ufo_client)
    ws_client._recording_process = running_process
    create_subprocess_exec = AsyncMock()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_subprocess_exec)

    await ws_client._trigger_record_automation()

    create_subprocess_exec.assert_not_awaited()


@pytest.mark.asyncio
async def test_recording_continues_between_sequential_device_tasks():
    process_stdin = SimpleNamespace(write=MagicMock(), drain=AsyncMock())
    recording_process = SimpleNamespace(
        returncode=None,
        stdin=process_stdin,
        wait=AsyncMock(return_value=0),
        terminate=MagicMock(),
    )
    ufo_client = SimpleNamespace(client_id="windows_device_2")
    ws_client = UFOWebSocketClient("ws://localhost/ws", ufo_client)
    ws_client._recording_process = recording_process
    ws_client._recording_sessions = {"session-1", "session-2"}
    ws_client._recording_batches = {"constellation-1"}

    await ws_client.handle_task_end(
        SimpleNamespace(
            session_id="session-1",
            status=TaskStatus.COMPLETED,
            result="done",
        )
    )

    assert ws_client._recording_sessions == {"session-2"}
    process_stdin.write.assert_not_called()

    await ws_client.handle_task_end(
        SimpleNamespace(
            session_id="session-2",
            status=TaskStatus.FAILED,
            error="failed",
        )
    )

    assert ws_client._recording_sessions == set()
    process_stdin.write.assert_not_called()

    await ws_client.handle_message(
        ServerMessage(
            type=ServerMessageType.RECORDING_END,
            status=TaskStatus.COMPLETED,
            session_id="constellation-1",
        ).model_dump_json()
    )

    process_stdin.write.assert_called_once_with(b"\n")
    process_stdin.drain.assert_awaited_once_with()
    recording_process.wait.assert_awaited_once_with()
    recording_process.terminate.assert_not_called()
    assert ws_client._recording_process is None


@pytest.mark.asyncio
async def test_recording_waits_for_final_task_when_batch_end_arrives_first():
    process_stdin = SimpleNamespace(write=MagicMock(), drain=AsyncMock())
    recording_process = SimpleNamespace(
        returncode=None,
        stdin=process_stdin,
        wait=AsyncMock(return_value=0),
        terminate=MagicMock(),
    )
    ws_client = UFOWebSocketClient(
        "ws://localhost/ws", SimpleNamespace(client_id="windows_device_2")
    )
    ws_client._recording_process = recording_process
    ws_client._recording_sessions = {"session-2"}
    ws_client._recording_batches = {"constellation-1"}

    await ws_client.handle_message(
        ServerMessage(
            type=ServerMessageType.RECORDING_END,
            status=TaskStatus.COMPLETED,
            session_id="constellation-1",
        ).model_dump_json()
    )

    process_stdin.write.assert_not_called()

    await ws_client.handle_task_end(
        SimpleNamespace(
            session_id="session-2",
            status=TaskStatus.COMPLETED,
            result="done",
        )
    )

    process_stdin.write.assert_called_once_with(b"\n")