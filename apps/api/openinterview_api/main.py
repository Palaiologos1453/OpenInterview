from __future__ import annotations

import base64
import binascii
import json
from pathlib import Path
from time import perf_counter
import tempfile
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from .adapters.llm import build_llm_adapter, is_real_llm, llm_temperature
from .adapters.asr import build_asr_adapter
from .adapters.tts import build_tts_adapter, tts_voice_profile
from .auth import authenticate_websocket, auth_middleware
from .catalog import get_catalog
from .interview_engine import CampusInterviewEngine, InterviewConfig, InterviewSession
from .security import hash_token, new_api_token
from .services.metrics import registry as metrics_registry
from .services.question_bank import default_question_bank
from .services.coverage import question_coverage
from .services.provider_diagnostics import diagnose_llm_error
from .services.readiness import readiness_report, readiness_smoke_report
from .services.review import report_to_markdown, review_items_from_report
from .services.resume import analyze_resume
from .services.resume_file import extract_resume_text
from .services.realtime import RealtimeRegistry
from .services.session_store import SQLiteBackedSessionStore
from .services.voice_config import save_voice_model_config, voice_config_response
from .storage import Storage
from .settings import cors_origins, production_mode, require_auth
from .tracing import Trace
from .voice.audio import ensure_16k_mono_wav, is_pcm_s16le_encoding, write_pcm_s16le_wav
from .voice.voice_profiles import load_voice_profiles
from .schemas import (
    ASRRequest,
    ASRResponse,
    InterviewConfigRequest,
    InterviewStartResponse,
    LLMConnectionTestRequest,
    ReportResponse,
    ResumeExtractResponse,
    ResumeAnalyzeRequest,
    TTSRequest,
    TurnRequest,
    TurnResponse,
    UserCreateRequest,
    VADRequest,
    VoiceModelConfigRequest,
    RealtimeCreateRequest,
    RealtimeEventRequest,
    RealtimeAudioTurnRequest,
)

MAX_AUDIO_BYTES = 24 * 1024 * 1024
MAX_HISTORY_IMPORT_BYTES = 32 * 1024 * 1024
MAX_RESUME_UPLOAD_BYTES = 8 * 1024 * 1024


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
storage = Storage()
session_store = SQLiteBackedSessionStore(storage=storage, engine=engine)
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
def readiness_smoke(include_voice: bool = False, voice_check: str | None = None) -> dict:
    return readiness_smoke_report(include_voice=include_voice, voice_check=voice_check)


@app.get("/v1/voice/config")
def get_voice_config() -> dict:
    return voice_config_response()


@app.post("/v1/voice/config")
def save_voice_config(request: VoiceModelConfigRequest) -> dict:
    save_voice_model_config(
        vad_model=request.vad_model,
        asr_model_dir_value=request.asr_model_dir,
        tts_model_dir_value=request.tts_model_dir,
        cosyvoice_path_value=request.cosyvoice_path,
    )
    return voice_config_response()


@app.get("/v1/catalog")
def catalog() -> dict:
    payload = get_catalog()
    payload["voice_profiles"] = [profile.as_dict() for profile in load_voice_profiles()]
    return payload


@app.post("/v1/providers/llm/test")
def test_llm_connection(request: LLMConnectionTestRequest) -> dict:
    config = request.provider_config.model_dump()
    provider = (config.get("llm") or {}).get("provider") or "unknown"
    started_at = perf_counter()
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
        diagnostic = diagnose_llm_error(exc, provider)
        metrics_registry.record_llm_call(
            provider,
            _elapsed_ms(started_at),
            status="error",
            error_category=diagnostic["category"],
        )
        return {
            "ok": False,
            "provider": provider,
            "message": str(exc),
            "diagnostic": diagnostic,
        }

    metrics_registry.record_llm_call(provider, _elapsed_ms(started_at), status="ok")
    return {
        "ok": True,
        "provider": provider,
        "real_llm": is_real_llm(config),
        "message": "LLM 连接成功。" if is_real_llm(config) else "Mock LLM 可用，仅适合本地开发验证。",
        "sample": text[:120],
        "diagnostic": None,
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
    session_store.save(session)
    storage.create_interview(
        session.session_id,
        _redact_config(config_request.model_dump()),
        user_id=getattr(request.state, "user_id", None),
    )
    storage.save_trace(trace.as_dict(), interview_id=session.session_id)
    return result["payload"]


@app.post("/v1/interviews/{session_id}/turn", response_model=TurnResponse)
def answer_turn(session_id: str, request: TurnRequest) -> dict:
    with session_store.session_lock(session_id):
        existing_turn = storage.get_turn_by_request_id(session_id, request.request_id)
        if existing_turn and existing_turn.get("payload"):
            return existing_turn["payload"]

        session = _get_session(session_id)
        trace = Trace()
        try:
            with trace.span("interview.turn", answer_chars=len(request.answer)):
                payload = engine.answer(session, request.answer)
        except RuntimeError as exc:
            storage.save_trace(trace.as_dict(), interview_id=session_id)
            if "already finished" in str(exc):
                raise HTTPException(status_code=409, detail=str(exc)) from exc
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
            request_id=request.request_id,
            payload=payload,
        )
        session_store.save(session)
        storage.save_trace(trace.as_dict(), interview_id=session_id)
        return payload


@app.get("/v1/interviews/{session_id}/report", response_model=ReportResponse)
def report(session_id: str) -> dict:
    record = storage.get_interview(session_id)
    if not session_store.contains(session_id) and record and record.get("report"):
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
    started_at = perf_counter()
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
            synth_started = perf_counter()
            adapter.synthesize(
                request.text,
                output_path,
                voice=request.provider_config.tts.voice,
                voice_profile=voice_profile,
            )
            synth_ms = _elapsed_ms(synth_started)
            read_started = perf_counter()
            audio = output_path.read_bytes()
            read_ms = _elapsed_ms(read_started)
    except NotImplementedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return Response(
        content=audio,
        media_type=media_type,
        headers={
            "X-OpenInterview-TTS-Synthesize-Ms": str(synth_ms),
            "X-OpenInterview-TTS-Read-Ms": str(read_ms),
            "X-OpenInterview-TTS-Total-Ms": str(_elapsed_ms(started_at)),
        },
    )


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
    timings: dict[str, float] = {}
    started_at = perf_counter()
    try:
        span_started = perf_counter()
        audio = _decode_base64_audio(request.audio_base64)
        timings["decode_ms"] = _elapsed_ms(span_started)
        with tempfile.NamedTemporaryFile(
            prefix="openinterview-asr-",
            suffix=".wav",
            delete=False,
        ) as wav_file:
            wav_path = Path(wav_file.name)
        span_started = perf_counter()
        if is_pcm_s16le_encoding(request.audio_encoding):
            model_input = write_pcm_s16le_wav(
                audio,
                wav_path,
                sample_rate=request.sample_rate,
                channels=request.channels,
            )
        else:
            with tempfile.NamedTemporaryFile(
                prefix="openinterview-asr-",
                suffix=suffix,
                delete=False,
            ) as temp_file:
                temp_file.write(audio)
                temp_path = Path(temp_file.name)
            model_input = ensure_16k_mono_wav(temp_path, wav_path)
        timings["convert_ms"] = _elapsed_ms(span_started)
        trace = Trace()
        span_started = perf_counter()
        with trace.span("asr.transcribe", provider=request.provider_config.asr.provider):
            text = adapter.transcribe(model_input, language=request.provider_config.asr.language)
        timings["asr_ms"] = _elapsed_ms(span_started)
        storage.save_transcript(text, source=request.provider_config.asr.provider)
        storage.save_trace(trace.as_dict())
    except HTTPException:
        raise
    except NotImplementedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)
        if wav_path and wav_path.exists():
            wav_path.unlink(missing_ok=True)

    timings["total_ms"] = _elapsed_ms(started_at)
    return {"text": text, "timings": timings}


@app.post("/v1/vad/detect")
def detect_voice_activity(request: VADRequest) -> dict:
    suffix = Path(request.filename or "audio.wav").suffix or ".wav"
    temp_path: Path | None = None
    wav_path: Path | None = None
    try:
        audio = _decode_base64_audio(request.audio_base64)
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
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)
        if wav_path and wav_path.exists():
            wav_path.unlink(missing_ok=True)


@app.get("/v1/questions")
def list_questions(direction_id: str | None = None) -> dict:
    if direction_id and direction_id not in _valid_direction_ids():
        return {"questions": []}
    return {"questions": question_bank.list_questions(direction_id or "backend")}


@app.get("/v1/questions/coverage")
def questions_coverage(direction_id: str = "backend") -> dict:
    if direction_id not in _valid_direction_ids():
        raise HTTPException(status_code=404, detail=f"Unknown direction: {direction_id}")
    return question_coverage(question_bank.list_questions(direction_id), direction_id=direction_id)


@app.get("/v1/questions/{question_id}")
def get_question(question_id: str) -> dict:
    question = question_bank.get_question(question_id)
    if not question or not set(question.get("directions", [])).intersection(_valid_direction_ids() | {"general"}):
        raise HTTPException(status_code=404, detail=f"Unknown question: {question_id}")
    return question


@app.post("/v1/resume/analyze")
def resume_analyze(request: ResumeAnalyzeRequest) -> dict:
    return analyze_resume(request.text).as_dict()


@app.post("/v1/resume/extract", response_model=ResumeExtractResponse)
async def resume_extract(file: UploadFile = File(...)) -> dict:
    content = await _read_upload_limited(file, MAX_RESUME_UPLOAD_BYTES, "简历文件超过 8MB，请先导出为文本或压缩内容后再导入。")
    try:
        return extract_resume_text(file.filename or "resume", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/interviews")
def list_interviews(limit: int = 50) -> dict:
    return {"interviews": storage.list_interviews(limit)}


@app.post("/v1/interviews/{session_id}/review-items")
def create_review_items(session_id: str) -> dict:
    payload = report(session_id)
    items = review_items_from_report(payload)
    for item in items:
        storage.upsert_review_item(item)
    return {"created": len(items), "items": items}


@app.get("/v1/interviews/{session_id}/report.md")
def export_report_markdown(session_id: str) -> PlainTextResponse:
    payload = report(session_id)
    filename = f"openinterview-report-{session_id[:8]}.md"
    return PlainTextResponse(
        report_to_markdown(payload),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/v1/interviews/export")
def export_interviews() -> JSONResponse:
    exported = storage.export_interviews()
    filename = f"openinterview-history-{storage.utc_timestamp_for_filename()}.json"
    return JSONResponse(
        exported,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/v1/interviews/import")
async def import_interviews(file: UploadFile = File(...)) -> dict:
    content = await _read_upload_limited(file, MAX_HISTORY_IMPORT_BYTES, "history file exceeds 32MB")
    try:
        payload = json.loads(content.decode("utf-8-sig"))
        stats = storage.import_interviews(payload)
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="history file must be UTF-8 JSON") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="history file is not valid JSON") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session_store.clear()
    return {"imported": stats}


@app.get("/v1/metrics")
def metrics() -> dict:
    payload = storage.metrics()
    payload["runtime"] = metrics_registry.snapshot()
    return payload


@app.get("/v1/metrics/prometheus")
def metrics_prometheus() -> PlainTextResponse:
    return PlainTextResponse(
        metrics_registry.prometheus_text(),
        media_type="text/plain; version=0.0.4",
    )


@app.delete("/v1/interviews")
def clear_interviews() -> dict:
    session_store.clear()
    deleted = storage.clear_interviews()
    return {"deleted": deleted}


@app.delete("/v1/interviews/{session_id}")
def delete_interview(session_id: str) -> dict:
    session_store.delete(session_id)
    deleted = storage.delete_interview(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Unknown session: {session_id}")
    return {"deleted": True}


@app.get("/v1/review-items")
def list_review_items(limit: int = 100, status: str | None = None) -> dict:
    return {"items": storage.list_review_items(limit=limit, status=status)}


@app.patch("/v1/review-items/{item_id}")
def update_review_item(item_id: str, payload: dict) -> dict:
    status = str(payload.get("status") or "").strip()
    if status not in {"todo", "practicing", "mastered", "ignored"}:
        raise HTTPException(status_code=400, detail="status must be todo/practicing/mastered/ignored")
    if not storage.update_review_item_status(item_id, status):
        raise HTTPException(status_code=404, detail=f"Unknown review item: {item_id}")
    return {"updated": True}


@app.delete("/v1/review-items")
def clear_review_items() -> dict:
    return {"deleted": storage.clear_review_items()}


@app.delete("/v1/review-items/{item_id}")
def delete_review_item(item_id: str) -> dict:
    if not storage.delete_review_item(item_id):
        raise HTTPException(status_code=404, detail=f"Unknown review item: {item_id}")
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
    realtime_registry.save(session)
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
    timings: dict[str, float] = {}
    started_at = perf_counter()
    try:
        realtime_session.record(
            "user_speech_start",
            {
                "filename": request.filename,
                "audio_encoding": request.audio_encoding,
                "sample_rate": request.sample_rate,
                "channels": request.channels,
            },
        )
        realtime_registry.save(realtime_session)
        span_start = perf_counter()
        audio = _decode_base64_audio(request.audio_base64)
        timings["decode_ms"] = _elapsed_ms(span_start)
        with tempfile.NamedTemporaryFile(
            prefix="openinterview-realtime-",
            suffix=".wav",
            delete=False,
        ) as wav_file:
            wav_path = Path(wav_file.name)

        span_start = perf_counter()
        with trace.span("realtime.audio.convert"):
            if is_pcm_s16le_encoding(request.audio_encoding):
                model_input = write_pcm_s16le_wav(
                    audio,
                    wav_path,
                    sample_rate=request.sample_rate,
                    channels=request.channels,
                )
            else:
                with tempfile.NamedTemporaryFile(
                    prefix="openinterview-realtime-",
                    suffix=suffix,
                    delete=False,
                ) as temp_file:
                    temp_file.write(audio)
                    temp_path = Path(temp_file.name)
                model_input = ensure_16k_mono_wav(temp_path, wav_path)
        timings["convert_ms"] = _elapsed_ms(span_start)

        realtime_session.record("vad_endpoint", {})
        realtime_registry.save(realtime_session)
        span_start = perf_counter()
        with trace.span("vad.detect"):
            from .voice.local_vad import SileroVAD

            vad = SileroVAD(threshold=request.vad_threshold).detect_file(model_input)
        timings["vad_ms"] = _elapsed_ms(span_start)

        if vad.get("speech_ms", 0) <= 0:
            realtime_session.record("cancel", {"reason": "no_speech"})
            realtime_registry.save(realtime_session)
            storage.save_trace(trace.as_dict(), interview_id=realtime_session.interview_id)
            timings["total_ms"] = _elapsed_ms(started_at)
            return {
                "session": realtime_session.as_dict(),
                "vad": vad,
                "transcript": "",
                "turn": None,
                "skipped": True,
                "reason": "no_speech",
                "timings": timings,
            }

        span_start = perf_counter()
        with trace.span("asr.transcribe", provider=request.provider_config.asr.provider):
            text = asr_adapter.transcribe(model_input, language=request.provider_config.asr.language)
        timings["asr_ms"] = _elapsed_ms(span_start)
        text = text.strip()
        storage.save_transcript(
            text,
            source=request.provider_config.asr.provider,
            interview_id=realtime_session.interview_id,
        )
        realtime_session.record("asr_final", {"text": text})
        realtime_registry.save(realtime_session)

        turn_payload = None
        if request.submit_to_interview and interview_session:
            with session_store.session_lock(interview_session.session_id):
                span_start = perf_counter()
                with trace.span("interview.turn", answer_chars=len(text)):
                    try:
                        turn_payload = engine.answer(interview_session, text)
                    except RuntimeError as exc:
                        if "already finished" in str(exc):
                            raise HTTPException(status_code=409, detail=str(exc)) from exc
                        raise
                timings["turn_ms"] = _elapsed_ms(span_start)
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
                    payload=turn_payload,
                )
                session_store.save(interview_session)
            realtime_session.record(
                "tts_start",
                {
                    "audio_id": f"turn-{turn_payload['turn_index']}",
                    "text": turn_payload["next_question"],
                },
            )
            realtime_registry.save(realtime_session)
        else:
            realtime_session.record("playback_confirmed", {})
            realtime_registry.save(realtime_session)

        storage.save_trace(trace.as_dict(), interview_id=realtime_session.interview_id)
        timings["total_ms"] = _elapsed_ms(started_at)
        return {
            "session": realtime_session.as_dict(),
            "vad": vad,
            "transcript": text,
            "turn": turn_payload,
            "skipped": False,
            "reason": None,
            "timings": timings,
        }
    except HTTPException:
        storage.save_trace(trace.as_dict(), interview_id=realtime_session.interview_id)
        raise
    except NotImplementedError as exc:
        storage.save_trace(trace.as_dict(), interview_id=realtime_session.interview_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        realtime_session.record("cancel", {"reason": "error", "error": str(exc)})
        realtime_registry.save(realtime_session)
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
        on_session_updated=session_store.save,
        on_realtime_updated=realtime_registry.save,
        session_lock_factory=session_store.session_lock,
    )
    await connection.run()


def _get_session(session_id: str) -> InterviewSession:
    session = session_store.get(session_id)
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


def _elapsed_ms(start: float) -> float:
    return round((perf_counter() - start) * 1000, 2)


async def _read_upload_limited(file: UploadFile, max_bytes: int, error_message: str) -> bytes:
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=error_message)
    return content


def _decode_base64_audio(audio_base64: str) -> bytes:
    try:
        audio = base64.b64decode(audio_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="audio_base64 must be valid base64") from exc
    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="audio payload exceeds 24MB")
    return audio


def _valid_direction_ids() -> set[str]:
    return {item["id"] for item in get_catalog()["directions"]}
