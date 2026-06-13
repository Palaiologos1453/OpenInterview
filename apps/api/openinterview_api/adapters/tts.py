from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Protocol

from ..settings import default_tts_model_dir
from ..voice.local_tts import CosyVoiceTTS
from ..voice.voice_profiles import VoiceProfile
from ..voice.voice_profiles import find_voice_profile


class TTSAdapter(Protocol):
    def synthesize(
        self,
        text: str,
        output_path: Path,
        *,
        voice: str | None = None,
        voice_profile: VoiceProfile | None = None,
    ) -> Path:
        """Convert text to speech and return the generated audio path."""


@dataclass
class DisabledTTSAdapter:
    reason: str = "TTS is disabled in MVP."

    def synthesize(
        self,
        text: str,
        output_path: Path,
        *,
        voice: str | None = None,
        voice_profile: VoiceProfile | None = None,
    ) -> Path:
        del text, output_path, voice, voice_profile
        raise NotImplementedError(self.reason)


@dataclass
class PiperTTSAdapter:
    executable: str = "piper"
    model_path: Path | None = None

    def synthesize(
        self,
        text: str,
        output_path: Path,
        *,
        voice: str | None = None,
        voice_profile: VoiceProfile | None = None,
    ) -> Path:
        del text, output_path, voice, voice_profile
        raise NotImplementedError("Call Piper CLI or library here.")


@dataclass
class APITTSAdapter:
    api_base: str
    model: str
    api_key: str
    response_format: str = "mp3"
    timeout_seconds: int = 60

    def synthesize(
        self,
        text: str,
        output_path: Path,
        *,
        voice: str | None = None,
        voice_profile: VoiceProfile | None = None,
    ) -> Path:
        del voice_profile
        endpoint = _openai_speech_endpoint(self.api_base)
        payload = {
            "model": self.model,
            "input": text,
            "voice": voice or "alloy",
            "response_format": self.response_format,
        }
        request = Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                output_path.write_bytes(response.read())
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"TTS provider HTTP {exc.code}: {body[:300]}") from exc
        except URLError as exc:
            raise RuntimeError(f"TTS provider network error: {exc.reason}") from exc
        return output_path


def build_tts_adapter(config: dict | None) -> TTSAdapter:
    settings = (config or {}).get("tts", config or {})
    provider = (settings.get("provider") or "browser").strip().lower()
    if provider in {"", "browser", "disabled"}:
        return DisabledTTSAdapter()
    if provider in {"openai", "openai_compatible", "compatible"}:
        api_base = settings.get("api_base") or "https://api.openai.com/v1"
        model = settings.get("model") or "gpt-4o-mini-tts"
        api_key = settings.get("api_key") or ""
        if not api_key:
            raise ValueError("TTS API key is required for OpenAI-compatible provider.")
        return APITTSAdapter(
            api_base=api_base,
            model=model,
            api_key=api_key,
            response_format=settings.get("response_format") or "mp3",
            timeout_seconds=int(settings.get("timeout_seconds") or 60),
        )
    if provider == "piper":
        return PiperTTSAdapter(model_path=Path(settings["model"]) if settings.get("model") else None)
    if provider in {"cosyvoice", "local_cosyvoice"}:
        return CosyVoiceTTS(model_dir=Path(settings.get("model") or default_tts_model_dir()))
    raise ValueError(f"Unknown TTS provider: {provider}")


def tts_voice_profile(config: dict | None):
    settings = (config or {}).get("tts", config or {})
    return find_voice_profile(settings.get("voice_profile_id"))


def _openai_speech_endpoint(api_base: str) -> str:
    base = api_base.rstrip("/")
    if base.endswith("/audio/speech"):
        return base
    if base.endswith("/v1"):
        return f"{base}/audio/speech"
    return f"{base}/v1/audio/speech"
