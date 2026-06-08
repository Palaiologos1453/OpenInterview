from __future__ import annotations

import argparse
from pathlib import Path
import os
import sys
import logging


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser(description="CosyVoice local synthesis helper.")
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--reference-audio")
    parser.add_argument("--reference-text")
    parser.add_argument("--style-prompt")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    args = parser.parse_args()
    if args.device == "cpu":
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
        raise SystemExit(
            "CosyVoice runtime is not installed. Use Python 3.10 and install requirements-voice.txt."
        ) from exc

    if args.device == "auto" and not _cuda_is_supported(torch):
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        torch.cuda.is_available = lambda: False
    cosyvoice_file_utils.load_wav = _load_wav_with_soundfile(torch, librosa, sf)
    cosyvoice_frontend.load_wav = cosyvoice_file_utils.load_wav
    model = CosyVoice3(args.model_dir, load_trt=False, fp16=torch.cuda.is_available())
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    reference_audio = args.reference_audio
    reference_text = args.reference_text
    if not reference_audio and cosyvoice_path:
        default_prompt = Path(cosyvoice_path) / "asset" / "zero_shot_prompt.wav"
        if default_prompt.exists():
            reference_audio = str(default_prompt)
            reference_text = reference_text or "You are a helpful assistant.<|endofprompt|>希望你以后能够做的比我还好呦。"

    if args.style_prompt and reference_audio:
        instruct_text = f"You are a helpful assistant. {args.style_prompt}<|endofprompt|>"
        generator = model.inference_instruct2(args.text, instruct_text, reference_audio, stream=False)
    elif reference_audio and reference_text:
        generator = model.inference_zero_shot(args.text, reference_text, reference_audio, stream=False)
    else:
        raise SystemExit("CosyVoice3 requires reference audio for zero-shot or instruct synthesis.")

    first = next(generator)
    audio = first["tts_speech"]
    sample_rate = model.sample_rate
    _save_wav_with_soundfile(audio, output_path, sample_rate, sf)


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
