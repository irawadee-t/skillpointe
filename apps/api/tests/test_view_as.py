"""
Tests for admin "view as applicant" debug mode (X-View-As-Applicant header).

Guardrails under test:
- admin + header on a GET /applicant/me/* endpoint resolves the TARGET applicant
- non-admin sending the header gets 403 (even an applicant)
- any mutating method under view-as gets 403 "View-as is read-only"
- POST /admin/view-as/{id}/start writes exactly one audit_logs row
- normal applicant sessions are unchanged when the header is absent
"""
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

VIEW_AS_HEADER = "X-View-As-Applicant"

TARGET_APPLICANT_ID = "11111111-2222-3333-4444-555555555555"
TARGET_USER_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _set_role(mock_supabase_client: MagicMock, role: str) -> None:
    """Configure the user_profiles lookup inside get_current_user."""
    mock_supabase_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"role": role, "onboarding_complete": True}
    ]


def _db_ctx(conn: AsyncMock) -> MagicMock:
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


def _applicant_lookup_row() -> dict:
    return {
        "id": TARGET_APPLICANT_ID,
        "user_id": TARGET_USER_ID,
        "email": "jane.smith@example.com",
        "first_name": "Jane",
        "last_name": "Smith",
    }


def _profile_row_for(user_id: str) -> dict:
    """Minimal applicants row shape for GET /applicant/me/profile."""
    return {
        "id": TARGET_APPLICANT_ID,
        "first_name": "Jane",
        "last_name": "Smith",
        "program_name_raw": "Welding Technology",
        "city": "Austin",
        "state": "TX",
        "region": "Central",
        "willing_to_relocate": True,
        "willing_to_travel": False,
        "commute_radius_miles": None,
        "expected_completion_date": "2026-08-01",
        "available_from_date": "2026-08-15",
        "enrollment_status": None,
        "degree_type": None,
        "school_name": None,
        "school_city": None,
        "school_state": None,
        "career_path": None,
        "program_field": None,
        "specific_career": None,
        "program_start_date": None,
        "gpa": None,
        "travel_preference": None,
        "relocation_preference": None,
        "relocation_states": None,
        "age_range": None,
        "gender": None,
        "military_status": False,
        "military_dependent": False,
        "current_wages": None,
        "has_internship": False,
        "activities": None,
        "honor_societies": None,
        "canonical_job_family_code": "welding",
    }


# ---------------------------------------------------------------------------
# Admin + header → target applicant resolved on GET
# ---------------------------------------------------------------------------

def test_admin_with_header_resolves_target_applicant_on_get_profile(
    client: TestClient, admin_token: str, mock_supabase_client: MagicMock
):
    _set_role(mock_supabase_client, "admin")

    # Dependency-side lookup (applicants by id) inside require_applicant
    dep_conn = AsyncMock()
    dep_conn.fetchrow = AsyncMock(return_value=_applicant_lookup_row())

    # Router-side lookup (applicants by user_id) inside get_my_profile —
    # capture the user_id param to prove the TARGET's user_id was used.
    router_conn = AsyncMock()
    captured: dict = {}

    async def _fetchrow(query, *params):
        captured["params"] = params
        return _profile_row_for(params[0])

    router_conn.fetchrow = AsyncMock(side_effect=_fetchrow)

    with (
        patch("app.auth.dependencies.get_db", return_value=_db_ctx(dep_conn)),
        patch("app.routers.applicants.get_db", return_value=_db_ctx(router_conn)),
    ):
        resp = client.get(
            "/applicant/me/profile",
            headers={
                "Authorization": f"Bearer {admin_token}",
                VIEW_AS_HEADER: TARGET_APPLICANT_ID,
            },
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["applicant_id"] == TARGET_APPLICANT_ID
    assert body["first_name"] == "Jane"
    # The profile query must carry the TARGET applicant id as the view-as
    # resolution parameter (it wins over the user_id fallback via COALESCE).
    assert captured["params"][1] == TARGET_APPLICANT_ID


def test_admin_with_header_unknown_applicant_404(
    client: TestClient, admin_token: str, mock_supabase_client: MagicMock
):
    _set_role(mock_supabase_client, "admin")
    dep_conn = AsyncMock()
    dep_conn.fetchrow = AsyncMock(return_value=None)

    with patch("app.auth.dependencies.get_db", return_value=_db_ctx(dep_conn)):
        resp = client.get(
            "/applicant/me/profile",
            headers={
                "Authorization": f"Bearer {admin_token}",
                VIEW_AS_HEADER: TARGET_APPLICANT_ID,
            },
        )
    assert resp.status_code == 404


def test_admin_can_view_unlinked_applicant_profile(
    client: TestClient, admin_token: str, mock_supabase_client: MagicMock
):
    """Bulk-imported applicants (user_id NULL) are the primary debug target —
    view-as must resolve their rows by applicant id, not by auth user id."""
    _set_role(mock_supabase_client, "admin")
    lookup = _applicant_lookup_row()
    lookup["user_id"] = None  # no linked auth user

    dep_conn = AsyncMock()
    dep_conn.fetchrow = AsyncMock(return_value=lookup)

    router_conn = AsyncMock()
    captured: dict = {}

    async def _fetchrow(query, *params):
        captured["params"] = params
        captured["query"] = query
        return _profile_row_for(params[0])

    router_conn.fetchrow = AsyncMock(side_effect=_fetchrow)

    with (
        patch("app.auth.dependencies.get_db", return_value=_db_ctx(dep_conn)),
        patch("app.routers.applicants.get_db", return_value=_db_ctx(router_conn)),
    ):
        resp = client.get(
            "/applicant/me/profile",
            headers={
                "Authorization": f"Bearer {admin_token}",
                VIEW_AS_HEADER: TARGET_APPLICANT_ID,
            },
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["applicant_id"] == TARGET_APPLICANT_ID
    assert body["first_name"] == "Jane"
    # user_id fallback param is the ADMIN's own id (never a fabricated uuid)…
    assert captured["params"][0] == "admin-user-uuid"
    # …but resolution is driven by the applicant id via COALESCE.
    assert captured["params"][1] == TARGET_APPLICANT_ID
    assert "COALESCE" in captured["query"]


def test_unlinked_applicant_side_tables_return_empty_lists(
    client: TestClient, admin_token: str, mock_supabase_client: MagicMock
):
    """user_id-less applicants have no applications — endpoint returns [] not
    an error."""
    _set_role(mock_supabase_client, "admin")
    lookup = _applicant_lookup_row()
    lookup["user_id"] = None

    dep_conn = AsyncMock()
    dep_conn.fetchrow = AsyncMock(return_value=lookup)

    router_conn = AsyncMock()
    router_conn.fetch = AsyncMock(return_value=[])

    with (
        patch("app.auth.dependencies.get_db", return_value=_db_ctx(dep_conn)),
        patch("app.routers.applications.get_db", return_value=_db_ctx(router_conn)),
    ):
        resp = client.get(
            "/applicant/me/applications",
            headers={
                "Authorization": f"Bearer {admin_token}",
                VIEW_AS_HEADER: TARGET_APPLICANT_ID,
            },
        )

    assert resp.status_code == 200, resp.text
    assert resp.json() == []
    # The applications query resolves by the view-as applicant id.
    args = router_conn.fetch.await_args.args
    assert TARGET_APPLICANT_ID in args


def test_unlinked_applicant_mutation_still_403(
    client: TestClient, admin_token: str, mock_supabase_client: MagicMock
):
    """Read-only guard fires before any resolution — no DB access needed."""
    _set_role(mock_supabase_client, "admin")
    resp = client.patch(
        "/applicant/me/profile",
        json={"city": "Dallas"},
        headers={
            "Authorization": f"Bearer {admin_token}",
            VIEW_AS_HEADER: TARGET_APPLICANT_ID,
        },
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "View-as is read-only"


def test_admin_with_malformed_header_404(
    client: TestClient, admin_token: str, mock_supabase_client: MagicMock
):
    _set_role(mock_supabase_client, "admin")
    resp = client.get(
        "/applicant/me/profile",
        headers={
            "Authorization": f"Bearer {admin_token}",
            VIEW_AS_HEADER: "not-a-uuid",
        },
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Non-admin + header → 403
# ---------------------------------------------------------------------------

def test_applicant_sending_header_gets_403(
    client: TestClient, applicant_token: str, mock_supabase_client: MagicMock
):
    _set_role(mock_supabase_client, "applicant")
    resp = client.get(
        "/applicant/me/profile",
        headers={
            "Authorization": f"Bearer {applicant_token}",
            VIEW_AS_HEADER: TARGET_APPLICANT_ID,
        },
    )
    assert resp.status_code == 403
    assert "admin" in resp.json()["detail"].lower()


def test_employer_sending_header_gets_403(
    client: TestClient, employer_token: str, mock_supabase_client: MagicMock
):
    _set_role(mock_supabase_client, "employer")
    resp = client.get(
        "/applicant/me/profile",
        headers={
            "Authorization": f"Bearer {employer_token}",
            VIEW_AS_HEADER: TARGET_APPLICANT_ID,
        },
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Mutations under view-as → 403 read-only
# ---------------------------------------------------------------------------

def test_patch_profile_under_view_as_is_readonly_403(
    client: TestClient, admin_token: str, mock_supabase_client: MagicMock
):
    _set_role(mock_supabase_client, "admin")
    resp = client.patch(
        "/applicant/me/profile",
        json={"city": "Dallas"},
        headers={
            "Authorization": f"Bearer {admin_token}",
            VIEW_AS_HEADER: TARGET_APPLICANT_ID,
        },
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "View-as is read-only"


def test_post_chat_session_under_view_as_is_readonly_403(
    client: TestClient, admin_token: str, mock_supabase_client: MagicMock
):
    """Chat session creation is explicitly blocked under view-as."""
    _set_role(mock_supabase_client, "admin")
    resp = client.post(
        "/applicant/me/chat/sessions",
        json={},
        headers={
            "Authorization": f"Bearer {admin_token}",
            VIEW_AS_HEADER: TARGET_APPLICANT_ID,
        },
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "View-as is read-only"


def test_post_interest_under_view_as_is_readonly_403(
    client: TestClient, admin_token: str, mock_supabase_client: MagicMock
):
    _set_role(mock_supabase_client, "admin")
    resp = client.post(
        f"/applicant/me/matches/{TARGET_APPLICANT_ID}/interest",
        json={"interest_level": "interested"},
        headers={
            "Authorization": f"Bearer {admin_token}",
            VIEW_AS_HEADER: TARGET_APPLICANT_ID,
        },
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "View-as is read-only"


# ---------------------------------------------------------------------------
# Audit logging via POST /admin/view-as/{id}/start
# ---------------------------------------------------------------------------

def test_start_view_as_writes_one_audit_row(
    client: TestClient, admin_token: str, mock_supabase_client: MagicMock
):
    _set_role(mock_supabase_client, "admin")

    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=_applicant_lookup_row())
    conn.execute = AsyncMock(return_value="INSERT 0 1")

    with patch("app.routers.admin.get_db", return_value=_db_ctx(conn)):
        resp = client.post(
            f"/admin/view-as/{TARGET_APPLICANT_ID}/start",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["applicant_id"] == TARGET_APPLICANT_ID
    assert body["has_linked_account"] is True

    # Exactly one audit row written, with the right action + entities.
    assert conn.execute.await_count == 1
    args = conn.execute.await_args.args
    sql = args[0]
    assert "INSERT INTO public.audit_logs" in sql
    assert "admin_view_as_applicant" in sql
    assert args[1] == "admin-user-uuid"          # actor = the admin
    assert args[2] == TARGET_APPLICANT_ID        # entity = the applicant


def test_start_view_as_requires_admin(
    client: TestClient, applicant_token: str, mock_supabase_client: MagicMock
):
    _set_role(mock_supabase_client, "applicant")
    resp = client.post(
        f"/admin/view-as/{TARGET_APPLICANT_ID}/start",
        headers={"Authorization": f"Bearer {applicant_token}"},
    )
    assert resp.status_code == 403


def test_start_view_as_unknown_applicant_404(
    client: TestClient, admin_token: str, mock_supabase_client: MagicMock
):
    _set_role(mock_supabase_client, "admin")
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    with patch("app.routers.admin.get_db", return_value=_db_ctx(conn)):
        resp = client.post(
            f"/admin/view-as/{TARGET_APPLICANT_ID}/start",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Normal sessions unchanged
# ---------------------------------------------------------------------------

def test_applicant_without_header_unchanged(
    client: TestClient, applicant_token: str, mock_supabase_client: MagicMock
):
    _set_role(mock_supabase_client, "applicant")
    conn = AsyncMock()
    captured: dict = {}

    async def _fetchrow(query, *params):
        captured["params"] = params
        return _profile_row_for(params[0])

    conn.fetchrow = AsyncMock(side_effect=_fetchrow)

    with patch("app.routers.applicants.get_db", return_value=_db_ctx(conn)):
        resp = client.get(
            "/applicant/me/profile",
            headers={"Authorization": f"Bearer {applicant_token}"},
        )
    assert resp.status_code == 200, resp.text
    # Keyed on the applicant's own auth user id — untouched behavior.
    assert captured["params"][0] == "applicant-user-uuid"


def test_admin_without_header_still_403_on_applicant_routes(
    client: TestClient, admin_token: str, mock_supabase_client: MagicMock
):
    _set_role(mock_supabase_client, "admin")
    resp = client.get(
        "/applicant/me/profile",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 403
