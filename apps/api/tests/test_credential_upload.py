"""
Tests for the credential document-upload lane (file upload + QR phone handoff).

Follows the established router-test pattern (see test_doc_verify.py /
test_employer_visibility.py): DB mocked via get_db patching, auth bypassed via
FastAPI dependency overrides. Covers:

  - upload validation: oversized file → 413, wrong type → 415
  - phone-link: token minted, sha256 hash (not the raw token) stored, 15-min TTL
  - public phone upload: invalid / expired / used token → 404 (no oracle)
  - single-use claim: raced duplicate claim → 404
  - unreadable image under heuristic OCR → routed to review queue, never a dead end
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user, require_applicant
from app.auth.schemas import CurrentUser
from app.main import app
from app.routers.credential_uploads import (
    MAX_UPLOAD_BYTES,
    hash_token,
    validate_upload,
)

APPLICANT_USER_ID = "aaaaaaaa-1111-2222-3333-444444444444"
APPLICANT_ID = "bbbbbbbb-1111-2222-3333-444444444444"
CREDENTIAL_ID = "cccccccc-1111-2222-3333-444444444444"
TOKEN_ID = "dddddddd-1111-2222-3333-444444444444"


def _applicant_user() -> CurrentUser:
    return CurrentUser(
        user_id=APPLICANT_USER_ID,
        email="applicant@test.com",
        role="applicant",
        onboarding_complete=True,
    )


def _cred_row(**overrides) -> dict:
    base = {
        "id": CREDENTIAL_ID,
        "applicant_id": APPLICANT_ID,
        "a_id": APPLICANT_ID,
        "a_user_id": APPLICANT_USER_ID,
        "raw_name": "EPA Section 608",
        "canonical_code": "epa_608",
        "canonical_name": "EPA Section 608 Technician Certification",
        "issuer": "Coastal Technical College",
        "verification_level": 0,
        "needs_review": False,
        "document_url": None,
    }
    base.update(overrides)
    return base


def _mock_db(fetchrow_side_effect=None, fetchrow_return=None):
    """Patch get_db in the router module with canned responses."""
    conn = AsyncMock()
    if fetchrow_side_effect is not None:
        conn.fetchrow = AsyncMock(side_effect=fetchrow_side_effect)
    else:
        conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock(return_value="UPDATE 1")

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("app.routers.credential_uploads.get_db", return_value=ctx), conn


async def _noop() -> None:
    return None


@pytest.fixture(autouse=True)
def _overrides():
    """Bypass auth + rate limiting; storage upload is stubbed to a path."""
    app.dependency_overrides[require_applicant] = _applicant_user
    # The sensitive rate limiter itself depends on get_current_user — override
    # that too so "Bearer x" isn't JWT-validated inside the limiter dependency.
    app.dependency_overrides[get_current_user] = _applicant_user
    # Patch the limiter instance to always allow (Redis-free tests).
    with patch("app.util.rate_limit._limiter_instance") as inst:
        decision = MagicMock(allowed=True, remaining=8, limit=8, reset_seconds=0)
        inst.return_value.check.return_value = decision
        with patch(
            "app.routers.credential_uploads.store_document",
            new=AsyncMock(return_value="documents/credentials/x/y/z.jpg"),
        ):
            yield
    app.dependency_overrides.clear()


client = TestClient(app)


# ---------------------------------------------------------------------------
# Pure helpers: token hashing + upload validation
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_hash_token_is_sha256_hex(self):
        assert hash_token("abc") == hashlib.sha256(b"abc").hexdigest()

    def test_validate_upload_accepts_images_and_pdf(self):
        for mime, ext in [("image/jpeg", "jpg"), ("image/png", "png"),
                          ("image/webp", "webp"), ("image/heic", "heic"),
                          ("application/pdf", "pdf")]:
            got_mime, got_ext = validate_upload("f", mime, 100)
            assert (got_mime, got_ext) == (mime, ext)

    def test_validate_upload_falls_back_to_extension(self):
        mime, ext = validate_upload("scan.PDF", "application/octet-stream", 100)
        assert (mime, ext) == ("application/pdf", "pdf")

    def test_validate_upload_rejects_unknown_type(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as e:
            validate_upload("evil.exe", "application/x-msdownload", 100)
        assert e.value.status_code == 415

    def test_validate_upload_rejects_oversize(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as e:
            validate_upload("big.jpg", "image/jpeg", MAX_UPLOAD_BYTES + 1)
        assert e.value.status_code == 413


# ---------------------------------------------------------------------------
# Direct upload endpoint
# ---------------------------------------------------------------------------

class TestDirectUpload:
    def test_rejects_wrong_type_with_415(self):
        db, _ = _mock_db(fetchrow_return=_cred_row())
        with db:
            r = client.post(
                f"/applicant/me/credentials/{CREDENTIAL_ID}/verify/upload",
                files={"file": ("notes.txt2", b"hello", "application/zip")},
                headers={"Authorization": "Bearer x"},
            )
        assert r.status_code == 415

    def test_rejects_oversize_with_413(self):
        db, _ = _mock_db(fetchrow_return=_cred_row())
        with db:
            r = client.post(
                f"/applicant/me/credentials/{CREDENTIAL_ID}/verify/upload",
                files={"file": ("big.jpg", b"x" * (MAX_UPLOAD_BYTES + 1), "image/jpeg")},
                headers={"Authorization": "Bearer x"},
            )
        assert r.status_code == 413

    def test_unreadable_image_routes_to_review(self):
        """Under the heuristic (text-only) provider, an image yields no text and
        must land in the review queue — status needs_review, never an error."""
        # fetchrow calls: credential lookup, pending-review-queue check, chain prev-hash
        db, conn = _mock_db(fetchrow_side_effect=[_cred_row(), None, None])
        with db:
            r = client.post(
                f"/applicant/me/credentials/{CREDENTIAL_ID}/verify/upload",
                files={"file": ("card.jpg", b"\xff\xd8\xff\xe0fakejpegbytes", "image/jpeg")},
                headers={"Authorization": "Bearer x"},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "needs_review"
        assert body["decision"] == "unreadable"
        assert body["new_verification_level"] == 0
        # Review queue insert + audit log both happened.
        executed_sql = " ".join(str(c.args[0]) for c in conn.execute.call_args_list)
        assert "review_queue_items" in executed_sql
        assert "audit_logs" in executed_sql

    def test_unreadable_image_does_not_flip_normalization_flag(self):
        """Regression: credentials.needs_review is the taxonomy-normalization
        flag (feeds the admin credentials queue + sidebar badge). A document
        that merely needs a human look must go to review_queue_items
        ('credential_ambiguity' → /admin/review) WITHOUT flagging a
        perfectly-normalized credential for normalization review."""
        db, conn = _mock_db(fetchrow_side_effect=[_cred_row(), None, None])
        with db:
            r = client.post(
                f"/applicant/me/credentials/{CREDENTIAL_ID}/verify/upload",
                files={"file": ("card.jpg", b"\xff\xd8\xff\xe0fakejpegbytes", "image/jpeg")},
                headers={"Authorization": "Bearer x"},
            )
        assert r.status_code == 200
        assert r.json()["status"] == "needs_review"
        # No UPDATE anywhere in this flow may set needs_review = true.
        for call in conn.execute.call_args_list:
            sql = str(call.args[0])
            assert "needs_review = true" not in sql, sql
        # …but the verification-lane review item was enqueued.
        executed_sql = " ".join(str(c.args[0]) for c in conn.execute.call_args_list)
        assert "credential_ambiguity" in executed_sql

    def test_unknown_credential_404(self):
        db, _ = _mock_db(fetchrow_return=None)
        with db:
            r = client.post(
                f"/applicant/me/credentials/{CREDENTIAL_ID}/verify/upload",
                files={"file": ("card.jpg", b"bytes", "image/jpeg")},
                headers={"Authorization": "Bearer x"},
            )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Signed document URL (portfolio view)
# ---------------------------------------------------------------------------

class TestDocumentUrl:
    URL = f"/applicant/me/credentials/{CREDENTIAL_ID}/document-url"

    def test_returns_signed_url_and_content_type(self):
        db, _ = _mock_db(fetchrow_return=_cred_row(
            document_url="documents/credentials/a/b/c.jpg",
        ))
        with db, patch(
            "app.routers.credential_uploads.create_signed_url",
            new=AsyncMock(return_value="http://localhost:54321/storage/v1/object/sign/documents/x?token=t"),
        ) as signer:
            r = client.get(self.URL, headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
        body = r.json()
        assert body["url"].startswith("http://localhost:54321/storage/v1/object/sign/")
        assert body["content_type"] == "image/jpeg"
        assert body["expires_in"] == 600
        # The bucket prefix is stripped before signing.
        assert signer.await_args.args[0] == "credentials/a/b/c.jpg"

    def test_credential_owned_by_another_applicant_404(self):
        """The ownership join returns nothing for someone else's credential."""
        db, _ = _mock_db(fetchrow_return=None)
        with db, patch(
            "app.routers.credential_uploads.create_signed_url", new=AsyncMock(),
        ) as signer:
            r = client.get(self.URL, headers={"Authorization": "Bearer x"})
        assert r.status_code == 404
        signer.assert_not_awaited()

    def test_credential_without_document_404(self):
        db, _ = _mock_db(fetchrow_return=_cred_row(document_url=None))
        with db, patch(
            "app.routers.credential_uploads.create_signed_url", new=AsyncMock(),
        ) as signer:
            r = client.get(self.URL, headers={"Authorization": "Bearer x"})
        assert r.status_code == 404
        signer.assert_not_awaited()

    def test_storage_failure_is_404_not_500(self):
        db, _ = _mock_db(fetchrow_return=_cred_row(
            document_url="documents/credentials/a/b/c.pdf",
        ))
        with db, patch(
            "app.routers.credential_uploads.create_signed_url",
            new=AsyncMock(return_value=None),
        ):
            r = client.get(self.URL, headers={"Authorization": "Bearer x"})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Phone link creation
# ---------------------------------------------------------------------------

class TestPhoneLink:
    def test_creates_single_use_token_and_stores_hash(self):
        expires = datetime.now(timezone.utc) + timedelta(minutes=15)
        db, conn = _mock_db(fetchrow_side_effect=[_cred_row(), {"expires_at": expires}])
        with db:
            r = client.post(
                f"/applicant/me/credentials/{CREDENTIAL_ID}/verify/phone-link",
                headers={"Authorization": "Bearer x"},
            )
        assert r.status_code == 200
        body = r.json()
        assert "/verify-doc/" in body["url"]
        assert body["expires_at"] == expires.isoformat()

        raw_token = body["url"].rsplit("/verify-doc/", 1)[1]
        insert_call = conn.fetchrow.call_args_list[1]
        stored_hash = insert_call.args[3]
        # The DB stores the sha256 of the token, never the token itself.
        assert stored_hash == hashlib.sha256(raw_token.encode()).hexdigest()
        assert raw_token not in str(insert_call)

    def test_404_when_credential_not_owned(self):
        db, _ = _mock_db(fetchrow_return=None)
        with db:
            r = client.post(
                f"/applicant/me/credentials/{CREDENTIAL_ID}/verify/phone-link",
                headers={"Authorization": "Bearer x"},
            )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Public phone upload — token validation
# ---------------------------------------------------------------------------

def _token_row(token: str, *, used: bool = False, expired: bool = False) -> dict:
    return {
        "id": TOKEN_ID,
        "token_hash": hash_token(token),
        "credential_id": CREDENTIAL_ID,
        "applicant_id": APPLICANT_ID,
        "used_at": datetime.now(timezone.utc) if used else None,
        "expires_at": datetime.now(timezone.utc)
        + (timedelta(minutes=-1) if expired else timedelta(minutes=10)),
    }


class TestPhoneUpload:
    FILES = {"file": ("photo.jpg", b"\xff\xd8\xff\xe0fakejpegbytes", "image/jpeg")}

    def test_invalid_token_404(self):
        db, _ = _mock_db(fetchrow_return=None)
        with db:
            r = client.post("/credential-uploads/badtoken", files=self.FILES)
        assert r.status_code == 404

    def test_expired_token_404(self):
        token = "tok-expired"
        db, _ = _mock_db(fetchrow_side_effect=[_token_row(token, expired=True)])
        with db:
            r = client.post(f"/credential-uploads/{token}", files=self.FILES)
        assert r.status_code == 404

    def test_used_token_404(self):
        token = "tok-used"
        db, _ = _mock_db(fetchrow_side_effect=[_token_row(token, used=True)])
        with db:
            r = client.post(f"/credential-uploads/{token}", files=self.FILES)
        assert r.status_code == 404

    def test_raced_claim_404(self):
        """Token valid at read time but claimed by a concurrent request →
        the atomic UPDATE ... WHERE used_at IS NULL returns nothing → 404."""
        token = "tok-raced"
        db, _ = _mock_db(fetchrow_side_effect=[_token_row(token), None])
        with db:
            r = client.post(f"/credential-uploads/{token}", files=self.FILES)
        assert r.status_code == 404

    def test_valid_token_lands_in_review_and_marks_used(self):
        token = "tok-good"
        db, conn = _mock_db(fetchrow_side_effect=[
            _token_row(token),                 # token lookup
            {"id": TOKEN_ID},                  # atomic claim
            _cred_row(),                       # credential
            {"user_id": APPLICANT_USER_ID},    # actor lookup
            None,                              # pending review-queue check
            None,                              # chain prev-hash
        ])
        with db:
            r = client.post(f"/credential-uploads/{token}", files=self.FILES)
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["status"] == "needs_review"
        # The single-use claim ran.
        claim_sql = str(conn.fetchrow.call_args_list[1].args[0])
        assert "used_at" in claim_sql and "used_at IS NULL" in claim_sql

    def test_bad_type_rejected_before_token_lookup(self):
        db, conn = _mock_db(fetchrow_return=None)
        with db:
            r = client.post(
                "/credential-uploads/whatever",
                files={"file": ("x.exe", b"MZ", "application/x-msdownload")},
            )
        assert r.status_code == 415
        conn.fetchrow.assert_not_called()
