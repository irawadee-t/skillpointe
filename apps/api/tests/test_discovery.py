"""
Unit tests for the employer verified-worker discovery invariants (pure logic).
The same consent predicate guards both the directory search and SKILLED Verify.
"""
from app.skilled_pro.discovery import (
    GATED_CATEGORY,
    MIN_VERIFIED_LEVEL,
    employer_may_access,
)
from app.skilled_pro.verification import VerificationLevel


def test_employer_access_requires_explicit_employer_consent():
    assert employer_may_access(["employer"]) is True
    assert employer_may_access(["employer", "job_board"]) is True


def test_employer_access_denied_without_employer():
    assert employer_may_access(["job_board"]) is False
    assert employer_may_access(["staffing_agency", "union"]) is False


def test_employer_access_denied_when_empty_or_none():
    assert employer_may_access([]) is False
    assert employer_may_access(None) is False


def test_employer_access_ignores_unknown_categories():
    # Garbage values are dropped; only a real 'employer' grant counts.
    assert employer_may_access(["garbage", "EMPLOYER_typo"]) is False
    assert employer_may_access(["garbage", "employer"]) is True


def test_min_verified_level_is_institution():
    # Employers must never see self-reported (level 0) as "verified".
    assert MIN_VERIFIED_LEVEL == VerificationLevel.INSTITUTION_VERIFIED.value == 1
    assert GATED_CATEGORY == "certifications"
