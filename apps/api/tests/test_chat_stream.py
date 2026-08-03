"""
test_chat_stream.py — POST /applicant/me/chat/sessions/{id}/messages/stream

The streaming endpoint MUST be buffer-then-stream: the full guardrail pipeline
(moderation → grounded generation → deterministic validation → regen/fallback)
runs to completion on the COMPLETE reply, the validated message is persisted,
and only THEN is the text chunked out as SSE. These tests pin:

  - SSE framing: `event: chunk` deltas that reassemble to the exact validated
    text, terminated by one `event: done` frame carrying the stored message.
  - Guardrail integration: the guarded pipeline is invoked exactly once with
    the full user message; a tripped guardrail streams the FALLBACK text (never
    the raw reply) and still queues the review item.
  - Error behavior: an unknown session returns a plain HTTP 404 (no SSE body),
    which is what lets the client fall back to the JSON path.
  - Regression: the JSON endpoint still returns the same stored message.

Mock-DB style follows test_interest_signal.py: patch get_db in the router
module, override the auth dependency, assert on executed SQL.
"""
from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user, require_applicant
from app.auth.schemas import CurrentUser
from app.main import app
from app.routers.chat import _chunk_text
from app.services.chat_guardrails import GuardrailResult

SESSION_ID = "55555555-0000-0000-0000-555555555555"
APPLICANT_ID = "11111111-0000-0000-0000-111111111111"
MESSAGE_ID = "99999999-0000-0000-0000-999999999999"

REPLY = (
    "You're missing the OSHA 10 certification, and that's very fixable: "
    "it's a 10-hour online course. Start there this week."
)


def _applicant_user() -> CurrentUser:
    # Unique user id per call so the per-user in-memory LLM rate limiter
    # (5/min) never trips across tests in one run.
    return CurrentUser(
        user_id=str(uuid.uuid4()),
        email="applicant@test.local",
        role="applicant",
        onboarding_complete=True,
    )


def _session_row(snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"context_snapshot": snapshot or {"top_matches": []}}


def _msg_row(content: str = REPLY) -> dict[str, Any]:
    return {
        "message_id": MESSAGE_ID,
        "role": "assistant",
        "content": content,
        "created_at": "2026-08-02T12:00:00+00:00",
    }


def _mock_conn(session_row: dict[str, Any] | None, content: str = REPLY) -> AsyncMock:
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=APPLICANT_ID)
    # fetchrow order: session ownership check, then assistant-message insert.
    conn.fetchrow = AsyncMock(side_effect=[session_row, _msg_row(content)])
    conn.fetch = AsyncMock(return_value=[])  # empty history
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    return conn


def _patch_db(conn: AsyncMock):
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("app.routers.chat.get_db", return_value=mock_ctx)


def _patch_guarded(text: str = REPLY, guard: GuardrailResult | None = None) -> Any:
    return patch(
        "app.routers.chat.generate_guarded_chat_response",
        new=AsyncMock(return_value=(text, guard or GuardrailResult(ok=True))),
    )


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _auth():
    user = _applicant_user()
    app.dependency_overrides[require_applicant] = lambda: user
    app.dependency_overrides[get_current_user] = lambda: user
    yield
    app.dependency_overrides.clear()


def _post_stream(client: TestClient, content: str = "what's my gap?"):
    return client.post(
        f"/applicant/me/chat/sessions/{SESSION_ID}/messages/stream",
        json={"content": content},
        headers={"Authorization": "Bearer fake"},
    )


def _parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    """Parse SSE text into (event, data) tuples, asserting frame shape."""
    events: list[tuple[str, dict[str, Any]]] = []
    for frame in body.split("\n\n"):
        if not frame.strip():
            continue
        lines = frame.split("\n")
        assert lines[0].startswith("event: "), f"bad frame: {frame!r}"
        assert lines[1].startswith("data: "), f"bad frame: {frame!r}"
        events.append((lines[0][7:], json.loads(lines[1][6:])))
    return events


# ---------------------------------------------------------------------------
# SSE framing
# ---------------------------------------------------------------------------

class TestStreamFraming:
    def test_stream_reassembles_to_validated_text(self, client: TestClient) -> None:
        conn = _mock_conn(_session_row())
        with _patch_db(conn), _patch_guarded():
            res = _post_stream(client)

        assert res.status_code == 200, res.text
        assert res.headers["content-type"].startswith("text/event-stream")

        events = _parse_sse(res.text)
        chunk_events = [d for e, d in events if e == "chunk"]
        done_events = [d for e, d in events if e == "done"]

        assert len(chunk_events) >= 2, "reply must arrive progressively, not as one blob"
        assert "".join(d["delta"] for d in chunk_events) == REPLY
        assert len(done_events) == 1
        assert events[-1][0] == "done"

        done = done_events[0]
        assert done["message_id"] == MESSAGE_ID
        assert done["role"] == "assistant"
        assert done["content"] == REPLY
        assert done["created_at"]

    def test_streamed_text_is_the_stored_message(self, client: TestClient) -> None:
        """What streams is exactly what was persisted — no divergence."""
        conn = _mock_conn(_session_row())
        with _patch_db(conn), _patch_guarded():
            res = _post_stream(client)

        insert_sql = str(conn.fetchrow.call_args_list[1].args[0])
        assert "INSERT INTO public.chat_messages" in insert_sql
        stored_content = conn.fetchrow.call_args_list[1].args[2]
        events = _parse_sse(res.text)
        assert "".join(d["delta"] for e, d in events if e == "chunk") == stored_content

    def test_chunk_text_preserves_content_exactly(self) -> None:
        for text in [REPLY, "one", "  leading and trailing  ", "line\nbreaks\n\nkept"]:
            assert "".join(_chunk_text(text)) == text
        assert _chunk_text("") == []


# ---------------------------------------------------------------------------
# Guardrails are non-negotiable
# ---------------------------------------------------------------------------

class TestStreamGuardrails:
    def test_guarded_pipeline_called_once_with_full_message(self, client: TestClient) -> None:
        conn = _mock_conn(_session_row())
        guarded = AsyncMock(return_value=(REPLY, GuardrailResult(ok=True)))
        with _patch_db(conn), patch(
            "app.routers.chat.generate_guarded_chat_response", new=guarded
        ):
            res = _post_stream(client, content="what's my gap?")

        assert res.status_code == 200
        guarded.assert_awaited_once()
        assert guarded.call_args.kwargs["user_message"] == "what's my gap?"

    def test_tripped_guardrail_streams_fallback_and_queues_review(self, client: TestClient) -> None:
        fallback = "Here's a quick snapshot from your matches: finish your profile first."
        guard = GuardrailResult(ok=False, checks_failed=["outcome_guarantee"], action="fallback")
        conn = _mock_conn(_session_row(), content=fallback)
        with _patch_db(conn), _patch_guarded(fallback, guard):
            res = _post_stream(client)

        assert res.status_code == 200
        events = _parse_sse(res.text)
        assert "".join(d["delta"] for e, d in events if e == "chunk") == fallback

        all_sql = " ".join(str(c.args[0]) for c in conn.execute.call_args_list)
        assert "INSERT INTO public.review_queue_items" in all_sql

    def test_stub_path_streams_without_openai_key(self, client: TestClient) -> None:
        """No OPENAI key → deterministic fallback text streams the same way."""
        snapshot = {
            "top_matches": [
                {"job_title": "Welder", "employer": "Acme", "score": 80.0,
                 "top_gaps": ["OSHA 10"], "recommended_next_step": "Get OSHA 10"},
            ]
        }
        from app.services.chat_guardrails import deterministic_fallback
        fallback_text = deterministic_fallback(snapshot)
        conn = _mock_conn(_session_row(snapshot), content=fallback_text)
        guard = GuardrailResult(ok=False, checks_failed=["llm_unavailable"], action="fallback")
        with _patch_db(conn), _patch_guarded(fallback_text, guard):
            res = _post_stream(client)

        assert res.status_code == 200
        events = _parse_sse(res.text)
        assert "".join(d["delta"] for e, d in events if e == "chunk") == fallback_text
        assert events[-1][0] == "done"


# ---------------------------------------------------------------------------
# Errors surface as plain HTTP (client falls back to JSON path)
# ---------------------------------------------------------------------------

class TestStreamErrors:
    def test_unknown_session_is_plain_404(self, client: TestClient) -> None:
        conn = _mock_conn(session_row=None)
        conn.fetchrow = AsyncMock(return_value=None)
        with _patch_db(conn), _patch_guarded():
            res = _post_stream(client)

        assert res.status_code == 404
        assert "text/event-stream" not in res.headers.get("content-type", "")

    def test_blank_content_is_422(self, client: TestClient) -> None:
        conn = _mock_conn(_session_row())
        with _patch_db(conn), _patch_guarded():
            res = _post_stream(client, content="   ")
        assert res.status_code == 422


# ---------------------------------------------------------------------------
# JSON endpoint regression
# ---------------------------------------------------------------------------

class TestJsonEndpointUnchanged:
    def test_json_post_still_returns_stored_message(self, client: TestClient) -> None:
        conn = _mock_conn(_session_row())
        with _patch_db(conn), _patch_guarded():
            res = client.post(
                f"/applicant/me/chat/sessions/{SESSION_ID}/messages",
                json={"content": "what's my gap?"},
                headers={"Authorization": "Bearer fake"},
            )
        assert res.status_code == 201, res.text
        data = res.json()
        assert data["message_id"] == MESSAGE_ID
        assert data["content"] == REPLY
