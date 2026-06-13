from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from uuid import uuid4
import wave

from ..settings import cosyvoice_path
from ..settings import default_tts_model_dir
from ..settings import portable_ffmpeg
from ..settings import project_root
from .voice_profiles import VoiceProfile


_WORKERS: dict[str, "CosyVoiceWorker"] = {}
_WORKERS_LOCK = threading.Lock()


@dataclass
class CosyVoiceTTS:
    model_dir: Path | None = None

    def synthesize(
        self,
        text: str,
        output_path: Path,
        *,
        voice_profile: VoiceProfile | None = None,
        voice: str | None = None,
    ) -> Path:
        del voice
        model_dir = self.model_dir or default_tts_model_dir()
        if not model_dir.exists():
            raise FileNotFoundError(f"CosyVoice model directory not found: {model_dir}")

        try:
            worker = _cached_worker(model_dir)
            return worker.synthesize(text, output_path, voice_profile=voice_profile)
        except Exception:
            pass

        helper = Path(__file__).with_name("cosyvoice_cli.py")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            str(_voice_python()),
            str(helper),
            "--model-dir",
            str(model_dir),
            "--text",
            text,
            "--output",
            str(output_path),
        ]
        if voice_profile:
            reference_audio = voice_profile.resolved_reference_audio()
            if reference_audio:
                command.extend(["--reference-audio", str(reference_audio)])
            if voice_profile.reference_text:
                command.extend(["--reference-text", voice_profile.reference_text])
            if voice_profile.style_prompt:
                command.extend(["--style-prompt", voice_profile.style_prompt])

        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=180,
                env=_voice_subprocess_env(),
            )
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(exc.stderr.strip() or exc.stdout.strip()) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("CosyVoice synthesis timed out.") from exc

        return output_path


class CosyVoiceWorker:
    def __init__(self, model_dir: Path):
        self.model_dir = model_dir
        self.lock = threading.Lock()
        helper = Path(__file__).with_name("cosyvoice_worker.py")
        self.process = subprocess.Popen(
            [
                str(_voice_python()),
                str(helper),
                "--model-dir",
                str(model_dir),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=_voice_subprocess_env(),
        )
        ready = self.process.stdout.readline() if self.process.stdout else ""
        payload = json.loads(ready or "{}")
        if payload.get("type") != "ready":
            error = self.process.stderr.readline().strip() if self.process.stderr else ""
            raise RuntimeError(error or "CosyVoice worker failed to start.")

    def synthesize(
        self,
        text: str,
        output_path: Path,
        *,
        voice_profile: VoiceProfile | None = None,
    ) -> Path:
        if not self.process.stdin or not self.process.stdout:
            raise RuntimeError("CosyVoice worker pipes are closed.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        request = {
            "type": "synthesize",
            "id": uuid4().hex,
            "text": text,
            "output": str(output_path),
        }
        if voice_profile:
            reference_audio = voice_profile.resolved_reference_audio()
            request["reference_audio"] = str(reference_audio) if reference_audio else None
            request["reference_text"] = voice_profile.reference_text
            request["style_prompt"] = voice_profile.style_prompt
        with self.lock:
            self.process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
            line = self.process.stdout.readline()
        payload = json.loads(line or "{}")
        if payload.get("type") == "error":
            raise RuntimeError(payload.get("error") or "CosyVoice worker failed.")
        if payload.get("type") != "result":
            raise RuntimeError("CosyVoice worker returned an unexpected response.")
        return Path(payload["output"])


def _cached_worker(model_dir: Path) -> CosyVoiceWorker:
    key = str(model_dir.resolve())
    with _WORKERS_LOCK:
        worker = _WORKERS.get(key)
        if worker is None or worker.process.poll() is not None:
            worker = CosyVoiceWorker(model_dir)
            _WORKERS[key] = worker
        return worker


def _voice_python() -> Path:
    local = project_root() / "voice_venv" / "Scripts" / "python.exe"
    return local if local.exists() else Path(sys.executable)


def _voice_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    python_paths: list[str] = []
    runtime_path = cosyvoice_path()
    if runtime_path:
        env.setdefault("OPENINTERVIEW_COSYVOICE_PATH", str(runtime_path))
        python_paths.extend(
            [
                str(runtime_path),
                str(runtime_path / "third_party" / "Matcha-TTS"),
            ]
        )
    existing_pythonpath = env.get("PYTHONPATH")
    if existing_pythonpath:
        python_paths.append(existing_pythonpath)
    if python_paths:
        env["PYTHONPATH"] = os.pathsep.join(python_paths)

    ffmpeg = portable_ffmpeg()
    if ffmpeg.exists():
        path_parts = [str(ffmpeg.parent), env.get("PATH", "")]
        env["PATH"] = os.pathsep.join(part for part in path_parts if part)
    return env


def write_silence_wav(output_path: Path, duration_ms: int = 300, sample_rate: int = 16000) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(sample_rate * duration_ms / 1000)
    with wave.open(str(output_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frames)
    return output_path


def ensure_wav_output(source: Path, target: Path) -> Path:
    if source == target:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target
