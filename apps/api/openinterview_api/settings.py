from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def portable_ffmpeg() -> Path:
    root = project_root() / "tools" / "ffmpeg"
    matches = list(root.glob("**/bin/ffmpeg.exe"))
    return matches[0] if matches else root / "bin" / "ffmpeg.exe"


def ensure_portable_ffmpeg_on_path() -> Path | None:
    ffmpeg = portable_ffmpeg()
    if not ffmpeg.exists():
        return None
    ffmpeg_dir = str(ffmpeg.parent)
    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    if ffmpeg_dir not in path_parts:
        os.environ["PATH"] = os.pathsep.join([ffmpeg_dir, os.environ.get("PATH", "")])
    return ffmpeg


def cosyvoice_path() -> Path | None:
    value = os.environ.get("OPENINTERVIEW_COSYVOICE_PATH")
    if value:
        return Path(value)
    default = Path("D:/CosyVoice")
    if default.exists():
        return default
    local = project_root() / "third_party" / "CosyVoice"
    return local if local.exists() else None


def data_dir() -> Path:
    path = Path(os.environ.get("OPENINTERVIEW_DATA_DIR", project_root() / "data"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    return Path(os.environ.get("OPENINTERVIEW_DB_PATH", data_dir() / "openinterview.sqlite"))


def models_dir() -> Path:
    return Path(os.environ.get("OPENINTERVIEW_MODELS_DIR", project_root() / "models"))


def voices_dir() -> Path:
    path = Path(os.environ.get("OPENINTERVIEW_VOICES_DIR", project_root() / "voices"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_vad_model() -> Path:
    return models_dir() / "vad" / "silero-vad" / "silero_vad.onnx"


def default_asr_model_dir() -> Path:
    return models_dir() / "asr" / "SenseVoiceSmall"


def default_tts_model_dir() -> Path:
    return models_dir() / "tts" / "Fun-CosyVoice3-0.5B"


def require_auth() -> bool:
    return os.environ.get("OPENINTERVIEW_REQUIRE_AUTH", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def cors_origins() -> list[str]:
    raw = os.environ.get("OPENINTERVIEW_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173")
    return [item.strip() for item in raw.split(",") if item.strip()]


def production_mode() -> bool:
    return os.environ.get("OPENINTERVIEW_ENV", "development").strip().lower() in {
        "prod",
        "production",
    }
