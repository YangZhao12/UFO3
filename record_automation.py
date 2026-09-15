import os
import re
import shutil
import subprocess
from pathlib import Path


POWER_TIMEOUTS = (
    ("SUB_VIDEO", "VIDEOIDLE", "monitor-timeout-ac"),
    ("SUB_SLEEP", "STANDBYIDLE", "standby-timeout-ac"),
    ("SUB_SLEEP", "HIBERNATEIDLE", "hibernate-timeout-ac"),
)


def disable_ac_power_timeouts() -> None:
    for subgroup, setting, change_name in POWER_TIMEOUTS:
        result = subprocess.run(
            ["powercfg", "/query", "SCHEME_CURRENT", subgroup, setting],
            check=True,
            capture_output=True,
            text=True,
        )
        ac_index = re.search(
            r"^\s*.*(?:AC|交流).*?:\s*(0x[0-9a-f]+)\s*$",
            result.stdout,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        if ac_index is None:
            raise RuntimeError(f"Unable to read the AC power setting for {setting}")

        if int(ac_index.group(1), 16) == 0:
            print(f"Power setting {change_name} is already disabled; skipping.")
            continue

        subprocess.run(
            ["powercfg", "/change", change_name, "0"],
            check=True,
        )
        print(f"Disabled power setting {change_name}.")


def find_ffmpeg() -> str:
    configured_path = os.environ.get("FFMPEG_PATH")
    if configured_path and Path(configured_path).is_file():
        return configured_path

    executable = shutil.which("ffmpeg")
    if executable:
        return executable

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        winget_link = Path(local_app_data) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"
        if winget_link.is_file():
            return str(winget_link)

    raise FileNotFoundError(
        "FFmpeg was not found. Install it with `winget install Gyan.FFmpeg`, "
        "restart the terminal, or set FFMPEG_PATH to ffmpeg.exe."
    )


def main() -> None:
    disable_ac_power_timeouts()
    output_path = Path("automation_recording.mp4").resolve()
    recording = subprocess.Popen(
        [
            find_ffmpeg(),
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
            str(output_path),
        ],
        stdin=subprocess.PIPE,
    )

    try:
        input("Recording started. Press Enter to stop recording...\n")
    except KeyboardInterrupt:
        print("\nStopping recording...")
    finally:
        if recording.stdin:
            recording.stdin.write(b"q\n")
            recording.stdin.flush()

        try:
            recording.wait(timeout=10)
        except subprocess.TimeoutExpired:
            recording.terminate()
            recording.wait(timeout=5)

    if recording.returncode != 0:
        raise RuntimeError(f"FFmpeg recording failed with exit code {recording.returncode}")

    print(f"Recording saved to {output_path}")


if __name__ == "__main__":
    main()