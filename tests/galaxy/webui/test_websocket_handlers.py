from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.websockets import WebSocketState

from galaxy.webui.handlers.websocket_handlers import WebSocketMessageHandler


@pytest.mark.asyncio
async def test_completed_request_ignores_closed_websocket():
    handler = WebSocketMessageHandler(SimpleNamespace())
    handler.galaxy_service.process_request = AsyncMock(
        return_value={"status": "completed"}
    )
    websocket = SimpleNamespace(
        application_state=WebSocketState.DISCONNECTED,
        client_state=WebSocketState.DISCONNECTED,
        send_json=AsyncMock(
            side_effect=RuntimeError(
                "Unexpected ASGI message 'websocket.send', after sending 'websocket.close'"
            )
        ),
    )

    await handler._process_request_in_background(websocket, "long request")

    handler.galaxy_service.process_request.assert_awaited_once_with("long request")
    websocket.send_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_completed_request_handles_disconnect_during_send():
    handler = WebSocketMessageHandler(SimpleNamespace())
    handler.galaxy_service.process_request = AsyncMock(return_value="saved result")
    websocket = SimpleNamespace(
        application_state=WebSocketState.CONNECTED,
        client_state=WebSocketState.CONNECTED,
        send_json=AsyncMock(
            side_effect=RuntimeError(
                "Unexpected ASGI message 'websocket.send', after sending 'websocket.close'"
            )
        ),
    )

    await handler._process_request_in_background(websocket, "long request")

    websocket.send_json.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_request_notifies_connected_websocket_once():
    handler = WebSocketMessageHandler(SimpleNamespace())
    handler.galaxy_service.process_request = AsyncMock(
        side_effect=ValueError("processing failed")
    )
    websocket = SimpleNamespace(
        application_state=WebSocketState.CONNECTED,
        client_state=WebSocketState.CONNECTED,
        send_json=AsyncMock(),
    )

    await handler._process_request_in_background(websocket, "bad request")

    websocket.send_json.assert_awaited_once()
    payload = websocket.send_json.await_args.args[0]
    assert payload["type"] == "request_failed"
    assert payload["error"] == "processing failed"