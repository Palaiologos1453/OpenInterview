from contextlib import asynccontextmanager
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
import asyncio

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller import app  # noqa: E402


class CloudJoinTests(unittest.TestCase):
    def test_cloud_credentials_go_only_to_backend_not_room_dispatch(self):
        backend = SimpleNamespace(post=AsyncMock(side_effect=[{}, {}, {
            "session_id": "test-session", "next_question": "请介绍项目。", "interview_strategy": "semantic"}]))
        server = SimpleNamespace(room=SimpleNamespace(create_room=AsyncMock(), delete_room=AsyncMock()),
            agent_dispatch=SimpleNamespace(create_dispatch=AsyncMock()))
        original = app.router.lifespan_context

        @asynccontextmanager
        async def lifespan(_):
            app.state.config = {"url": "ws://127.0.0.1:7880", "api_key": "devkey", "api_secret": "x" * 40}
            app.state.backend = backend
            app.state.livekit = server
            app.state.join_lock = asyncio.Lock()
            app.state.active = None
            yield

        app.router.lifespan_context = lifespan
        try:
            with TestClient(app) as client:
                missing = client.post("/join", json={})
                self.assertEqual(missing.status_code, 400)
                backend.post.assert_not_called()
                response = client.post("/join", json={"llm": {
                    "api_base": "https://test.invalid/v1", "model": "cloud-model", "api_key": "PRIVATE-KEY"}})
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("PRIVATE-KEY", response.text)
                dispatched = server.agent_dispatch.create_dispatch.call_args.args[0]
                self.assertNotIn("PRIVATE-KEY", dispatched.metadata)
                self.assertEqual(json.loads(dispatched.metadata)["interview_strategy"], "semantic")
                created = backend.post.call_args_list[-1].args[1]
                self.assertEqual(created["provider_config"]["llm"]["api_key"], "PRIVATE-KEY")
                self.assertEqual(created["provider_config"]["tts"]["provider"], "cosyvoice")
        finally:
            app.router.lifespan_context = original
