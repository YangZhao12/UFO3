import subprocess
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, call, patch

import pytest
from fastmcp.exceptions import ToolError

from ufo.client.mcp.local_servers.cli_mcp_server import (
    _is_cli_command_allowed,
    _parse_allowed_command,
    _resolve_cli_executable,
    create_cli_mcp_server,
    get_settings_uri_page,
    is_settings_uri_command,
)
from ufo.agents.processors.strategies.host_agent_processing_strategy import (
    _is_successful_settings_launch,
    _verify_settings_page,
)
from aip.messages import Result, ResultStatus


class TestCliSettingsUri(unittest.TestCase):
    def test_ffmpeg_resolves_from_winget_links_when_not_on_path(self):
        command = ["ffmpeg", "-version"]

        with patch.dict(
            "os.environ", {"LOCALAPPDATA": r"C:\Users\Test\AppData\Local"}, clear=True
        ), patch("shutil.which", return_value=None), patch.object(
            Path, "resolve", return_value=Path(r"C:\ffmpeg\bin\ffmpeg.exe")
        ), patch.object(
            Path, "is_file", return_value=True
        ):
            resolved = _resolve_cli_executable(command)

        self.assertEqual(
            resolved[0],
            r"C:\ffmpeg\bin\ffmpeg.exe",
        )
        self.assertEqual(resolved[1:], ["-version"])

    def test_ffmpeg_recording_command_is_allowed_without_shell(self):
        command = (
            "ffmpeg -y -f gdigrab -framerate 30 -i desktop "
            "-c:v libx264 -preset ultrafast automation_recording.mp4"
        )

        self.assertEqual(
            _parse_allowed_command(command),
            [
                "ffmpeg",
                "-y",
                "-f",
                "gdigrab",
                "-framerate",
                "30",
                "-i",
                "desktop",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "automation_recording.mp4",
            ],
        )
        self.assertTrue(_is_cli_command_allowed(command))
        self.assertFalse(_is_cli_command_allowed(f"{command} & powershell -Command whoami"))

    def test_direct_settings_commands_are_normalized_without_shell(self):
        self.assertEqual(
            _parse_allowed_command("start ms-settings:sound"),
            ["explorer.exe", "ms-settings:sound"],
        )
        self.assertEqual(
            _parse_allowed_command("Start-Process 'ms-settings:sound'"),
            ["explorer.exe", "ms-settings:sound"],
        )

    def test_start_snipping_tool_is_normalized_without_shell(self):
        self.assertEqual(
            _parse_allowed_command("start snippingtool"),
            ["SnippingTool.exe"],
        )
        self.assertEqual(
            _parse_allowed_command("start SnippingTool.exe"),
            ["SnippingTool.exe"],
        )

    def test_other_start_commands_remain_blocked(self):
        self.assertFalse(_is_cli_command_allowed("start powershell"))
        self.assertFalse(_is_cli_command_allowed("start https://example.com"))
        self.assertFalse(
            _is_cli_command_allowed(
                "powershell -Command Start-Process 'ms-settings:sound'"
            )
        )

    def test_settings_uri_completion_requires_exact_successful_launch(self):
        success = [Result(status=ResultStatus.SUCCESS, result=None)]
        failure = [Result(status=ResultStatus.FAILURE, result=None)]

        self.assertTrue(is_settings_uri_command("start ms-settings:sound"))
        self.assertEqual(get_settings_uri_page("start ms-settings:sound"), "sound")
        self.assertTrue(
            _is_successful_settings_launch(
                "run_shell", {"bash_command": "start ms-settings:sound"}, success
            )
        )
        self.assertFalse(
            _is_successful_settings_launch(
                "run_shell", {"bash_command": "start ms-settings:sound"}, failure
            )
        )
        self.assertFalse(
            _is_successful_settings_launch(
                "run_shell",
                {"bash_command": "start ms-settings:sound extra"},
                success,
            )
        )

    def test_run_shell_launches_normalized_arguments(self):
        server = create_cli_mcp_server()
        run_shell = server._tool_manager._tools["run_shell"].fn

        with patch("subprocess.Popen") as popen, patch("time.sleep"):
            run_shell("start ms-settings:sound")

        popen.assert_called_once_with(
            ["explorer.exe", "ms-settings:sound"], shell=False
        )

    def test_run_shell_waits_for_timed_ffmpeg_recording(self):
        server = create_cli_mcp_server()
        run_shell = server._tool_manager._tools["run_shell"].fn

        with patch(
            "ufo.client.mcp.local_servers.cli_mcp_server._resolve_cli_executable",
            return_value=["ffmpeg.exe", "-t", "60", "recording.mp4"],
        ), patch("subprocess.Popen") as popen, patch("time.sleep") as sleep:
            popen.return_value.returncode = 0
            run_shell("ffmpeg -t 60 recording.mp4")

        popen.return_value.wait.assert_called_once_with(timeout=90)
        sleep.assert_not_called()

    def test_run_shell_terminates_timed_out_ffmpeg_recording(self):
        server = create_cli_mcp_server()
        run_shell = server._tool_manager._tools["run_shell"].fn

        with patch(
            "ufo.client.mcp.local_servers.cli_mcp_server._resolve_cli_executable",
            return_value=["ffmpeg.exe", "-t", "60", "recording.mp4"],
        ), patch("subprocess.Popen") as popen, patch("time.sleep"):
            popen.return_value.wait.side_effect = [
                subprocess.TimeoutExpired("ffmpeg.exe", 90),
                None,
            ]
            with self.assertRaisesRegex(
                ToolError, "did not stop after its configured duration"
            ):
                run_shell("ffmpeg -t 60 recording.mp4")

        popen.return_value.terminate.assert_called_once_with()
        self.assertEqual(
            popen.return_value.wait.call_args_list,
            [call(timeout=90), call(timeout=5)],
        )


@pytest.mark.asyncio
async def test_settings_page_verification_requires_visible_heading():
    dispatcher = AsyncMock()
    dispatcher.execute_commands.side_effect = [
        [
            Result(
                status=ResultStatus.SUCCESS,
                result=[{"id": "7", "name": "设置"}],
            )
        ],
        [Result(status=ResultStatus.SUCCESS, result={"root_name": "设置"})],
        [
            Result(
                status=ResultStatus.SUCCESS,
                result=[{"control_text": "声音", "control_type": "Text"}],
            )
        ],
    ]

    assert await _verify_settings_page(dispatcher, "start ms-settings:sound")


@pytest.mark.asyncio
async def test_system_settings_page_verification_requires_visible_heading():
    dispatcher = AsyncMock()
    dispatcher.execute_commands.side_effect = [
        [
            Result(
                status=ResultStatus.SUCCESS,
                result=[{"id": "7", "name": "Settings"}],
            )
        ],
        [Result(status=ResultStatus.SUCCESS, result={"root_name": "Settings"})],
        [
            Result(
                status=ResultStatus.SUCCESS,
                result=[{"control_text": "System", "control_type": "Text"}],
            )
        ],
    ]

    assert await _verify_settings_page(dispatcher, "start ms-settings:system")


@pytest.mark.asyncio
async def test_settings_page_verification_waits_for_localized_hierarchical_heading():
    dispatcher = AsyncMock()
    dispatcher.execute_commands.side_effect = [
        [Result(status=ResultStatus.SUCCESS, result=[])],
        [
            Result(
                status=ResultStatus.SUCCESS,
                result=[{"id": "7", "name": "设置"}],
            )
        ],
        [Result(status=ResultStatus.SUCCESS, result={"root_name": "设置"})],
        [
            Result(
                status=ResultStatus.SUCCESS,
                result=[{"control_name": "系统\u200b > 屏幕", "control_type": "Text"}],
            )
        ],
    ]

    with patch(
        "ufo.agents.processors.strategies.host_agent_processing_strategy.asyncio.sleep",
        new_callable=AsyncMock,
    ):
        assert await _verify_settings_page(
            dispatcher, "start ms-settings:system"
        )


@pytest.mark.asyncio
async def test_settings_page_verification_rejects_wrong_heading():
    dispatcher = AsyncMock()
    setup_results = [
        [
            Result(
                status=ResultStatus.SUCCESS,
                result=[{"id": "7", "name": "Settings"}],
            )
        ],
        [Result(status=ResultStatus.SUCCESS, result={"root_name": "Settings"})],
    ]
    wrong_heading_result = [
        Result(
            status=ResultStatus.SUCCESS,
            result=[{"control_text": "Display", "control_type": "Text"}],
        )
    ]
    dispatcher.execute_commands.side_effect = [
        *setup_results,
        *[
            wrong_heading_result
            for _ in range(5)
        ],
    ]

    with patch(
        "ufo.agents.processors.strategies.host_agent_processing_strategy.asyncio.sleep",
        new_callable=AsyncMock,
    ):
        assert not await _verify_settings_page(
            dispatcher, "start ms-settings:sound"
        )


if __name__ == "__main__":
    unittest.main()