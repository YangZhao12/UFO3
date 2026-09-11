import unittest
from unittest.mock import AsyncMock, patch

import pytest

from ufo.client.mcp.local_servers.cli_mcp_server import (
    _is_cli_command_allowed,
    _parse_allowed_command,
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
    def test_direct_settings_commands_are_normalized_without_shell(self):
        self.assertEqual(
            _parse_allowed_command("start ms-settings:sound"),
            ["explorer.exe", "ms-settings:sound"],
        )
        self.assertEqual(
            _parse_allowed_command("Start-Process 'ms-settings:sound'"),
            ["explorer.exe", "ms-settings:sound"],
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
async def test_settings_page_verification_rejects_wrong_heading():
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
                result=[{"control_text": "Display", "control_type": "Text"}],
            )
        ],
    ]

    assert not await _verify_settings_page(dispatcher, "start ms-settings:sound")


if __name__ == "__main__":
    unittest.main()