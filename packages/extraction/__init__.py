"""
extraction — LLM-powered signal extraction for SkillPointe Match.

Phase 7: Extracts structured signals from applicant profiles and job postings,
generates embeddings for semantic scoring, and flags low-confidence items
for admin review.

This package has NO database I/O. All DB reads/writes happen in scripts/.
"""
from .client import get_openai_client, call_llm_json, generate_embedding
from .applicant_extractor import extract_applicant_signals, ApplicantSignals
from .job_extractor import extract_job_signals, JobSignals
from .verifier import verify_extraction, VerificationResult
from .embeddings import build_applicant_text, build_job_text, cosine_similarity

__all__ = [
    "get_openai_client",
    "call_llm_json",
    "generate_embedding",
    "extract_applicant_signals",
    "ApplicantSignals",
    "extract_job_signals",
    "JobSignals",
    "verify_extraction",
    "VerificationResult",
    "build_applicant_text",
    "build_job_text",
    "cosine_similarity",
]
