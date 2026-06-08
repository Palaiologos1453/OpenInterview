from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

import yaml

from ..settings import project_root


@dataclass
class VoiceProfile:
    id: str
    name: str
    persona: str
    gender: str
    style: str
    provider: str
    mode: str
    reference_audio: str | None = None
    reference_text: str | None = None
    style_prompt: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def load_voice_profiles(path: Path | None = None) -> list[VoiceProfile]:
    profile_path = path or project_root() / "configs" / "voice-profiles.example.yaml"
    if not profile_path.exists():
        return _default_profiles()
    data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    profiles = []
    for item in data.get("voice_profiles", []):
        profiles.append(VoiceProfile(**item))
    return profiles


def find_voice_profile(profile_id: str | None) -> VoiceProfile | None:
    if not profile_id:
        return None
    for profile in load_voice_profiles():
        if profile.id == profile_id:
            return profile
    return None


def _default_profiles() -> list[VoiceProfile]:
    return [
        VoiceProfile(
            id="young_engineer",
            name="青年工程师",
            persona="技术一面",
            gender="male",
            style="calm, concise, technical",
            provider="cosyvoice",
            mode="instruct",
            style_prompt="年轻男性工程师，语速中等，表达清晰，技术面试风格。",
        )
    ]

