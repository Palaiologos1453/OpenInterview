"""LiveKit adapters for the existing local inference service.

SenseVoice is batch recognition; LiveKit's VAD StreamAdapter invokes it per
speech segment. This does not claim token-by-token streaming ASR.
"""
import base64
from uuid import uuid4

from livekit.agents import stt, tts, utils, APIConnectOptions

from backend import InterviewBackend


NO_RETRY = APIConnectOptions(max_retry=0, timeout=240)


class LocalSenseVoice(stt.STT):
    def __init__(self, backend: InterviewBackend):
        super().__init__(capabilities=stt.STTCapabilities(streaming=False, interim_results=False))
        self.backend = backend

    @property
    def model(self):
        return "SenseVoiceSmall"

    @property
    def provider(self):
        return "local"

    async def _recognize_impl(self, buffer, *, language, conn_options):
        frame = utils.merge_frames(buffer)
        text = await self.backend.recognize(frame.data.tobytes(), frame.sample_rate, frame.num_channels)
        return stt.SpeechEvent(type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[stt.SpeechData(language="zh", text=text)])


class LocalCosyVoice(tts.TTS):
    def __init__(self, backend: InterviewBackend):
        # streaming=False describes incremental TEXT input. ChunkedStream still
        # emits audio immediately; it does not wait for a complete WAV file.
        super().__init__(capabilities=tts.TTSCapabilities(streaming=False), sample_rate=24000, num_channels=1)
        self.backend = backend

    @property
    def model(self):
        return "CosyVoice3"

    @property
    def provider(self):
        return "local"

    def synthesize(self, text, *, conn_options=NO_RETRY):
        return _Speech(tts=self, input_text=text, conn_options=NO_RETRY)


class _Speech(tts.ChunkedStream):
    async def _run(self, output_emitter):
        output_emitter.initialize(request_id=uuid4().hex, sample_rate=24000,
            num_channels=1, mime_type="audio/pcm", frame_size_ms=20, stream=False)
        async for event in self._tts.backend.speech(self._input_text):
            if event["sample_rate"] != 24000:
                raise ValueError("This adapter expects the CosyVoice3 24 kHz model")
            output_emitter.push(base64.b64decode(event["data"], validate=True))
