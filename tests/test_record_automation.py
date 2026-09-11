from unittest.mock import MagicMock

import pytest

import record_automation


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
    monkeypatch.setattr(record_automation, "find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(record_automation.subprocess, "Popen", popen)
    monkeypatch.setattr("builtins.input", manual_stop)

    record_automation.main()

    manual_stop.assert_called_once_with(
        "Recording started. Press Enter to stop recording...\n"
    )
    recording.stdin.write.assert_called_once_with(b"q\n")
    recording.stdin.flush.assert_called_once_with()
    recording.wait.assert_called_once_with(timeout=10)