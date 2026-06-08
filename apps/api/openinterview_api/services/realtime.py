from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class RealtimeEvent:
    type: str
    payload: dict
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class RealtimeSession:
    id: str = field(default_factory=lambda: str(uuid4()))
    interview_id: str | None = None
    state: str = "idle"
    playback_generation: int = 0
    current_audio_id: str | None = None
    events: list[RealtimeEvent] = field(default_factory=list)

    def record(self, event_type: str, payload: dict | None = None) -> dict:
        payload = payload or {}
        event = RealtimeEvent(event_type, payload)
        self.events.append(event)
        if event_type == "user_speech_start":
            self.state = "listening"
        elif event_type == "vad_endpoint":
            self.state = "transcribing"
        elif event_type == "asr_final":
            self.state = "thinking"
        elif event_type == "tts_start":
            self.state = "speaking"
            self.playback_generation += 1
            self.current_audio_id = payload.get("audio_id")
        elif event_type == "playback_confirmed":
            self.state = "idle"
            self.current_audio_id = None
        elif event_type == "cancel":
            self.state = "cancelled"
            self.playback_generation += 1
            self.current_audio_id = None
        return self.as_dict()

    def as_dict(self) -> dict:
        data = asdict(self)
        data["events"] = [asdict(event) for event in self.events[-100:]]
        return data


class RealtimeRegistry:
    def __init__(self):
        self.sessions: dict[str, RealtimeSession] = {}

    def create(self, interview_id: str | None = None) -> RealtimeSession:
        session = RealtimeSession(interview_id=interview_id)
        self.sessions[session.id] = session
        return session

    def get(self, session_id: str) -> RealtimeSession | None:
        return self.sessions.get(session_id)

