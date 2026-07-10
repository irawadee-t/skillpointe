"""
Document-verification assessment (pure).

Compares an OCR extraction against the worker's *claimed* credential (name +
issuer) and decides whether the document attests to it. The router turns a
'verified' decision into VerificationEvidence -> derive_level (caps at
Institution-Verified for a document; SKILLED-Verified additionally needs identity
KYC). Pure + unit-tested; no I/O, no DB.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.integrations.ocr import OCRExtraction

_STOP = {"the", "of", "and", "for", "a", "an", "in", "to", "certificate",
         "certification", "license", "program", "inc", "llc"}


def _tokens(s: str | None) -> set[str]:
    if not s:
        return set()
    return {t for t in re.findall(r"[a-z0-9]+", s.lower()) if len(t) > 2 and t not in _STOP}


def _overlap(claim: set[str], text: set[str]) -> float:
    if not claim:
        return 0.0
    return len(claim & text) / len(claim)


@dataclass(frozen=True)
class DocAssessment:
    decision: str                 # 'verified' | 'review' | 'rejected'
    score: float                  # 0..1 overall confidence the doc supports the claim
    name_matched: bool
    issuer_matched: bool
    document_authentic: bool
    reasons: list[str] = field(default_factory=list)


def assess(
    extraction: OCRExtraction,
    claimed_name: str,
    claimed_issuer: str | None = None,
    *,
    verify_threshold: float = 0.7,
    review_threshold: float = 0.4,
) -> DocAssessment:
    blob = _tokens(extraction.raw_text) | _tokens(" ".join(extraction.fields.values()))
    name_overlap = _overlap(_tokens(claimed_name), blob)
    name_matched = name_overlap >= 0.5

    issuer_tokens = _tokens(claimed_issuer)
    detected = _tokens(extraction.issuer_detected) | blob
    if issuer_tokens:
        issuer_overlap = _overlap(issuer_tokens, detected)
        issuer_matched = issuer_overlap >= 0.5
    else:
        # No issuer claimed — accept a detected institutional issuer as corroboration.
        issuer_overlap = 1.0 if extraction.issuer_detected else 0.0
        issuer_matched = extraction.issuer_detected is not None

    authentic = bool(extraction.authentic)

    score = round(
        0.45 * name_overlap
        + 0.25 * issuer_overlap
        + 0.20 * (1.0 if authentic else 0.0)
        + 0.10 * float(extraction.confidence),
        3,
    )

    reasons: list[str] = []
    reasons.append(("matched" if name_matched else "weak match") + f" on credential name ({name_overlap:.0%})")
    reasons.append(("issuer recognized" if issuer_matched else "issuer not confirmed")
                   + (f": {extraction.issuer_detected}" if extraction.issuer_detected else ""))
    if not authentic:
        reasons.append("document lacked enough structure to confirm authenticity")
    if extraction.signature_detected:
        reasons.append("signature/authority block detected")

    if name_matched and issuer_matched and authentic and score >= verify_threshold:
        decision = "verified"
    elif score >= review_threshold:
        decision = "review"
    else:
        decision = "rejected"

    return DocAssessment(
        decision=decision, score=score, name_matched=name_matched,
        issuer_matched=issuer_matched, document_authentic=authentic, reasons=reasons,
    )
