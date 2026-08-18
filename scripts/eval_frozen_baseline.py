"""Score the FROZEN baseline ranking snapshot against the golden labels.

The live matches table mutates on every recompute; before/after comparisons
are only honest when "before" comes from the versioned snapshot taken ahead
of any change (audit/baseline/<sha>/rankings_full.csv). This computes the
same metrics as scripts/eval_harness.py on that frozen order.

Usage: python scripts/eval_frozen_baseline.py [--baseline audit/baseline/295f107]
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packages"))

from matching.eval_metrics import (  # noqa: E402
    mrr,
    ndcg_at_k,
    precision_at_k,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", default="audit/baseline/295f107")
    ap.add_argument("--labels", default="audit/golden/labels.csv")
    args = ap.parse_args()

    labels: dict[str, dict[str, float]] = {}
    for r in csv.DictReader(open(REPO / args.labels)):
        labels.setdefault(r["applicant_id"], {})[r["job_id"]] = float(r["grade"])

    ranked: dict[str, list[tuple[int, str]]] = {}
    for r in csv.DictReader(open(REPO / args.baseline / "rankings_full.csv")):
        ranked.setdefault(r["applicant_id"], []).append((int(r["rank"]), r["job_id"]))

    rows = []
    for app_id, grades in sorted(labels.items()):
        order = [j for _, j in sorted(ranked.get(app_id, []))]
        if not order:
            continue
        relevant = {j for j, g in grades.items() if g >= 2}
        rows.append((
            precision_at_k(relevant, order, 5),
            precision_at_k(relevant, order, 10),
            ndcg_at_k(grades, order, 10),
            mrr(relevant, order),
        ))

    n = len(rows)
    if not n:
        print("no overlap between labels and baseline snapshot")
        return 1

    def col(i):
        vals = [r[i] for r in rows if r[i] is not None]
        return sum(vals) / len(vals) if vals else float("nan")

    print(f"FROZEN BASELINE ({args.baseline}) vs golden labels — {n} applicants")
    print("| Ranker | P@5 | P@10 | NDCG@10 | MRR |")
    print("|---|---|---|---|---|")
    print(f"| baseline production | {col(0):.4f} | {col(1):.4f} | {col(2):.4f} | {col(3):.4f} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
