"""Loopback-only configuration; no inference gateway or cloud defaults."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs" / "livekit.local.json"
AGENT_NAME = "openinterview-local"


def loopback_url(value: str, schemes=("http", "ws")) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme not in schemes or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("Local voice services must use a loopback URL without credentials.")
    return value.rstrip("/")


def load_config() -> dict:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    config["url"] = loopback_url(config["url"], ("ws",))
    config["api_url"] = loopback_url(os.environ.get("OPENINTERVIEW_API_URL", config["api_url"]), ("http",))
    return config


LOCAL_PROVIDERS = {
    "llm": {"provider": "mock"},
    "asr": {"provider": "sensevoice"},
    "tts": {"provider": "cosyvoice", "response_format": "wav", "voice_profile_id": "young_engineer"},
}
