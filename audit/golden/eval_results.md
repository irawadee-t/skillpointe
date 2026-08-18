# Matching Engine — Offline Evaluation

- Labels file: `audit/golden/labels.csv`
- Applicants evaluated: 21 (skipped 1 with no matches rows)
- Labeled pairs: 258
- Relevance: grade >= 2 is relevant; NDCG uses graded values
- Random baseline: seed 42, mean over 20 draws

## Mean metrics per ranker

| Ranker | P@5 | P@10 | NDCG@10 | MRR |
|---|---|---|---|---|
| production | 0.2667 | 0.2000 | 0.7523 | 0.6218 |
| random | 0.1729 | 0.1738 | 0.6696 | 0.4504 |
| popularity | 0.1810 | 0.1762 | 0.6690 | 0.3272 |
| bm25 | 0.2000 | 0.1810 | 0.7738 | 0.6559 |

## Production order — by applicant state

| State | n | P@5 | P@10 | NDCG@10 | MRR |
|---|---|---|---|---|---|
| AZ | 5 | 0.2800 | 0.2200 | 0.8713 | 0.7500 |
| CA | 4 | 0.2000 | 0.1000 | 0.5964 | 0.4167 |
| FL | 6 | 0.0333 | 0.0167 | 0.7109 | 0.2500 |
| GA | 6 | 0.5333 | 0.4333 | 0.7983 | 0.6667 |

## Production order — by n-gaps tier of labeled items

Each row scores production order against only the labeled items in that tier.

| n-gaps tier | applicants | P@5 | P@10 | NDCG@10 | MRR |
|---|---|---|---|---|---|
| 0 | 1 | 0.2000 | 0.1000 | 1.0000 | 1.0000 |
| 1 | 14 | 0.1571 | 0.0786 | 0.9401 | 0.8000 |
| 2 | 21 | 0.1524 | 0.1429 | 0.6270 | 0.3517 |
| 3+ | 19 | 0.0000 | 0.0000 | 0.2102 | — |
| unknown | 4 | 0.0000 | 0.0000 | 0.0000 | — |

## Exposure (production order, top-10)

| Catalog coverage@10 | Gini of exposure@10 | Catalog size (jobs table) |
|---|---|---|
| 0.0198 | 0.2841 | 2827 |
