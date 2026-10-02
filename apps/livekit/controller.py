import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import timedelta
import json
from pathlib import Path
from uuid import uuid4
from typing import Literal

import httpx

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from livekit import api
from pydantic import BaseModel, Field

from backend import InterviewBackend
from local_config import AGENT_NAME, LOCAL_PROVIDERS, load_config


@asynccontextmanager
async def lifespan(app):
    config = load_config()
    app.state.config = config
    app.state.backend = InterviewBackend(config["api_url"])
    app.state.livekit = api.LiveKitAPI(config["url"], config["api_key"], config["api_secret"])
    app.state.join_lock = asyncio.Lock()
    app.state.active = None
    try:
        yield
    finally:
        await app.state.backend.close()
        await app.state.livekit.aclose()


app = FastAPI(lifespan=lifespan)


class JoinRequest(BaseModel):
    direction_id: str = "backend"
    difficulty_id: str = "campus"
    mode_id: str = "fundamentals"
    resume_text: str = Field(default="", max_length=20000)
    interview_strategy: Literal["rules", "semantic"] = "semantic"
    llm: dict | None = None


@app.get("/health")
async def health():
    try:
        await app.state.livekit.room.list_rooms(api.ListRoomsRequest())
        response = await app.state.backend.client.get("/health")
        response.raise_for_status()
        return {"ok": True, "audio_local": True, "cloud_llm_optional": True}
    except Exception as exc:
        raise HTTPException(503, detail=str(exc)) from exc


@app.post("/join")
async def join(request: JoinRequest):
    async with app.state.join_lock:
        if app.state.active:
            rooms = await app.state.livekit.room.list_rooms(api.ListRoomsRequest(names=[app.state.active["room"]]))
            if rooms.rooms:
                raise HTTPException(409, "已有本地面试，请先结束当前连接。")
            app.state.active = None
        backend = app.state.backend
        providers = {**LOCAL_PROVIDERS}
        if request.interview_strategy == "semantic":
            settings = request.llm or {}
            if not all(str(settings.get(key) or "").strip() for key in ("api_base", "model", "api_key")):
                raise HTTPException(400, "请填写云端 LLM 的 API Base、Model 和 API Key。")
            providers["llm"] = {"provider": "openai_compatible", "temperature": 0.1,
                **{key: settings[key] for key in ("api_base", "model", "api_key")}}
        # Prewarm before the timed conversation starts. No cloud calls.
        await asyncio.gather(
            backend.post("/v1/tts/warmup", {"text": "预热", "provider_config": LOCAL_PROVIDERS}),
            backend.post("/v1/asr/warmup", {}),
        )
        try:
            interview = await backend.post("/v1/interviews", {
                **request.model_dump(exclude={"llm"}), "provider_config": providers,
            })
        except httpx.HTTPStatusError as exc:
            raise HTTPException(400, "创建面试失败，请检查方向、模式和云端模型配置。") from exc
        room_name = "openinterview-" + uuid4().hex
        try:
            await app.state.livekit.room.create_room(api.CreateRoomRequest(
                name=room_name, empty_timeout=60, departure_timeout=20, max_participants=2))
            await app.state.livekit.agent_dispatch.create_dispatch(api.CreateAgentDispatchRequest(
                agent_name=AGENT_NAME, room=room_name, metadata=json.dumps(interview)))
        except Exception as exc:
            with suppress(Exception):
                await app.state.livekit.room.delete_room(api.DeleteRoomRequest(room=room_name))
            raise HTTPException(503, "LiveKit 房间或 Agent 调度失败，请检查本地日志。") from exc
        config = app.state.config
        token = (api.AccessToken(config["api_key"], config["api_secret"])
            .with_identity("candidate-" + uuid4().hex).with_ttl(timedelta(minutes=120))
            .with_grants(api.VideoGrants(room_join=True, room=room_name,
                can_publish=True, can_subscribe=True, can_publish_data=True)).to_jwt())
        app.state.active = {"room": room_name, "session_id": interview["session_id"]}
        return {"url": config["url"], "token": token, "room": room_name,
                "session_id": interview["session_id"], "question": interview["next_question"]}


@app.post("/leave")
async def leave():
    async with app.state.join_lock:
        if app.state.active:
            await app.state.livekit.room.delete_room(api.DeleteRoomRequest(room=app.state.active["room"]))
            app.state.active = None
    return {"left": True}


@app.get("/report/{session_id}")
async def report(session_id: str):
    response = await app.state.backend.client.get(f"/v1/interviews/{session_id}/report.md")
    response.raise_for_status()
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(response.text)


app.mount("/", StaticFiles(directory=Path(__file__).parent / "web", html=True))
