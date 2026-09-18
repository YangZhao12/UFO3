import asyncio
import json
import unittest
from unittest.mock import AsyncMock

from aip.messages import (
    ClientMessageType,
    ServerMessage,
    ServerMessageType,
    TaskStatus,
)
from aip.protocol.task_execution import TaskExecutionProtocol
from galaxy.client.components.connection_manager import WebSocketConnectionManager
from galaxy.client.components.types import TaskRequest


class ImmediateResponseTransport:
    is_connected = True

    def __init__(self, connection_manager, device_id):
        self.connection_manager = connection_manager
        self.device_id = device_id

    async def send(self, payload):
        request = json.loads(payload.decode("utf-8"))
        response = ServerMessage(
            type=ServerMessageType.TASK_END,
            session_id=request["session_id"],
            status=TaskStatus.COMPLETED,
            result={"output": "completed immediately"},
        )
        self.connection_manager.complete_task_response(
            request["session_id"], response, sender_device_id=self.device_id
        )


class TestImmediateTaskResponse(unittest.IsolatedAsyncioTestCase):
    async def test_response_arriving_during_send_is_not_lost(self):
        device_id = "device-1"
        manager = WebSocketConnectionManager(task_name="test")
        transport = ImmediateResponseTransport(manager, device_id)
        manager._transports[device_id] = transport
        manager._task_protocols[device_id] = TaskExecutionProtocol(transport)

        result = await manager.send_task_to_device(
            device_id,
            TaskRequest(
                task_id="task-1",
                device_id=device_id,
                task_name="immediate-response",
                request="run",
                timeout=0.1,
            ),
        )

        self.assertEqual(result.result, {"output": "completed immediately"})
        self.assertEqual(manager._pending_tasks, {})

    async def test_recording_batch_control_is_sent_once_per_device(self):
        device_id = "device-1"
        manager = WebSocketConnectionManager(task_name="batch-1")
        protocol = AsyncMock()
        manager._task_protocols[device_id] = protocol

        await manager.start_recording_batch(device_id)
        await manager.start_recording_batch(device_id)
        await manager.end_recording_batch(device_id)
        await manager.end_recording_batch(device_id)

        self.assertEqual(protocol.send_recording_control_request.await_count, 2)
        self.assertEqual(
            protocol.send_recording_control_request.await_args_list[0].args[0],
            ClientMessageType.RECORDING_START,
        )
        self.assertEqual(
            protocol.send_recording_control_request.await_args_list[1].args[0],
            ClientMessageType.RECORDING_END,
        )
        self.assertEqual(manager._recording_devices, set())

    async def test_unscoped_error_completes_only_pending_task_for_device(self):
        device_id = "device-1"
        manager = WebSocketConnectionManager(task_name="test")
        pending_future = asyncio.get_running_loop().create_future()
        manager._pending_tasks["test@task-1"] = (device_id, pending_future)
        error_response = ServerMessage(
            type=ServerMessageType.ERROR,
            status=TaskStatus.ERROR,
            error="Task rejected",
        )

        handled = manager.complete_task_error(device_id, error_response)

        self.assertTrue(handled)
        self.assertIs(await pending_future, error_response)


if __name__ == "__main__":
    unittest.main()