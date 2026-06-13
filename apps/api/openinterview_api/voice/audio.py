from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import wave

from ..settings import portable_ffmpeg


PCM_S16LE_ENCODINGS = {"pcm_s16le", "s16le", "pcm", "audio/pcm", "audio/l16"}


def is_pcm_s16le_encoding(encoding: str | None) -> bool:
    normalized = (encoding or "").strip().lower().replace("-", "_")
    return normalized in PCM_S16LE_ENCODINGS


def write_pcm_s16le_wav(
    audio: bytes,
    output_path: Path,
    *,
    sample_rate: int = 16000,
    channels: int = 1,
) -> Path:
    if sample_rate != 16000 or channels != 1:
        raise ValueError("pcm_s16le audio must be 16 kHz mono.")
    if len(audio) % 2 != 0:
        raise ValueError("pcm_s16le audio length must be aligned to 16-bit samples.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(audio)
    return output_path


def ensure_16k_mono_wav(input_path: Path, output_path: Path) -> Path:
    if input_path.suffix.lower() == ".wav":
        try:
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
