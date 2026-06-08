from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import threading

from ..settings import default_asr_model_dir


_MODEL_CACHE: dict[tuple[str, str], object] = {}
_MODEL_LOCK = threading.Lock()


@dataclass
class SenseVoiceASR:
    model_dir: Path | None = None
    device: str = "auto"

    def transcribe(self, audio_path: Path, *, language: str = "zh-CN") -> str:
        model_dir = self.model_dir or default_asr_model_dir()
        if not model_dir.exists():
            raise FileNotFoundError(f"SenseVoice model directory not found: {model_dir}")

        try:
            from funasr import AutoModel
        except ImportError as exc:
            raise RuntimeError(
                "funasr is required for local SenseVoice ASR. "
                "Install the voice runtime environment from requirements-voice.txt."
            ) from exc

        device = self._resolve_device()
        try:
            return self._transcribe_with_device(AutoModel, model_dir, audio_path, language, device)
        except Exception as exc:
            if device == "cuda" and _is_cuda_kernel_error(exc):
                return self._transcribe_with_device(AutoModel, model_dir, audio_path, language, "cpu")
            raise

    def _resolve_device(self) -> str:
        requested = (self.device or "auto").strip().lower()
        if requested != "auto":
            return requested
        try:
            import torch

            if not torch.cuda.is_available():
                return "cpu"
            major, minor = torch.cuda.get_device_capability(0)
            supported = getattr(torch.cuda, "get_arch_list", lambda: [])()
            if f"sm_{major}{minor}" not in supported:
                return "cpu"
            return "cuda"
        except Exception:
            return "cpu"

    def _transcribe_with_device(self, auto_model, model_dir: Path, audio_path: Path, language: str, device: str) -> str:
        model = _cached_model(auto_model, model_dir, device)
        result = model.generate(
            input=str(audio_path),
            language=_sensevoice_language(language),
            use_itn=True,
            batch_size_s=60,
            merge_vad=True,
        )
        return _extract_text(result)


def _cached_model(auto_model, model_dir: Path, device: str):
    key = (str(model_dir.resolve()), device)
    with _MODEL_LOCK:
        model = _MODEL_CACHE.get(key)
        if model is None:
            model = auto_model(
                model=str(model_dir),
                trust_remote_code=True,
                device=device,
                disable_update=True,
            )
            _MODEL_CACHE[key] = model
        return model


def _sensevoice_language(language: str) -> str:
    normalized = language.lower()
    if normalized.startswith("zh"):
        return "zh"
    if normalized.startswith("en"):
        return "en"
    return "auto"


def _is_cuda_kernel_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "no kernel image is available" in message or "cudaerrornokernelimagefordevice" in message


def _extract_text(result) -> str:
    if isinstance(result, str):
        return _clean_text(result)
    if isinstance(result, list):
        parts = []
        for item in result:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("sentence") or ""))
            else:
                parts.append(str(item))
        return _clean_text("\n".join(part for part in parts if part))
    if isinstance(result, dict):
        return _clean_text(str(result.get("text") or result.get("sentence") or ""))
    return _clean_text(str(result))


def _clean_text(text: str) -> str:
    return re.sub(r"<\|[^|]+?\|>", "", text).strip()
