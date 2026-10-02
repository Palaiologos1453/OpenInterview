"""Local LiveKit Agent: Silero + SenseVoice + interview rules + CosyVoice."""
import asyncio
import json
import logging
import os

os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["HF_HUB_OFFLINE"] = "1"

from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, cli, StopResponse  # noqa: E402
from livekit.plugins import silero  # noqa: E402
from livekit.agents.voice import room_io  # noqa: E402

from backend import InterviewBackend  # noqa: E402
from local_config import AGENT_NAME, load_config  # noqa: E402
from local_plugins import LocalCosyVoice, LocalSenseVoice  # noqa: E402
from incremental_stt import IncrementalSenseVoice  # noqa: E402
from speculation import ReplyPreparation  # noqa: E402

logger = logging.getLogger("openinterview.livekit")


class InterviewAgent(Agent):
    def __init__(self, backend, metadata, room):
        super().__init__(instructions="本地面试官。按面试引擎返回的题目提问。")
        self.backend = backend
        self.metadata = metadata
        self.room = room
        self.finished = False
        self.output_tts = LocalCosyVoice(backend)
        self.turn_lock = asyncio.Lock()
        self.preparation = ReplyPreparation(backend, metadata["session_id"],
            enabled=os.environ.get("OPENINTERVIEW_VOICE_PREFETCH", "1") != "0")

    async def observe_transcript(self, event):
        if event["type"] == "partial" and not self.finished:
            self.preparation.observe(event["text"])
        await self.room.local_participant.publish_data(json.dumps(event, ensure_ascii=False),
            reliable=True, topic="openinterview.transcript")

    async def close(self):
        await self.preparation.close()
        if self.output_tts.prepared:
            await self.output_tts.prepared.close()

    async def on_enter(self):
        self.session.say(self.metadata["next_question"])

    async def tts_node(self, text, model_settings):
        # Questions come from the local engine as complete text. Send one model
        # request instead of re-running reference inference for every sentence.
        question = "".join([part async for part in text])
        if not question.strip():
            return
        async with self.session.tts.synthesize(question) as stream:
            async for audio in stream:
                yield audio.frame

    async def on_user_turn_completed(self, turn_ctx, new_message):
        text = (new_message.text_content or "").strip()
        if not text or self.finished:
            raise StopResponse()
        async with self.turn_lock:
            await self.preparation.seal()
            result = await self.backend.answer(self.metadata["session_id"], text, new_message.id)
            prepared = await self.preparation.take(result)
            if self.session.tts.prepared:
                await self.session.tts.prepared.close()
            self.session.tts.prepared = prepared
            self.finished = result["is_finished"]
            await self.room.local_participant.publish_data(
                json.dumps({"type": "turn", "answer": text, "turn": result,
                    "pipeline_metrics": self.preparation.metrics}, ensure_ascii=False),
                reliable=True, topic="openinterview.turn",
            )
            self.session.say(result["next_question"] or "本次面试已结束，可以查看报告。")
        # Only the final answer advances the interview; previews used a copy.
        raise StopResponse()


async def entrypoint(ctx: JobContext):
    config = load_config()
    metadata = json.loads(ctx.job.metadata)
    backend = InterviewBackend(config["api_url"])
    await ctx.connect()
    await ctx.wait_for_participant()
    vad = silero.VAD.load(min_silence_duration=0.8, max_buffered_speech=120, force_cpu=True)
    agent = InterviewAgent(backend, metadata, ctx.room)
    async def cleanup():
        await agent.close()
        await backend.close()

    ctx.add_shutdown_callback(cleanup)
    recognizer = (IncrementalSenseVoice(backend, vad, agent.observe_transcript)
        if os.environ.get("OPENINTERVIEW_INCREMENTAL_ASR", "1") != "0" else LocalSenseVoice(backend))
    session = AgentSession(
        stt=recognizer, tts=agent.output_tts, vad=vad,
        # SDK AEC warmup otherwise replaces early overlapping speech with
        # silence, clipping the beginning of an immediate candidate answer.
        # Browser capture requests AEC; headset input requires no discard window.
        aec_warmup_duration=0,
        turn_handling={"turn_detection": "vad", "endpointing": {"min_delay": 0.8, "max_delay": 3.0},
            "interruption": {"mode": "vad", "enabled": True, "min_duration": 0.35, "min_words": 0},
            "preemptive_generation": {"enabled": False}},
    )
    session.on("error", lambda event: logger.error("Local voice error: %s", event))
    await session.start(agent=agent, room=ctx.room, record=False, session_host=False,
        room_options=room_io.RoomOptions(audio_input=room_io.AudioInputOptions(sample_rate=16000), text_input=False))


if __name__ == "__main__":
    config = load_config()
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, agent_name=AGENT_NAME,
        ws_url=config["url"], api_key=config["api_key"], api_secret=config["api_secret"],
        host="127.0.0.1", port=0, num_idle_processes=0, initialize_process_timeout=60))
