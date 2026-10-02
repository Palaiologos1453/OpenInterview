from __future__ import annotations

from dataclasses import dataclass
import atexit
from collections import deque
import json
import os
import queue
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from time import monotonic
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

        return _cached_worker(model_dir).synthesize(text, output_path, voice_profile=voice_profile)

    def synthesize_stream(
        self, text: str, output_path: Path, *,
        voice_profile: VoiceProfile | None = None, voice: str | None = None,
    ):
        """Yield native PCM immediately; never replay a failed partial stream."""
        del voice
        model_dir = self.model_dir or default_tts_model_dir()
        if not model_dir.exists():
            raise FileNotFoundError(f"CosyVoice model directory not found: {model_dir}")
        yield from _cached_worker(model_dir).synthesize_stream(
            text, output_path, voice_profile=voice_profile)


class CosyVoiceWorker:
    def __init__(self, model_dir: Path):
        self.model_dir = model_dir
        self.lock = threading.Lock()
        self.events = queue.Queue()
        self.diagnostics = deque(maxlen=20)
        self.closed = False
        helper = Path(__file__).with_name("cosyvoice_worker.py")
        self.process = subprocess.Popen(
            [str(_voice_python()), str(helper), "--model-dir", str(model_dir)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            env=_voice_subprocess_env(),
        )
        # Drain both pipes continuously: progress logs must never fill stderr
        # and deadlock inference. A queue gives Windows pipe reads a deadline.
        self.readers = [
            threading.Thread(target=self._read_stdout, daemon=True),
            threading.Thread(target=self._read_stderr, daemon=True),
        ]
        for reader in self.readers:
            reader.start()
        try:
            payload = self._receive(monotonic() + 180)
            if payload.get("type") != "ready":
                raise RuntimeError("CosyVoice worker failed to start: " + str(payload))
        except BaseException:
            self.close()
            raise

    def _read_stdout(self):
        try:
            for line in self.process.stdout:
                try:
                    payload = json.loads(line)
                except ValueError:
                    self.diagnostics.append(line.strip())
                    continue
                if isinstance(payload, dict):
                    self.events.put(payload)
        finally:
            self.events.put({"type": "eof"})

    def _read_stderr(self):
        for line in self.process.stderr:
            self.diagnostics.append(line.strip())

    def _receive(self, deadline):
        try:
            payload = self.events.get(timeout=max(deadline - monotonic(), 0))
        except queue.Empty as exc:
            raise RuntimeError("CosyVoice worker timed out.") from exc
        if payload.get("type") == "eof":
            raise RuntimeError("CosyVoice worker exited: " + "\n".join(self.diagnostics))
        return payload

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        for reader in self.readers:
            reader.join(timeout=2)
        for pipe in (self.process.stdin, self.process.stdout, self.process.stderr):
            pipe.close()

    def _request(self, text, output_path, voice_profile, *, stream):
        request = {"type": "synthesize", "id": uuid4().hex, "text": text,
                   "output": str(output_path), "stream": stream}
        if voice_profile:
            ref = voice_profile.resolved_reference_audio()
            request.update(reference_audio=str(ref) if ref else None,
                           reference_text=voice_profile.reference_text,
                           style_prompt=voice_profile.style_prompt)
        # Serialize all requests and readers. Early close drains the response;
        # timeout/protocol failure discards the worker to prevent stale chunks.
        if not self.lock.acquire(timeout=180):
            raise RuntimeError("CosyVoice worker is busy; retry later.")
        completed = False
        draining = False
        deadline = monotonic() + 180
        try:
            if self.closed or self.process.poll() is not None:
                raise RuntimeError("CosyVoice worker is closed; retry the request.")
            self.process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
            deadline = monotonic() + 180
            while True:
                payload = self._receive(deadline)
                if payload.get("id") != request["id"]:
                    raise RuntimeError("CosyVoice worker response ID mismatch.")
                kind = payload.get("type")
                if kind == "error":
                    completed = True
                    raise RuntimeError(payload.get("error") or "CosyVoice worker failed.")
                if kind == "result":
                    completed = True
                    yield payload
                    return
                if kind != "chunk" or not stream:
                    raise RuntimeError("CosyVoice worker returned an unexpected response.")
                yield payload
        except GeneratorExit:
            if not completed and self.process.poll() is None:
                # Playback interruption must not unload the GPU model. Finish
                # consuming this request in the background, discard old audio,
                # and keep the lock until its terminal response has been read.
                draining = True
                threading.Thread(target=self._drain_request,
                    args=(request["id"], deadline), daemon=True).start()
            raise
        finally:
            if not completed and not draining:
                self.close()
            if not draining:
                self.lock.release()

    def _drain_request(self, request_id, deadline):
        try:
            while True:
                payload = self._receive(deadline)
                if payload.get("id") != request_id:
                    raise RuntimeError("CosyVoice drain response ID mismatch")
                if payload.get("type") in {"result", "error"}:
                    return
                if payload.get("type") != "chunk":
                    raise RuntimeError("Unexpected CosyVoice drain response")
        except Exception:
            self.close()
        finally:
            self.lock.release()

    def synthesize(self, text, output_path, *, voice_profile=None) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        for payload in self._request(text, output_path, voice_profile, stream=False):
            return Path(payload["output"])
        raise RuntimeError("CosyVoice returned no output.")

    def synthesize_stream(self, text, output_path, *, voice_profile=None):
        iterator = self._request(text, output_path, voice_profile, stream=True)
        try:
            for payload in iterator:
                if payload["type"] == "chunk":
                    yield payload
        finally:
            iterator.close()


def _cached_worker(model_dir: Path) -> CosyVoiceWorker:
    key = str(model_dir.resolve())
    with _WORKERS_LOCK:
        worker = _WORKERS.get(key)
        if worker is None or worker.closed or worker.process.poll() is not None:
            worker = CosyVoiceWorker(model_dir)
            _WORKERS[key] = worker
        return worker


def _voice_python() -> Path:
    local = project_root() / "voice_venv" / "Scripts" / "python.exe"
    return local if local.exists() else Path(sys.executable)


def _voice_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
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


@atexit.register
def close_tts_workers():
    with _WORKERS_LOCK:
        workers = list(_WORKERS.values())
        _WORKERS.clear()
    for worker in workers:
        worker.close()
