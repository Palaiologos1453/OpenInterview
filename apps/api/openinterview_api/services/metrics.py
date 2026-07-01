from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Mapping


Labels = Mapping[str, object | None]


@dataclass
class LatencyStats:
    count: int = 0
    sum_ms: float = 0.0
    max_ms: float = 0.0

    def observe(self, value_ms: float) -> None:
        self.count += 1
        self.sum_ms += value_ms
        self.max_ms = max(self.max_ms, value_ms)

    def as_dict(self) -> dict:
        avg_ms = self.sum_ms / self.count if self.count else 0.0
        return {
            "count": self.count,
            "avg_ms": round(avg_ms, 2),
            "sum_ms": round(self.sum_ms, 2),
            "max_ms": round(self.max_ms, 2),
        }


@dataclass
class MetricsRegistry:
    counters: dict[tuple[str, tuple[tuple[str, str], ...]], int] = field(default_factory=lambda: defaultdict(int))
    latencies: dict[tuple[str, tuple[tuple[str, str], ...]], LatencyStats] = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock)

    def increment(self, name: str, labels: Labels | None = None, amount: int = 1) -> None:
        key = (name, _labels_key(labels or {}))
        with self.lock:
            self.counters[key] += amount

    def observe_latency(self, name: str, value_ms: float, labels: Labels | None = None) -> None:
        key = (name, _labels_key(labels or {}))
        with self.lock:
            stats = self.latencies.setdefault(key, LatencyStats())
            stats.observe(value_ms)

    def record_operation(
        self,
        operation: str,
        duration_ms: float,
        *,
        status: str = "ok",
        error_category: str | None = None,
        labels: Labels | None = None,
    ) -> None:
        merged = {
            "operation": operation,
            "status": status,
            "error_category": error_category or "none",
            **(labels or {}),
        }
        self.increment("openinterview_operation_total", merged)
        self.observe_latency("openinterview_operation_latency_ms", duration_ms, merged)

    def record_llm_call(
        self,
        provider: str,
        duration_ms: float,
        *,
        status: str,
        error_category: str | None = None,
    ) -> None:
        labels = {
            "provider": provider or "unknown",
            "status": status,
            "error_category": error_category or "none",
        }
        self.increment("openinterview_llm_calls_total", labels)
        self.observe_latency("openinterview_llm_latency_ms", duration_ms, labels)

    def snapshot(self) -> dict:
        with self.lock:
            counters = [
                {"name": name, "labels": dict(labels), "value": value}
                for (name, labels), value in sorted(self.counters.items())
            ]
            latencies = [
                {"name": name, "labels": dict(labels), **stats.as_dict()}
                for (name, labels), stats in sorted(self.latencies.items())
            ]
        return {"counters": counters, "latencies": latencies}

    def prometheus_text(self) -> str:
        lines = [
            "# HELP openinterview_operation_total Operation executions by status.",
            "# TYPE openinterview_operation_total counter",
        ]
        with self.lock:
            counter_items = sorted(self.counters.items())
            latency_items = sorted(self.latencies.items())
        for (name, labels), value in counter_items:
            lines.append(f"{name}{_prometheus_labels(labels)} {value}")

        seen_latency_names = sorted({name for (name, _labels), _stats in latency_items})
        for name in seen_latency_names:
            lines.append(f"# HELP {name} Operation latency in milliseconds.")
            lines.append(f"# TYPE {name} summary")
        for (name, labels), stats in latency_items:
            labels_text = _prometheus_labels(labels)
            lines.append(f"{name}_count{labels_text} {stats.count}")
            lines.append(f"{name}_sum{labels_text} {round(stats.sum_ms, 2)}")
            lines.append(f"{name}_max{labels_text} {round(stats.max_ms, 2)}")
        return "\n".join(lines) + "\n"


registry = MetricsRegistry()


def record_span(
    name: str,
    duration_ms: float,
    metadata: Labels | None = None,
    *,
    status: str = "ok",
    error_category: str | None = None,
) -> None:
    labels = _span_labels(name, metadata or {})
    registry.record_operation(name, duration_ms, status=status, error_category=error_category, labels=labels)


def _span_labels(name: str, metadata: Labels) -> dict[str, str]:
    labels: dict[str, str] = {}
    for key in ("provider", "direction", "difficulty", "event_type"):
        value = metadata.get(key)
        if value:
            labels[key] = str(value)
    if name.startswith("asr."):
        labels.setdefault("capability", "asr")
    elif name.startswith("vad."):
        labels.setdefault("capability", "vad")
    elif name.startswith("interview."):
        labels.setdefault("capability", "interview")
    elif name.startswith("realtime."):
        labels.setdefault("capability", "realtime")
    return labels


def _labels_key(labels: Labels) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((str(key), _clean_label_value(value)) for key, value in labels.items()))


def _clean_label_value(value: object | None) -> str:
    if value is None:
        return "none"
    text = str(value)
    return text if text else "none"


def _prometheus_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    values = ",".join(f'{key}="{_escape_label(value)}"' for key, value in labels)
    return "{" + values + "}"


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
