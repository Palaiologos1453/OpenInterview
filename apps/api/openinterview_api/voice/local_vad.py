from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import wave

from ..settings import default_vad_model


@dataclass
class VADSegment:
    start_ms: int
    end_ms: int
    speech_probability: float


class SileroVAD:
    def __init__(self, model_path: Path | None = None, threshold: float = 0.5):
        self.model_path = model_path or default_vad_model()
        self.threshold = threshold

    def detect_file(self, audio_path: Path) -> dict:
        if not self.model_path.exists():
            return _energy_vad(audio_path, self.threshold, reason=f"Silero VAD model not found: {self.model_path}")
        try:
            import numpy as np
            import onnxruntime as ort
        except ImportError as exc:
            return _energy_vad(audio_path, self.threshold, reason=f"Silero VAD dependency missing: {exc}")

        samples, sample_rate = _read_wav_mono(audio_path)
        if sample_rate != 16000:
            raise ValueError("MVP local VAD expects 16kHz mono WAV input.")

        session = ort.InferenceSession(str(self.model_path), providers=["CPUExecutionProvider"])
        input_names = [item.name for item in session.get_inputs()]
        window = 512
        state = np.zeros((2, 1, 128), dtype=np.float32)
        context = np.zeros((1, 64), dtype=np.float32)
        speech_windows = []

        for offset in range(0, len(samples), window):
            chunk = samples[offset:offset + window]
            if len(chunk) < window:
                chunk = np.pad(chunk, (0, window - len(chunk)))
            model_input = np.concatenate([context, chunk.reshape(1, -1)], axis=1).astype(np.float32)
            inputs = {
                input_names[0]: model_input,
                input_names[1]: state,
                input_names[2]: np.array(sample_rate, dtype=np.int64),
            }
            output = session.run(None, inputs)
            probability = float(np.squeeze(output[0]))
            state = output[1]
            context = model_input[:, -64:]
            if probability >= self.threshold:
                start_ms = int(offset / sample_rate * 1000)
                end_ms = int((offset + window) / sample_rate * 1000)
                speech_windows.append(VADSegment(start_ms, end_ms, probability))

        merged = _merge_segments(speech_windows)
        return {
            "provider": "silero",
            "sample_rate": sample_rate,
            "duration_ms": int(len(samples) / sample_rate * 1000),
            "speech_ms": sum(item.end_ms - item.start_ms for item in merged),
            "segments": [item.__dict__ for item in merged],
        }


def _read_wav_mono(path: Path) -> tuple[object, int]:
    import numpy as np

    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_rate = wav.getframerate()
        sample_width = wav.getsampwidth()
        frames = wav.readframes(wav.getnframes())
    if sample_width != 2:
        raise ValueError("MVP local VAD expects 16-bit PCM WAV input.")
    data = np.frombuffer(frames, dtype=np.int16)
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1).astype(np.int16)
    samples = data.astype(np.float32) / 32768.0
    return samples, sample_rate


def _energy_vad(path: Path, threshold: float, *, reason: str) -> dict:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_rate = wav.getframerate()
        sample_width = wav.getsampwidth()
        frames = wav.readframes(wav.getnframes())
    if sample_width != 2:
        raise ValueError("Fallback VAD expects 16-bit PCM WAV input.")

    sample_count = len(frames) // 2
    if sample_count <= 0:
        return {
            "provider": "energy_fallback",
            "fallback_reason": reason,
            "sample_rate": sample_rate,
            "duration_ms": 0,
            "speech_ms": 0,
            "segments": [],
        }

    values = [int.from_bytes(frames[index:index + 2], "little", signed=True) for index in range(0, len(frames), 2)]
    if channels > 1:
        mono = []
        for index in range(0, len(values), channels):
            chunk = values[index:index + channels]
            if chunk:
                mono.append(sum(chunk) / len(chunk))
        values = mono

    window_size = max(sample_rate // 20, 1)
    speech_windows: list[VADSegment] = []
    energy_threshold = max(500.0, 5000.0 * threshold)
    for offset in range(0, len(values), window_size):
        window = values[offset:offset + window_size]
        if not window:
            continue
        mean_abs = sum(abs(item) for item in window) / len(window)
        if mean_abs >= energy_threshold:
            start_ms = int(offset / sample_rate * 1000)
            end_ms = int(min(offset + window_size, len(values)) / sample_rate * 1000)
            speech_windows.append(VADSegment(start_ms, end_ms, min(mean_abs / 32768.0, 1.0)))

    merged = _merge_segments(speech_windows)
    return {
        "provider": "energy_fallback",
        "fallback_reason": reason,
        "sample_rate": sample_rate,
        "duration_ms": int(len(values) / sample_rate * 1000),
        "speech_ms": sum(item.end_ms - item.start_ms for item in merged),
        "segments": [item.__dict__ for item in merged],
    }


def _merge_segments(windows: list[VADSegment], max_gap_ms: int = 250) -> list[VADSegment]:
    if not windows:
        return []
    merged = [windows[0]]
    for window in windows[1:]:
        last = merged[-1]
        if window.start_ms - last.end_ms <= max_gap_ms:
            last.end_ms = window.end_ms
            last.speech_probability = max(last.speech_probability, window.speech_probability)
        else:
            merged.append(window)
    return merged
