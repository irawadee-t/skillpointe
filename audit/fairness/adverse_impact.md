# Adverse-impact audit (four-fifths rule)

Groups below the minimum size are suppressed. Ratio = group rate /
highest group rate; < 0.80 flags adverse impact (EEOC guideline).

## gender x surfaced

| group | n | rate | impact ratio | flag |
|---|---|---|---|---|
| Prefer not to answer | 194 | 0.778 | 1.000 |  |
| Male | 28363 | 0.777 | 0.998 |  |
| Nonbinary | 233 | 0.691 | 0.888 |  |
| Female | 12249 | 0.541 | 0.695 | ADVERSE (<0.80) |

## gender x actionable

| group | n | rate | impact ratio | flag |
|---|---|---|---|---|
| Male | 28363 | 0.382 | 1.000 |  |
| Prefer not to answer | 194 | 0.345 | 0.904 |  |
| Nonbinary | 233 | 0.296 | 0.775 | ADVERSE (<0.80) |
| Female | 12249 | 0.241 | 0.629 | ADVERSE (<0.80) |

## age_range x surfaced

| group | n | rate | impact ratio | flag |
|---|---|---|---|---|
| Prefer not to answer | 73 | 0.726 | 1.000 |  |
| 18–24 | 21034 | 0.726 | 1.000 |  |
| Under 18 | 6894 | 0.691 | 0.952 |  |
| 45–54 | 1284 | 0.688 | 0.947 |  |
| 25–34 | 7815 | 0.677 | 0.932 |  |
| 35–44 | 3681 | 0.676 | 0.931 |  |
| 55+ | 357 | 0.655 | 0.903 |  |

## age_range x actionable

| group | n | rate | impact ratio | flag |
|---|---|---|---|---|
| Prefer not to answer | 73 | 0.384 | 1.000 |  |
| 18–24 | 21034 | 0.358 | 0.934 |  |
| 25–34 | 7815 | 0.321 | 0.836 |  |
| Under 18 | 6894 | 0.320 | 0.835 |  |
| 35–44 | 3681 | 0.317 | 0.827 |  |
| 45–54 | 1284 | 0.304 | 0.792 | ADVERSE (<0.80) |
| 55+ | 357 | 0.291 | 0.760 | ADVERSE (<0.80) |

## military_status x surfaced

| group | n | rate | impact ratio | flag |
|---|---|---|---|---|
| veteran/military | 1336 | 0.784 | 1.000 |  |
| civilian | 41666 | 0.672 | 0.857 |  |

## military_status x actionable

| group | n | rate | impact ratio | flag |
|---|---|---|---|---|
| veteran/military | 1336 | 0.397 | 1.000 |  |
| civilian | 41666 | 0.323 | 0.813 |  |

## Summary
Flagged (investigate the causal path before shipping ranking changes):
- gender=Female on actionable: ratio 0.629
- gender=Female on surfaced: ratio 0.695
- age_range=55+ on actionable: ratio 0.760
- gender=Nonbinary on actionable: ratio 0.775
- age_range=45–54 on actionable: ratio 0.792

## Causal-path analysis for the flagged gender disparity

Surfaced rate by gender WITHIN career path (2026-08-18 live query):

| career_path | female n | male n | female surfaced | male surfaced |
|---|---|---|---|---|
| Healthcare | 3,965 | 908 | 1.8% | 1.0% |
| Construction & Building Trades | 3,122 | 15,210 | 84.7% | 83.5% |
| Other Skilled Trade Industry | 2,323 | 2,506 | 96.6% | 96.4% |
| Transportation | 914 | 4,732 | 67.3% | 71.0% |
| Public & Emergency Service | 554 | 321 | 31.2% | 31.5% |
| Manufacturing | 311 | 1,348 | 89.1% | 92.4% |

Within every stratum the gender gap is within noise. The aggregate 0.63-0.70
impact ratio is COMPOSITION: female applicants disproportionately chose
Healthcare (and Public & Emergency Service), fields where the job catalog has
zero (respectively near-zero) postings, so everyone in those fields goes
unserved regardless of gender. The engine takes no protected attribute as
input (verified: recompute fetch list + zero references in packages/matching).

Mitigation is catalog acquisition — healthcare and public-service partners —
not a scoring change. A scoring "fix" that force-surfaced wrong-field jobs to
female applicants would hide the real gap and degrade honesty. Track this
table on every partner onboarding; the age_range 45+/55+ actionable ratios
(0.76-0.79) warrant the same stratified check next audit.

Regulatory note: if the platform is used to screen or rank candidates for
employers in NYC (Local Law 144) or similar jurisdictions, an annual
independent bias audit with published results may be required — this document
is the internal precursor, not that audit. Confirm scope with counsel.
