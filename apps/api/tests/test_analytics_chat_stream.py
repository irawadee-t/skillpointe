"""
test_analytics_chat_stream.py — POST /employer/me/analytics/chat/stream

The employer analytics chat stream MUST be buffer-then-stream, exactly like
the applicant planning chat (test_chat_stream.py): the full grounding + answer
pipeline runs to completion, and only THEN is the finished text chunked out as
SSE. These tests pin:

  - SSE framing: `event: chunk` deltas that reassemble to the exact answer,
    terminated by one `event: done` frame carrying the full ChatOut payload.
  - Stream/JSON parity: with identical grounding data, the streamed text is
    byte-identical to what POST /chat returns.
  - Error behavior: a missing employer profile returns a plain HTTP 404 (no
    SSE body) and validation errors a plain 422 — what lets the client fall
    back to the JSON path.
  - Regression: the JSON endpoint still returns the deterministic answer.

Mock-DB style follows test_chat_stream.py: patch get_db in the router module,
override the auth dependency. get_settings is patched to the no-key path so
answers are the deterministic SQL-grounded ones (stubbed=True).
"""
from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user, require_employer_or_admin
from app.auth.schemas import CurrentUser
from app.main import app
from app.routers.analytics_chat import _deterministic_answer

EMPLOYER_ID = "77777777-0000-0000-0000-777777777777"

COUNTERS: dict[str, Any] = {
    "outreach_sent": 4,
    "candidates_interested": 9,
    "self_reported_applied": 3,
    "hires": 2,
    "total_apps": 12,
    "hired_apps": 2,
    "jobs": 5,
    "avg_days_to_hire": 11,
    "median_wage": 52000,
    "platform_median_wage": 48000,
    "dormant_count": 1,
}

FASTEST_ROWS = [
    {"title": "Maintenance Technician", "n": 6},
    {"title": "CNC Operator", "n": 4},
]

TRADE_ROWS = [
    {"family": "Industrial Maintenance", "n": 5},
    {"family": "Welding", "n": 2},
]

QUESTION = "Which of my jobs is filling the fastest?"


def _employer_user() -> CurrentUser:
    return CurrentUser(
        user_id=str(uuid.uuid4()),
        email="employer@test.local",
        role="employer",
        onboarding_complete=True,
    )


def _mock_conn(emp_row: dict[str, Any] | None = None) -> AsyncMock:
    conn = AsyncMock()
    # fetchrow order: employer_contacts lookup, then the counters row.
    conn.fetchrow = AsyncMock(side_effect=[emp_row, COUNTERS])
    # fetch order: fastest-filling jobs, then trade families.
    conn.fetch = AsyncMock(side_effect=[FASTEST_ROWS, TRADE_ROWS])
    return conn


def _patch_db(conn: AsyncMock):
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("app.routers.analytics_chat.get_db", return_value=mock_ctx)


def _patch_no_llm():
    """Force the deterministic (no OpenAI key) path regardless of local .env."""
    return patch(
        "app.routers.analytics_chat.get_settings",
        return_value=MagicMock(openai_api_key=""),
    )


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _auth():
    user = _employer_user()
    app.dependency_overrides[require_employer_or_admin] = lambda: user
    app.dependency_overrides[get_current_user] = lambda: user
    yield
    app.dependency_overrides.clear()


def _post_stream(client: TestClient, question: str = QUESTION):
    return client.post(
        "/employer/me/analytics/chat/stream",
        json={"question": question},
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


def _expected_answer(question: str = QUESTION) -> str:
    context = {
        "total_applications": COUNTERS["total_apps"],
        "hired_applications": COUNTERS["hired_apps"],
        "jobs_posted": COUNTERS["jobs"],
        "avg_days_to_hire": COUNTERS["avg_days_to_hire"],
        "median_wage": COUNTERS["median_wage"],
        "platform_median_wage": COUNTERS["platform_median_wage"],
        "dormant_awaiting_review": COUNTERS["dormant_count"],
        "outreach_sent": COUNTERS["outreach_sent"],
        "candidates_interested": COUNTERS["candidates_interested"],
        "self_reported_applied": COUNTERS["self_reported_applied"],
        "hires_reported": COUNTERS["hires"],
        "fastest_jobs_30d": [(r["title"], r["n"]) for r in FASTEST_ROWS],
        "top_trades_this_month": [(r["family"], r["n"]) for r in TRADE_ROWS],
    }
    return _deterministic_answer(question, context)


# ---------------------------------------------------------------------------
# SSE framing
# ---------------------------------------------------------------------------

class TestStreamFraming:
    def test_stream_reassembles_to_full_answer(self, client: TestClient) -> None:
        conn = _mock_conn({"employer_id": EMPLOYER_ID})
        with _patch_db(conn), _patch_no_llm():
            res = _post_stream(client)

        assert res.status_code == 200, res.text
        assert res.headers["content-type"].startswith("text/event-stream")

        events = _parse_sse(res.text)
        chunk_events = [d for e, d in events if e == "chunk"]
        done_events = [d for e, d in events if e == "done"]

        assert len(chunk_events) >= 2, "answer must arrive progressively, not as one blob"
        streamed = "".join(d["delta"] for d in chunk_events)
        assert streamed == _expected_answer()
        assert "Maintenance Technician" in streamed  # grounded in the SQL rows

        assert len(done_events) == 1
        assert events[-1][0] == "done"
        done = done_events[0]
        assert done["answer"] == streamed
        assert done["stubbed"] is True

    def test_streamed_text_matches_json_endpoint(self, client: TestClient) -> None:
        """Stream/JSON parity: identical grounding data → identical answer."""
        with _patch_db(_mock_conn({"employer_id": EMPLOYER_ID})), _patch_no_llm():
            stream_res = _post_stream(client)
        with _patch_db(_mock_conn({"employer_id": EMPLOYER_ID})), _patch_no_llm():
            json_res = client.post(
                "/employer/me/analytics/chat",
                json={"question": QUESTION},
                headers={"Authorization": "Bearer fake"},
            )

        assert stream_res.status_code == 200 and json_res.status_code == 200
        events = _parse_sse(stream_res.text)
        streamed = "".join(d["delta"] for e, d in events if e == "chunk")
        assert streamed == json_res.json()["answer"]

    def test_wage_question_streams_grounded_benchmark(self, client: TestClient) -> None:
        question = "How does my median wage compare to the platform?"
        conn = _mock_conn({"employer_id": EMPLOYER_ID})
        with _patch_db(conn), _patch_no_llm():
            res = _post_stream(client, question=question)

        assert res.status_code == 200
        events = _parse_sse(res.text)
        streamed = "".join(d["delta"] for e, d in events if e == "chunk")
        assert streamed == _expected_answer(question)
        assert "$52,000" in streamed and "$48,000" in streamed


# ---------------------------------------------------------------------------
# Errors surface as plain HTTP (client falls back to JSON path)
# ---------------------------------------------------------------------------

class TestStreamErrors:
    def test_missing_employer_profile_is_plain_404(self, client: TestClient) -> None:
        conn = _mock_conn(emp_row=None)
        with _patch_db(conn), _patch_no_llm():
            res = _post_stream(client)

        assert res.status_code == 404
        assert "text/event-stream" not in res.headers.get("content-type", "")

    def test_too_short_question_is_422(self, client: TestClient) -> None:
        conn = _mock_conn({"employer_id": EMPLOYER_ID})
        with _patch_db(conn), _patch_no_llm():
            res = _post_stream(client, question="a")
        assert res.status_code == 422
        assert "text/event-stream" not in res.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# JSON endpoint regression
# ---------------------------------------------------------------------------

class TestJsonEndpointUnchanged:
    def test_json_post_still_returns_deterministic_answer(self, client: TestClient) -> None:
        conn = _mock_conn({"employer_id": EMPLOYER_ID})
        with _patch_db(conn), _patch_no_llm():
            res = client.post(
                "/employer/me/analytics/chat",
                json={"question": QUESTION},
                headers={"Authorization": "Bearer fake"},
            )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["answer"] == _expected_answer()
        assert data["stubbed"] is True
