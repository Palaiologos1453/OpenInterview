"""Bounded SenseVoice snapshots while listening, with authoritative final ASR.

This is an adapter for a batch model, not a claim of native streaming decoding.
Only one snapshot is in flight. Slow partials are skipped, never queued.
"""
import asyncio
import logging
import time
from uuid import uuid4

from livekit.agents import stt, utils, vad

from local_plugins import LocalSenseVoice, NO_RETRY

logger = logging.getLogger(__name__)


class IncrementalSenseVoice(LocalSenseVoice):
    def __init__(self, backend, detector, observer, *, interval=1.2, max_partial_seconds=20):
        super().__init__(backend)
        self._capabilities = stt.STTCapabilities(streaming=True, interim_results=True)
        self.detector = detector
        self.observer = observer
        self.interval = interval
        self.max_partial_seconds = max_partial_seconds

    def stream(self, *, language=None, conn_options=NO_RETRY):
        return _Stream(self)


class _Stream(stt.RecognizeStream):
    def __init__(self, provider):
        super().__init__(stt=provider, conn_options=NO_RETRY, sample_rate=16000)
        self.provider = provider
        self.revision = 0
        self.partial_task = None
        self.utterance = ""
        self.active = False

    async def _partial(self, frames, revision, utterance):
        try:
            frame = utils.merge_frames(frames)
            text = await self.provider.backend.recognize(
                frame.data.tobytes(), frame.sample_rate, frame.num_channels, persist=False)
            if self.active and revision == self.revision and text.strip():
                self._event_ch.send_nowait(stt.SpeechEvent(stt.SpeechEventType.INTERIM_TRANSCRIPT,
                    alternatives=[stt.SpeechData(language="zh", text=text)]))
                await self.provider.observer({"type": "partial", "text": text, "utterance": utterance})
        except asyncio.CancelledError:
            raise
        except Exception:
            # Opportunistic work must not prevent authoritative final recognition.
            logger.warning("Partial ASR unavailable; continuing with final recognition.")

    async def _run(self):
        detector = self.provider.detector.stream()

        async def forward():
            async for frame in self._input_ch:
                if isinstance(frame, self._FlushSentinel):
                    detector.flush()
                else:
                    detector.push_frame(frame)
            detector.end_input()

        async def recognize():
            frames = []
            seconds = 0
            next_partial = self.provider.interval
            async for event in detector:
                if event.type == vad.VADEventType.START_OF_SPEECH:
                    self.revision += 1
                    self.active = True
                    self.utterance = uuid4().hex
                    frames = list(event.frames)
                    seconds = sum(f.duration for f in frames)
                    next_partial = seconds + self.provider.interval
                    self._event_ch.send_nowait(stt.SpeechEvent(stt.SpeechEventType.START_OF_SPEECH))
                    await self.provider.observer({"type": "speech_start", "utterance": self.utterance})
                elif event.type == vad.VADEventType.INFERENCE_DONE and self.active:
                    seconds += sum(f.duration for f in event.frames)
                    if seconds <= self.provider.max_partial_seconds:
                        frames.extend(event.frames)
                        if seconds >= next_partial and (not self.partial_task or self.partial_task.done()):
                            next_partial = seconds + self.provider.interval
                            self.partial_task = asyncio.create_task(self._partial(
                                list(frames), self.revision, self.utterance))
                    else:
                        frames = []  # no repeated full-history decoding for long answers
                elif event.type == vad.VADEventType.END_OF_SPEECH:
                    self.active = False
                    self.revision += 1  # late partials can no longer overwrite the final
                    if self.partial_task:
                        # Finish the one in-flight snapshot before final inference;
                        # cancellation would not stop an already running GPU request.
                        await self.partial_task
                    ended_at = time.time() - event.silence_duration - event.inference_duration
                    self._event_ch.send_nowait(stt.SpeechEvent(stt.SpeechEventType.END_OF_SPEECH,
                        speech_end_time=ended_at))
                    final = await self.provider.recognize(utils.merge_frames(event.frames), conn_options=NO_RETRY)
                    if final.alternatives and final.alternatives[0].text.strip():
                        text = final.alternatives[0].text
                        await self.provider.observer({"type": "final", "text": text, "utterance": self.utterance})
                        self._event_ch.send_nowait(stt.SpeechEvent(stt.SpeechEventType.FINAL_TRANSCRIPT,
                            alternatives=final.alternatives, speech_end_time=ended_at))
                    frames = []

        tasks = [asyncio.create_task(forward()), asyncio.create_task(recognize())]
        try:
            await asyncio.gather(*tasks)
        finally:
            self.active = False
            self.revision += 1
            if self.partial_task:
                tasks.append(self.partial_task)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await detector.aclose()
