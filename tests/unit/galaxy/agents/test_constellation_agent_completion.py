import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from galaxy.agents.constellation_agent_states import (
    ConstellationAgentStatus,
    ContinueConstellationAgentState,
)
from galaxy.constellation.enums import ConstellationState
from galaxy.core.events import EventType
from galaxy.client.components.task_queue_manager import TaskQueueManager
from galaxy.client.components.types import TaskRequest
from galaxy.galaxy_client import GalaxyClient
from ufo.module.context import Context


@pytest.mark.asyncio
async def test_completion_events_are_collected_within_batch_window():
    queue = asyncio.Queue()
    first_event = SimpleNamespace(task_id="task-1")
    second_event = SimpleNamespace(task_id="task-2")

    async def publish_second_event():
        await asyncio.sleep(0.01)
        await queue.put(second_event)

    publisher = asyncio.create_task(publish_second_event())
    events = await ContinueConstellationAgentState._collect_completion_events(
        queue, first_event, batch_window=0.05
    )
    await publisher

    assert events == [first_event, second_event]


@pytest.mark.asyncio
async def test_completed_constellation_skips_editing():
    constellation = SimpleNamespace(
        state=ConstellationState.COMPLETED,
        tasks={"task-1": object()},
    )
    event = SimpleNamespace(task_id="task-1", data={"constellation": constellation})
    synchronizer = Mock()
    synchronizer.merge_and_sync_constellation_states.return_value = constellation
    agent = SimpleNamespace(
        logger=Mock(),
        task_completion_queue=asyncio.Queue(),
        orchestrator=SimpleNamespace(_modification_synchronizer=synchronizer),
        process_editing=AsyncMock(),
        status=ConstellationAgentStatus.CONTINUE.value,
        _current_constellation=None,
    )
    await agent.task_completion_queue.put(event)

    await ContinueConstellationAgentState().handle(agent, Mock(spec=Context))

    agent.process_editing.assert_not_awaited()
    synchronizer.complete_modifications.assert_called_once_with(["task-1"])
    assert agent.status == ConstellationAgentStatus.FINISH.value
    assert agent._current_constellation is constellation


@pytest.mark.asyncio
async def test_failed_constellation_still_runs_editing():
    constellation = SimpleNamespace(
        state=ConstellationState.FAILED,
        tasks={"task-1": object()},
    )
    event = SimpleNamespace(task_id="task-1", data={"constellation": constellation})
    synchronizer = Mock()
    synchronizer.merge_and_sync_constellation_states.return_value = constellation
    agent = SimpleNamespace(
        logger=Mock(),
        task_completion_queue=asyncio.Queue(),
        orchestrator=SimpleNamespace(_modification_synchronizer=synchronizer),
        process_editing=AsyncMock(),
        status=ConstellationAgentStatus.CONTINUE.value,
    )
    await agent.task_completion_queue.put(event)

    with patch("galaxy.agents.constellation_agent_states.asyncio.sleep", AsyncMock()):
        await ContinueConstellationAgentState().handle(agent, Mock(spec=Context))

    agent.process_editing.assert_awaited_once()
    synchronizer.complete_modifications.assert_not_called()


@pytest.mark.asyncio
async def test_explicit_safe_task_skips_editing():
    task = SimpleNamespace(task_data={"skip_constellation_editing": True})
    constellation = SimpleNamespace(
        state=ConstellationState.EXECUTING,
        tasks={"task-1": task},
        get_task=Mock(return_value=task),
    )
    event = SimpleNamespace(
        task_id="task-1",
        event_type=EventType.TASK_COMPLETED,
        data={"constellation": constellation},
    )
    synchronizer = Mock()
    synchronizer.merge_and_sync_constellation_states.return_value = constellation
    agent = SimpleNamespace(
        logger=Mock(),
        task_completion_queue=asyncio.Queue(),
        orchestrator=SimpleNamespace(_modification_synchronizer=synchronizer),
        process_editing=AsyncMock(),
        status=ConstellationAgentStatus.CONTINUE.value,
        _current_constellation=None,
    )
    await agent.task_completion_queue.put(event)

    await ContinueConstellationAgentState().handle(agent, Mock(spec=Context))

    agent.process_editing.assert_not_awaited()
    synchronizer.complete_modifications.assert_called_once_with(["task-1"])
    assert agent._current_constellation is constellation


@pytest.mark.asyncio
async def test_cancel_task_removes_queue_and_pending_future():
    manager = TaskQueueManager()
    request = TaskRequest(
        task_id="task-1",
        device_id="device-1",
        request="test",
        task_name="test",
    )
    future = manager.enqueue_task("device-1", request)

    assert manager.cancel_task("device-1", "task-1") is True
    assert future.cancelled()
    assert manager.get_queued_task_ids("device-1") == []
    assert manager.get_pending_task_ids("device-1") == []


@pytest.mark.asyncio
async def test_busy_device_timeout_removes_task_from_queue():
    from galaxy.client.components.types import DeviceStatus
    from galaxy.client.device_manager import ConstellationDeviceManager

    manager = ConstellationDeviceManager(default_task_timeout=0.01)
    device = SimpleNamespace(
        device_id="device-1",
        status=DeviceStatus.BUSY,
    )
    manager.device_registry.get_device = Mock(return_value=device)
    manager.device_registry.is_device_busy = Mock(return_value=True)

    with pytest.raises(asyncio.TimeoutError):
        await manager.assign_task_to_device(
            task_id="task-1",
            device_id="device-1",
            task_description="test",
            task_data={},
        )

    assert manager.task_queue_manager.get_queued_task_ids("device-1") == []
    assert manager.task_queue_manager.get_pending_task_ids("device-1") == []


@pytest.mark.asyncio
async def test_direct_request_bypasses_galaxy_session():
    client = GalaxyClient.__new__(GalaxyClient)
    execution_result = SimpleNamespace(
        is_successful=True,
        result={"message": "done"},
        error=None,
    )
    device_manager = SimpleNamespace(
        device_registry=SimpleNamespace(get_all_devices=Mock(return_value={})),
        assign_task_to_device=AsyncMock(return_value=execution_result),
    )
    client._client = SimpleNamespace(device_manager=device_manager)
    client._current_request_task = None
    client._session = None
    client.task_name = "direct-task"
    client.session_name = "test-session"
    client.display = Mock()
    client.logger = Mock()
    client._save_result = Mock()

    with patch("galaxy.galaxy_client.GalaxySession") as session_class:
        result = await client.process_request(
            "start ms-settings:sound",
            target_device_id="windows_device_1",
            direct=True,
        )

    session_class.assert_not_called()
    device_manager.assign_task_to_device.assert_awaited_once()
    assert result["status"] == "completed"
    assert result["mode"] == "direct"