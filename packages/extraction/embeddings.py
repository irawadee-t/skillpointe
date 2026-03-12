"""
embeddings.py — Text combination and cosine similarity for semantic scoring.

Pure functions with no DB I/O.
"""
from __future__ import annotations

import math
from typing import Any


def build_applicant_text(applicant: dict[str, Any]) -> str:
    """Combine all applicant text fields into a single string for embedding."""
    parts = []
    if applicant.get("program_name_raw"):
        parts.append(f"Program: {applicant['program_name_raw']}")
    if applicant.get("bio_raw"):
        parts.append(f"Bio: {applicant['bio_raw']}")
    if applicant.get("experience_raw"):
        parts.append(f"Experience: {applicant['experience_raw']}")
    if applicant.get("career_goals_raw"):
        parts.append(f"Career Goals: {applicant['career_goals_raw']}")
    return "\n\n".join(parts)


def build_job_text(job: dict[str, Any]) -> str:
    """Combine all job text fields into a single string for embedding."""
    parts = []
    title = job.get("title_raw") or job.get("title_normalized")
    if title:
        parts.append(f"Title: {title}")
    if job.get("description_raw"):
        parts.append(f"Description: {job['description_raw']}")
    if job.get("requirements_raw"):
        parts.append(f"Requirements: {job['requirements_raw']}")
    if job.get("preferred_qualifications_raw"):
        parts.append(f"Preferred: {job['preferred_qualifications_raw']}")
    return "\n\n".join(parts)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    Compute cosine similarity between two vectors.

    OpenAI embeddings are unit-normalized, so this reduces to dot product,
    but we compute the full formula for safety.

    Returns value in [-1, 1].
    """
    if len(a) != len(b) or not a:
        return 0.0

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)


def semantic_score_from_embeddings(
    applicant_embedding: list[float] | None,
    job_embedding: list[float] | None,
) -> tuple[float, str]:
    """
    Compute semantic score (0–100) from applicant and job embeddings.

    Returns (score, note).
    """
    if applicant_embedding is None or job_embedding is None:
        return 50.0, "embedding missing — using neutral default"

    sim = cosine_similarity(applicant_embedding, job_embedding)
    score = max(0.0, min(100.0, sim * 100.0))
    return round(score, 2), f"cosine similarity: {sim:.4f}"
