from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

from ..settings import portable_ffmpeg


def ensure_16k_mono_wav(input_path: Path, output_path: Path) -> Path:
    if input_path.suffix.lower() == ".wav":
        try:
            import wave

            with wave.open(str(input_path), "rb") as wav:
                if wav.getnchannels() == 1 and wav.getframerate() == 16000 and wav.getsampwidth() == 2:
                    if input_path != output_path:
                        shutil.copy2(input_path, output_path)
                    return output_path
        except Exception:
            pass

    portable = portable_ffmpeg()
    ffmpeg = str(portable) if portable.exists() else shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            "ffmpeg is required to convert browser audio to 16k mono WAV. "
            "Install ffmpeg and make sure it is available on PATH."
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(input_path),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-sample_fmt",
        "s16",
        str(output_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "ffmpeg conversion failed.")
    return output_path
