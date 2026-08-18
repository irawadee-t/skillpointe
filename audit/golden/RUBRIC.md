# Golden-set labeling rubric (2026-08-18, labeler: Claude session, single-labeler)

Grades on pairs sampled from the frozen baseline (top-10 + 3 random below-fold
per applicant, 22 applicants, 258 pairs). Labeled from raw facts only
(program/career text, job title/level/creds/location); system scores and
gap counts were NOT shown during labeling.

- 3 would advance today: same or exactly-stated field, entry-accessible
  (entry / will-train / apprenticeship), feasible geography.
- 2 worth a look: same field mid-level with attainable requirements, or
  adjacent field (same sector) entry-accessible, or same-field farther away.
- 1 stretch with a named path: adjacent field mid-level, generic
  entry-friendly work for an undeclared profile, or feasible but far.
- 0 no: management/supervisory for a trainee, 5+year senior asks,
  wrong-sector aspiration, infeasible geography, corrupted data
  (e.g. Canadian postings mislabeled as California).

Known limitations: single labeler (no Cohen's kappa); the applicant's stated
free-text career (specific_career) was treated as ground truth for their
field even though the current pipeline ignores it — that is deliberate: the
labels measure what the system SHOULD know from its own data.
