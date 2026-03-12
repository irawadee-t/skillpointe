"""
verifier.py — Extraction verification and review queue flagging.

Step 7.3: Checks extraction quality and decides whether items need
human review. Can optionally call an LLM for ambiguous cases.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from .client import call_llm_json
from .prompts import VERIFIER_SYSTEM, format_verifier_prompt


@dataclass
class VerificationResult:
    entity_type: str            # 'applicant' or 'job'
    entity_id: str
    is_consistent: bool
    confidence_appropriate: bool
    issues: list[dict]
    suggested_confidence: str
    needs_human_review: bool
    review_reason: str | None
    review_queue_items: list[dict] = field(default_factory=list)


def verify_extraction(
    entity_type: str,
    entity_id: str,
    source_text: str,
    extraction_output: dict,
    client: OpenAI | None = None,
    model: str | None = None,
    use_llm: bool = False,
) -> VerificationResult:
    """
    Verify an extraction result. Uses heuristic checks by default;
    optionally calls an LLM for deeper verification.

    Returns VerificationResult with review_queue_items to be inserted into DB.
    """
    issues: list[dict] = []
    needs_review = False
    review_reason = None

    overall_conf = extraction_output.get("overall_confidence", "low")

    # Heuristic: flag if overall confidence is low
    if overall_conf == "low":
        needs_review = True
        review_reason = "low overall extraction confidence"
        issues.append({
            "type": "wrong_confidence",
            "description": "overall confidence is low — extraction may be unreliable",
            "severity": "warning",
        })

    # Heuristic: check for empty extraction on non-empty source
    if source_text and len(source_text.strip()) > 50:
        signal_keys = (
            ["skills", "certifications", "experience_signals"]
            if entity_type == "applicant"
            else ["required_skills", "required_credentials"]
        )
        total_items = sum(len(extraction_output.get(k, [])) for k in signal_keys)
        if total_items == 0:
            needs_review = True
            review_reason = review_reason or "no signals extracted from non-empty text"
            issues.append({
                "type": "missing_signal",
                "description": "source text is non-empty but no key signals were extracted",
                "severity": "warning",
            })

    # Heuristic: flag conflicting family signals
    families_key = "desired_job_families" if entity_type == "applicant" else "job_family_signals"
    families = extraction_output.get(families_key, [])
    if len(families) > 2:
        needs_review = True
        review_reason = review_reason or "multiple conflicting job family signals"
        issues.append({
            "type": "ambiguity",
            "description": f"{len(families)} job family signals detected — possible ambiguity",
            "severity": "warning",
        })

    # Optional LLM verification for borderline cases
    if use_llm and client and model and (needs_review or overall_conf == "medium"):
        try:
            llm_result = _llm_verify(client, model, entity_type, source_text, extraction_output)
            if llm_result.get("needs_human_review"):
                needs_review = True
                review_reason = llm_result.get("review_reason") or review_reason
            issues.extend(llm_result.get("issues", []))
            overall_conf = llm_result.get("suggested_confidence", overall_conf)
        except Exception:
            pass  # LLM verification is best-effort

    # Build review queue items
    queue_items: list[dict] = []
    if needs_review:
        queue_items.append({
            "item_type": "low_confidence_extraction",
            "entity_type": f"extracted_{entity_type}_signals",
            "description": review_reason or "extraction flagged for review",
            "flags": json.dumps(issues),
            "confidence_level": overall_conf,
            "priority": 3 if any(i.get("severity") == "critical" for i in issues) else 5,
        })

    return VerificationResult(
        entity_type=entity_type,
        entity_id=entity_id,
        is_consistent=not any(i.get("severity") == "critical" for i in issues),
        confidence_appropriate=overall_conf != "low",
        issues=issues,
        suggested_confidence=overall_conf,
        needs_human_review=needs_review,
        review_reason=review_reason,
        review_queue_items=queue_items,
    )


def _llm_verify(
    client: OpenAI,
    model: str,
    entity_type: str,
    source_text: str,
    extraction_output: dict,
) -> dict:
    prompt = format_verifier_prompt(
        entity_type=entity_type,
        source_text=source_text,
        extraction_json=json.dumps(extraction_output, indent=2),
    )
    return call_llm_json(client, model, VERIFIER_SYSTEM, prompt)
