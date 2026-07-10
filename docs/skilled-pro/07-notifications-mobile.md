# 07 — Notifications & Mobile

**Exec summary.** SKILLED Pro should ship native iOS + Android apps via **React Native + Expo (EAS)**, because the team already writes React/Next and can share API clients, types, validation, and business logic with the existing web app while paying for one mobile codebase instead of two. Notifications should run through a thin **FastAPI notification service** that owns a `device_tokens` table and fans out to **Expo Push** (free APNs+FCM abstraction) for push, **Knock** or **Courier** for orchestration/in-app feed/digests as volume grows, and **Resend** (with **Postmark** as the deliverability-critical fallback) for email. Geo-targeted "nearby openings + shift dispatch" is the one place that justifies a paid native dependency (**Transistor `react-native-background-geolocation`**) and demands the most careful consent and App-Store handling, because background location plus push-to-nearby is exactly what reviewers scrutinize.

This doc covers each sub-area with: (1) 2026 state of the art, (2) opinionated recommendation for a React/Next + FastAPI + Supabase team, (3) concrete frameworks/services/costs/tradeoffs, (4) privacy + compliance, (5) fit to *this* stack (shared API, Supabase auth, notification service + token table), (6) risks + app-store gotchas.

---

## 1. Native iOS & Android apps with worker-facing feature parity

### 1.1 State of the art (2026)
The 2026 field is **React Native (RN), Expo, Flutter, and Lynx**. Flutter holds the larger raw market share (~46% vs RN ~35%) and ships a great UI engine (Impeller 2.0), but it's Dart — a second language and a second talent pool for a React shop. RN's New Architecture (Fabric/TurboModules/bridgeless) is now the default and has closed most of the historical performance gap. **Expo is officially the recommended way to start new RN projects** per React Native's own docs; the old "managed vs bare" split is gone in favor of **Continuous Native Generation (CNG)** + config plugins, so you can drop to native code when needed without "ejecting." Expo Application Services (**EAS Build / EAS Submit / EAS Update**) handle cloud builds, store submission, and OTA JS updates.

### 1.2 Recommendation
**React Native + Expo, with EAS for build/submit/OTA.** This is the clear pick for a small team with an existing React/Next codebase. Rationale:
- **Talent reuse:** your engineers already write React + TypeScript. No new language.
- **Code sharing:** RN lets you share ~70–90% of *business logic* (API clients, Zod/validation schemas, the `packages/types` Supabase types, formatting, matching-result rendering logic) with the web app. UI is platform-specific but the data layer isn't.
- **Velocity:** EAS Update ships JS-only bug fixes over-the-air (within store policy) without a full review cycle — valuable for a small team.

Avoid Flutter unless you hire Dart talent; avoid native Swift/Kotlin (2x codebases, 2x maintenance — wrong for a small team) *except* for any future deep-OS feature.

### 1.3 Code-sharing strategy (concrete)
Restructure toward a shared monorepo. The repo is already a pnpm monorepo (`apps/web`, `apps/api`, `packages/*`), so:
- Add `apps/mobile/` (Expo) alongside `apps/web/`.
- Extract a **`packages/api-client`** (typed fetch wrappers around the FastAPI routes documented in CLAUDE.md) consumed by *both* web and mobile.
- Reuse **`packages/types`** (already auto-generated Supabase types) in mobile.
- Keep matching *explanation/labeling* presentation helpers (top_strengths/top_gaps/match_label formatting) in a shared package so the web and mobile match cards stay consistent.
- Do **not** attempt React Native Web to literally reuse `apps/web` screens — the web app is Next 15 with a Cohere/editorial design system; rebuild screens natively, share logic only.

**Worker-facing feature parity** (the priority surface): auth/login, profile + setup, browse jobs, ranked matches + dimension breakdown, interest signals, planning chat, DM inbox/thread, and push notifications. Employer/admin surfaces can stay web-only for v1 (they're desk-bound users); the mobile app is the *worker* app.

### 1.4 Tradeoffs / cost
- **Expo EAS:** Free tier exists; **Production $99/mo**, **Enterprise $999/mo** (includes EAS Build minutes, EAS Update, priority support). Push delivery is free at all tiers.
- **Apple Developer Program:** $99/yr. **Google Play:** $25 one-time.
- Tradeoff: EAS build minutes can be a cost/throughput bottleneck; you can self-host builds to cap cost.

### 1.5 Fit to this stack
Supabase has first-class Expo support (`@supabase/supabase-js` + `expo-secure-store` for the session). Auth tokens from Supabase are the same JWTs FastAPI already validates in `apps/api/app/auth/dependencies.py` (HS256/ES256) — **no backend auth changes needed**; the mobile app calls the *same* API with the same bearer token. RBAC, employer isolation, and `get_settings()` config all stay as-is.

### 1.6 Risks + app-store gotchas
- **Timeline:** EAS Submit upload ≈ 10–15 min. **TestFlight external review** ≈ half a day to ~1.5 days. **Full App Store review** averages 24–48h but can stretch to 7 days; new accounts + sensitive features (location!) skew longer. Budget for rejection/resubmit cycles — each adds days.
- **Metadata rejections** (missing privacy policy, vague description, wrong screenshots) are the most common avoidable delay.
- **OTA updates (EAS Update):** allowed for JS, but you cannot use OTA to change documented behavior or sneak features past review — Apple guideline 2.5.x.
- **Expo Go is not your production app** — it's a dev client; ship a real build via EAS.

---

## 2. Push (APNs+FCM), in-app, and email

### 2.1 State of the art (2026)
Three layers are now distinct:
- **Transport** — Expo Push (free unified APNs+FCM), or FCM v1 direct, or OneSignal. **FCM legacy HTTP API is dead; FCM v1 (OAuth) is mandatory.**
- **Orchestration** ("notification infrastructure") — **Knock** and **Courier** dominate: workflows, batching/digests, per-user preferences, multi-channel routing, in-app feed components, template version control.
- **In-app feed** — pre-built React components (Knock ships these) for a notification center/toast/banner.

### 2.2 Recommendation (phased)
**Phase A (launch): Expo Push direct + a FastAPI notification service.** Cheapest, fastest, zero per-message cost, sub-50ms median send latency, and it cleanly abstracts APNs+FCM. Your FastAPI service holds the device-token table and calls the Expo Push API server-side.

**Phase B (scale): add Knock as the orchestration layer.** When you need digests ("5 new matches today" instead of 5 pings), per-user channel preferences, send-time optimization, and an in-app feed, put Knock in front. Knock can still deliver push via your Expo/FCM/APNs credentials, so Phase A isn't throwaway. Choose **Courier instead** if your complexity is in *routing across many providers* rather than rich in-app UI, or if the lower price matters more than pre-built components.

**Email: Resend** as primary (best DX, React Email templates version-controlled in-repo, clean Python/REST API for FastAPI). Keep **Postmark** in mind for deliverability-critical transactional mail (password resets, employer outreach receipts) — Postmark's transactional-only shared IPs have the cleanest reputation. **SES** only if email volume explodes and cost dominates (it's ~$0.10/1k but painful: sandbox approval, bounce handling, no niceties).

### 2.3 Frameworks / services / cost / tradeoffs
| Option | Cost | Best for | Tradeoff |
|---|---|---|---|
| **Expo Push** | Free | RN/Expo apps, transport only | No orchestration/segmentation/analytics; tied to Expo tokens |
| **FCM v1 direct** | Free | Full control | You build orchestration; manage APNs+FCM separately |
| **OneSignal** | Free ≤10k subs; Growth $9+/mo; Pro $99+/mo | Built-in segmentation, A/B, STO, analytics fast | Higher send latency (~221ms vs Expo ~41ms p50); SDK adds weight |
| **Knock** | 10k msgs free; paid from **$250/mo** | In-app feed + digests + preferences + DX | Pricier; overkill if you only need transport |
| **Courier** | 10k msgs free; **$99/mo** (Essentials $110/50k, Business $275/50k) | Broad provider routing (50+), AI workflow nodes | In-app components less polished than Knock |
| **Resend** | Free 3k/mo, 1 domain | Transactional + DX, React Email | Younger; for critical mail pair with Postmark |
| **Postmark** | Overage model from 10k base (~$68.50/50k) | Deliverability of transactional mail | Transactional-only (no marketing) |
| **Amazon SES** | ~$0.10 / 1k | High volume, lowest cost | Sandbox approval friction, you build everything |

### 2.4 Privacy + compliance
- **Notification permission** is opt-in on both platforms (iOS prompt; Android 13+ runtime `POST_NOTIFICATIONS`). Ask *contextually* (after the user sees their first matches), not on cold launch, to protect grant rate.
- Honor unsubscribe/preferences per channel; email must include unsubscribe + comply with CAN-SPAM/CASL for any non-transactional content. Keep job-match pushes clearly transactional/service messages.
- Store only the device token + platform + user link; don't log notification *content* with PII longer than needed.

### 2.5 Fit to this stack
Add a **`notifications` router** in FastAPI mirroring existing routers, plus a `device_tokens` table:

```
device_tokens(
  id uuid pk,
  user_id uuid fk -> user_profiles,
  expo_push_token text,            -- ExponentPushToken[...]
  platform text,                   -- ios | android
  last_seen_at timestamptz,
  revoked bool default false,
  unique(user_id, expo_push_token)
)
```
- Mobile registers/re-registers the Expo token **on every app launch** (tokens rotate) via `POST /me/device-tokens` (upsert).
- New endpoints, all behind existing role guards: `POST /me/device-tokens`, `DELETE /me/device-tokens/{id}`.
- Fan-out: the notification service reads tokens for a user, batches to the Expo Push API, then **polls receipts** to prune dead tokens (set `revoked=true` on `DeviceNotRegistered`).
- Hook notification triggers into existing events already logged in `engagement_events` (e.g. new match computed → push; `dm_sent` → push; `outreach_sent` → push). Reuse the fire-and-forget recompute pattern already used on job/applicant create.
- Backend secrets (FCM v1 service account JSON, APNs key, Resend/Knock keys) via `get_settings()` Pydantic Settings — **never `os.environ.get()`** per the guardrail.

### 2.6 Risks + gotchas
- **FCM v1 migration is non-negotiable** — provision a Firebase service account and upload the APNs key/p8 to EAS.
- **Expo token ≠ FCM/APNs token** — if you ever leave Expo Push you must re-collect native tokens.
- **Silent token death:** tokens go stale on reinstall/restore; without receipt-driven pruning your send volume and error rate creep up.
- **iOS notification "Provisional authorization"** can deliver quietly to Notification Center to preserve grant rates — consider it for low-friction onboarding.

---

## 3. AI-optimized notification timing (send-time optimization)

### 3.1 State of the art (2026)
Send-Time Optimization (STO) builds a **per-user engagement model** ("when has *this* worker historically opened our notifications?") and schedules each send at that user's individual optimum, rather than a global best hour. Reported lifts: roughly **2–10% on open/click for optimized messages**, with vendor case studies claiming up to ~23% higher opens / ~41% more revenue at the high end. It's standard in Braze, OneSignal, CleverTap, Airship, and Adobe Journey Optimizer; Knock/Courier expose scheduling/throttling primitives you can drive with your own model.

### 3.2 Recommendation
**Don't build a custom ML model at launch.** Two-stage plan:
1. **Heuristic v0 (week one):** quiet hours + timezone + role-aware windows. Trades workers are often on-site early; default match-alert sends to **late afternoon/early evening local time**, suppress overnight, and respect per-user quiet-hours preferences. This captures most of the easy win.
2. **STO v1:** once you have engagement history in `engagement_events`, either (a) let **OneSignal/Braze STO** do it if you adopt one of them, or (b) compute a per-user "best send hour" feature in a nightly job from `engagement_events` open/click timestamps and pass a `send_at` to Knock/Expo. You already have OpenAI in the stack, but STO is a tabular/statistics problem — a simple per-user histogram beats an LLM here.

### 3.3 Frameworks / cost / tradeoffs
- Built-in STO: included in OneSignal Pro / Braze / CleverTap (bundled in platform cost). Lowest effort, vendor lock-in.
- DIY: free compute, full control, but you own the model quality and cold-start (new users have no history → fall back to heuristic).
- Tradeoff: STO delays delivery to hit the optimal window — **never apply it to time-critical sends** (see §4 shift dispatch: those must go *now*).

### 3.4 Privacy + compliance
- STO uses behavioral engagement data — disclose in privacy policy that you analyze in-app activity to time messages. This is **first-party** analytics (no ATT prompt needed) as long as you don't share/track across other companies' apps.
- Always honor quiet hours and frequency caps regardless of model output.

### 3.5 Fit to this stack
`engagement_events` already logs `interest_set`, `apply_click`, `dm_sent`, `outreach_sent`, `hire_reported` with timestamps — that's your STO training data, no new instrumentation. A nightly script (mirroring `scripts/recompute_matches.py`) computes `preferred_send_hour` per user; the notification service reads it when scheduling non-urgent pushes.

### 3.6 Risks
- Cold start: new workers have no history — fall back to the heuristic.
- Over-optimization clusters everyone into the same "optimal" hour — add jitter/throttling.
- Don't let STO silently hold a *shift-dispatch* alert; tag messages as `urgent` to bypass STO.

---

## 4. Geo-targeted alerts: nearby openings + shift dispatch

### 4.1 State of the art (2026)
This is the hardest, most-scrutinized area. Two modes:
- **Nearby openings:** when a new job lands within X miles of a worker, push them. Can be done **server-side** from a coarse last-known/home location — no background location needed.
- **Live shift dispatch / geofencing:** detect entry/exit of a job-site geofence or continuously know who's nearby — requires **background location**. OS battery rules tightened hard: **iOS 18+/Android 15** aggressively throttle and will permanently restrict apps flagged as battery drainers; iOS background execution stays capped at ~30s. Expo's TaskManager supports basic background location + geofencing, but **production-grade, battery-safe geofencing needs a dedicated native SDK** — the de-facto standard is **Transistor `react-native-background-geolocation`**.

### 4.2 Recommendation
**Tier the feature by need:**
- **Default (most workers): server-side proximity.** Store a coarse worker location (home zip/city or last foreground location, with consent). On new-job insert, compute distance server-side and push if within radius. Zero background-location risk, no extra App-Store burden, geography is already first-class in your matching engine (gates + scorer) so the distance math/data already exists.
- **Premium (active job-seekers / on-shift): background geofencing** via Transistor SDK, **opt-in only**, for true shift-dispatch ("a 2-hr emergency electrician shift opened 1 mile away — claim it").

### 4.3 Frameworks / cost / tradeoffs
- **`expo-location` + `expo-task-manager`:** free, covers foreground + basic geofencing; weak for always-on background reliability under 2026 OS throttling.
- **Transistor `react-native-background-geolocation`:** purpose-built, battery-conscious, motion-detection-gated geofencing; free in DEBUG, **per-app-identifier license required for release builds** (one purchase covers iOS+Android, unlimited users/devices). This is the correct production choice for shift dispatch.
- Geofence math/storage: PostGIS in Supabase (or simple Haversine in FastAPI) for server-side proximity; the device SDK handles on-device geofences for the premium tier.
- Tradeoff: background location is the single biggest battery, privacy, and review-risk surface — only enable it for the users who actually need it.

### 4.4 Privacy + compliance (critical here)
- **iOS permission ladder:** request **When-In-Use first**, demonstrate value, then escalate to **Always** only when the user opts into shift dispatch. Provide clear `NSLocationWhenInUseUsageDescription` / `NSLocationAlwaysAndWhenInUseUsageDescription` strings explaining the job-dispatch benefit. iOS will independently re-prompt the user about "Always" access later — design for that.
- **ATT (App Tracking Transparency):** required *only if you track across other companies' apps/sites or share with data brokers/ad networks*. First-party "use my location to show nearby jobs" does **not** require ATT — but referencing ad/attribution/analytics SDKs that fingerprint can trigger rejection. Keep location first-party and you avoid the ATT prompt entirely.
- **Android:** `ACCESS_FINE_LOCATION` + separately-requested `ACCESS_BACKGROUND_LOCATION` (Android 11+ forces a two-step flow to Settings); Play Store requires a **prominent in-app disclosure** + a Play Console declaration justifying background location, reviewed manually.
- Data minimization: store coarse location for nearby-alerts; for live dispatch, keep precise location ephemeral (don't retain location history beyond the dispatch window). Disclose all of this in the privacy policy and Apple Privacy Nutrition Labels.

### 4.5 Fit to this stack
- New columns/table: `worker_location(user_id, geog, accuracy, source, consent_level, updated_at)`; consent_level in {none, nearby, dispatch}.
- New endpoint `POST /me/location` (role-guarded) to update coarse location; gate it on consent_level.
- Nearby-openings trigger: extend the existing fire-and-forget recompute on job create (`POST /employer/me/jobs`) to also enqueue proximity pushes — reuse the notification service + `device_tokens` fan-out from §2.5.
- Geography already a first-class matching concept, so distance scoring/data is consistent between matches and alerts (no divergent geo logic — honors the "geography is first-class" guardrail).

### 4.6 Risks + app-store gotchas
- **#1 rejection cause for location apps:** requesting **Always**/background location without a clearly demonstrated, user-visible need. Reviewers test this. Don't ask for Always at launch; gate it behind the shift-dispatch opt-in.
- **Geofence-entry push when app is closed is fragile** — known issues across iOS/Android; the Transistor SDK is the most reliable but still test on real devices, low-power mode, and after reboot.
- **Battery-drainer flagging** (iOS 18+/Android 15) can permanently restrict background work — use motion-gated geofencing, not continuous high-accuracy polling.
- **Google Play background-location review** adds days and requires a demo video — budget timeline for it.
- Shift-dispatch alerts must bypass STO/quiet-hours (mark `urgent`) — a delayed dispatch ping is useless.

---

## Sources
- https://www.groovyweb.co/blog/react-native-vs-flutter-vs-expo-vs-lynx-2026
- https://tech-insider.org/flutter-vs-react-native-2026/
- https://www.bolderapps.com/blog-posts/flutter-vs-react-native-in-2026-why-the-new-architecture-and-impeller-2-0-changed-everything
- https://docs.expo.dev/submit/introduction/
- https://expo.dev/changelog/expo-go-and-app-store-may-2026
- https://www.shipnative.dev/blog/expo-eas-app-store-submission-checklist
- https://www.lowcode.agency/blog/app-store-review-time
- https://docs.expo.dev/push-notifications/overview/
- https://docs.expo.dev/guides/using-push-notifications-services/
- https://www.courier.com/integrations/compare/expo-vs-onesignal-push
- https://knock.app/push-api-benchmarks/compare/expo-vs-onesignal
- https://www.pkgpulse.com/blog/notifee-vs-expo-notifications-vs-onesignal-react-native-push-2026
- https://knock.app/blog/evaluating-the-best-push-notifications-providers
- https://www.sequenzy.com/versus/courier-vs-knock
- https://knock.app/blog/the-top-notification-infrastructure-platforms-for-developers
- https://apiscout.dev/guides/novu-vs-knock-vs-courier-notification-api-2026
- https://www.buildmvpfast.com/blog/resend-vs-ses-vs-postmark-transactional-email-deliverability-saas-2026
- https://www.buildmvpfast.com/api-costs/email
- https://draymor.com/blog/ai-powered-send-time-optimization-explained
- https://www.airship.com/blog/our-machine-learning-model-for-predictive-send-time-optimization/
- https://clevertap.com/blog/machine-learning-powered-best-time-to-send-campaigns/
- https://pushpilot.ai/blog/best-time-to-send-push-notifications-2026
- https://docs.expo.dev/versions/latest/sdk/location/
- https://github.com/transistorsoft/react-native-background-geolocation
- https://docs.transistorsoft.com/purchase/
- https://shop.transistorsoft.com/products/react-native-background-geolocation-premium-license
- https://dev.to/eira-wexford/run-react-native-background-tasks-2026-for-optimal-performance-d26
- https://developer.apple.com/app-store/user-privacy-and-data-use/
- https://developer.apple.com/documentation/apptrackingtransparency
- https://supabase.com/docs/guides/functions/examples/push-notifications
