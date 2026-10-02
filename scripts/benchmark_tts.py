"""Measure local CosyVoice cold/warm first PCM and completion latency.

Runs the real worker without an API server; never calls a paid provider.
"""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import queue
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from openinterview_api.voice.local_tts import _voice_python, _voice_subprocess_env  # noqa: E402
from openinterview_api.settings import default_tts_model_dir  # noqa: E402
from openinterview_api.voice.voice_profiles import find_voice_profile  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--text", default="请介绍你负责的项目，说明业务背景、个人贡献、技术方案和验证结果。")
    parser.add_argument("--output", type=Path, default=ROOT / "logs" / "tts-benchmark.json")
    parser.add_argument("--worker-script", type=Path, default=ROOT / "apps/api/openinterview_api/voice/cosyvoice_worker.py")
    parser.add_argument("--batch-only", action="store_true")
    args = parser.parse_args()
    started = time.perf_counter()
    process = subprocess.Popen(
        [str(_voice_python()), str(args.worker_script), "--model-dir", str(default_tts_model_dir())],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", env=_voice_subprocess_env(),
    )
    events = queue.Queue()
    errors = []

    def stdout_reader():
        for line in process.stdout:
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            if isinstance(payload, dict):
                events.put(payload)
        events.put({"type": "error", "error": "worker exited: " + "".join(errors[-10:])})

    def stderr_reader():
        for line in process.stderr:
            errors.append(line)
            del errors[:-30]

    threading.Thread(target=stdout_reader, daemon=True).start()
    threading.Thread(target=stderr_reader, daemon=True).start()
    rows = []
    try:
        ready = events.get(timeout=180)
        if ready.get("type") != "ready":
            raise RuntimeError(str(ready))
        load_ms = (time.perf_counter() - started) * 1000
        print(f"Worker load: {load_ms:.0f} ms", flush=True)
        with tempfile.TemporaryDirectory() as tmp:
            # First request captures cold inference, following pairs are warm.
            modes = [False] + ([False] if args.batch_only else [False, True]) * args.runs
            for index, stream in enumerate(modes):
                path = Path(tmp) / f"speech-{index}.wav"
                request = {"type": "synthesize", "id": str(index), "text": args.text,
                           "output": str(path), "stream": stream}
                profile = find_voice_profile("young_engineer")
                if profile:
                    ref = profile.resolved_reference_audio()
                    request.update(reference_audio=str(ref) if ref else None,
                                   reference_text=profile.reference_text, style_prompt=profile.style_prompt)
                started = time.perf_counter()
                process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
                process.stdin.flush()
                first_ms = None
                audio_seconds = 0
                chunks = 0
                while True:
                    event = events.get(timeout=180)
                    elapsed = (time.perf_counter() - started) * 1000
                    if event.get("type") == "error":
                        raise RuntimeError(str(event))
                    if event.get("type") == "chunk":
                        first_ms = elapsed if first_ms is None else first_ms
                        chunks += 1
                        audio_seconds += len(base64.b64decode(event["data"])) / (
                            event["sample_rate"] * event["channels"] * event["sample_width"])
                    if event.get("type") == "result":
                        if not stream:
                            first_ms = elapsed
                            with wave.open(str(path), "rb") as wav:
                                audio_seconds = wav.getnframes() / wav.getframerate()
                        break
                row = {"mode": "stream" if stream else "batch", "cold": index == 0,
                       "first_audio_ms": round(first_ms, 2), "total_ms": round(elapsed, 2),
                       "audio_seconds": round(audio_seconds, 3), "chunks": chunks,
                       "rtf": round(elapsed / 1000 / audio_seconds, 3)}
                rows.append(row)
                print(json.dumps(row), flush=True)
        summary = {}
        for mode in ("batch", "stream"):
            warm = [row["first_audio_ms"] for row in rows if row["mode"] == mode and not row["cold"]]
            if warm:
                summary[mode + "_warm_first_audio_median_ms"] = statistics.median(warm)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({"text": args.text, "worker": str(args.worker_script),
            "worker_load_ms": round(load_ms, 2), "summary": summary, "runs": rows},
            ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        for pipe in (process.stdin, process.stdout, process.stderr):
            pipe.close()


if __name__ == "__main__":
    main()
