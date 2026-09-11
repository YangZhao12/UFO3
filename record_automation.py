import os
import shutil
import subprocess
from pathlib import Path


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