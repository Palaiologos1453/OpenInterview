from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Iterator, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class LLMAdapter(Protocol):
    def complete(self, messages: list[dict[str, str]], *, temperature: float = 0.4) -> str:
        """Return a text completion for interview generation or evaluation."""

    def complete_stream(self, messages: list[dict[str, str]], *, temperature: float = 0.4) -> Iterator[str]:
        """Yield completion text as it arrives from a streaming provider."""


@dataclass
class MockLLMAdapter:
    name: str = "mock-campus-interviewer"

    def complete(self, messages: list[dict[str, str]], *, temperature: float = 0.4) -> str:
        del messages, temperature
        return "这是 mock LLM 回复。请在 provider 配置中接入真实模型。"

    def complete_stream(self, messages: list[dict[str, str]], *, temperature: float = 0.4) -> Iterator[str]:
        yield self.complete(messages, temperature=temperature)


@dataclass
class OpenAICompatibleLLMAdapter:
    api_base: str
    model: str
    api_key: str
    timeout_seconds: int = 45

    def complete(self, messages: list[dict[str, str]], *, temperature: float = 0.4) -> str:
        endpoint = _openai_chat_endpoint(self.api_base)
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            # Decisions are short JSON objects. Capping generation prevents a
            # provider from spending seconds on verbose explanations.
            "max_tokens": 700,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        data = _post_json(endpoint, payload, headers=headers, timeout_seconds=self.timeout_seconds)
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("LLM provider returned an unexpected response shape.") from exc

    def complete_stream(self, messages: list[dict[str, str]], *, temperature: float = 0.4) -> Iterator[str]:
        endpoint = _openai_chat_endpoint(self.api_base)
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 700,
            "stream": True,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "text/event-stream",
        }
        for item in _post_stream(endpoint, payload, headers=headers, timeout_seconds=self.timeout_seconds):
            if item == "[DONE]":
                break
            try:
                content = item["choices"][0].get("delta", {}).get("content")
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError("LLM provider returned an unexpected streaming response shape.") from exc
            if content:
                yield content


@dataclass
class OllamaLLMAdapter:
    api_base: str = "http://127.0.0.1:11434"
    model: str = "qwen"
    timeout_seconds: int = 90

    def complete(self, messages: list[dict[str, str]], *, temperature: float = 0.4) -> str:
        endpoint = f"{self.api_base.rstrip('/')}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": 700},
        }
        data = _post_json(endpoint, payload, headers={"Content-Type": "application/json"}, timeout_seconds=self.timeout_seconds)
        try:
            return data["message"]["content"].strip()
        except (KeyError, TypeError) as exc:
            raise RuntimeError("Ollama returned an unexpected response shape.") from exc

    def complete_stream(self, messages: list[dict[str, str]], *, temperature: float = 0.4) -> Iterator[str]:
        endpoint = f"{self.api_base.rstrip('/')}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature, "num_predict": 700},
        }
        for item in _post_stream(
            endpoint, payload, headers={"Content-Type": "application/json"}, timeout_seconds=self.timeout_seconds
        ):
            if item.get("done"):
                break
            content = (item.get("message") or {}).get("content")
            if content:
                yield content


def build_llm_adapter(config: dict | None) -> LLMAdapter:
    settings = (config or {}).get("llm", config or {})
    provider = (settings.get("provider") or "mock").strip().lower()

    if provider in {"", "mock", "disabled"}:
        return MockLLMAdapter()

    if provider in {"openai", "openai_compatible", "compatible"}:
        api_base = settings.get("api_base") or "https://api.openai.com/v1"
        model = settings.get("model") or "gpt-4o-mini"
        api_key = settings.get("api_key") or ""
        if not api_key:
            raise ValueError("LLM API key is required for OpenAI-compatible provider.")
        return OpenAICompatibleLLMAdapter(
            api_base=api_base,
            model=model,
            api_key=api_key,
            timeout_seconds=int(settings.get("timeout_seconds") or 45),
        )

    if provider == "ollama":
        return OllamaLLMAdapter(
            api_base=settings.get("api_base") or "http://127.0.0.1:11434",
            model=settings.get("model") or "qwen",
            timeout_seconds=int(settings.get("timeout_seconds") or 90),
        )

    raise ValueError(f"Unknown LLM provider: {provider}")


def is_real_llm(config: dict | None) -> bool:
    settings = (config or {}).get("llm", config or {})
    provider = (settings.get("provider") or "mock").strip().lower()
    return provider not in {"", "mock", "disabled"}


def llm_allows_fallback(config: dict | None) -> bool:
    settings = (config or {}).get("llm", config or {})
    return bool(settings.get("allow_fallback"))


def llm_temperature(config: dict | None) -> float:
    settings = (config or {}).get("llm", config or {})
    return float(settings.get("temperature") or 0.4)


def _openai_chat_endpoint(api_base: str) -> str:
    base = api_base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _post_json(endpoint: str, payload: dict, *, headers: dict[str, str], timeout_seconds: int) -> dict:
    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Provider HTTP {exc.code}: {body[:300]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Provider network error: {exc.reason}") from exc


def _post_stream(endpoint: str, payload: dict, *, headers: dict[str, str], timeout_seconds: int) -> Iterator[object]:
    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                if line.startswith("data:"):
                    line = line[5:].strip()
                    if line == "[DONE]":
                        yield line
                        return
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RuntimeError("LLM provider returned invalid streaming JSON.") from exc
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Provider HTTP {exc.code}: {body[:300]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Provider network error: {exc.reason}") from exc
