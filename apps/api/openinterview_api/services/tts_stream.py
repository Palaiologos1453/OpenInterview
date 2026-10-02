from __future__ import annotations

import anyio


async def iterate_tts_chunks(iterator):
    """Run blocking inference off the event loop and close it on disconnect.

    AnyIO waits for an in-flight next() before closing the generator; cancelling
    asyncio.to_thread(next, ...) directly can otherwise close a running generator.
    """
    sentinel = object()
    try:
        while True:
            chunk = await anyio.to_thread.run_sync(lambda: next(iterator, sentinel))
            if chunk is sentinel:
                return
            yield chunk
    finally:
        with anyio.CancelScope(shield=True):
            await anyio.to_thread.run_sync(iterator.close)
