"""
OCR / document-intelligence adapter (reference integration).

Verifies user-uploaded credential documents (diplomas, transcripts, union/trade
cards). Production target: AWS Textract `AnalyzeDocument` with QUERIES + SIGNATURES
(see docs/skilled-pro/02-credentials-verification.md §3). Google Document AI and
Azure Document Intelligence are drop-in alternatives behind the same Protocol.

The factory returns a NullOCRProvider unless an OCR provider is configured, so the
credential pipeline runs end-to-end in dev without any cloud account.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from app.integrations import IntegrationNotConfigured


@dataclass(frozen=True)
class OCRExtraction:
    """Normalized result of analyzing one credential document."""
    raw_text: str
    fields: dict[str, str] = field(default_factory=dict)   # e.g. {"degree": "...", "issuer": "..."}
    issuer_detected: str | None = None
    signature_detected: bool = False
    confidence: float = 0.0          # 0..1 overall extraction confidence
    authentic: bool = False          # passed forgery/tamper heuristics
    provider: str = "null"


@runtime_checkable
class OCRProvider(Protocol):
    def analyze(self, document_url: str, queries: list[str] | None = None) -> OCRExtraction:
        ...


class NullOCRProvider:
    """
    Safe default. Performs no OCR; returns an empty, non-authentic result so the
    credential stays SELF_REPORTED. Lets the platform run without a cloud account.
    """
    def analyze(self, document_url: str, queries: list[str] | None = None) -> OCRExtraction:
        return OCRExtraction(raw_text="", confidence=0.0, authentic=False, provider="null")


class TextractOCRProvider:
    """
    AWS Textract implementation (activate when AWS credentials + opt-out SCP are set).
    Intentionally not wired to boto3 yet — raises a clear error if used unconfigured.
    Implementation plan is in the dossier; uses async AnalyzeDocument + S3 for PDFs.
    """
    def __init__(self) -> None:
        # Real impl: build a boto3 'textract' client from configured AWS creds.
        raise IntegrationNotConfigured(
            "Textract OCR is not configured. Set AWS credentials + the Organizations "
            "AI opt-out SCP, then implement analyze() per docs/skilled-pro/02 §3."
        )

    def analyze(self, document_url: str, queries: list[str] | None = None) -> OCRExtraction:  # pragma: no cover
        raise IntegrationNotConfigured("Textract OCR not implemented")


_ISSUER_RE = re.compile(
    r"([A-Z][A-Za-z.&'\- ]*?(?:University|College|Institute|Institution|Academy|"
    r"Technical(?: College| Institute)?|Community College|Department|Board|Council|"
    r"Administration|Agency|Union|Local \d+|EPA|OSHA|ASE|NCCER|AWS|HVAC Excellence))",
)
_CRED_KEYWORDS = (
    "certificate", "certification", "certified", "certifies", "license", "licensed",
    "diploma", "degree", "journeyman", "apprentice", "credential", "completion",
    "completed", "awarded", "earned", "hereby", "qualified",
)
_SIGNATURE_RE = re.compile(r"signature|signed by|authorized by|registrar|dean|director", re.I)
_DATE_RE = re.compile(r"\b(19|20)\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b")


class HeuristicOCRProvider:
    """
    Working, cloud-free OCR provider. Treats the supplied content as the document's
    text layer (the realistic dev path: pasted text, a text/PDF text layer, or an
    upstream OCR'd string) and extracts issuer / credential / dates / signature via
    deterministic patterns. Textract is the production swap behind the same Protocol;
    this keeps the verification pipeline fully runnable + testable without AWS.
    """

    provider_name = "heuristic"

    def analyze(self, document_url: str, queries: list[str] | None = None) -> OCRExtraction:
        return self._extract(document_url)

    def analyze_text(self, text: str) -> OCRExtraction:
        return self._extract(text or "")

    def _extract(self, content: str) -> OCRExtraction:
        text = content or ""
        fields: dict[str, str] = {}

        issuer = None
        m = _ISSUER_RE.search(text)
        if m:
            issuer = m.group(1).strip()
            fields["issuer"] = issuer

        for line in text.splitlines():
            low = line.lower()
            if any(k in low for k in _CRED_KEYWORDS):
                fields.setdefault("credential", line.strip())
                break

        dm = _DATE_RE.search(text)
        if dm:
            fields["date"] = dm.group(0)

        signature = bool(_SIGNATURE_RE.search(text))
        has_cred = "credential" in fields
        # Confidence grows with the number of corroborating signals found.
        signals = sum([bool(issuer), has_cred, bool(dm), signature])
        confidence = round(min(1.0, 0.25 * signals + (0.1 if len(text) > 120 else 0)), 3)
        # "Authentic" here = enough structure to be a real document (issuer + a
        # credential line + length). Production Textract adds forgery/signature checks.
        authentic = bool(issuer) and has_cred and len(text.strip()) >= 60

        return OCRExtraction(
            raw_text=text, fields=fields, issuer_detected=issuer,
            signature_detected=signature, confidence=confidence,
            authentic=authentic, provider=self.provider_name,
        )


def get_ocr_provider() -> OCRProvider:
    """
    Select the OCR provider. Default is the working heuristic provider so the
    verification pipeline runs end-to-end without a cloud account; set
    OCR_PROVIDER=textract (with AWS creds) for production, or =null to disable.
    """
    from app.config import get_settings
    provider = (getattr(get_settings(), "ocr_provider", "") or "").lower()
    if provider == "textract":
        return TextractOCRProvider()
    if provider == "null":
        return NullOCRProvider()
    return HeuristicOCRProvider()
