from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from openinterview_api.voice.local_vad import SileroVAD


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test local voice runtime.")
    parser.add_argument("--vad-only", action="store_true")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="openinterview-smoke-") as temp_dir:
        wav_path = Path(temp_dir) / "silence.wav"
        _write_silence(wav_path)
        vad = SileroVAD().detect_file(wav_path)
        print({"vad": vad})

    if args.vad_only:
        return
    print("ASR/TTS smoke requires Python 3.10 voice environment with FunASR and CosyVoice installed.")


def _write_silence(path: Path) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 16000)


if __name__ == "__main__":
    main()
