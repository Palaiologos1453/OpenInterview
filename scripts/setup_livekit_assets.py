"""Install pinned official Windows server and generate private loopback config."""
import hashlib
import json
from pathlib import Path
import secrets
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.13.7"
SERVER_SHA256 = "e539e7d2f75807b9c9202cd2a0bf2cb3d52fc4c52978a6953e0f47bc339fe77f"


def main():
    target = ROOT / "tools" / "livekit" / VERSION
    target.mkdir(parents=True, exist_ok=True)
    archive = target / f"livekit_{VERSION}_windows_amd64.zip"
    if not archive.exists():
        urllib.request.urlretrieve(
            f"https://github.com/livekit/livekit/releases/download/v{VERSION}/{archive.name}", archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SERVER_SHA256:
        raise RuntimeError("LiveKit server checksum mismatch")
    with zipfile.ZipFile(archive) as bundle:
        for name in ("livekit-server.exe", "LICENSE"):
            (target / name).write_bytes(bundle.read(name))
    path = ROOT / "configs" / "livekit.local.json"
    if not path.exists():
        path.write_text(json.dumps({"url": "ws://127.0.0.1:7880", "api_url": "http://127.0.0.1:8000",
            "api_key": "oi-" + secrets.token_hex(8), "api_secret": secrets.token_hex(32)}, indent=2), encoding="utf-8")
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    import yaml
    (ROOT / "configs" / "livekit.local.yaml").write_text(yaml.safe_dump({
        "port": 7880, "bind_addresses": ["127.0.0.1"],
        "rtc": {"tcp_port": 7881, "udp_port": 7882, "use_external_ip": False,
                "node_ip": "127.0.0.1", "stun_servers": []},
        "keys": {config["api_key"]: config["api_secret"]},
        "logging": {"level": "info"},
    }), encoding="utf-8")
    print("Verified LiveKit server and generated loopback config (credentials not printed).")


if __name__ == "__main__":
    main()
