import json
import unittest
from unittest.mock import patch

from openinterview_api.adapters.llm import OllamaLLMAdapter, OpenAICompatibleLLMAdapter


class _Response:
    def __init__(self, lines):
        self.lines = [line.encode("utf-8") for line in lines]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return iter(self.lines)


class LLMStreamTests(unittest.TestCase):
    def test_openai_sse_stream_yields_content_deltas(self):
        lines = [
            "data: " + json.dumps({"choices": [{"delta": {"content": "请说明"}}]}, ensure_ascii=False),
            "",
            "data: " + json.dumps({"choices": [{"delta": {"content": "边界？"}}]}, ensure_ascii=False),
            "data: [DONE]",
        ]
        adapter = OpenAICompatibleLLMAdapter("https://example.test/v1", "model", "key")
        with patch("openinterview_api.adapters.llm.urlopen", return_value=_Response(lines)):
            self.assertEqual("".join(adapter.complete_stream([])), "请说明边界？")

    def test_ollama_ndjson_stream_yields_content_deltas(self):
        lines = [
            json.dumps({"message": {"content": "请继续"}, "done": False}, ensure_ascii=False),
            json.dumps({"message": {"content": "说明？"}, "done": False}, ensure_ascii=False),
            json.dumps({"done": True}),
        ]
        adapter = OllamaLLMAdapter()
        with patch("openinterview_api.adapters.llm.urlopen", return_value=_Response(lines)):
            self.assertEqual("".join(adapter.complete_stream([])), "请继续说明？")

