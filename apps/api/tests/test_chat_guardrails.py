"""Guardrail tests for the applicant planning chat — the layer that keeps the
LLM from being harmful, fabricating, promising outcomes, or discouraging users."""
from unittest.mock import AsyncMock, patch

import pytest

from app.services import chat_guardrails as gr
from app.services.chat import generate_guarded_chat_response

CTX = {
    "focused_job": {
        "job_title": "Metal Fabricator",
        "employer": "Acme Industrial",
        "score": 77.0,
        "status": "near_fit",
        "top_strengths": ["Your trade matches this role", "Location works for you"],
        "top_gaps": ["OSHA 10 certification"],
        "required_missing_items": ["OSHA 10 certification"],
        # engine copy de-dashed (2026-08): sentence break instead of em dash
        "recommended_next_step": "Close match. Check the requirements.",
    }
}


# ---------------------------------------------------------------------------
# Deterministic output validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    "Great news — I've applied to the job for you!",
    "I have scheduled your interview for Tuesday.",
    "Your interview has been scheduled with the hiring manager.",
])
def test_catches_agency_claims(bad):
    assert "agency_claim" in gr.validate_reply(bad, CTX)


@pytest.mark.parametrize("bad", [
    "With that certification the job is guaranteed.",
    "You will definitely get this offer.",
    "I promise you'll be hired within a month.",
])
def test_catches_outcome_guarantees(bad):
    assert "outcome_guarantee" in gr.validate_reply(bad, CTX)


@pytest.mark.parametrize("bad", [
    "Honestly, you're not qualified for this kind of work.",
    "You'll never pass the certification exam.",
    "It's hopeless to apply without experience.",
    "Don't bother applying to this one.",
])
def test_catches_discouraging_tone(bad):
    assert "discouraging_tone" in gr.validate_reply(bad, CTX)


def test_catches_fabricated_employer():
    reply = "You should also apply at Globex Corporation, they pay much better."
    assert "unknown_employer_mention" in gr.validate_reply(reply, CTX)


@pytest.mark.parametrize("good", [
    # Honest gap + concrete path — must NOT trip anything.
    "You're missing the OSHA 10 certification, and that's very fixable: it's a "
    "10-hour online course. Once you have it, your profile meets the stated requirements.",
    # Mentioning the in-context employer is fine.
    "The Metal Fabricator role at Acme Industrial lists OSHA 10 as required.",
    # Direct, encouraging next-step advice.
    "Start with the OSHA 10 this week, then update your credentials page so employers see it.",
    # 'guarantee' in a benign, non-outcome sense should pass.
    "No certification can guarantee an interview, but OSHA 10 removes a hard requirement gap.",
])
def test_clean_replies_pass(good):
    assert gr.validate_reply(good, CTX) == []


def test_no_context_skips_employer_check():
    # Without grounded employers we can't judge mentions — don't false-positive.
    assert gr.validate_reply("Try applying at Initech.", {}) == []


# ---------------------------------------------------------------------------
# Deterministic fallback — must be useful and derived only from context
# ---------------------------------------------------------------------------

def test_fallback_job_focused_uses_real_data():
    text = gr.deterministic_fallback(CTX)
    assert "Metal Fabricator" in text
    assert "OSHA 10 certification" in text
    assert "Acme Industrial" in text


def test_fallback_no_context_is_safe():
    text = gr.deterministic_fallback({})
    assert "profile" in text.lower()


# ---------------------------------------------------------------------------
# Suggested questions — deterministic scaffolding
# ---------------------------------------------------------------------------

def test_suggested_questions_job_focused_leads_with_gap():
    qs = gr.suggested_questions(CTX)
    assert 2 <= len(qs) <= 4
    assert any("OSHA 10" in q for q in qs)
    assert all(len(q) < 120 for q in qs)


def test_suggested_questions_general():
    qs = gr.suggested_questions({"top_matches": [{"job_title": "Welder"}]})
    assert len(qs) == 4


# ---------------------------------------------------------------------------
# Pipeline orchestration (LLM + moderation mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_passes_clean_reply():
    with patch("app.services.chat.generate_chat_response", new=AsyncMock(
        return_value="OSHA 10 is your one gap — a 10-hour course closes it."
    )), patch("app.services.chat_guardrails.moderate", new=AsyncMock(return_value=(False, []))):
        text, guard = await generate_guarded_chat_response("s1", "what's my gap?", [], CTX)
    assert guard.ok and guard.action == "passed"
    assert "OSHA 10" in text


@pytest.mark.asyncio
async def test_pipeline_regenerates_on_violation_then_passes():
    bad = "You'll never pass the exam, don't bother applying."
    good = "The exam is challenging but very passable with prep — start with the study guide."
    llm = AsyncMock(side_effect=[bad, good])
    with patch("app.services.chat.generate_chat_response", new=llm), \
         patch("app.services.chat_guardrails.moderate", new=AsyncMock(return_value=(False, []))):
        text, guard = await generate_guarded_chat_response("s1", "can I pass?", [], CTX)
    assert text == good
    assert guard.action == "regenerated"
    assert "discouraging_tone" in guard.checks_failed
    assert llm.call_count == 2
    # The retry must carry the corrective instruction.
    assert "violated" in (llm.call_args.kwargs.get("corrective_note") or "")


@pytest.mark.asyncio
async def test_pipeline_falls_back_when_retry_also_fails():
    bad = "I've applied on your behalf — the job is guaranteed!"
    llm = AsyncMock(side_effect=[bad, bad])
    with patch("app.services.chat.generate_chat_response", new=llm), \
         patch("app.services.chat_guardrails.moderate", new=AsyncMock(return_value=(False, []))):
        text, guard = await generate_guarded_chat_response("s1", "did you apply?", [], CTX)
    assert guard.action == "fallback"
    # Fallback is built from context, never the bad reply.
    assert "guaranteed" not in text
    assert "Metal Fabricator" in text


@pytest.mark.asyncio
async def test_pipeline_llm_down_gives_useful_fallback_not_dead_end():
    with patch("app.services.chat.generate_chat_response",
               new=AsyncMock(side_effect=RuntimeError("boom"))), \
         patch("app.services.chat_guardrails.moderate", new=AsyncMock(return_value=(False, []))):
        text, guard = await generate_guarded_chat_response("s1", "help", [], CTX)
    assert guard.action == "fallback" and "llm_unavailable" in guard.checks_failed
    assert "Metal Fabricator" in text  # real content, not "try again later"


@pytest.mark.asyncio
async def test_pipeline_self_harm_input_gets_crisis_line():
    with patch("app.services.chat_guardrails.moderate",
               new=AsyncMock(return_value=(True, ["self-harm/intent"]))):
        text, guard = await generate_guarded_chat_response("s1", "…", [], CTX)
    assert guard.action == "refused"
    assert "988" in text


@pytest.mark.asyncio
async def test_pipeline_flagged_input_refused_without_llm_call():
    llm = AsyncMock()
    with patch("app.services.chat.generate_chat_response", new=llm), \
         patch("app.services.chat_guardrails.moderate",
               new=AsyncMock(return_value=(True, ["harassment"]))):
        text, guard = await generate_guarded_chat_response("s1", "…", [], CTX)
    assert guard.action == "refused"
    llm.assert_not_called()
