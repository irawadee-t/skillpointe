"""
applicant_extractor.py — Extract structured signals from applicant profile text.

Input: raw applicant dict (DB row format)
Output: ApplicantSignals dataclass (no DB I/O)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from .client import call_llm_json, generate_embedding
from .prompts import APPLICANT_SYSTEM, PROMPT_VERSION, format_applicant_prompt


@dataclass
class ApplicantSignals:
    applicant_id: str
    skills: list[dict]
    certifications: list[dict]
    desired_job_families: list[dict]
    work_style_signals: list[dict]
    experience_signals: list[dict]
    readiness_signals: list[dict]
    intent_signals: list[dict]
    embedding: list[float] | None
    overall_confidence: str
    raw_llm_output: dict
    prompt_version: str
    llm_model: str

    @property
    def confidence_enum(self) -> str:
        return self.overall_confidence if self.overall_confidence in ("high", "medium", "low") else "low"

    @property
    def requires_review(self) -> bool:
        if self.confidence_enum == "low":
            return True
        low_items = sum(
            1 for items in [self.skills, self.certifications, self.experience_signals]
            for item in items if item.get("confidence") == "low"
        )
        return low_items >= 3

    def certifications_list(self) -> list[str]:
        """Flat list of certification names for gate evaluation."""
        return [c["name"] for c in self.certifications if c.get("name")]

    def skills_list(self) -> list[str]:
        """Flat list of skill names."""
        return [s["skill"] for s in self.skills if s.get("skill")]

    def has_internship(self) -> bool:
        for exp in self.experience_signals:
            desc = (exp.get("description") or "").lower()
            if "internship" in desc or "intern" in desc:
                return True
        return False

    def experience_quality(self) -> str:
        """Summarize experience richness: 'strong', 'moderate', 'weak', 'none'."""
        if not self.experience_signals:
            return "none"
        high_rel = sum(1 for e in self.experience_signals if e.get("relevance") == "high")
        if high_rel >= 2 or (high_rel >= 1 and self.has_internship()):
            return "strong"
        if self.experience_signals:
            return "moderate"
        return "weak"


def extract_applicant_signals(
    client: OpenAI,
    model: str,
    applicant: dict[str, Any],
    generate_emb: bool = True,
    embedding_model: str = "text-embedding-3-small",
) -> ApplicantSignals:
    """
    Run LLM extraction on one applicant's profile text.

    applicant dict must include: id, program_name_raw, bio_raw,
    experience_raw, career_goals_raw.
    """
    app_id = str(applicant["id"])

    user_prompt = format_applicant_prompt(
        program_name=applicant.get("program_name_raw") or "",
        bio=applicant.get("bio_raw") or "",
        experience=applicant.get("experience_raw") or applicant.get("internship_details") or "",
        career_goals=applicant.get("career_goals_raw") or "",
        essay_background=applicant.get("essay_background") or "",
        activities=applicant.get("activities") or applicant.get("honor_societies") or "",
    )

    raw_output = call_llm_json(client, model, APPLICANT_SYSTEM, user_prompt)

    embedding = None
    if generate_emb:
        from .embeddings import build_applicant_text
        combined = build_applicant_text(applicant)
        if combined.strip():
            embedding = generate_embedding(client, combined, model=embedding_model)

    return ApplicantSignals(
        applicant_id=app_id,
        skills=raw_output.get("skills", []),
        certifications=raw_output.get("certifications", []),
        desired_job_families=raw_output.get("desired_job_families", []),
        work_style_signals=raw_output.get("work_style_signals", []),
        experience_signals=raw_output.get("experience_signals", []),
        readiness_signals=raw_output.get("readiness_signals", []),
        intent_signals=raw_output.get("intent_signals", []),
        embedding=embedding,
        overall_confidence=raw_output.get("overall_confidence", "low"),
        raw_llm_output=raw_output,
        prompt_version=PROMPT_VERSION,
        llm_model=model,
    )
