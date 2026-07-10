"""Unit tests for the heuristic OCR provider + document-verification assessment."""
from app.integrations.ocr import HeuristicOCRProvider, get_ocr_provider
from app.skilled_pro import doc_verify

GOOD_DOC = """
    Coastal Technical College
    This certifies that the holder has completed the
    EPA Section 608 Technician Certification
    Issued 2024 — Authorized by the Registrar
"""

WEAK_DOC = "some random note about welding"


def test_heuristic_provider_extracts_fields():
    ex = HeuristicOCRProvider().analyze_text(GOOD_DOC)
    assert ex.provider == "heuristic"
    assert ex.issuer_detected and "College" in ex.issuer_detected
    assert "credential" in ex.fields
    assert ex.signature_detected is True       # "Registrar"
    assert ex.authentic is True
    assert ex.confidence > 0


def test_default_provider_is_heuristic():
    assert isinstance(get_ocr_provider(), HeuristicOCRProvider)


def test_assess_verifies_matching_authentic_doc():
    ex = HeuristicOCRProvider().analyze_text(GOOD_DOC)
    a = doc_verify.assess(ex, "EPA Section 608 Technician Certification", "Coastal Technical College")
    assert a.decision == "verified"
    assert a.name_matched and a.issuer_matched and a.document_authentic
    assert a.score >= 0.7


def test_assess_rejects_unstructured_doc():
    ex = HeuristicOCRProvider().analyze_text(WEAK_DOC)
    a = doc_verify.assess(ex, "EPA Section 608 Technician Certification", "Coastal Technical College")
    assert a.decision in ("rejected", "review")
    assert a.document_authentic is False


def test_assess_name_mismatch_does_not_verify():
    ex = HeuristicOCRProvider().analyze_text(GOOD_DOC)
    a = doc_verify.assess(ex, "Commercial Driver License Class A", "Coastal Technical College")
    assert a.decision != "verified"
    assert a.name_matched is False
