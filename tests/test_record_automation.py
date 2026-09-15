from subprocess import CompletedProcess
from unittest.mock import MagicMock

import pytest

import record_automation


def test_disable_ac_power_timeouts_skips_settings_already_zero(monkeypatch):
    run = MagicMock(
        return_value=CompletedProcess(
            args=[],
            returncode=0,
            stdout="Current AC Power Setting Index: 0x00000000\n",
        )
    )
    monkeypatch.setattr(record_automation.subprocess, "run", run)

    record_automation.disable_ac_power_timeouts()

    assert run.call_count == 3
    assert all(call.args[0][1] == "/query" for call in run.call_args_list)


def test_disable_ac_power_timeouts_changes_only_nonzero_settings(monkeypatch):
    query_results = iter(
        [
            CompletedProcess([], 0, stdout="当前交流电源设置索引: 0x0000003c\n"),
            CompletedProcess([], 0, stdout="当前交流电源设置索引: 0x00000000\n"),
            CompletedProcess([], 0, stdout="当前交流电源设置索引: 0x00000078\n"),
        ]
    )
    change_calls = []

    def run(command, **kwargs):
        if command[1] == "/query":
            return next(query_results)
        change_calls.append(command)
        return CompletedProcess(command, 0)

    monkeypatch.setattr(record_automation.subprocess, "run", run)

    record_automation.disable_ac_power_timeouts()

    assert change_calls == [
        ["powercfg", "/change", "monitor-timeout-ac", "0"],
        ["powercfg", "/change", "hibernate-timeout-ac", "0"],
    ]


def test_find_ffmpeg_uses_winget_link_when_not_on_path(monkeypatch, tmp_path):
    winget_link = tmp_path / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"
    winget_link.parent.mkdir(parents=True)
    winget_link.touch()
    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(record_automation.shutil, "which", lambda _: None)

    assert record_automation.find_ffmpeg() == str(winget_link)


def test_find_ffmpeg_explains_how_to_install_or_configure(monkeypatch, tmp_path):
    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(record_automation.shutil, "which", lambda _: None)

    with pytest.raises(FileNotFoundError, match="winget install Gyan.FFmpeg"):
        record_automation.find_ffmpeg()


def test_main_waits_for_manual_stop_and_closes_recording(monkeypatch):
    recording = MagicMock(returncode=0)
    popen = MagicMock(return_value=recording)
    manual_stop = MagicMock(return_value="")
    disable_ac_power_timeouts = MagicMock()
    monkeypatch.setattr(
        record_automation, "disable_ac_power_timeouts", disable_ac_power_timeouts
    )
    monkeypatch.setattr(record_automation, "find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(record_automation.subprocess, "Popen", popen)
    monkeypatch.setattr("builtins.input", manual_stop)

    record_automation.main()

    disable_ac_power_timeouts.assert_called_once_with()
    manual_stop.assert_called_once_with(
        "Recording started. Press Enter to stop recording...\n"
    )
    recording.stdin.write.assert_called_once_with(b"q\n")
    recording.stdin.flush.assert_called_once_with()
    recording.wait.assert_called_once_with(timeout=10)