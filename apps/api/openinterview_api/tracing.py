from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from time import perf_counter
from uuid import uuid4


@dataclass
class TraceEvent:
    name: str
    duration_ms: float
    metadata: dict = field(default_factory=dict)


@dataclass
class Trace:
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    events: list[TraceEvent] = field(default_factory=list)

    @contextmanager
    def span(self, name: str, **metadata):
        start = perf_counter()
        try:
            yield
        finally:
            duration_ms = round((perf_counter() - start) * 1000, 2)
            self.events.append(TraceEvent(name=name, duration_ms=duration_ms, metadata=metadata))

    def as_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "events": [
                {
                    "name": event.name,
                    "duration_ms": event.duration_ms,
                    "metadata": event.metadata,
                }
                for event in self.events
            ],
        }

