from __future__ import annotations

import base64
from pathlib import Path
import tempfile
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from .adapters.llm import build_llm_adapter, is_real_llm, llm_temperature
from .adapters.asr import build_asr_adapter
from .adapters.tts import build_tts_adapter, tts_voice_profile
from .auth import authenticate_websocket, auth_middleware
from .catalog import get_catalog
from .interview_engine import CampusInterviewEngine, InterviewConfig, InterviewSession, Turn
from .security import hash_token, new_api_token
from .services.question_bank import default_question_bank
from .services.readiness import readiness_report, readiness_smoke_report
from .services.resume import analyze_resume
from .services.realtime import RealtimeRegistry
from .storage import Storage
from .settings import cors_origins, production_mode, require_auth
from .tracing import Trace
from .voice.audio import ensure_16k_mono_wav
from .voice.voice_profiles import load_voice_profiles
from .schemas import (
    ASRRequest,
    ASRResponse,
    InterviewConfigRequest,
    InterviewStartResponse,
    LLMConnectionTestRequest,
    ReportResponse,
    ResumeAnalyzeRequest,
    TTSRequest,
    TurnRequest,
    TurnResponse,
    UserCreateRequest,
    VADRequest,
    RealtimeCreateRequest,
    RealtimeEventRequest,
    RealtimeAudioTurnRequest,
)


app = FastAPI(
    title="OpenInterview API",
    version="0.1.0",
    description="Campus CS interview simulator API.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(auth_middleware)

engine = CampusInterviewEngine()
sessions: dict[str, InterviewSession] = {}
storage = Storage()
question_bank = default_question_bank()
realtime_registry = RealtimeRegistry()


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "openinterview-api",
        "database": str(storage.path),
        "production_mode": production_mode(),
        "require_auth": require_auth(),
        "cors_origins": cors_origins(),
    }


@app.get("/v1/readiness")
def readiness() -> dict:
    return readiness_report()


@app.get("/v1/readiness/smoke")
def readiness_smoke(include_voice: bool = False) -> dict:
    return readiness_smoke_report(include_voice=include_voice)


@app.get("/v1/catalog")
def catalog() -> dict:
    payload = get_catalog()
    payload["voice_profiles"] = [profile.as_dict() for profile in load_voice_profiles()]
    return payload


@app.post("/v1/providers/llm/test")
def test_llm_connection(request: LLMConnectionTestRequest) -> dict:
    config = request.provider_config.model_dump()
    try:
        adapter = build_llm_adapter(config)
        text = adapter.complete(
            [
                {
                    "role": "system",
                    "content": "你是 OpenInterview 的连接自检器。只返回一句简短中文确认。",
                },
                {
                    "role": "user",
                    "content": "请返回：连接成功",
                },
            ],
            temperature=llm_temperature(config),
        )
    except Exception as exc:
        return {
            "ok": False,
            "provider": (config.get("llm") or {}).get("provider") or "unknown",
            "message": str(exc),
        }

    provider = (config.get("llm") or {}).get("provider") or "mock"
    return {
        "ok": True,
        "provider": provider,
        "real_llm": is_real_llm(config),
        "message": "LLM 连接成功。" if is_real_llm(config) else "Mock LLM 可用，仅适合本地开发验证。",
        "sample": text[:120],
    }


@app.post("/v1/interviews", response_model=InterviewStartResponse)
def start_interview(request: Request, config_request: InterviewConfigRequest) -> dict:
    trace = Trace()
    try:
        with trace.span("interview.start", direction=config_request.direction_id, difficulty=config_request.difficulty_id):
            result = engine.start(InterviewConfig(**config_request.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session = result["session"]
    sessions[session.session_id] = session
    storage.create_interview(
        session.session_id,
        _redact_config(config_request.model_dump()),
        user_id=getattr(request.state, "user_id", None),
    )
    storage.save_trace(trace.as_dict(), interview_id=session.session_id)
    return result["payload"]


@app.post("/v1/interviews/{session_id}/turn", response_model=TurnResponse)
def answer_turn(session_id: str, request: TurnRequest) -> dict:
    session = _get_session(session_id)
    trace = Trace()
    try:
        with trace.span("interview.turn", answer_chars=len(request.answer)):
            payload = engine.answer(session, request.answer)
    except RuntimeError as exc:
        storage.save_trace(trace.as_dict(), interview_id=session_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    turn = session.history[-1]
    storage.save_turn(
        session_id,
        turn_index=payload["turn_index"],
        question=turn.question,
        answer=turn.answer,
        feedback=turn.feedback,
        tags=turn.tags,
        score=turn.score,
        question_meta=turn.question_meta,
    )
    storage.save_trace(trace.as_dict(), interview_id=session_id)
    return payload


@app.get("/v1/interviews/{session_id}/report", response_model=ReportResponse)
def report(session_id: str) -> dict:
    record = storage.get_interview(session_id)
    if session_id not in sessions and record and record.get("report"):
        return record["report"]
    session = _get_session(session_id)
    trace = Trace()
    try:
        with trace.span("interview.report", turns=len(session.history)):
            payload = engine.report(session)
    except RuntimeError as exc:
        storage.save_trace(trace.as_dict(), interview_id=session_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    storage.save_report(session_id, payload)
    storage.save_trace(trace.as_dict(), interview_id=session_id)
    return payload


@app.post("/v1/tts/speech")
def text_to_speech(request: TTSRequest) -> Response:
    config = request.provider_config.model_dump()
    if request.voice_profile_id:
        config.setdefault("tts", {})["voice_profile_id"] = request.voice_profile_id
    try:
        adapter = build_tts_adapter(config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audio_format = request.provider_config.tts.response_format or "mp3"
    media_type = _audio_media_type(audio_format)
    try:
        with tempfile.TemporaryDirectory(prefix="openinterview-tts-") as temp_dir:
            output_path = Path(temp_dir) / f"speech.{audio_format}"
            voice_profile = tts_voice_profile(config)
            adapter.synthesize(
                request.text,
                output_path,
                voice=request.provider_config.tts.voice,
                voice_profile=voice_profile,
            )
            audio = output_path.read_bytes()
    except NotImplementedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return Response(content=audio, media_type=media_type)


@app.post("/v1/asr/transcribe", response_model=ASRResponse)
def speech_to_text(request: ASRRequest) -> dict:
    config = request.provider_config.model_dump()
    try:
        adapter = build_asr_adapter(config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    suffix = Path(request.filename or "audio.webm").suffix or ".webm"
    temp_path: Path | None = None
    wav_path: Path | None = None
    try:
        audio = base64.b64decode(request.audio_base64)
        with tempfile.NamedTemporaryFile(
            prefix="openinterview-asr-",
            suffix=suffix,
            delete=False,
        ) as temp_file:
            temp_file.write(audio)
            temp_path = Path(temp_file.name)
        with tempfile.NamedTemporaryFile(
            prefix="openinterview-asr-",
            suffix=".wav",
            delete=False,
        ) as wav_file:
            wav_path = Path(wav_file.name)
        model_input = ensure_16k_mono_wav(temp_path, wav_path)
        trace = Trace()
        with trace.span("asr.transcribe", provider=request.provider_config.asr.provider):
            text = adapter.transcribe(model_input, language=request.provider_config.asr.language)
        storage.save_transcript(text, source=request.provider_config.asr.provider)
        storage.save_trace(trace.as_dict())
    except NotImplementedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)
        if wav_path and wav_path.exists():
            wav_path.unlink(missing_ok=True)

    return {"text": text}


@app.post("/v1/vad/detect")
def detect_voice_activity(request: VADRequest) -> dict:
    suffix = Path(request.filename or "audio.wav").suffix or ".wav"
    temp_path: Path | None = None
    wav_path: Path | None = None
    try:
        audio = base64.b64decode(request.audio_base64)
        with tempfile.NamedTemporaryFile(
            prefix="openinterview-vad-",
            suffix=suffix,
            delete=False,
        ) as temp_file:
            temp_file.write(audio)
            temp_path = Path(temp_file.name)
        with tempfile.NamedTemporaryFile(
            prefix="openinterview-vad-",
            suffix=".wav",
            delete=False,
        ) as wav_file:
            wav_path = Path(wav_file.name)
        model_input = ensure_16k_mono_wav(temp_path, wav_path)
        trace = Trace()
        with trace.span("vad.detect"):
            from .voice.local_vad import SileroVAD

            payload = SileroVAD(threshold=request.threshold).detect_file(model_input)
        storage.save_trace(trace.as_dict())
        return payload
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)
        if wav_path and wav_path.exists():
            wav_path.unlink(missing_ok=True)


@app.get("/v1/questions")
def list_questions(direction_id: str | None = None) -> dict:
    return {"questions": question_bank.list_questions(direction_id)}


@app.get("/v1/questions/{question_id}")
def get_question(question_id: str) -> dict:
    question = question_bank.get_question(question_id)
    if not question:
        raise HTTPException(status_code=404, detail=f"Unknown question: {question_id}")
    return question


@app.post("/v1/resume/analyze")
def resume_analyze(request: ResumeAnalyzeRequest) -> dict:
    return analyze_resume(request.text).as_dict()


@app.get("/v1/interviews")
def list_interviews(limit: int = 50) -> dict:
    return {"interviews": storage.list_interviews(limit)}


@app.get("/v1/interviews/export")
def export_interviews() -> JSONResponse:
    exported = storage.export_interviews()
    filename = f"openinterview-history-{storage.utc_timestamp_for_filename()}.json"
    return JSONResponse(
        exported,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/v1/metrics")
def metrics() -> dict:
    return storage.metrics()


@app.delete("/v1/interviews")
def clear_interviews() -> dict:
    sessions.clear()
    deleted = storage.clear_interviews()
    return {"deleted": deleted}


@app.delete("/v1/interviews/{session_id}")
def delete_interview(session_id: str) -> dict:
    sessions.pop(session_id, None)
    deleted = storage.delete_interview(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Unknown session: {session_id}")
    return {"deleted": True}


@app.post("/v1/users")
def create_user(request: UserCreateRequest) -> dict:
    user_id = str(uuid4())
    token = new_api_token()
    storage.create_user(user_id, request.display_name, hash_token(token))
    return {
        "user_id": user_id,
        "api_token": token,
        "note": "Store this token locally. OpenInterview does not show it again.",
    }


@app.post("/v1/realtime/sessions")
def create_realtime_session(request: RealtimeCreateRequest) -> dict:
    session = realtime_registry.create(request.interview_id)
    return session.as_dict()


@app.get("/v1/realtime/sessions/{session_id}")
def get_realtime_session(session_id: str) -> dict:
    session = realtime_registry.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Unknown realtime session: {session_id}")
    return session.as_dict()


@app.post("/v1/realtime/sessions/{session_id}/events")
def record_realtime_event(session_id: str, request: RealtimeEventRequest) -> dict:
    session = realtime_registry.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Unknown realtime session: {session_id}")
    trace = Trace()
    with trace.span("realtime.event", event_type=request.type):
        payload = session.record(request.type, request.payload)
    storage.save_trace(trace.as_dict(), interview_id=session.interview_id)
    return payload


@app.post("/v1/realtime/sessions/{session_id}/audio-turn")
def realtime_audio_turn(session_id: str, request: RealtimeAudioTurnRequest) -> dict:
    realtime_session = realtime_registry.get(session_id)
    if not realtime_session:
        raise HTTPException(status_code=404, detail=f"Unknown realtime session: {session_id}")

    interview_session = None
    if request.submit_to_interview:
        if not realtime_session.interview_id:
            raise HTTPException(status_code=400, detail="Realtime session is not bound to an interview.")
        interview_session = _get_session(realtime_session.interview_id)

    config = request.provider_config.model_dump()
    try:
        asr_adapter = build_asr_adapter(config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    suffix = Path(request.filename or "audio.webm").suffix or ".webm"
    temp_path: Path | None = None
    wav_path: Path | None = None
    trace = Trace()
    try:
        realtime_session.record("user_speech_start", {"filename": request.filename})
        audio = base64.b64decode(request.audio_base64)
        with tempfile.NamedTemporaryFile(
            prefix="openinterview-realtime-",
            suffix=suffix,
            delete=False,
        ) as temp_file:
            temp_file.write(audio)
            temp_path = Path(temp_file.name)
        with tempfile.NamedTemporaryFile(
            prefix="openinterview-realtime-",
            suffix=".wav",
            delete=False,
        ) as wav_file:
            wav_path = Path(wav_file.name)

        with trace.span("realtime.audio.convert"):
            model_input = ensure_16k_mono_wav(temp_path, wav_path)

        realtime_session.record("vad_endpoint", {})
        with trace.span("vad.detect"):
            from .voice.local_vad import SileroVAD

            vad = SileroVAD(threshold=request.vad_threshold).detect_file(model_input)

        if vad.get("speech_ms", 0) <= 0:
            realtime_session.record("cancel", {"reason": "no_speech"})
            storage.save_trace(trace.as_dict(), interview_id=realtime_session.interview_id)
            return {
                "session": realtime_session.as_dict(),
                "vad": vad,
                "transcript": "",
                "turn": None,
                "skipped": True,
                "reason": "no_speech",
            }

        with trace.span("asr.transcribe", provider=request.provider_config.asr.provider):
            text = asr_adapter.transcribe(model_input, language=request.provider_config.asr.language)
        text = text.strip()
        storage.save_transcript(
            text,
            source=request.provider_config.asr.provider,
            interview_id=realtime_session.interview_id,
        )
        realtime_session.record("asr_final", {"text": text})

        turn_payload = None
        if request.submit_to_interview and interview_session:
            with trace.span("interview.turn", answer_chars=len(text)):
                turn_payload = engine.answer(interview_session, text)
            turn = interview_session.history[-1]
            storage.save_turn(
                interview_session.session_id,
                turn_index=turn_payload["turn_index"],
                question=turn.question,
                answer=turn.answer,
                feedback=turn.feedback,
                tags=turn.tags,
                score=turn.score,
                question_meta=turn.question_meta,
            )
            realtime_session.record(
                "tts_start",
                {
                    "audio_id": f"turn-{turn_payload['turn_index']}",
                    "text": f"{turn_payload['interviewer_message']} {turn_payload['next_question']}",
                },
            )
        else:
            realtime_session.record("playback_confirmed", {})

        storage.save_trace(trace.as_dict(), interview_id=realtime_session.interview_id)
        return {
            "session": realtime_session.as_dict(),
            "vad": vad,
            "transcript": text,
            "turn": turn_payload,
            "skipped": False,
            "reason": None,
        }
    except NotImplementedError as exc:
        storage.save_trace(trace.as_dict(), interview_id=realtime_session.interview_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        realtime_session.record("cancel", {"reason": "error", "error": str(exc)})
        storage.save_trace(trace.as_dict(), interview_id=realtime_session.interview_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)
        if wav_path and wav_path.exists():
            wav_path.unlink(missing_ok=True)


@app.websocket("/v1/realtime/sessions/{session_id}/duplex")
async def realtime_duplex(session_id: str, websocket: WebSocket) -> None:
    if not await authenticate_websocket(websocket):
        return
    realtime_session = realtime_registry.get(session_id)
    if not realtime_session:
        await websocket.close(code=1008)
        return
    if not realtime_session.interview_id:
        await websocket.close(code=1008)
        return
    interview_session = _get_session(realtime_session.interview_id)
    from .services.duplex import DuplexRealtimeConnection

    connection = DuplexRealtimeConnection(
        websocket=websocket,
        realtime_session=realtime_session,
        interview_session=interview_session,
        engine=engine,
        storage=storage,
    )
    await connection.run()


def _get_session(session_id: str) -> InterviewSession:
    session = sessions.get(session_id)
    if session is None:
        session = _restore_session(session_id)
        if session:
            sessions[session_id] = session
    if session is None:
        raise HTTPException(status_code=404, detail=f"Unknown session: {session_id}")
    return session


def _audio_media_type(audio_format: str) -> str:
    normalized = audio_format.lower()
    if normalized == "wav":
        return "audio/wav"
    if normalized == "opus":
        return "audio/ogg"
    if normalized == "aac":
        return "audio/aac"
    return "audio/mpeg"


def _redact_config(config: dict) -> dict:
    copied = dict(config)
    provider_config = copied.get("provider_config")
    if isinstance(provider_config, dict):
        provider_config = {
            group: {
                key: ("***" if key == "api_key" and value else value)
                for key, value in settings.items()
            }
            for group, settings in provider_config.items()
            if isinstance(settings, dict)
        }
        copied["provider_config"] = provider_config
    return copied


def _restore_session(session_id: str) -> InterviewSession | None:
    record = storage.get_interview(session_id)
    if not record:
        return None
    config = record["config"]
    provider_config = config.get("provider_config")
    redacted_provider_config = False
    if isinstance(provider_config, dict):
        for group in provider_config.values():
            if isinstance(group, dict) and group.get("api_key") == "***":
                group["api_key"] = ""
                redacted_provider_config = True
        if redacted_provider_config:
            llm = provider_config.get("llm")
            if isinstance(llm, dict):
                llm["provider"] = "mock"
    try:
        interview_config = InterviewConfig(**config)
    except TypeError:
        return None
    session = InterviewSession(config=interview_config, session_id=session_id)
    turns = storage.get_interview_turns(session_id)
    for item in turns:
        session.history.append(
            Turn(
                question=item["question"],
                answer=item["answer"],
                feedback=item["feedback"],
                tags=item["tags"],
                score=item["score"],
                question_meta=item.get("question_meta"),
            )
        )
    session.turn_index = len(session.history)
    session.current_question = engine._select_question(session, step=session.turn_index)
    return session
