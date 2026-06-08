from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from ..settings import models_dir, project_root


def editable_voice_models_config_path() -> Path:
    env_path = os.environ.get("OPENINTERVIEW_VOICE_MODELS_CONFIG")
    if env_path:
        return Path(env_path)
    return project_root() / "configs" / "voice-models.local.yaml"


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


def cosyvoice_runtime_path() -> Path | None:
    env_path = os.environ.get("OPENINTERVIEW_COSYVOICE_PATH")
    if env_path:
        return Path(env_path)
    configured = _model_config_value(["tts", "default", "runtime_path"])
    if configured:
        return _resolve_repo_path(configured)
    legacy_configured = _model_config_value(["cosyvoice", "default", "runtime_path"])
    if legacy_configured:
        return _resolve_repo_path(legacy_configured)
    default = Path("D:/CosyVoice")
    if default.exists():
        return default
    local = project_root() / "third_party" / "CosyVoice"
    return local if local.exists() else None


def voice_config_summary() -> dict:
    model_config = voice_models_config_path()
    profiles_config = voice_profiles_config_path()
    runtime_path = cosyvoice_runtime_path()
    return {
        "models_config": str(model_config) if model_config else None,
        "editable_models_config": str(editable_voice_models_config_path()),
        "profiles_config": str(profiles_config),
        "models_dir": str(models_dir()),
        "vad_model": str(vad_model_path()),
        "asr_model_dir": str(asr_model_dir()),
        "tts_model_dir": str(tts_model_dir()),
        "cosyvoice_path": str(runtime_path) if runtime_path else None,
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


def read_voice_model_config() -> dict:
    config_path = voice_models_config_path()
    if not config_path or not config_path.exists():
        return {}
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def save_voice_model_config(
    *,
    vad_model: str | None = None,
    asr_model_dir_value: str | None = None,
    tts_model_dir_value: str | None = None,
    cosyvoice_path_value: str | None = None,
) -> dict:
    config_path = editable_voice_models_config_path()
    data: dict[str, Any]
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        data = loaded if isinstance(loaded, dict) else {}
    else:
        data = {}

    _set_nested_path(data, ["vad", "default", "local_file"], vad_model)
    _set_nested_path(data, ["asr", "default", "local_dir"], asr_model_dir_value)
    _set_nested_path(data, ["tts", "default", "local_dir"], tts_model_dir_value)
    _set_nested_path(data, ["tts", "default", "runtime_path"], cosyvoice_path_value)

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return voice_config_summary()


def voice_config_response() -> dict:
    summary = voice_config_summary()
    return {
        **summary,
        "exists": {
            "models_config": bool(summary["models_config"] and Path(summary["models_config"]).exists()),
            "vad_model": vad_model_path().exists(),
            "asr_model_dir": asr_model_dir().exists(),
            "tts_model_dir": tts_model_dir().exists(),
            "cosyvoice_path": bool(cosyvoice_runtime_path() and cosyvoice_runtime_path().exists()),
        },
        "raw": read_voice_model_config(),
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


def _set_nested_path(data: dict[str, Any], keys: list[str], value: str | None) -> None:
    if value is None:
        return
    current: dict[str, Any] = data
    for key in keys[:-1]:
        child = current.get(key)
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    final_key = keys[-1]
    normalized = str(value).strip()
    if normalized:
        current[final_key] = normalized
    else:
        current.pop(final_key, None)
