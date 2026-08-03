"""
Credential taxonomy — canonical registry, deterministic normalizer, type-ahead
suggestions, and the admin canonical-fix endpoint.

Covers:
  Registry invariants — unique codes/slugs, valid categories, job families
    drawn from the canonical 44, aliases globally unambiguous.
  Normalizer — exact/alias hits, case/punctuation-insensitivity,
    longest-alias-wins specificity ("CDL A" ≠ "CDL"), word-boundary safety,
    honest no-match (flags for review, never silent-guess).
  Suggest — prefix beats containment, deterministic, empty for junk.
  API — suggest round-trips canonical fields; admin fix writes audit_logs and
    resolves pending review items; unknown slug is rejected.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user, require_admin
from app.auth.schemas import CurrentUser
from app.main import app
from app.skilled_pro import taxonomy
from app.skilled_pro.taxonomy import CredentialType

# The 44 canonical job families (mirrors canonical_job_families.code — keep in
# sync with supabase/migrations/20260310000002_taxonomy.sql and successors).
CANONICAL_FAMILIES = {
    "administrative", "auto_body", "automotive", "aviation", "building_automation",
    "childcare_education", "civil_survey", "construction", "construction_mgmt",
    "cosmetology", "culinary", "data_center", "dental", "dietetics", "drafting",
    "electrical", "electronics", "energy_lineman", "field_service",
    "health_information", "healthcare_support", "heavy_equipment", "hvac",
    "industrial_maintenance", "it_support", "lab_sciences", "logistics",
    "manufacturing", "marine", "nursing", "pharmacy", "physical_therapy",
    "plumbing", "power_plant", "radiology", "rail_transit", "respiratory",
    "robotics", "security", "solar_energy", "surgical_tech", "veterinary",
    "welding", "wind_energy",
}


# ---------------------------------------------------------------------------
# Registry invariants
# ---------------------------------------------------------------------------

def test_registry_size_and_coverage():
    assert len(taxonomy.TAXONOMY) >= 100, "registry should cover the major U.S. trade credentials"
    covered = set()
    for c in taxonomy.TAXONOMY:
        covered.update(c.job_families)
    assert covered == CANONICAL_FAMILIES & covered
    assert len(covered) == 44, f"expected all 44 families covered, got {len(covered)}"


def test_registry_codes_and_slugs_unique():
    codes = [c.code for c in taxonomy.TAXONOMY]
    slugs = [c.slug for c in taxonomy.TAXONOMY]
    assert len(codes) == len(set(codes))
    assert len(slugs) == len(set(slugs))


def test_registry_families_are_canonical():
    for c in taxonomy.TAXONOMY:
        bad = set(c.job_families) - CANONICAL_FAMILIES
        assert not bad, f"{c.code} references unknown job families: {bad}"


def test_registry_types_valid():
    for c in taxonomy.TAXONOMY:
        assert isinstance(c.type, CredentialType)


def test_legacy_db_slugs_still_present():
    """Slugs seeded by the original credential_definitions migration must stay
    resolvable — credentials rows may reference them via canonical_code."""
    legacy = [
        "osha_10", "osha_30", "nccer_core", "nccer_electrical", "nccer_welding",
        "nccer_hvac", "nccer_pipefitting", "nccer_industrial_maint", "aws_d1_1",
        "epa_608", "cdl_a", "cdl_b", "mssc_cpt", "dol_journeyworker",
        "associate_applied_science", "associate_science",
    ]
    for slug in legacy:
        assert taxonomy.get_by_slug(slug) is not None, slug


# ---------------------------------------------------------------------------
# Normalizer
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,code", [
    ("OSHA 10", "OSHA_10"),
    ("osha-10", "OSHA_10"),
    ("OSHA 10 Hour", "OSHA_10"),
    ("10-hour card", "OSHA_10"),
    ("EPA 608", "EPA_608"),
    ("e.p.a. 608", "EPA_608"),
    ("NATE certified", "NATE"),
    ("Journeyman Plumber", "PLUMB_JOURNEYMAN"),
    ("registered nurse", "RN"),
    ("LVN", "LPN_LVN"),
    ("CPhT", "PTCB_CPHT"),
    ("RBT", "RBT"),
    ("bls", "BLS"),
    ("ServSafe", "SERVSAFE_MGR"),
    ("guard card", "GUARD_CARD"),
    ("A&P mechanic", "FAA_AP"),
    ("Part 107", "FAA_107"),
    ("hazmat endorsement", "CDL_HAZMAT"),
    ("GED", "GED"),
    ("bachelor of science", "BACHELOR"),
])
def test_normalize_exact_and_alias_hits(raw, code):
    res = taxonomy.normalize(raw)
    assert res.canonical is not None, f"{raw!r} did not match"
    assert res.canonical.code == code
    assert res.is_confident


def test_normalize_case_and_punctuation_insensitive():
    for variant in ("OSHA 10", "osha 10", "OSHA-10", "Osha  10!", "OSHA_10"):
        res = taxonomy.normalize(variant)
        assert res.canonical is not None and res.canonical.code == "OSHA_10", variant


def test_longest_alias_wins_specificity():
    """The CDL family is the canonical first-match-wins trap: bare 'CDL' must
    NOT swallow class-specific strings."""
    assert taxonomy.normalize("CDL").canonical.code == "CDL_UNSPEC"
    assert taxonomy.normalize("CDL A").canonical.code == "CDL_A"
    assert taxonomy.normalize("CDL Class B").canonical.code == "CDL_B"
    # Containment stage: longer alias beats the shorter one inside noise.
    res = taxonomy.normalize("current class a cdl holder")
    assert res.canonical.code == "CDL_A"
    assert res.method == "token"
    # Same for OSHA inside a noisy string.
    res = taxonomy.normalize("active OSHA 30 safety card (2025)")
    assert res.canonical.code == "OSHA_30"


def test_word_boundary_safety():
    """Aliases only fire at word boundaries: 'ase' must not match inside
    'phase', 'rn' not inside 'journeyman'."""
    assert taxonomy.normalize("phase one complete").canonical is None
    assert taxonomy.normalize("perndale academy").canonical is None
    res = taxonomy.normalize("ASE")
    assert res.canonical is not None and res.canonical.code == "ASE"


def test_ambiguous_bare_tokens_go_to_review():
    """'CDA' is genuinely ambiguous (dental assistant vs child development
    associate) — the taxonomy must not silent-guess."""
    res = taxonomy.normalize("CDA")
    assert not res.is_confident
    # The specific forms resolve.
    assert taxonomy.normalize("CDA credential").canonical.code == "CDA_CREDENTIAL"
    assert taxonomy.normalize("certified dental assistant").canonical.code == "DANB_CDA"


def test_no_match_flags_for_review():
    res = taxonomy.normalize("underwater basket weaving level 7")
    assert res.canonical is None
    assert res.confidence == 0.0
    assert res.method == "none"
    assert not res.is_confident


def test_fuzzy_typo_still_matches_below_full_confidence():
    res = taxonomy.normalize("jorneyman electrician")
    assert res.canonical is not None
    assert res.canonical.code == "ELEC_JOURNEYMAN"
    assert res.method == "fuzzy"
    assert res.confidence < 1.0


def test_slug_roundtrip():
    for c in taxonomy.TAXONOMY:
        assert taxonomy.get_by_slug(c.slug) is c
        assert taxonomy.get_by_slug(c.slug.upper()) is c
        assert taxonomy.get_by_code(c.code) is c


# ---------------------------------------------------------------------------
# Suggest (type-ahead)
# ---------------------------------------------------------------------------

def test_suggest_prefix_first_and_deterministic():
    top = taxonomy.suggest("osha 1")
    assert top and top[0].code == "OSHA_10"
    assert [c.code for c in taxonomy.suggest("osha 1")] == [c.code for c in top]


def test_suggest_contains_and_limit():
    out = taxonomy.suggest("cdl", limit=10)
    codes = {c.code for c in out}
    assert "CDL_UNSPEC" in codes and "CDL_A" in codes
    assert len(out) <= 10


def test_suggest_junk_and_short_queries():
    assert taxonomy.suggest("zzzzqqqq") == []
    assert taxonomy.suggest("a") == []
    assert taxonomy.suggest("") == []


# ---------------------------------------------------------------------------
# API — suggest endpoint + admin canonical fix
# ---------------------------------------------------------------------------

def _applicant_user() -> CurrentUser:
    return CurrentUser(
        user_id=str(uuid.uuid4()), email="worker@test.com",
        role="applicant", onboarding_complete=True,
    )


def _admin_user() -> CurrentUser:
    return CurrentUser(
        user_id=str(uuid.uuid4()), email="admin@test.com",
        role="admin", onboarding_complete=True,
    )


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def _mock_db(conn: AsyncMock):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("app.routers.credential_taxonomy.get_db", return_value=ctx)


def test_suggest_endpoint_roundtrips_canonical_fields(client: TestClient):
    app.dependency_overrides[get_current_user] = _applicant_user
    resp = client.get("/credentials/taxonomy/suggest", params={"q": "osha 10"})
    assert resp.status_code == 200
    body = resp.json()
    assert body, "expected suggestions for 'osha 10'"
    top = body[0]
    assert top["slug"] == "osha_10"
    assert top["name"] == "OSHA 10-Hour Safety Card"
    assert top["category"] == "safety"
    assert top["validity_note"]


def test_suggest_endpoint_requires_auth(client: TestClient):
    resp = client.get("/credentials/taxonomy/suggest", params={"q": "osha"})
    assert resp.status_code in (401, 403)


def test_admin_fix_writes_audit_and_resolves_review(client: TestClient):
    admin = _admin_user()
    app.dependency_overrides[require_admin] = lambda: admin
    cred_id = str(uuid.uuid4())
    applicant_id = str(uuid.uuid4())

    cred_row = {
        "id": cred_id, "applicant_id": applicant_id,
        "raw_name": "my osha thing", "canonical_code": None,
    }
    def_row = {"id": str(uuid.uuid4())}
    final_row = {
        "id": cred_id, "applicant_id": applicant_id, "applicant_name": "Jane Doe",
        "raw_name": "my osha thing", "canonical_code": "osha_10",
        "canonical_name": "OSHA 10-Hour Safety Card", "credential_type": "safety",
        "issuer": "OSHA-authorized trainer", "normalization_confidence": 1.0,
        "needs_review": False, "source": "self", "verification_level": 0,
    }

    conn = AsyncMock()
    conn.fetchrow = AsyncMock(side_effect=[cred_row, def_row, final_row])
    conn.execute = AsyncMock()
    # asyncpg's conn.transaction() is synchronous and returns a Transaction.
    conn.transaction = MagicMock(return_value=AsyncMock())

    with _mock_db(conn), patch(
        "app.routers.credential_taxonomy.append_credential_record", new=AsyncMock()
    ) as record_mock:
        resp = client.patch(
            f"/admin/credentials/{cred_id}/canonical",
            json={"slug": "osha_10", "note": "confirmed from document"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["canonical_code"] == "osha_10"
    assert body["raw_name"] == "my osha thing"  # raw text untouched

    executed_sql = " ".join(str(c.args[0]) for c in conn.execute.call_args_list)
    assert "INSERT INTO public.audit_logs" in executed_sql
    assert "credential.canonical_fix" in executed_sql
    assert "review_queue_items" in executed_sql and "overridden" in executed_sql
    # Signed credential_records entry appended.
    record_mock.assert_awaited_once()
    assert record_mock.await_args.args[3] == "canonical_fixed"


def test_admin_fix_rejects_unknown_slug(client: TestClient):
    app.dependency_overrides[require_admin] = _admin_user
    resp = client.patch(
        f"/admin/credentials/{uuid.uuid4()}/canonical",
        json={"slug": "not_a_real_slug"},
    )
    assert resp.status_code == 422


def test_admin_fix_requires_admin(client: TestClient):
    app.dependency_overrides[get_current_user] = _applicant_user
    resp = client.patch(
        f"/admin/credentials/{uuid.uuid4()}/canonical", json={"slug": "osha_10"},
    )
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Queue invariant — the normalization "Needs review" flag
# ---------------------------------------------------------------------------

def test_exact_and_alias_matches_are_confident_and_never_flagged():
    """The admin credentials queue (WHERE needs_review) must only ever contain
    genuinely uncertain normalizations. Exact canonical-name and known-alias
    matches score 1.0 — above the is_confident threshold — so every writer
    (`needs_review = not norm.is_confident`) keeps them out of the queue.
    Regression for exact-match rows ("OSHA 30-Hour Safety Card · 100%
    confidence") appearing under Needs review."""
    for raw in ("OSHA 30-Hour Safety Card", "osha 30", "EPA Section 608 Technician Certification",
                "Fall Protection Training", "CDL Class A"):
        r = taxonomy.normalize(raw)
        assert r.method == "alias", (raw, r.method)
        assert r.confidence == 1.0
        assert r.is_confident, f"{raw!r} must never be flagged for normalization review"


def test_uncertain_matches_stay_flagged():
    """Partial/fuzzy/no-match results stay below the confidence bar and keep
    feeding the queue — the flag is honest, not silenced."""
    assert not taxonomy.normalize("quantum basket weaving level 9").is_confident
    assert taxonomy.normalize("quantum basket weaving level 9").method == "none"
