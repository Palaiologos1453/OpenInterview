"""Exercise real local WebRTC audio, VAD, ASR, interview turn and TTS.

Run using apps/livekit/.venv/Scripts/python.exe while start-livekit.ps1 runs
with a temporary -DatabasePath. Creates a synthetic spoken candidate answer.
"""
import asyncio
import argparse
import json
from pathlib import Path
import sys
import time
import wave

import httpx
from livekit import rtc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "livekit"))
from local_config import LOCAL_PROVIDERS, load_config  # noqa: E402


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reuse-fixture", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "logs/livekit/smoke-result.json")
    args = parser.parse_args()
    config = load_config()
    audio_events = []
    tasks = []
    got_audio = asyncio.Event()
    got_turn = asyncio.Event()
    turns = []
    partials = []
    turn_received_at = None
    room = rtc.Room()
    async with httpx.AsyncClient(timeout=240, trust_env=False) as client:
        # Short answer audio generated exclusively by local CosyVoice.
        fixture = ROOT / "logs" / "livekit" / "candidate.wav"
        if not args.reuse_fixture or not fixture.exists():
            response = await client.post(config["api_url"] + "/v1/tts/speech", json={
                "text": "我负责订单系统的缓存优化，使用Redis和MySQL，通过压测验证延迟降低百分之三十。",
                "provider_config": LOCAL_PROVIDERS})
            response.raise_for_status()
            fixture.write_bytes(response.content)

        async def consume(track):
            stream = rtc.AudioStream(track, sample_rate=24000, num_channels=1)
            try:
                async for event in stream:
                    if any(abs(value) > 100 for value in event.frame.data):
                        audio_events.append(time.perf_counter())
                        got_audio.set()
            finally:
                await stream.aclose()

        @room.on("track_subscribed")
        def track_subscribed(track, publication, participant):
            print("Subscribed:", track.kind, publication.sid, flush=True)
            if track.kind == rtc.TrackKind.KIND_AUDIO:
                tasks.append(asyncio.create_task(consume(track)))

        @room.on("data_received")
        def data_received(packet):
            nonlocal turn_received_at
            if packet.topic == "openinterview.transcript":
                event = json.loads(packet.data)
                if event["type"] == "partial":
                    partials.append({"time": time.perf_counter(), "text": event["text"]})
            if packet.topic == "openinterview.turn":
                turn_received_at = time.perf_counter()
                turns.append(json.loads(packet.data))
                got_turn.set()

        try:
            joined = await client.post("http://127.0.0.1:5180/join", json={})
            joined.raise_for_status()
            info = joined.json()
            started = time.perf_counter()
            await room.connect(info["url"], info["token"], options=rtc.RoomOptions(
                rtc_config=rtc.RtcConfiguration(ice_servers=[])))
            print("Room connected", flush=True)
            await asyncio.wait_for(got_audio.wait(), timeout=90)
            first_audio_ms = (time.perf_counter() - started) * 1000
            print(f"Received real Agent audio at {first_audio_ms:.0f} ms after join", flush=True)
            # Publish during the question to exercise barge-in as well as ASR.
            with wave.open(str(fixture), "rb") as wav:
                sample_rate = wav.getframerate()
                assert wav.getnchannels() == 1 and wav.getsampwidth() == 2
                source = rtc.AudioSource(sample_rate, 1)
                track = rtc.LocalAudioTrack.create_audio_track("candidate", source)
                publication = await room.local_participant.publish_track(track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
                await asyncio.wait_for(publication.wait_for_subscription(), 10)
                samples = sample_rate // 50
                # Allow the remote VAD subscription to attach before real speech.
                for _ in range(50):
                    await source.capture_frame(rtc.AudioFrame(data=b"\0\0" * samples, sample_rate=sample_rate,
                        num_channels=1, samples_per_channel=samples))
                await source.wait_for_playout()
                speech_start = time.perf_counter()
                while data := wav.readframes(samples):
                    await source.capture_frame(rtc.AudioFrame(data=data, sample_rate=sample_rate,
                        num_channels=1, samples_per_channel=len(data) // 2))
                await source.wait_for_playout()
                speech_end = time.perf_counter()
                for _ in range(100):
                    await source.capture_frame(rtc.AudioFrame(data=b"\0\0" * samples, sample_rate=sample_rate,
                        num_channels=1, samples_per_channel=samples))
                await source.wait_for_playout()
            await asyncio.wait_for(got_turn.wait(), timeout=90)
            turn_ms = (turn_received_at - speech_end) * 1000
            print("Recognized:", turns[0]["answer"], flush=True)
            assert turns[0]["turn"]["turn_index"] == 1
            assert "订单" in turns[0]["answer"], "Beginning of candidate answer was lost"
            while not any(t >= turn_received_at for t in audio_events):
                got_audio.clear()
                await asyncio.wait_for(got_audio.wait(), timeout=90)
            reply_audio_ms = (next(t for t in audio_events if t >= turn_received_at) - speech_end) * 1000
            report = await client.get(config["api_url"] + f"/v1/interviews/{info['session_id']}/report")
            report.raise_for_status()
            assert len(report.json()["turns"]) == 1
            result = {"ok": True, "transport": "real local WebRTC", "model_calls": "local SenseVoice and CosyVoice",
                "first_agent_audio_after_join_ms": round(first_audio_ms, 2),
                "turn_result_after_candidate_playout_ms": round(turn_ms, 2),
                "reply_audio_after_candidate_playout_ms": round(reply_audio_ms, 2),
                "received_non_silent_audio_frames": len(audio_events),
                "first_partial_after_speech_start_ms": round((partials[0]["time"] - speech_start) * 1000, 2) if partials else None,
                "partials_before_speech_end": sum(p["time"] < speech_end for p in partials),
                "pipeline_metrics": turns[0].get("pipeline_metrics", {}),
                "recognized_answer": turns[0]["answer"], "persisted_turns": 1}
            args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
            print(json.dumps(result,ensure_ascii=False),flush=True)
        finally:
            await room.disconnect()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await client.post("http://127.0.0.1:5180/leave")


if __name__ == "__main__":
    asyncio.run(main())
