"""
sse.py — shared helpers for buffer-then-stream SSE endpoints.

Both chat surfaces (applicant planning chat, employer analytics chat) deliver
replies the same way: the FULL pipeline runs to completion server-side, the
validated text is the only thing that ever leaves, and delivery is paced as
Server-Sent Events so the client can fill the bubble progressively.

Framing contract (identical for every stream endpoint):

    event: chunk  data: {"delta": "..."}    (repeated)
    event: done   data: {<final payload>}   (terminal)

Any auth/ownership/validation error surfaces BEFORE the stream starts, as a
plain HTTP error — which is what lets clients fall back to the JSON endpoint.
"""
from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any

# ~4 word-tokens per SSE chunk; total artificial stream time is capped so long
# replies don't crawl. The reply is already fully generated AND validated
# before the first byte is emitted (buffer-then-stream) — this only paces
# delivery so the bubble fills progressively.
STREAM_CHUNK_TOKENS = 4
STREAM_MAX_SECONDS = 2.0
STREAM_CHUNK_DELAY = 0.024

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",  # disable proxy buffering (nginx)
}


def chunk_text(text: str, tokens_per_chunk: int = STREAM_CHUNK_TOKENS) -> list[str]:
    """Split text into whitespace-preserving chunks of a few tokens each."""
    pieces = re.findall(r"\S+\s*|\s+", text)
    if not pieces:
        return []
    return [
        "".join(pieces[i : i + tokens_per_chunk])
        for i in range(0, len(pieces), tokens_per_chunk)
    ]


def sse_frame(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def paced_text_stream(text: str, done_payload: dict[str, Any]) -> AsyncIterator[str]:
    """Yield `chunk` frames for already-validated text, then one `done` frame."""
    chunks = chunk_text(text)
    delay = min(STREAM_CHUNK_DELAY, STREAM_MAX_SECONDS / max(1, len(chunks)))
    for chunk in chunks:
        yield sse_frame("chunk", {"delta": chunk})
        await asyncio.sleep(delay)
    yield sse_frame("done", done_payload)
