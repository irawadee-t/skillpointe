#!/usr/bin/env python3
"""
eval_harness.py — offline evaluation harness for the matching engine.

Turns "the matches look good" into numbers. For every applicant present in a
graded labels file, pulls that applicant's candidate list from the `matches`
table, orders it four ways, and scores each ordering against the labels:

  production   ORDER BY n_gaps ASC NULLS LAST,
                        policy_adjusted_score DESC NULLS LAST,
                        distance_miles ASC NULLS LAST, job_id
  random       shuffle of the same candidate set, seeded 42,
               averaged over 20 draws
  popularity   job with the most rows in the matches table first
               (global popularity, ties by job_id)
  bm25         BM25Okapi (k1=1.5, b=0.75) over each candidate job's
               title_raw + description_raw, query = the applicant's
               program_field + career_path + specific_career +
               essay_background + experience_raw

Labels CSV columns: applicant_id, job_id, grade (0-3).
grade >= 2 counts as "relevant" for the binary metrics (P@k, MRR);
NDCG uses the graded values directly.

Reported: mean P@5, P@10, NDCG@10, MRR per ranker; per-slice breakdown by
applicant state and by n-gaps tier of the labeled items (production order);
catalog coverage@10 and Gini of exposure across the sample under production
order. Prints a markdown report and writes audit/golden/eval_results.md.

Usage:
  python scripts/eval_harness.py                                   # audit/golden/labels.csv
  python scripts/eval_harness.py --labels audit/golden/labels_smoke.csv
  python scripts/eval_harness.py --make-smoke                      # generate smoke fixture

The smoke fixture (audit/golden/labels_smoke.csv, never labels.csv) samples
3 applicants from the DB with grades derived from eligibility_status
(eligible=3, near_fit with n_gaps=1 -> 2, n_gaps=2 -> 1, else 0) purely to
prove the harness runs end to end.
"""
from __future__ import annotations

import argparse
import csv
import math
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages"))

from matching.eval_metrics import (
    catalog_coverage_at_k,
    gini_of_exposure,
    mrr,
    ndcg_at_k,
    precision_at_k,
)

DEFAULT_LABELS = REPO_ROOT / "audit" / "golden" / "labels.csv"
SMOKE_LABELS = REPO_ROOT / "audit" / "golden" / "labels_smoke.csv"
RESULTS_MD = REPO_ROOT / "audit" / "golden" / "eval_results.md"

RELEVANT_GRADE = 2.0  # grade >= 2 counts as relevant for binary metrics
RANDOM_SEED = 42
RANDOM_DRAWS = 20

PRODUCTION_ORDER_SQL = """
    SELECT job_id
      FROM matches
     WHERE applicant_id = %s
     ORDER BY n_gaps ASC NULLS LAST,
              policy_adjusted_score DESC NULLS LAST,
              distance_miles ASC NULLS LAST,
              job_id
"""


# ---------------------------------------------------------------------------
# BM25
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str | None) -> list[str]:
    """Lowercase alphanumeric tokens."""
    return _TOKEN_RE.findall((text or "").lower())


class BM25Okapi:
    """Minimal BM25Okapi (k1=1.5, b=0.75) over pre-tokenized documents."""

    def __init__(self, corpus: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.n_docs = len(corpus)
        self.doc_freqs = [Counter(doc) for doc in corpus]
        self.doc_lens = [len(doc) for doc in corpus]
        self.avgdl = (sum(self.doc_lens) / self.n_docs) if self.n_docs else 0.0
        df: Counter = Counter()
        for doc in corpus:
            df.update(set(doc))
        # Okapi IDF with the +1 floor (rank_bm25 convention, never negative)
        self.idf = {
            term: math.log((self.n_docs - n + 0.5) / (n + 0.5) + 1.0)
            for term, n in df.items()
        }

    def score(self, query: list[str], index: int) -> float:
        freqs = self.doc_freqs[index]
        dl = self.doc_lens[index]
        norm = self.k1 * (1.0 - self.b + self.b * dl / self.avgdl) if self.avgdl else self.k1
        score = 0.0
        for term in query:
            tf = freqs.get(term)
            if not tf:
                continue
            score += self.idf.get(term, 0.0) * tf * (self.k1 + 1.0) / (tf + norm)
        return score

    def rank(self, query: list[str], doc_ids: list) -> list:
        """doc_ids in the same order as the corpus; ties broken by str(id)."""
        scored = [(self.score(query, i), doc_id) for i, doc_id in enumerate(doc_ids)]
        scored.sort(key=lambda pair: (-pair[0], str(pair[1])))
        return [doc_id for _, doc_id in scored]


# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------

def load_labels(path: Path) -> dict[str, dict[str, float]]:
    """labels[applicant_id][job_id] = grade. Ids are kept as strings."""
    labels: dict[str, dict[str, float]] = defaultdict(dict)
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        required = {"applicant_id", "job_id", "grade"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(
                f"ERROR: labels file {path} is missing columns: {', '.join(sorted(missing))}"
            )
        for row in reader:
            labels[row["applicant_id"].strip()][row["job_id"].strip()] = float(row["grade"])
    return dict(labels)


def fetch_candidates(conn, applicant_id: str) -> list[str]:
    """Applicant's candidate job list in production order."""
    with conn.cursor() as cur:
        cur.execute(PRODUCTION_ORDER_SQL, (applicant_id,))
        return [str(row[0]) for row in cur.fetchall()]


def fetch_popularity(conn) -> dict[str, int]:
    """Global popularity: rows per job in the matches table."""
    with conn.cursor() as cur:
        cur.execute("SELECT job_id, count(*) FROM matches GROUP BY job_id")
        return {str(job_id): int(n) for job_id, n in cur.fetchall()}


def fetch_job_texts(conn, job_ids: list[str]) -> dict[str, str]:
    if not job_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, coalesce(title_raw, ''), coalesce(description_raw, '') "
            "FROM jobs WHERE id = ANY(%s::uuid[])",
            (job_ids,),
        )
        return {str(jid): f"{title} {desc}" for jid, title, desc in cur.fetchall()}


def fetch_applicant_info(conn, applicant_ids: list[str]) -> dict[str, dict]:
    """State + concatenated query text per applicant."""
    if not applicant_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, state, program_field, career_path, specific_career, "
            "       essay_background, experience_raw "
            "FROM applicants WHERE id = ANY(%s::uuid[])",
            (applicant_ids,),
        )
        out = {}
        for aid, state, *texts in cur.fetchall():
            out[str(aid)] = {
                "state": state or "unknown",
                "query_text": " ".join(t for t in texts if t),
            }
        return out


def fetch_label_gap_tiers(conn, labels: dict[str, dict[str, float]]) -> dict[tuple[str, str], str]:
    """n-gaps tier ('0', '1', '2', '3+', 'unknown') for each labeled pair."""
    pairs = [(aid, jid) for aid, jobs in labels.items() for jid in jobs]
    if not pairs:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT applicant_id, job_id, n_gaps FROM matches "
            "WHERE applicant_id = ANY(%s::uuid[])",
            (sorted(labels.keys()),),
        )
        gaps = {(str(a), str(j)): g for a, j, g in cur.fetchall()}
    tiers = {}
    for pair in pairs:
        g = gaps.get(pair)
        if g is None:
            tiers[pair] = "unknown"
        elif g >= 3:
            tiers[pair] = "3+"
        else:
            tiers[pair] = str(int(g))
    return tiers


def fetch_catalog_size(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM jobs")
        return int(cur.fetchone()[0])


# ---------------------------------------------------------------------------
# Metrics plumbing
# ---------------------------------------------------------------------------

METRIC_NAMES = ["P@5", "P@10", "NDCG@10", "MRR"]


def score_ranking(ranking: list[str], grades: dict[str, float]) -> dict[str, float | None]:
    relevant = {jid for jid, g in grades.items() if g >= RELEVANT_GRADE}
    return {
        "P@5": precision_at_k(relevant, ranking, 5),
        "P@10": precision_at_k(relevant, ranking, 10),
        "NDCG@10": ndcg_at_k(grades, ranking, 10),
        "MRR": mrr(relevant, ranking),
    }


def mean_of(values: list[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def mean_metrics(per_applicant: list[dict[str, float | None]]) -> dict[str, float | None]:
    return {name: mean_of([m[name] for m in per_applicant]) for name in METRIC_NAMES}


def fmt(value: float | None) -> str:
    return f"{value:.4f}" if value is not None else "—"


# ---------------------------------------------------------------------------
# Smoke-fixture generation
# ---------------------------------------------------------------------------

def grade_from_status(status: str, n_gaps) -> int:
    """eligible=3, near_fit n_gaps=1 -> 2, n_gaps=2 -> 1, else 0."""
    if status == "eligible":
        return 3
    if status == "near_fit" and n_gaps == 1:
        return 2
    if status == "near_fit" and n_gaps == 2:
        return 1
    return 0


def make_smoke_fixture(conn) -> Path:
    """Sample 3 applicants and derive synthetic grades from eligibility_status."""
    with conn.cursor() as cur:
        # Deterministic sample: applicants whose candidate lists span the
        # grade spectrum (some eligible, some 1-gap, some 2-gap matches).
        cur.execute(
            """
            SELECT applicant_id FROM matches
            GROUP BY applicant_id
            HAVING count(*) FILTER (WHERE eligibility_status = 'eligible') >= 2
               AND count(*) FILTER (WHERE n_gaps = 1) >= 1
               AND count(*) FILTER (WHERE n_gaps = 2) >= 2
            ORDER BY applicant_id
            LIMIT 3
            """
        )
        applicant_ids = [str(r[0]) for r in cur.fetchall()]
        if len(applicant_ids) < 3:
            raise SystemExit(
                "ERROR: could not sample 3 applicants with mixed-eligibility "
                "candidate lists from the matches table."
            )
        cur.execute(
            "SELECT applicant_id, job_id, eligibility_status, n_gaps FROM matches "
            "WHERE applicant_id = ANY(%s::uuid[]) ORDER BY applicant_id, job_id",
            (applicant_ids,),
        )
        rows = cur.fetchall()

    SMOKE_LABELS.parent.mkdir(parents=True, exist_ok=True)
    with SMOKE_LABELS.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["applicant_id", "job_id", "grade"])
        for aid, jid, status, n_gaps in rows:
            writer.writerow([str(aid), str(jid), grade_from_status(status, n_gaps)])
    print(f"Wrote smoke fixture: {SMOKE_LABELS} ({len(rows)} labels, {len(applicant_ids)} applicants)")
    return SMOKE_LABELS


# ---------------------------------------------------------------------------
# Main evaluation
# ---------------------------------------------------------------------------

def evaluate(conn, labels_path: Path) -> str:
    labels = load_labels(labels_path)
    if not labels:
        raise SystemExit(f"ERROR: labels file {labels_path} contains no rows.")

    applicant_ids = sorted(labels.keys())
    popularity = fetch_popularity(conn)
    applicant_info = fetch_applicant_info(conn, applicant_ids)
    gap_tiers = fetch_label_gap_tiers(conn, labels)
    catalog_size = fetch_catalog_size(conn)

    per_ranker: dict[str, list[dict]] = defaultdict(list)
    production_rankings: list[list[str]] = []
    by_state: dict[str, list[dict]] = defaultdict(list)
    by_tier: dict[str, list[dict]] = defaultdict(list)
    skipped: list[str] = []

    for aid in applicant_ids:
        grades = labels[aid]
        production = fetch_candidates(conn, aid)
        if not production:
            skipped.append(aid)
            continue
        production_rankings.append(production)

        # (a) production order — straight from SQL
        prod_metrics = score_ranking(production, grades)
        per_ranker["production"].append(prod_metrics)

        # (b) random within the same candidate set, seeded, averaged over draws
        rng = random.Random(RANDOM_SEED)
        draws = []
        for _ in range(RANDOM_DRAWS):
            shuffled = production[:]
            rng.shuffle(shuffled)
            draws.append(score_ranking(shuffled, grades))
        per_ranker["random"].append(mean_metrics(draws))

        # (c) global popularity, ties by job_id
        by_pop = sorted(production, key=lambda j: (-popularity.get(j, 0), j))
        per_ranker["popularity"].append(score_ranking(by_pop, grades))

        # (d) BM25 over candidate job text, query = applicant text fields
        job_texts = fetch_job_texts(conn, production)
        corpus = [tokenize(job_texts.get(j, "")) for j in production]
        bm25 = BM25Okapi(corpus)
        query = tokenize(applicant_info.get(aid, {}).get("query_text", ""))
        per_ranker["bm25"].append(score_ranking(bm25.rank(query, production), grades))

        # Slices (production order)
        state = applicant_info.get(aid, {}).get("state", "unknown")
        by_state[state].append(prod_metrics)
        tier_grades: dict[str, dict[str, float]] = defaultdict(dict)
        for jid, grade in grades.items():
            tier_grades[gap_tiers.get((aid, jid), "unknown")][jid] = grade
        for tier, tg in tier_grades.items():
            by_tier[tier].append(score_ranking(production, tg))

    if not production_rankings:
        raise SystemExit(
            "ERROR: none of the labeled applicants have rows in the matches table."
        )

    coverage = catalog_coverage_at_k(production_rankings, catalog_size, 10)
    gini = gini_of_exposure(production_rankings, 10)

    # ---- report ----------------------------------------------------------
    lines: list[str] = []
    lines.append("# Matching Engine — Offline Evaluation")
    lines.append("")
    labels_display = labels_path.resolve()
    try:
        labels_display = labels_display.relative_to(REPO_ROOT.resolve())
    except ValueError:
        pass
    lines.append(f"- Labels file: `{labels_display}`")
    lines.append(f"- Applicants evaluated: {len(production_rankings)}"
                 + (f" (skipped {len(skipped)} with no matches rows)" if skipped else ""))
    lines.append(f"- Labeled pairs: {sum(len(v) for v in labels.values())}")
    lines.append(f"- Relevance: grade >= {RELEVANT_GRADE:g} is relevant; NDCG uses graded values")
    lines.append(f"- Random baseline: seed {RANDOM_SEED}, mean over {RANDOM_DRAWS} draws")
    lines.append("")
    lines.append("## Mean metrics per ranker")
    lines.append("")
    lines.append("| Ranker | " + " | ".join(METRIC_NAMES) + " |")
    lines.append("|---|" + "---|" * len(METRIC_NAMES))
    for ranker in ["production", "random", "popularity", "bm25"]:
        means = mean_metrics(per_ranker[ranker])
        lines.append(f"| {ranker} | " + " | ".join(fmt(means[n]) for n in METRIC_NAMES) + " |")
    lines.append("")
    lines.append("## Production order — by applicant state")
    lines.append("")
    lines.append("| State | n | " + " | ".join(METRIC_NAMES) + " |")
    lines.append("|---|---|" + "---|" * len(METRIC_NAMES))
    for state in sorted(by_state):
        means = mean_metrics(by_state[state])
        lines.append(f"| {state} | {len(by_state[state])} | "
                     + " | ".join(fmt(means[n]) for n in METRIC_NAMES) + " |")
    lines.append("")
    lines.append("## Production order — by n-gaps tier of labeled items")
    lines.append("")
    lines.append("Each row scores production order against only the labeled items in that tier.")
    lines.append("")
    lines.append("| n-gaps tier | applicants | " + " | ".join(METRIC_NAMES) + " |")
    lines.append("|---|---|" + "---|" * len(METRIC_NAMES))
    for tier in sorted(by_tier, key=lambda t: (t == "unknown", t)):
        means = mean_metrics(by_tier[tier])
        lines.append(f"| {tier} | {len(by_tier[tier])} | "
                     + " | ".join(fmt(means[n]) for n in METRIC_NAMES) + " |")
    lines.append("")
    lines.append("## Exposure (production order, top-10)")
    lines.append("")
    lines.append("| Catalog coverage@10 | Gini of exposure@10 | Catalog size (jobs table) |")
    lines.append("|---|---|---|")
    lines.append(f"| {fmt(coverage)} | {fmt(gini)} | {catalog_size} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS,
                        help=f"Graded labels CSV (default: {DEFAULT_LABELS.relative_to(REPO_ROOT)})")
    parser.add_argument("--out", type=Path, default=RESULTS_MD,
                        help=f"Markdown report path (default: {RESULTS_MD.relative_to(REPO_ROOT)})")
    parser.add_argument("--make-smoke", action="store_true",
                        help="Generate audit/golden/labels_smoke.csv from the DB and exit")
    args = parser.parse_args()

    from etl.db import get_connection
    conn = get_connection()
    try:
        if args.make_smoke:
            make_smoke_fixture(conn)
            return 0

        if not args.labels.exists():
            print(
                f"ERROR: labels file not found: {args.labels}\n\n"
                "The harness needs a graded labels CSV with columns "
                "applicant_id, job_id, grade (0-3).\n"
                "Produce labels there, or generate a synthetic smoke fixture:\n"
                "  python scripts/eval_harness.py --make-smoke\n"
                "  python scripts/eval_harness.py --labels audit/golden/labels_smoke.csv"
            )
            return 2

        report = evaluate(conn, args.labels)
        print(report)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report)
        print(f"Wrote {args.out}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
