from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from time import perf_counter
from uuid import uuid4

from .services.metrics import record_span


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
        status = "ok"
        error_category = None
        try:
            yield
        except Exception as exc:
            from .services.errors import classify_error

            status = "error"
            error_category = classify_error(exc)
            raise
        finally:
            duration_ms = round((perf_counter() - start) * 1000, 2)
            self.events.append(TraceEvent(name=name, duration_ms=duration_ms, metadata=metadata))
            record_span(
                name,
                duration_ms,
                metadata,
                status=status,
                error_category=error_category,
            )

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
