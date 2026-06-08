from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from ..settings import models_dir, project_root


def voice_models_config_path() -> Path | None:
    env_path = os.environ.get("OPENINTERVIEW_VOICE_MODELS_CONFIG")
    if env_path:
        return Path(env_path)
    local = project_root() / "configs" / "voice-models.local.yaml"
    if local.exists():
        return local
    return None


def voice_profiles_config_path() -> Path:
    env_path = os.environ.get("OPENINTERVIEW_VOICE_PROFILES")
    if env_path:
        return Path(env_path)
    local = project_root() / "configs" / "voice-profiles.local.yaml"
    if local.exists():
        return local
    return project_root() / "configs" / "voice-profiles.example.yaml"


def vad_model_path() -> Path:
    env_path = os.environ.get("OPENINTERVIEW_VAD_MODEL")
    if env_path:
        return Path(env_path)
    configured = _model_config_value(["vad", "default", "local_file"])
    if configured:
        return _resolve_repo_path(configured)
    return models_dir() / "vad" / "silero-vad" / "silero_vad.onnx"


def asr_model_dir() -> Path:
    env_path = os.environ.get("OPENINTERVIEW_ASR_MODEL_DIR")
    if env_path:
        return Path(env_path)
    configured = _model_config_value(["asr", "default", "local_dir"])
    if configured:
        return _resolve_repo_path(configured)
    return models_dir() / "asr" / "SenseVoiceSmall"


def tts_model_dir() -> Path:
    env_path = os.environ.get("OPENINTERVIEW_TTS_MODEL_DIR")
    if env_path:
        return Path(env_path)
    configured = _model_config_value(["tts", "default", "local_dir"])
    if configured:
        return _resolve_repo_path(configured)
    return models_dir() / "tts" / "Fun-CosyVoice3-0.5B"


def voice_config_summary() -> dict:
    model_config = voice_models_config_path()
    profiles_config = voice_profiles_config_path()
    return {
        "models_config": str(model_config) if model_config else None,
        "profiles_config": str(profiles_config),
        "models_dir": str(models_dir()),
        "vad_model": str(vad_model_path()),
        "asr_model_dir": str(asr_model_dir()),
        "tts_model_dir": str(tts_model_dir()),
        "env_overrides": {
            "OPENINTERVIEW_VOICE_MODELS_CONFIG": os.environ.get("OPENINTERVIEW_VOICE_MODELS_CONFIG"),
            "OPENINTERVIEW_VOICE_PROFILES": os.environ.get("OPENINTERVIEW_VOICE_PROFILES"),
            "OPENINTERVIEW_MODELS_DIR": os.environ.get("OPENINTERVIEW_MODELS_DIR"),
            "OPENINTERVIEW_VAD_MODEL": os.environ.get("OPENINTERVIEW_VAD_MODEL"),
            "OPENINTERVIEW_ASR_MODEL_DIR": os.environ.get("OPENINTERVIEW_ASR_MODEL_DIR"),
            "OPENINTERVIEW_TTS_MODEL_DIR": os.environ.get("OPENINTERVIEW_TTS_MODEL_DIR"),
            "OPENINTERVIEW_COSYVOICE_PATH": os.environ.get("OPENINTERVIEW_COSYVOICE_PATH"),
        },
    }


def _model_config_value(path: list[str]) -> str | None:
    config_path = voice_models_config_path()
    if not config_path or not config_path.exists():
        return None
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    value: Any = data
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return str(value).strip() if value else None


def _resolve_repo_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return project_root() / path
