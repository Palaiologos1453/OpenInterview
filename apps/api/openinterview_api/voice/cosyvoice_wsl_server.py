"""Standalone WSL CosyVoice vLLM + TensorRT streaming service."""
from __future__ import annotations

import base64
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import librosa
import soundfile as sf
import torch

import cosyvoice.cli.frontend as frontend
import cosyvoice.utils.file_utils as files


def _load_wav(path: str, target_sr: int):
    audio, sample_rate = sf.read(path, dtype="float32", always_2d=False)
    if getattr(audio, "ndim", 1) > 1:
        audio = audio.mean(axis=1)
    if sample_rate != target_sr:
        audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=target_sr)
    return torch.from_numpy(audio).unsqueeze(0)


files.load_wav = _load_wav
frontend.load_wav = _load_wav
AutoModel = None


MODEL = os.environ.get("OPENINTERVIEW_COSYVOICE_MODEL", "/mnt/d/OpenInterview/models/tts/Fun-CosyVoice3-0.5B")
REFERENCE_AUDIO = os.environ.get("OPENINTERVIEW_COSYVOICE_REFERENCE_AUDIO", "/mnt/d/CosyVoice/asset/zero_shot_prompt.wav")
REFERENCE_TEXT = os.environ.get(
    "OPENINTERVIEW_COSYVOICE_REFERENCE_TEXT",
    "You are a helpful assistant.<|endofprompt|>希望你以后能够做的比我还好呦。",
)
PORT = int(os.environ.get("OPENINTERVIEW_COSYVOICE_PORT", "50051"))
MODEL_INSTANCE = None
CANCEL_EVENTS: dict[str, threading.Event] = {}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path.startswith("/v1/tts/abort/"):
            request_id = self.path.rsplit("/", 1)[-1]
            event = CANCEL_EVENTS.get(request_id)
            if event:
                event.set()
            self.send_response(200)
            self.end_headers()
            return
        if self.path != "/v1/tts/stream":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            text = str(payload.get("text") or "").strip()
            if not text:
                raise ValueError("text is required")
            request_id = str(payload.get("request_id") or "")
            cancel_event = threading.Event()
            if request_id:
                CANCEL_EVENTS[request_id] = cancel_event
            reference_audio = payload.get("reference_audio") or REFERENCE_AUDIO
            reference_text = payload.get("reference_text") or REFERENCE_TEXT
            style_prompt = payload.get("style_prompt")
            if style_prompt:
                reference_text = f"You are a helpful assistant. {style_prompt}<|endofprompt|>"
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            for index, item in enumerate(MODEL_INSTANCE.inference_zero_shot(text, reference_text, reference_audio, stream=True)):
                if cancel_event.is_set():
                    break
                pcm = item["tts_speech"].detach().cpu().float()
                if pcm.ndim == 2:
                    pcm = pcm[0]
                pcm = (torch.clamp(pcm, -1, 1) * 32767).to(torch.int16).numpy().tobytes()
                self.wfile.write((json.dumps({
                    "type": "chunk", "index": index, "sample_rate": MODEL_INSTANCE.sample_rate,
                    "channels": 1, "sample_width": 2,
                    "data": base64.b64encode(pcm).decode("ascii"),
                }) + "\n").encode("utf-8"))
                self.wfile.flush()
            self.wfile.write(b'{"type":"done"}\n')
            self.wfile.flush()
            if request_id:
                CANCEL_EVENTS.pop(request_id, None)
        except Exception as exc:
            try:
                self.wfile.write((json.dumps({"type": "error", "error": str(exc)}) + "\n").encode("utf-8"))
                self.wfile.flush()
            except Exception:
                pass

    def log_message(self, *_args):
        return


def main():
    global MODEL_INSTANCE, AutoModel
    from cosyvoice.cli.cosyvoice import AutoModel as CosyVoiceAutoModel
    AutoModel = CosyVoiceAutoModel
    MODEL_INSTANCE = AutoModel(model_dir=MODEL, load_trt=True, load_vllm=True, fp16=False)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
