from __future__ import annotations

import asyncio
import base64
from pathlib import Path
import re
import tempfile
from time import perf_counter
from typing import Awaitable, Callable
import wave

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from ..adapters.asr import build_asr_adapter
from ..adapters.tts import build_tts_adapter, tts_voice_profile
from ..interview_engine import CampusInterviewEngine, InterviewSession
from ..storage import Storage
from ..tracing import Trace
from ..voice.audio import ensure_16k_mono_wav, is_pcm_s16le_encoding, write_pcm_s16le_wav
from ..voice.local_vad import SileroVAD
from .realtime import RealtimeSession


SendJson = Callable[[dict], Awaitable[None]]


class DuplexRealtimeConnection:
    def __init__(
        self,
        *,
        websocket: WebSocket,
        realtime_session: RealtimeSession,
        interview_session: InterviewSession,
        engine: CampusInterviewEngine,
        storage: Storage,
    ):
        self.websocket = websocket
        self.realtime_session = realtime_session
        self.interview_session = interview_session
        self.engine = engine
        self.storage = storage
        self.provider_config: dict = {}
        self.mime_type = "audio/webm"
        self.audio_encoding = "webm"
        self.sample_rate = 16000
        self.channels = 1
        self.audio_chunks: list[bytes] = []
        self.cancel_generation = 0
        self.partial_interval_chunks = 8
        self.partial_window_chunks = 12
        self.enable_partial_asr = False
        self.partial_task: asyncio.Task | None = None
        self.send_lock = asyncio.Lock()
        self.turn_started_at = 0.0
        self.turn_timings: dict[str, float] = {}

    async def run(self) -> None:
        await self.websocket.accept()
        await self._send(
            {
                "type": "ready",
                "session": self.realtime_session.as_dict(),
                "protocol": "openinterview.realtime.v1",
            }
        )
        try:
            while True:
                message = await self.websocket.receive_json()
                await self._handle_message(message)
        except WebSocketDisconnect:
            return

    async def _handle_message(self, message: dict) -> None:
        event_type = message.get("type")
        if event_type == "start":
            self.provider_config = message.get("provider_config") or {}
            self.mime_type = message.get("mime_type") or "audio/webm"
            self.audio_encoding = message.get("audio_encoding") or self.mime_type
            self.sample_rate = int(message.get("sample_rate") or 16000)
            self.channels = int(message.get("channels") or 1)
            self.partial_interval_chunks = int(message.get("partial_interval_chunks") or 8)
            self.partial_window_chunks = int(message.get("partial_window_chunks") or 12)
            self.enable_partial_asr = bool(message.get("enable_partial_asr"))
            self.audio_chunks = []
            self.realtime_session.record(
                "user_speech_start",
                {
                    "mime_type": self.mime_type,
                    "audio_encoding": self.audio_encoding,
                    "sample_rate": self.sample_rate,
                    "channels": self.channels,
                },
            )
            await self._send({"type": "listening", "session": self.realtime_session.as_dict()})
            return

        if event_type == "audio":
            if message.get("audio_encoding"):
                self.audio_encoding = message["audio_encoding"]
            if message.get("sample_rate"):
                self.sample_rate = int(message["sample_rate"])
            if message.get("channels"):
                self.channels = int(message["channels"])
            chunk = _decode_audio_chunk(message)
            if chunk:
                self.audio_chunks.append(chunk)
            if len(self.audio_chunks) % max(self.partial_interval_chunks, 1) == 0:
                await self._send(
                    {
                        "type": "asr_partial",
                        "text": "",
                        "is_final": False,
                        "audio_bytes": sum(len(item) for item in self.audio_chunks),
                    }
                )
                self._schedule_partial_asr()
            return

        if event_type == "commit":
            await self._finalize_audio_turn(message)
            return

        if event_type == "cancel":
            self.cancel_generation += 1
            self.audio_chunks = []
            self.realtime_session.record("cancel", {"reason": "client_cancel"})
            await self._send({"type": "cancelled", "session": self.realtime_session.as_dict()})
            return

        await self._send({"type": "error", "error": f"Unknown realtime event: {event_type}"})

    async def _finalize_audio_turn(self, message: dict) -> None:
        if self.partial_task and not self.partial_task.done():
            self.partial_task.cancel()
        if message.get("provider_config"):
            self.provider_config = message["provider_config"]
        if not self.provider_config:
            await self._send({"type": "error", "error": "provider_config is required before commit."})
            return
        if not self.audio_chunks:
            await self._send({"type": "error", "error": "No audio chunks received."})
            return

        generation = self.cancel_generation
        trace = Trace()
        self.turn_started_at = perf_counter()
        self.turn_timings = {}
        suffix = _suffix_for_mime(self.mime_type)
        audio = b"".join(self.audio_chunks)
        self.audio_chunks = []

        with tempfile.TemporaryDirectory(prefix="openinterview-ws-") as temp_dir:
            temp_root = Path(temp_dir)
            input_path = temp_root / f"input{suffix}"
            wav_path = temp_root / "input.wav"
            try:
                await self._send({"type": "vad_start"})
                started = perf_counter()
                with trace.span("realtime.ws.audio.convert"):
                    if is_pcm_s16le_encoding(self.audio_encoding):
                        model_input = write_pcm_s16le_wav(
                            audio,
                            wav_path,
                            sample_rate=self.sample_rate,
                            channels=self.channels,
                        )
                    else:
                        input_path.write_bytes(audio)
                        model_input = ensure_16k_mono_wav(input_path, wav_path)
                await self._record_timing("convert_ms", started)
                self.realtime_session.record("vad_endpoint", {})
                started = perf_counter()
                with trace.span("vad.detect"):
                    vad = SileroVAD(
                        threshold=float(message.get("vad_threshold") or 0.5)
                    ).detect_file(model_input)
                await self._record_timing("vad_ms", started)
                await self._send({"type": "vad_final", "vad": vad})
                if vad.get("speech_ms", 0) <= 0:
                    self.realtime_session.record("cancel", {"reason": "no_speech"})
                    self.storage.save_trace(trace.as_dict(), interview_id=self.realtime_session.interview_id)
                    await self._record_timing("total_ms", self.turn_started_at)
                    await self._send(
                        {
                            "type": "done",
                            "skipped": True,
                            "reason": "no_speech",
                            "session": self.realtime_session.as_dict(),
                            "timings": dict(self.turn_timings),
                        }
                    )
                    return

                await self._send({"type": "asr_start"})
                config = self.provider_config
                asr_adapter = build_asr_adapter(config)
                started = perf_counter()
                with trace.span("asr.transcribe", provider=(config.get("asr") or {}).get("provider")):
                    text = await asyncio.to_thread(
                        asr_adapter.transcribe,
                        model_input,
                        language=(config.get("asr") or {}).get("language") or "zh-CN",
                    )
                await self._record_timing("asr_ms", started)
                text = text.strip()
                self.storage.save_transcript(
                    text,
                    source=(config.get("asr") or {}).get("provider") or "unknown",
                    interview_id=self.realtime_session.interview_id,
                )
                self.realtime_session.record("asr_final", {"text": text})
                await self._send({"type": "asr_final", "text": text, "is_final": True})

                started = perf_counter()
                with trace.span("interview.turn", answer_chars=len(text)):
                    turn_payload = self.engine.answer(self.interview_session, text)
                await self._record_timing("turn_ms", started)
                turn = self.interview_session.history[-1]
                self.storage.save_turn(
                    self.interview_session.session_id,
                    turn_index=turn_payload["turn_index"],
                    question=turn.question,
                    answer=turn.answer,
                    feedback=turn.feedback,
                    tags=turn.tags,
                    score=turn.score,
                    question_meta=turn.question_meta,
                )
                await self._send({"type": "turn", "turn": turn_payload})

                speech_text = turn_payload["next_question"]
                if generation == self.cancel_generation:
                    started = perf_counter()
                    await self._stream_tts(speech_text, config, generation, temp_root / "speech")
                    await self._record_timing("tts_total_ms", started)
                self.storage.save_trace(trace.as_dict(), interview_id=self.realtime_session.interview_id)
                await self._record_timing("total_ms", self.turn_started_at)
                await self._send(
                    {
                        "type": "done",
                        "skipped": False,
                        "session": self.realtime_session.as_dict(),
                        "timings": dict(self.turn_timings),
                    }
                )
            except Exception as exc:
                self.realtime_session.record("cancel", {"reason": "error", "error": str(exc)})
                self.storage.save_trace(trace.as_dict(), interview_id=self.realtime_session.interview_id)
                await self._send({"type": "error", "error": str(exc)})

    async def _stream_tts(
        self,
        text: str,
        config: dict,
        generation: int,
        output_base: Path,
    ) -> None:
        tts_settings = config.get("tts") or {}
        provider = (tts_settings.get("provider") or "browser").strip().lower()
        if provider in {"", "browser", "disabled"}:
            await self._send(
                {
                    "type": "tts_start",
                    "provider": provider or "browser",
                    "format": "browser",
                    "media_type": "browser",
                    "text": text,
                }
            )
            await self._send({"type": "tts_text", "text": text})
            await self._send({"type": "tts_done"})
            return

        adapter = build_tts_adapter(config)
        audio_format = tts_settings.get("response_format") or "mp3"
        voice_profile = tts_voice_profile(config)
        self.realtime_session.record("tts_start", {"audio_id": f"turn-{self.interview_session.turn_index}"})
        await self._send(
            {
                "type": "tts_start",
                "provider": provider,
                "format": audio_format,
                "media_type": _audio_media_type(audio_format),
                "text": text,
            }
        )
        for index, segment in enumerate(_split_tts_segments(text)):
            if generation != self.cancel_generation:
                break
            output_path = output_base.with_name(f"{output_base.name}-{index}").with_suffix(f".{audio_format}")
            started = perf_counter()
            await asyncio.to_thread(
                adapter.synthesize,
                segment,
                output_path,
                voice=tts_settings.get("voice"),
                voice_profile=voice_profile,
            )
            await self._send(
                {
                    "type": "tts_segment_done",
                    "index": index,
                    "duration_ms": _elapsed_ms(started),
                    "chars": len(segment),
                }
            )
            await self._stream_pcm_from_audio(output_path, generation)
        await self._send({"type": "tts_done"})
        self.realtime_session.record("playback_confirmed", {})

    def _schedule_partial_asr(self) -> None:
        if not self.enable_partial_asr or not self.provider_config:
            return
        if self.partial_task and not self.partial_task.done():
            return
        chunks = list(self.audio_chunks[-max(self.partial_window_chunks, 1):])
        mime_type = self.mime_type
        audio_encoding = self.audio_encoding
        sample_rate = self.sample_rate
        channels = self.channels
        config = dict(self.provider_config)
        self.partial_task = asyncio.create_task(
            self._emit_partial_asr(chunks, mime_type, audio_encoding, sample_rate, channels, config)
        )

    async def _emit_partial_asr(
        self,
        chunks: list[bytes],
        mime_type: str,
        audio_encoding: str,
        sample_rate: int,
        channels: int,
        config: dict,
    ) -> None:
        if not chunks:
            return
        suffix = _suffix_for_mime(mime_type)
        try:
            with tempfile.TemporaryDirectory(prefix="openinterview-ws-partial-") as temp_dir:
                temp_root = Path(temp_dir)
                input_path = temp_root / f"partial{suffix}"
                wav_path = temp_root / "partial.wav"
                audio = b"".join(chunks)
                if is_pcm_s16le_encoding(audio_encoding):
                    model_input = await asyncio.to_thread(
                        write_pcm_s16le_wav,
                        audio,
                        wav_path,
                        sample_rate=sample_rate,
                        channels=channels,
                    )
                else:
                    input_path.write_bytes(audio)
                    model_input = await asyncio.to_thread(ensure_16k_mono_wav, input_path, wav_path)
                vad = await asyncio.to_thread(SileroVAD().detect_file, model_input)
                if vad.get("speech_ms", 0) <= 0:
                    return
                asr_settings = config.get("asr") or {}
                adapter = build_asr_adapter(config)
                text = await asyncio.to_thread(
                    adapter.transcribe,
                    model_input,
                    language=asr_settings.get("language") or "zh-CN",
                )
                text = text.strip()
                if text:
                    await self._send({"type": "asr_partial", "text": text, "is_final": False})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._send({"type": "asr_partial_error", "error": str(exc)})

    async def _stream_pcm_from_audio(self, audio_path: Path, generation: int) -> None:
        pcm_wav = audio_path.with_suffix(".stream.wav")
        await asyncio.to_thread(ensure_16k_mono_wav, audio_path, pcm_wav)
        with wave.open(str(pcm_wav), "rb") as wav:
            sample_rate = wav.getframerate()
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            if sample_width != 2:
                await self._send({"type": "error", "error": "Streaming TTS expects 16-bit PCM audio."})
                return
            await self._send(
                {
                    "type": "tts_pcm_start",
                    "sample_rate": sample_rate,
                    "channels": channels,
                    "sample_width": sample_width,
                }
            )
            frames_per_chunk = max(int(sample_rate * 0.25), 1)
            index = 0
            while generation == self.cancel_generation:
                frames = wav.readframes(frames_per_chunk)
                if not frames:
                    break
                await self._send(
                    {
                        "type": "tts_pcm_chunk",
                        "index": index,
                        "data": base64.b64encode(frames).decode("ascii"),
                    }
                )
                index += 1
                await asyncio.sleep(0)

    async def _send(self, payload: dict) -> None:
        async with self.send_lock:
            await self.websocket.send_json(payload)

    async def _record_timing(self, name: str, started_at: float) -> None:
        duration_ms = _elapsed_ms(started_at)
        self.turn_timings[name] = duration_ms
        await self._send({"type": "timing", "name": name, "duration_ms": duration_ms})


def _decode_audio_chunk(message: dict) -> bytes:
    data = message.get("data") or ""
    if not data:
        return b""
    return base64.b64decode(data)


def _suffix_for_mime(mime_type: str) -> str:
    normalized = mime_type.lower()
    if "wav" in normalized:
        return ".wav"
    if "ogg" in normalized or "opus" in normalized:
        return ".ogg"
    if "mp4" in normalized or "m4a" in normalized:
        return ".m4a"
    return ".webm"


def _audio_media_type(audio_format: str) -> str:
    normalized = audio_format.lower()
    if normalized == "wav":
        return "audio/wav"
    if normalized == "opus":
        return "audio/ogg"
    if normalized == "aac":
        return "audio/aac"
    return "audio/mpeg"


def _elapsed_ms(start: float) -> float:
    return round((perf_counter() - start) * 1000, 2)


def _split_tts_segments(text: str, max_chars: int = 90) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    parts = [part.strip() for part in re.split(r"(?<=[。！？!?；;])", stripped) if part.strip()]
    if not parts:
        parts = [stripped]
    segments: list[str] = []
    current = ""
    for part in parts:
        if not current:
            current = part
        elif len(current) + len(part) <= max_chars:
            current += part
        else:
            segments.append(current)
            current = part
    if current:
        segments.append(current)
    return segments
