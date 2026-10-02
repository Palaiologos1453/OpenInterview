import base64
import json

import httpx

from local_config import LOCAL_PROVIDERS, loopback_url


class InterviewBackend:
    def __init__(self, url: str, *, transport=None):
        self.client = httpx.AsyncClient(
            base_url=loopback_url(url, ("http",)), timeout=240, trust_env=False,
            transport=transport,
        )

    async def post(self, path, payload):
        response = await self.client.post(path, json=payload)
        response.raise_for_status()
        return response.json()

    async def answer(self, interview_id, text, request_id):
        return await self.post(f"/v1/interviews/{interview_id}/turn", {
            "answer": text, "request_id": request_id,
        })

    async def recognize(self, data: bytes, sample_rate: int, channels: int) -> str:
        result = await self.post("/v1/asr/transcribe", {
            "audio_base64": base64.b64encode(data).decode("ascii"),
            "filename": "speech.pcm", "audio_encoding": "pcm_s16le",
            "sample_rate": sample_rate, "channels": channels,
            "provider_config": LOCAL_PROVIDERS,
        })
        return result["text"]

    async def speech(self, text):
        completed = False
        async with self.client.stream("POST", "/v1/tts/speech/stream", json={
            "text": text, "provider_config": LOCAL_PROVIDERS,
        }) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                event = json.loads(line)
                if event["type"] == "error":
                    raise RuntimeError(event["error"])
                if event["type"] == "chunk":
                    if event["sample_width"] != 2 or event["channels"] != 1:
                        raise ValueError("Expected mono PCM16 from local CosyVoice")
                    yield event
                elif event["type"] == "done":
                    completed = True
        if not completed:
            raise RuntimeError("Local TTS stream ended without completion")

    async def close(self):
        await self.client.aclose()
