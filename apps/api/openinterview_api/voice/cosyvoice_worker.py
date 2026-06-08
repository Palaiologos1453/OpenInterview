from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import sys


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser(description="Long-running CosyVoice worker.")
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    args = parser.parse_args()
    runtime = _Runtime(args.model_dir, args.device)
    print(json.dumps({"type": "ready"}, ensure_ascii=False), flush=True)

    for line in sys.stdin:
        try:
            request = json.loads(line)
            if request.get("type") == "shutdown":
                break
            output = runtime.synthesize(request)
            print(json.dumps({"type": "result", "id": request.get("id"), "output": output}, ensure_ascii=False), flush=True)
        except Exception as exc:
            print(
                json.dumps({"type": "error", "id": request.get("id") if "request" in locals() else None, "error": str(exc)}, ensure_ascii=False),
                flush=True,
            )


class _Runtime:
    def __init__(self, model_dir: str, device: str):
        if device == "cpu":
            os.environ["CUDA_VISIBLE_DEVICES"] = ""
        cosyvoice_path = os.environ.get("OPENINTERVIEW_COSYVOICE_PATH")
        if cosyvoice_path:
            sys.path.insert(0, cosyvoice_path)
            sys.path.insert(0, str(Path(cosyvoice_path) / "third_party" / "Matcha-TTS"))

        try:
            import torch
            import librosa
            import soundfile as sf
            from cosyvoice.cli.cosyvoice import CosyVoice3
            import cosyvoice.cli.frontend as cosyvoice_frontend
            import cosyvoice.utils.file_utils as cosyvoice_file_utils
        except ImportError as exc:
            raise RuntimeError(
                "CosyVoice runtime is not installed. Use Python 3.10 and install requirements-voice.txt."
            ) from exc

        if device == "auto" and not _cuda_is_supported(torch):
            os.environ["CUDA_VISIBLE_DEVICES"] = ""
            torch.cuda.is_available = lambda: False

        cosyvoice_file_utils.load_wav = _load_wav_with_soundfile(torch, librosa, sf)
        cosyvoice_frontend.load_wav = cosyvoice_file_utils.load_wav
        self.model = CosyVoice3(model_dir, load_trt=False, fp16=torch.cuda.is_available())
        self.sample_rate = self.model.sample_rate
        self.sf = sf
        self.cosyvoice_path = cosyvoice_path

    def synthesize(self, request: dict) -> str:
        text = request["text"]
        output_path = Path(request["output"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        reference_audio = request.get("reference_audio")
        reference_text = request.get("reference_text")
        style_prompt = request.get("style_prompt")

        if not reference_audio and self.cosyvoice_path:
            default_prompt = Path(self.cosyvoice_path) / "asset" / "zero_shot_prompt.wav"
            if default_prompt.exists():
                reference_audio = str(default_prompt)
                reference_text = reference_text or "You are a helpful assistant.<|endofprompt|>希望你以后能够做的比我还好呦。"

        if style_prompt and reference_audio:
            instruct_text = f"You are a helpful assistant. {style_prompt}<|endofprompt|>"
            generator = self.model.inference_instruct2(text, instruct_text, reference_audio, stream=True)
        elif reference_audio and reference_text:
            generator = self.model.inference_zero_shot(text, reference_text, reference_audio, stream=True)
        else:
            raise RuntimeError("CosyVoice3 requires reference audio for zero-shot or instruct synthesis.")

        chunks = []
        for item in generator:
            chunks.append(item["tts_speech"])
        if not chunks:
            raise RuntimeError("CosyVoice returned no audio.")

        import torch

        audio = torch.cat(chunks, dim=-1)
        _save_wav_with_soundfile(audio, output_path, self.sample_rate, self.sf)
        return str(output_path)


def _cuda_is_supported(torch_module) -> bool:
    if not torch_module.cuda.is_available():
        return False
    try:
        major, minor = torch_module.cuda.get_device_capability(0)
        supported = torch_module.cuda.get_arch_list()
        return f"sm_{major}{minor}" in supported
    except Exception:
        return False


def _load_wav_with_soundfile(torch_module, librosa_module, soundfile_module):
    def load_wav(path: str, target_sr: int):
        audio, sample_rate = soundfile_module.read(path, dtype="float32", always_2d=False)
        if getattr(audio, "ndim", 1) > 1:
            audio = audio.mean(axis=1)
        if sample_rate != target_sr:
            audio = librosa_module.resample(audio, orig_sr=sample_rate, target_sr=target_sr)
        return torch_module.from_numpy(audio).unsqueeze(0)

    return load_wav


def _save_wav_with_soundfile(audio, output_path: Path, sample_rate: int, soundfile_module) -> None:
    data = audio.detach().cpu().float().numpy()
    if data.ndim == 2 and data.shape[0] == 1:
        data = data[0]
    elif data.ndim == 2:
        data = data.T
    soundfile_module.write(str(output_path), data, sample_rate)


if __name__ == "__main__":
    main()
