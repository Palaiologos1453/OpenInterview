"""Read-only previews and a bounded, unplayed speculative audio stream."""
import asyncio
import base64
from collections import deque
from contextlib import suppress


class PreparedSpeech:
    def __init__(self, backend, question, *, max_seconds=30):
        self.backend = backend
        self.question = question
        self.max_seconds = max_seconds
        self.chunks = deque()
        self.committed = False
        self.seconds = 0
        self.done = False
        self.error = None
        self.changed = asyncio.Event()
        self.task = asyncio.create_task(self._produce())

    async def _produce(self):
        stream = self.backend.speech(self.question)
        try:
            async for chunk in stream:
                data = base64.b64decode(chunk["data"], validate=True)
                self.seconds += len(data) / (chunk["sample_rate"] * chunk["channels"] * chunk["sample_width"])
                if not self.committed and self.seconds > self.max_seconds:
                    raise ValueError("Speculative audio budget exceeded")
                self.chunks.append(chunk)
                self.changed.set()
        except asyncio.CancelledError:
            self.error = RuntimeError("Speculation cancelled")
            raise
        except Exception as exc:
            self.error = exc
        finally:
            await stream.aclose()
            self.done = True
            self.changed.set()

    async def events(self):
        try:
            while True:
                self.changed.clear()
                if self.error:
                    raise self.error
                while self.chunks:
                    chunk = self.chunks.popleft()
                    yield chunk
                if self.done:
                    return
                await self.changed.wait()
        finally:
            await self.close()

    async def close(self):
        if not self.task.done():
            self.task.cancel()
        with suppress(asyncio.CancelledError):
            await self.task


class ReplyPreparation:
    def __init__(self, backend, session_id, *, enabled=True):
        self.backend = backend
        self.session_id = session_id
        self.enabled = enabled
        self.turn_index = 0
        self.generation = 0
        self.preview_task = None
        self.prepared = None
        self.last_question = None
        self.attempted = False
        self.metrics = {"preview_calls": 0, "prefetch_started": 0, "prefetch_hits": 0, "prefetch_misses": 0}

    def observe(self, text):
        if not self.enabled or self.attempted or len(text.strip()) < 12:
            return
        if self.preview_task and not self.preview_task.done():
            return
        self.preview_task = asyncio.create_task(self._preview(text, self.generation, self.turn_index))

    async def _preview(self, text, generation, turn_index):
        try:
            self.metrics["preview_calls"] += 1
            result = await self.backend.preview(self.session_id, text, turn_index)
            if generation != self.generation or result["base_turn_index"] != turn_index:
                return
            question = result["next_question"]
            # Two independent transcript snapshots must predict the same question.
            if question and not result["is_finished"] and question == self.last_question:
                self.attempted = True
                self.prepared = PreparedSpeech(self.backend, question)
                self.metrics["prefetch_started"] += 1
            self.last_question = question
        except asyncio.CancelledError:
            raise
        except Exception:
            pass  # final answer path remains authoritative and reports its errors

    async def seal(self):
        """Freeze preview work before committing the final answer."""
        self.generation += 1
        if self.preview_task:
            self.preview_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.preview_task
            self.preview_task = None

    async def take(self, result):
        prepared, self.prepared = self.prepared, None
        hit = bool(prepared and not prepared.error
            and result["turn_index"] == self.turn_index + 1
            and result["next_question"] == prepared.question)
        if prepared:
            self.metrics["prefetch_hits" if hit else "prefetch_misses"] += 1
            if not hit:
                await prepared.close()
            else:
                prepared.committed = True
        self.turn_index = result["turn_index"]
        self.last_question = None
        self.attempted = False
        return prepared if hit else None

    async def close(self):
        await self.seal()
        if self.prepared:
            await self.prepared.close()
            self.prepared = None
