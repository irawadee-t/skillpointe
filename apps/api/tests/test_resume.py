"""Unit tests for AI summary (prompt + fallback) and PDF résumé generation."""
from app.skilled_pro.ai import build_summary_prompt, template_summary
from app.skilled_pro.resume import build_resume_pdf

PROFILE = {
    "name": "Jordan Rivera",
    "trade": "Electrical",
    "city": "Carrollton",
    "state": "GA",
    "available_from": "2026-08-01",
    "willing_to_relocate": True,
    "credentials": [
        {"name": "EPA Section 608 Technician Certification", "badge": "Institution-Verified",
         "credential_type": "certification", "issuer": "EPA"},
        {"name": "OSHA 30", "badge": "Self-Reported", "credential_type": "safety", "issuer": "OSHA"},
    ],
}


def test_prompt_grounds_in_facts_and_forbids_invention():
    msgs = build_summary_prompt(PROFILE)
    system = msgs[0]["content"].lower()
    user = msgs[1]["content"]
    assert "only the facts" in system or "never invent" in system
    assert "EPA Section 608 Technician Certification" in user
    assert "Carrollton, GA" in user


def test_template_summary_is_factual_and_counts_verified():
    s = template_summary(PROFILE)
    assert "Jordan Rivera" in s
    assert "Electrical" in s
    # Only the institution-verified one counts as "verified"
    assert "1 verified credential" in s
    assert "open to relocation" in s.lower()


def test_template_summary_handles_sparse_profile():
    s = template_summary({"name": "Pat"})
    assert "Pat" in s and isinstance(s, str) and len(s) > 0


def test_resume_pdf_is_valid_bytes():
    pdf = build_resume_pdf(PROFILE, summary="A skilled electrical trainee.")
    assert isinstance(pdf, (bytes, bytearray))
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 800           # non-trivial document


def test_resume_pdf_handles_minimal_profile():
    pdf = build_resume_pdf({"name": "Pat Doe", "credentials": []}, summary=None)
    assert pdf[:5] == b"%PDF-"


def test_resume_pdf_strips_non_latin1():
    # Should not raise on unicode in names/credentials.
    pdf = build_resume_pdf(
        {"name": "José Núñez", "credentials": [{"name": "Wéld — Cért", "badge": "SKILLED Verified"}]},
        summary="Café-level welding — détail oriented.",
    )
    assert pdf[:5] == b"%PDF-"
