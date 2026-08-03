# Deploy checklist — shipping `riya-updates` to production

Verified against the working tree on 2026-08-03. Supersedes the migration counts in
`DEPLOY_RUNBOOK.md` (that document was written for an earlier branch).

**Live stack:** Vercel project `skilled-nation` (deploys from `main`) · FastAPI on Railway ·
Supabase Cloud · Upstash Redis · GitHub `irawadee-t/skillpointe`.

**The one rule:** migrate the database FIRST, then the backend, then the frontend.
Merging to `main` before the DB is migrated breaks the live site (missing tables and columns).

---

## Order of operations

### 1. Database (Supabase Cloud) — REQUIRES YOUR LOGIN

26 new migrations are pending. All are additive (new tables, columns, enum values,
indexes); none drop or rewrite existing data.

```bash
supabase login                      # opens a browser, one time
supabase link --project-ref <PROJECT_REF>
supabase migration list --linked    # SAFETY CHECK: confirm the 26 show as not applied
supabase db push                    # applies pending migrations in order
```

Pending migrations:

```
20260720000001_account_change_attempt_lockout      20260801182914_credential_taxonomy_registry
20260720000002_credential_source_badge_checkr      20260801194258_perf_matches_applicant_elig_idx
20260720000003_scale_search_and_indexes            20260802090000_job_import_row_held
20260721000001_dob_minor_protection                20260802110000_application_status_revert
20260721000002_chat_guardrails                     20260802130000_interviewers_and_calendar_feed
20260721000003_job_sections_cache                  20260802150000_needs_review_is_normalization_flag
20260721000004_credential_phone_upload             20260802170000_job_lifecycle_and_source_freshness
20260801062214_employer_career_sources             20260803090000_notification_kinds_realtime_rls
20260801062752_taxonomy_industries_and_scholarship  20260803120000_interview_cancel_and_deferred_notify
20260801064744_jobs_employment_type                20260803150000_calendar_connections
20260801080000_applicant_job_coordinates           (+ team invites / scheduling requests, career
20260801090000_match_tiers_and_distance             source profiles, internal apply config,
20260801100000_career_source_profiles               notification kinds — see supabase/migrations)
20260801120000_internal_apply_config
```

Note: `20260803090000_notification_kinds_realtime_rls` enables row-level security on
`notifications` and enrolls tables in the realtime publication. It closes a real hole
(notifications were readable by any client holding the anon key) — do not skip it.

### 2. Backend (Railway)

Railway auto-deploys from `main` via `railway.json` watchPatterns.

**Environment variables to set before/with this deploy:**

| Variable | Value | Why |
|---|---|---|
| `API_PUBLIC_URL` | your Railway service URL | Defaults to `localhost:8000`. Used to build calendar OAuth redirect URIs. |
| `WEB_PUBLIC_URL` | `https://skilled-nation.vercel.app` | Used in emails and redirects back to the app. |
| `HEADLESS_SCRAPE_ENABLED` | `false` | **Required.** Defaults true, but `playwright` is deliberately not in `requirements.txt` and Railway has no Chromium. The import sits inside the function so nothing crashes, but the daily sweep would log errors every tick. |
| `CALENDAR_FAKE_PROVIDER` | leave UNSET | The demo calendar. `enforce_production_safety` refuses to boot if it is true in production. |
| `RESEND_API_KEY` (preferred) or `SMTP_HOST` + `SMTP_PORT` | your mail provider | **Team invites, join links, and scheduling-request emails do not send without it.** The sender picks Resend first, then explicit SMTP, then (local only) the Supabase mail sink. Setting the key is the only change needed: the code path is identical and already verified end to end locally. |
| `GOOGLE_CALENDAR_CLIENT_ID` / `_SECRET` | optional | Google busy-time overlay. Feature hides itself when unset. |
| `MS_GRAPH_CLIENT_ID` / `_SECRET` | optional | Outlook busy-time overlay. Hides itself when unset. |
| `CHECKR_API_KEY` | optional | Background checks. The UI hides the method entirely when unset. |

Already-present variables (Supabase keys, `REDIS_URL`, `OPENAI_API_KEY`, `CORS_ORIGINS`)
carry over unchanged.

New Python dependency this branch adds: `pypdf` (already declared in `requirements.txt`).
The ICS calendar feed is hand-rolled, so no `icalendar` dependency is needed at runtime.

### 3. Frontend (Vercel)

Merging to `main` triggers the deploy. No new frontend env vars are required.

```bash
git checkout main && git merge riya-updates && git push origin main
```

---

## Post-deploy verification

1. `GET /health` on Railway returns `status: ok` with postgres, supabase, and redis all ok.
2. Sign in as each role; confirm the dashboard, matches, and applications pages render.
3. Admin → Career sources: confirm sources list and a manual sync succeeds.
4. Admin → Matching: confirm the config page loads the active version.
5. Check Railway logs for scheduler ticks: no repeated headless errors (proves
   `HEADLESS_SCRAPE_ENABLED=false` took effect).

## Rollback

`supabase db push` is additive and safe to leave in place. To roll back code only,
revert the merge commit on `main` and push. The additive schema stays compatible
with the previous application version.
