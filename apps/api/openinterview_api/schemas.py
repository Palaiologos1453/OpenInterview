from __future__ import annotations

from pydantic import BaseModel, Field


class LLMProviderSettings(BaseModel):
    provider: str = Field(default="openai_compatible")
    api_base: str | None = None
    model: str | None = None
    api_key: str | None = None
    temperature: float = Field(default=0.4, ge=0, le=2)
    timeout_seconds: int = Field(default=45, ge=5, le=180)
    allow_fallback: bool = Field(default=False)


class ASRProviderSettings(BaseModel):
    provider: str = Field(default="browser")
    api_base: str | None = None
    model: str | None = None
    api_key: str | None = None
    language: str = Field(default="zh-CN")
    timeout_seconds: int = Field(default=60, ge=5, le=300)
    device: str = Field(default="auto")


class TTSProviderSettings(BaseModel):
    provider: str = Field(default="browser")
    api_base: str | None = None
    model: str | None = None
    api_key: str | None = None
    voice: str | None = None
    response_format: str = Field(default="mp3")
    timeout_seconds: int = Field(default=60, ge=5, le=300)
    voice_profile_id: str | None = None


class ProviderSettings(BaseModel):
    llm: LLMProviderSettings = Field(default_factory=LLMProviderSettings)
    asr: ASRProviderSettings = Field(default_factory=ASRProviderSettings)
    tts: TTSProviderSettings = Field(default_factory=TTSProviderSettings)


class LLMConnectionTestRequest(BaseModel):
    provider_config: ProviderSettings = Field(default_factory=ProviderSettings)


class InterviewConfigRequest(BaseModel):
    direction_id: str = Field(default="backend")
    difficulty_id: str = Field(default="campus")
    mode_id: str = Field(default="comprehensive")
    interviewer_style_id: str = Field(default="small_company_basic")
    candidate_name: str | None = None
    resume_text: str | None = None
    duration_minutes: int = Field(default=30, ge=5, le=120)
    language: str = Field(default="zh-CN")
    provider_config: ProviderSettings = Field(default_factory=ProviderSettings)


class InterviewStartResponse(BaseModel):
    session_id: str
    opening_message: str
    next_question: str
    rubric: list[dict]
    provider_notice: str | None = None


class TurnRequest(BaseModel):
    answer: str = Field(default="")


class TurnResponse(BaseModel):
    session_id: str
    turn_index: int
    interviewer_message: str
    next_question: str
    focus_tags: list[str]
    is_finished: bool
    provider_notice: str | None = None


class ReportResponse(BaseModel):
    session_id: str
    direction: str
    difficulty: str
    interviewer_style: str | None = None
    overall_score: float
    ai_summary: str | None = None
    dimensions: list[dict]
    strengths: list[str]
    improvements: list[str]
    review_plan: list[str]
    practice_drills: list[dict] = Field(default_factory=list)
    answer_guides: list[dict] = Field(default_factory=list)
    study_guides: list[dict] = Field(default_factory=list)
    turns: list[dict]


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    provider_config: ProviderSettings = Field(default_factory=ProviderSettings)
    voice_profile_id: str | None = None


class ASRRequest(BaseModel):
    audio_base64: str = Field(min_length=1)
    filename: str = Field(default="answer.webm")
    provider_config: ProviderSettings = Field(default_factory=ProviderSettings)


class ASRResponse(BaseModel):
    text: str


class VADRequest(BaseModel):
    audio_base64: str = Field(min_length=1)
    filename: str = Field(default="audio.wav")
    threshold: float = Field(default=0.5, ge=0.1, le=0.95)


class VoiceModelConfigRequest(BaseModel):
    vad_model: str | None = None
    asr_model_dir: str | None = None
    tts_model_dir: str | None = None
    cosyvoice_path: str | None = None


class ResumeAnalyzeRequest(BaseModel):
    text: str = Field(default="")


class ResumeExtractResponse(BaseModel):
    filename: str
    type: str
    text: str
    chars: int


class UserCreateRequest(BaseModel):
    display_name: str = Field(default="Local User", min_length=1, max_length=80)


class RealtimeCreateRequest(BaseModel):
    interview_id: str | None = None


class RealtimeEventRequest(BaseModel):
    type: str
    payload: dict = Field(default_factory=dict)


class RealtimeAudioTurnRequest(BaseModel):
    audio_base64: str = Field(min_length=1)
    filename: str = Field(default="answer.webm")
    provider_config: ProviderSettings = Field(default_factory=ProviderSettings)
    vad_threshold: float = Field(default=0.5, ge=0.1, le=0.95)
    submit_to_interview: bool = Field(default=True)
