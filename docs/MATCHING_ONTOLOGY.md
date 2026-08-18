# SKILLED Nation Matching Ontology

The single design rule: **every gap is classified as impossible or bridgeable,
and every bridgeable gap surfaces with its path stated.** A door only closes
when crossing it would take years, not weeks or a conversation.

## The axes, and how each one applies the rule

| Axis | Impossible (hard fail) | Bridgeable (near fit + stated path) | Status |
|---|---|---|---|
| Career field | Different sector entirely (nursing ↔ manufacturing) | Different field, same sector — "related fields within Healthcare" | live |
| Credentials | Degree-class requirements: bachelor's, associate's, RN/LPN licensure | Certifications and licenses (CDL, EPA 608, OSHA 10) — "You can still earn X. Check the training options on this page, then apply." Training pathways render on the match page. | live |
| Timing | Finish date more than 24 months out | Within 12 months — "Apply, then message the employer about timing." DMs are one click away. Under 3 months counts as available (employers hire ahead). | live |
| Seniority | Supervisory ladder for a trainee (foreman, superintendent) — a different ladder, not a rung | "We will train" passes a trainee whatever the level label; a known-years applicant is graded against the posting's stated ask, close = near fit | live |
| Geography | Beyond ~1.5× the stated radius with an explicit no-relocate preference | Inside radius passes regardless of state line (border metros: Camden→Philadelphia). Slightly beyond radius = near fit. No stated preference is missing data, never a refusal. | live |
| Experience years | Ask exceeds applicant's years by 3+ | Within 2 years of the ask — "close" | live |

## Practical signals extracted from posting text

Real applicants decide on these before anything else; all are deterministic
extractions with the source phrase recorded:

- **Shift** (day / evening / night / weekend / rotating) — a student in class
  until 3pm needs the 2nd-shift roles; 206 of 664 postings state one.
- **Apprenticeship** — paid earn-while-you-learn roles are the strongest
  possible match for this audience; 55 flagged.
- **Veteran-friendly** — pairs with the PSA military_status field.
- **Entry-friendly** — "no experience necessary" / "we will train"; passes the
  seniority gate outright. 164 postings.
- **Credentials** — required vs preferred vs mentioned, graded per sentence.

## Ranking-layer rules

- **Gap count outranks score.** The empirical audit (2026-08) found near-fit
  score spread within one applicant's list was 3.2 points -- ordering noise --
  while 47k of 400k near-fits were exactly ONE gate from eligible, buried
  among three-gap marginals. Every ranked read now orders by
  (n_gaps ASC, score DESC): a one-cert-away at 55 beats a three-gap at 58.
  primary_gap names the most structural gate for the card's one-sentence
  story. Applies to applicant matches AND employer candidate lists.

- **Score order rules — no per-employer diversity cap.** A cap was tried and
  removed (2026-08): it is a mega-marketplace anti-spam pattern, and on a
  six-partner catalog it demotes genuinely better-fit jobs below worse ones
  purely for employer variety, fighting the honest ranking. If one partner has
  the five best jobs for you, you see all five, in order. Revisit only if the
  employer count grows past the point where one source can flood a page.
- **Nearby shelf stays distance-ordered** — its premise is "because you're
  close", never blended into score order.
- **Unknown is neutral, never zero** — missing data on either side scores
  null-default and is flagged, not punished.

## Evidence-first audit decisions (2026-08-18)

- **Evidence-weighted scoring.** The neutral-default census found 88% of
  pairs had 3+ of 9 dimensions resolved to constants (timing 100% defaulted,
  compensation 99%, experience a constant-55 masquerading as evidence), which
  compressed every list into a ~3-point band. The structured score is now the
  weighted mean over evidence-backed dimensions only; `score_evidence_pct`
  is stored per match and the UI shows "Early estimate" instead of a numeral
  below 40% evidence. Constants can no longer impersonate confidence.
- **Adjacent-state candidate generation.** The geography gate always passed
  border commutes (Camden -> Philadelphia), but the same-state prefilter never
  generated those pairs — 31.9% of applicants had zero matches while 98% of
  them had feasible jobs one state over. The prefilter now includes adjacent
  states (packages/matching/state_adjacency.py); the gate remains the decider.
- **US-only guard.** Scrapers had parsed "Whitby, ON, CA" as California and
  served Ontario postings to CA applicants. parse_location now recognizes
  Canadian provinces; _fetch_jobs filters on country; 15 rows corrected.
- **O*NET as external ground truth.** All active jobs carry onet_soc_code +
  job zone (audit/onet/). Known impurities to work: manufacturing_production
  is a catch-all (41% SOC agreement); "Lead X" titles inflate to senior on
  low-preparation occupations; warehouse roles hide in other_transportation.
- **Golden set + eval harness.** 258 hand-labeled pairs (audit/golden/) and
  packages/matching/eval_metrics.py + scripts/eval_harness.py compute
  P@K/NDCG/MRR vs random, popularity, and BM25 nulls. No ranking change ships
  without moving these numbers.
- **Ranked-impression logging.** match_impressions records what was shown at
  which position with serve-time scoring state — the prerequisite for any
  learned ranker and for honest offline evaluation of click data.
- **Known catalog gaps (not algorithm bugs):** no welding jobs in FL/AZ, no
  automotive in AZ, no healthcare anywhere — applicants in those fields see
  only adjacent-field stretches. Partner acquisition is the fix.
- **specific_career is unread by matching** (see below) — applicants who
  typed "aviation maintenance technician" rank their exact-match job by
  generic same-state order only.

## Designed, not yet implemented (needs product input)

- **Applicant field inference from free text** — specific_career / program
  text should feed the family classifier (the job side already does this);
  13.4% of PSA applicants stated a career the matcher ignores.

- **Shift preference on the applicant profile** — the job side is extracted;
  the applicant side needs a profile field before it can gate or score.
- **Pay-floor honesty** — when a job pays below the applicant's stated current
  wage, say so on the card rather than hiding or penalizing it.
- **Veteran boost in employer soft-pref dimension** — flag exists on both
  sides; wiring it into scoring is a policy decision (SCORING_CONFIG).
- **Engagement-informed ranking** — interest/apply/hire events exist in
  engagement_events; a learning-to-rank pass is future work and belongs in
  the policy layer, never in base fit.

## Provenance

Seniority levels follow O*NET Job Zones (preparation = education + related
experience + on-the-job training), collapsed to entry (zones 1-2), mid (3),
senior (4), management (supervisory ladder). Career fields and sectors are
Tasha's "Industry & Career List Revisions v2", generated into code, SQL, and
TS by scripts/gen_taxonomy.py. Credential canon is the 127-definition registry
in apps/api/app/skilled_pro/taxonomy.py.
