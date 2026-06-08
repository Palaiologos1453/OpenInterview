from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import tempfile
import time

from ..settings import (
    cosyvoice_path,
    default_asr_model_dir,
    default_tts_model_dir,
    default_vad_model,
    ensure_portable_ffmpeg_on_path,
    portable_ffmpeg,
)
from .voice_config import voice_config_summary
from ..voice.local_tts import write_silence_wav


def readiness_report() -> dict:
    ensure_portable_ffmpeg_on_path()
    checks = {
        "ffmpeg": _ffmpeg_check(),
        "vad_model": _path_check(default_vad_model()),
        "asr_model": _path_check(default_asr_model_dir() / "model.pt"),
        "tts_model_llm": _path_check(default_tts_model_dir() / "llm.pt"),
        "tts_model_flow": _path_check(default_tts_model_dir() / "flow.pt"),
        "onnxruntime": _module_check("onnxruntime"),
        "funasr": _module_check("funasr"),
        "cosyvoice": _cosyvoice_check(),
        "torch": _module_check("torch"),
        "torchaudio": _module_check("torchaudio"),
    }
    checks["cuda"] = _cuda_check()
    ready_for_local_voice = all(
        checks[key]["ok"]
        for key in [
            "ffmpeg",
            "vad_model",
            "asr_model",
            "tts_model_llm",
            "tts_model_flow",
            "onnxruntime",
            "funasr",
            "cosyvoice",
            "torch",
            "torchaudio",
        ]
    )
    return {
        "ready_for_core_api": True,
        "ready_for_local_voice": ready_for_local_voice,
        "voice_config": voice_config_summary(),
        "checks": checks,
    }


def readiness_smoke_report(*, include_voice: bool = False, voice_check: str | None = None) -> dict:
    ensure_portable_ffmpeg_on_path()
    started = time.perf_counter()
    checks = {
        "wav_fixture": _smoke_wav_fixture(),
        "vad": _smoke_vad(),
    }
    target = (voice_check or "").strip().lower()
    if include_voice and target in {"", "all", "asr"}:
        checks["asr"] = _smoke_asr()
    if include_voice and target in {"", "all", "tts"}:
        checks["tts"] = _smoke_tts()
    return {
        "ok": all(item["ok"] for item in checks.values()),
        "include_voice": include_voice,
        "voice_check": target or ("all" if include_voice else None),
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "checks": checks,
    }


def _binary_check(name: str) -> dict:
    path = shutil.which(name)
    return {"ok": path is not None, "path": path}


def _ffmpeg_check() -> dict:
    portable = portable_ffmpeg()
    if portable.exists():
        return {"ok": True, "path": str(portable), "portable": True}
    path = shutil.which("ffmpeg")
    return {"ok": path is not None, "path": path, "portable": False}


def _module_check(name: str) -> dict:
    spec = importlib.util.find_spec(name)
    return {"ok": spec is not None, "module": name}


def _cosyvoice_check() -> dict:
    spec = importlib.util.find_spec("cosyvoice")
    path = cosyvoice_path()
    package_file = path / "cosyvoice" / "cli" / "cosyvoice.py" if path else None
    return {
        "ok": spec is not None or bool(package_file and package_file.exists()),
        "module": "cosyvoice",
        "path": str(path) if path else None,
        "importable": spec is not None,
    }


def _path_check(path: Path) -> dict:
    return {"ok": path.exists(), "path": str(path), "size": path.stat().st_size if path.exists() else 0}


def _cuda_check() -> dict:
    try:
        import torch

        return {
            "ok": bool(torch.cuda.is_available()),
            "device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
            "device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _smoke_wav_fixture() -> dict:
    try:
        with tempfile.TemporaryDirectory(prefix="openinterview-smoke-") as temp_dir:
            path = Path(temp_dir) / "silence.wav"
            write_silence_wav(path, duration_ms=300)
            return {"ok": path.exists(), "bytes": path.stat().st_size}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _smoke_vad() -> dict:
    try:
        from ..voice.local_vad import SileroVAD

        with tempfile.TemporaryDirectory(prefix="openinterview-smoke-") as temp_dir:
            path = Path(temp_dir) / "silence.wav"
            write_silence_wav(path, duration_ms=300)
            result = SileroVAD().detect_file(path)
            return {"ok": "segments" in result, "speech_ms": result.get("speech_ms", 0)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _smoke_asr() -> dict:
    try:
        from ..voice.local_asr import SenseVoiceASR

        with tempfile.TemporaryDirectory(prefix="openinterview-smoke-") as temp_dir:
            path = Path(temp_dir) / "silence.wav"
            write_silence_wav(path, duration_ms=600)
            text = SenseVoiceASR().transcribe(path)
            return {"ok": isinstance(text, str), "text_chars": len(text)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _smoke_tts() -> dict:
    try:
        from ..voice.local_tts import CosyVoiceTTS

        with tempfile.TemporaryDirectory(prefix="openinterview-smoke-") as temp_dir:
            output = Path(temp_dir) / "speech.wav"
            CosyVoiceTTS().synthesize("你好，OpenInterview 语音自检。", output)
            return {"ok": output.exists() and output.stat().st_size > 44, "bytes": output.stat().st_size if output.exists() else 0}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
