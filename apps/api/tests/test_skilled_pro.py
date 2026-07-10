"""
Unit tests for the SKILLED Pro core (taxonomy, signing, verification, consent,
API keys, rate limiting). All pure logic — no DB, no network, no Redis — so the
trust- and consent-governing code is provably correct in CI.
"""
from __future__ import annotations

import pytest

from app.skilled_pro import taxonomy
from app.skilled_pro.taxonomy import CredentialType
from app.skilled_pro import signing
from app.skilled_pro.signing import sign_record, verify_record, verify_chain, GENESIS_HASH
from app.skilled_pro.verification import (
    VerificationLevel,
    CredentialSource,
    VerificationEvidence,
    derive_level,
)
from app.skilled_pro.consent import (
    ConsentState,
    ConsentScope,
    RequesterCategory,
    can_share_externally,
    filter_categories_for_requester,
    parse_external_sharing,
)
from app.skilled_pro import apikeys
from app.skilled_pro.ratelimit import RateLimiter, InMemoryBackend, TIERS, RateTier


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,code", [
    ("OSHA 10", "OSHA_10"),
    ("osha-30 card", "OSHA_30"),
    ("EPA Section 608", "EPA_608"),
    ("epa 608 universal", "EPA_608"),
    ("Journeyman Electrician", "ELEC_JOURNEYMAN"),
    ("Master Electrician License", "ELEC_MASTER"),
    ("AWS Certified Welder", "AWS_CW"),
    ("ASE Certified", "ASE"),
    ("CDL-A", "CDL_A"),
    ("Class A CDL", "CDL_A"),
    ("NCCER Core", "NCCER"),
    ("forklift certification", "FORKLIFT_PIT"),
    ("Associate of Applied Science", "ASSOCIATE"),
])
def test_normalize_known_credentials(raw, code):
    res = taxonomy.normalize(raw)
    assert res.canonical is not None, f"{raw!r} did not match"
    assert res.canonical.code == code
    assert res.is_confident


def test_normalize_substring_with_noise():
    res = taxonomy.normalize("active OSHA 30 safety card (2025)")
    assert res.canonical is not None
    assert res.canonical.code == "OSHA_30"
    assert res.method in ("token", "alias")


def test_normalize_fuzzy_typo():
    res = taxonomy.normalize("jorneyman electrician")  # typo
    assert res.canonical is not None
    assert res.canonical.code == "ELEC_JOURNEYMAN"


def test_normalize_unknown_returns_none():
    res = taxonomy.normalize("underwater basket weaving level 7")
    assert res.canonical is None
    assert res.confidence == 0.0
    assert not res.is_confident


def test_normalize_empty():
    assert taxonomy.normalize("").canonical is None
    assert taxonomy.normalize("   ").canonical is None


def test_taxonomy_codes_unique_and_typed():
    codes = [c.code for c in taxonomy.TAXONOMY]
    assert len(codes) == len(set(codes))
    for c in taxonomy.TAXONOMY:
        assert isinstance(c.type, CredentialType)


# ---------------------------------------------------------------------------
# Signing + tamper-evident chain
# ---------------------------------------------------------------------------

def test_sign_and_verify_roundtrip():
    priv, pub = signing.generate_keypair()
    record = {"applicant_id": "abc", "code": "EPA_608", "issued": "2025-01-01"}
    signed = sign_record(record, priv)
    assert verify_record(record, signed, pub)


def test_canonicalization_is_order_independent():
    a = {"x": 1, "y": 2}
    b = {"y": 2, "x": 1}
    assert signing.content_hash(a) == signing.content_hash(b)


def test_tamper_breaks_verification():
    priv, pub = signing.generate_keypair()
    record = {"code": "AWS_CW", "level": 1}
    signed = sign_record(record, priv)
    tampered = {"code": "AWS_CW", "level": 2}  # attacker upgrades the level
    assert not verify_record(tampered, signed, pub)


def test_wrong_key_fails():
    priv, _ = signing.generate_keypair()
    _, other_pub = signing.generate_keypair()
    record = {"code": "ASE"}
    signed = sign_record(record, priv)
    assert not verify_record(record, signed, other_pub)


def test_hash_chain_links_and_detects_history_tampering():
    priv, pub = signing.generate_keypair()
    r1 = {"code": "OSHA_10", "n": 1}
    s1 = sign_record(r1, priv, prev_hash=GENESIS_HASH)
    r2 = {"code": "OSHA_30", "n": 2}
    s2 = sign_record(r2, priv, prev_hash=s1.chain_hash)
    assert verify_chain([(r1, s1), (r2, s2)], pub)
    # Re-point r2 to genesis (as if r1 were deleted) -> chain breaks.
    s2_orphan = sign_record(r2, priv, prev_hash=GENESIS_HASH)
    assert not verify_chain([(r1, s1), (r2, s2_orphan)], pub)


# ---------------------------------------------------------------------------
# Verification badges
# ---------------------------------------------------------------------------

def test_self_reported_default():
    ev = VerificationEvidence(source=CredentialSource.SELF)
    assert derive_level(ev) == VerificationLevel.SELF_REPORTED
    assert derive_level(ev).badge == "Self-Reported"


def test_sis_feed_is_institution_verified():
    ev = VerificationEvidence(source=CredentialSource.SIS)
    assert derive_level(ev) == VerificationLevel.INSTITUTION_VERIFIED


def test_authentic_document_with_issuer_is_institution_verified():
    ev = VerificationEvidence(
        source=CredentialSource.DOCUMENT_UPLOAD,
        issuer_matched=True,
        document_authentic=True,
    )
    assert derive_level(ev) == VerificationLevel.INSTITUTION_VERIFIED


def test_document_without_authenticity_stays_self_reported():
    ev = VerificationEvidence(
        source=CredentialSource.DOCUMENT_UPLOAD,
        issuer_matched=True,
        document_authentic=False,
    )
    assert derive_level(ev) == VerificationLevel.SELF_REPORTED


def test_skilled_verified_requires_identity_and_signature():
    ev = VerificationEvidence(
        source=CredentialSource.SIS,
        identity_verified=True,
        signature_valid=True,
    )
    assert derive_level(ev) == VerificationLevel.SKILLED_VERIFIED
    # Missing identity -> drops to institution.
    ev2 = VerificationEvidence(source=CredentialSource.SIS, signature_valid=True)
    assert derive_level(ev2) == VerificationLevel.INSTITUTION_VERIFIED


def test_self_reported_cannot_reach_skilled_verified_even_with_flags():
    # A client trying to assert identity+signature on a self-reported cred can't escalate.
    ev = VerificationEvidence(
        source=CredentialSource.SELF, identity_verified=True, signature_valid=True
    )
    assert derive_level(ev) == VerificationLevel.SELF_REPORTED


# ---------------------------------------------------------------------------
# Consent
# ---------------------------------------------------------------------------

def test_external_sharing_denied_by_default():
    st = ConsentState()
    assert not can_share_externally(st, RequesterCategory.EMPLOYER)
    assert not st.allows(ConsentScope.DISPLAY)
    assert st.allows(ConsentScope.INTERNAL_USE)  # opted in at signup by default


def test_external_sharing_is_per_requester_category():
    st = ConsentState(external_sharing=frozenset({RequesterCategory.EMPLOYER}))
    assert can_share_externally(st, RequesterCategory.EMPLOYER)
    assert not can_share_externally(st, RequesterCategory.JOB_BOARD)
    assert not can_share_externally(st, RequesterCategory.BACKGROUND_CHECK)


def test_filter_categories_for_requester():
    states = {
        "certifications": ConsentState(external_sharing=frozenset({RequesterCategory.EMPLOYER})),
        "employment_history": ConsentState(external_sharing=frozenset({RequesterCategory.JOB_BOARD})),
        "wage_expectations": ConsentState(),  # nothing
    }
    allowed = filter_categories_for_requester(states, RequesterCategory.EMPLOYER)
    assert allowed == ["certifications"]


def test_parse_external_sharing_tolerant():
    parsed = parse_external_sharing(["employer", "garbage", "job_board"])
    assert parsed == frozenset({RequesterCategory.EMPLOYER, RequesterCategory.JOB_BOARD})


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------

def test_api_key_generation_and_verify():
    gk = apikeys.generate_api_key(live=True)
    assert gk.raw.startswith("skid_live_")
    assert gk.prefix.startswith("skid_live_")
    assert apikeys.verify_key(gk.raw, gk.key_hash)
    assert not apikeys.verify_key(gk.raw + "x", gk.key_hash)


def test_api_key_hash_does_not_contain_raw():
    gk = apikeys.generate_api_key()
    assert gk.raw not in gk.key_hash
    assert len(gk.key_hash) == 64  # sha256 hex


def test_api_key_prefix_recovery():
    gk = apikeys.generate_api_key()
    assert apikeys.prefix_of(gk.raw) == gk.prefix


def test_api_key_pepper_changes_hash():
    raw = "skid_live_fixedbodyvalue"
    assert apikeys.hash_key(raw) != apikeys.hash_key(raw, pepper="secret")
    assert apikeys.verify_key(raw, apikeys.hash_key(raw, "secret"), pepper="secret")


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

def test_rate_limiter_allows_then_blocks():
    limiter = RateLimiter(InMemoryBackend())
    tier = RateTier("t", limit=3, window=60)
    results = [limiter.check("partner-1", tier, now=1000) for _ in range(4)]
    assert [r.allowed for r in results] == [True, True, True, False]
    assert results[0].remaining == 2
    assert results[3].remaining == 0
    assert results[3].limit == 3


def test_rate_limiter_window_resets():
    limiter = RateLimiter(InMemoryBackend())
    tier = RateTier("t", limit=1, window=60)
    assert limiter.check("p", tier, now=0).allowed
    assert not limiter.check("p", tier, now=30).allowed   # same window
    assert limiter.check("p", tier, now=61).allowed        # next window


def test_rate_limiter_isolates_identities():
    limiter = RateLimiter(InMemoryBackend())
    tier = RateTier("t", limit=1, window=60)
    assert limiter.check("a", tier, now=0).allowed
    assert limiter.check("b", tier, now=0).allowed  # different partner unaffected


def test_tiers_defined():
    for name in ("free", "standard", "premium", "bulk"):
        assert name in TIERS
        assert TIERS[name].limit > 0
