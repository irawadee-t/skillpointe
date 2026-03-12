"""
job_extractor.py — Extract structured signals from job posting text.

Input: raw job dict (DB row format)
Output: JobSignals dataclass (no DB I/O)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from .client import call_llm_json, generate_embedding
from .prompts import JOB_SYSTEM, PROMPT_VERSION, format_job_prompt


@dataclass
class JobSignals:
    job_id: str
    required_skills: list[dict]
    preferred_skills: list[dict]
    required_credentials: list[dict]
    preferred_credentials: list[dict]
    job_family_signals: list[dict]
    experience_level: dict
    physical_requirements: list[dict]
    work_style_signals: list[dict]
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
            1 for items in [self.required_skills, self.required_credentials]
            for item in items if item.get("confidence") == "low"
        )
        return low_items >= 2

    def required_credential_names(self) -> list[str]:
        """Flat list of required credential names for gate evaluation."""
        return [c["credential"] for c in self.required_credentials if c.get("credential")]

    def required_skill_names(self) -> list[str]:
        """Flat list of required skill names."""
        return [s["skill"] for s in self.required_skills if s.get("skill")]

    def critical_skill_names(self) -> list[str]:
        """Skills marked as critical importance."""
        return [
            s["skill"] for s in self.required_skills
            if s.get("importance") == "critical" and s.get("skill")
        ]


def extract_job_signals(
    client: OpenAI,
    model: str,
    job: dict[str, Any],
    generate_emb: bool = True,
    embedding_model: str = "text-embedding-3-small",
) -> JobSignals:
    """
    Run LLM extraction on one job posting.

    job dict must include: id, title_raw, description_raw,
    requirements_raw, preferred_qualifications_raw.
    """
    job_id = str(job["id"])

    user_prompt = format_job_prompt(
        title=job.get("title_raw") or job.get("title_normalized") or "",
        description=job.get("description_raw") or "",
        requirements=job.get("requirements_raw") or "",
        preferred_qualifications=job.get("preferred_qualifications_raw") or "",
    )

    raw_output = call_llm_json(client, model, JOB_SYSTEM, user_prompt)

    embedding = None
    if generate_emb:
        from .embeddings import build_job_text
        combined = build_job_text(job)
        if combined.strip():
            embedding = generate_embedding(client, combined, model=embedding_model)

    return JobSignals(
        job_id=job_id,
        required_skills=raw_output.get("required_skills", []),
        preferred_skills=raw_output.get("preferred_skills", []),
        required_credentials=raw_output.get("required_credentials", []),
        preferred_credentials=raw_output.get("preferred_credentials", []),
        job_family_signals=raw_output.get("job_family_signals", []),
        experience_level=raw_output.get("experience_level", {}),
        physical_requirements=raw_output.get("physical_requirements", []),
        work_style_signals=raw_output.get("work_style_signals", []),
        embedding=embedding,
        overall_confidence=raw_output.get("overall_confidence", "low"),
        raw_llm_output=raw_output,
        prompt_version=PROMPT_VERSION,
        llm_model=model,
    )
