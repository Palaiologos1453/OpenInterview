from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Protocol

from ..settings import default_asr_model_dir
from ..voice.local_asr import SenseVoiceASR


class ASRAdapter(Protocol):
    def transcribe(self, audio_path: Path, *, language: str = "zh-CN") -> str:
        """Convert an audio file to text."""


@dataclass
class DisabledASRAdapter:
    reason: str = "ASR is disabled in MVP."

    def transcribe(self, audio_path: Path, *, language: str = "zh-CN") -> str:
        del audio_path, language
        raise NotImplementedError(self.reason)


@dataclass
class FasterWhisperASRAdapter:
    model_size: str = "small"
    device: str = "auto"

    def transcribe(self, audio_path: Path, *, language: str = "zh-CN") -> str:
        del audio_path, language
        raise NotImplementedError("Install faster-whisper and implement local transcription here.")


@dataclass
class APIASRAdapter:
    api_base: str
    model: str
    api_key: str
    timeout_seconds: int = 60

    def transcribe(self, audio_path: Path, *, language: str = "zh-CN") -> str:
        endpoint = _openai_transcription_endpoint(self.api_base)
        boundary = f"----OpenInterview{uuid.uuid4().hex}"
        body = _multipart_body(
            boundary,
            fields={"model": self.model, "language": language},
            files={"file": audio_path},
        )
        request = Request(
            endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"ASR provider HTTP {exc.code}: {body_text[:300]}") from exc
        except URLError as exc:
            raise RuntimeError(f"ASR provider network error: {exc.reason}") from exc

        text = payload.get("text")
        if not isinstance(text, str):
            raise RuntimeError("ASR provider returned an unexpected response shape.")
        return text


def build_asr_adapter(config: dict | None) -> ASRAdapter:
    settings = (config or {}).get("asr", config or {})
    provider = (settings.get("provider") or "browser").strip().lower()
    if provider in {"", "browser", "disabled"}:
        return DisabledASRAdapter()
    if provider in {"openai", "openai_compatible", "compatible"}:
        api_base = settings.get("api_base") or "https://api.openai.com/v1"
        model = settings.get("model") or "gpt-4o-mini-transcribe"
        api_key = settings.get("api_key") or ""
        if not api_key:
            raise ValueError("ASR API key is required for OpenAI-compatible provider.")
        return APIASRAdapter(
            api_base=api_base,
            model=model,
            api_key=api_key,
            timeout_seconds=int(settings.get("timeout_seconds") or 60),
        )
    if provider == "faster_whisper":
        return FasterWhisperASRAdapter(model_size=settings.get("model") or "small")
    if provider in {"sensevoice", "local_sensevoice"}:
        model_dir = Path(settings.get("model") or default_asr_model_dir())
        return SenseVoiceASR(
            model_dir=model_dir,
            device=settings.get("device") or "auto",
        )
    raise ValueError(f"Unknown ASR provider: {provider}")


def _openai_transcription_endpoint(api_base: str) -> str:
    base = api_base.rstrip("/")
    if base.endswith("/audio/transcriptions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/audio/transcriptions"
    return f"{base}/v1/audio/transcriptions"


def _multipart_body(boundary: str, *, fields: dict[str, str], files: dict[str, Path]) -> bytes:
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                f"{value}\r\n".encode(),
            ]
        )
    for name, path in files.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="{name}"; '
                    f'filename="{path.name}"\r\n'
                ).encode(),
                b"Content-Type: application/octet-stream\r\n\r\n",
                path.read_bytes(),
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks)
