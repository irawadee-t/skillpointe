"""Give the demo applicant pool a realistic spread on the fields the matching
engine actually gates on.

The seeded pool was uniform: no years of experience on file, 3 of 346 willing
to relocate. A uniform population cannot demonstrate that the engine
discriminates, because every applicant hits the same gates the same way.

Assignment is DETERMINISTIC -- each value is derived from an md5 of the
applicant's id, so reruns produce identical data and the deterministic engine
stays reproducible. This is demo/test data only; it never runs against real
applicant records (guarded on the demo email domain).
"""
import argparse
import os
import sys
from pathlib import Path

import psycopg2

for _p in Path(__file__).resolve().parents:
    if (_p / "apps").is_dir():
        sys.path.insert(0, str(_p / "apps" / "api"))
        break

# Demo/seed pools only. Real applicant records must never be rewritten, so
# every statement is scoped to these domains.
DEMO_DOMAINS = ("%@skillednation-demo.test", "%@scholarship-import.local")

# (bucket upper bound as a fraction of the hash space, SQL expression)
# Modelled on a trade-school intake: mostly early-career, a real tail of
# career-changers, and a chunk with nothing on file yet -- NULL is a
# first-class outcome because "not on file" is the honest default.
UPDATE_SQL = """
WITH h AS (
    SELECT id,
           MOD(('x' || substr(md5(id::text || ':exp'), 1, 8))::bit(32)::bigint, 100) AS r_exp,
           MOD(('x' || substr(md5(id::text || ':rel'), 1, 8))::bit(32)::bigint, 100) AS r_rel
      FROM public.applicants
     WHERE email LIKE ANY(%s)
)
UPDATE public.applicants a
   SET years_experience = CASE
           WHEN h.r_exp < 28 THEN NULL                        -- 28 pct: not on file
           WHEN h.r_exp < 60 THEN MOD(h.r_exp, 2)             -- 32 pct: 0-1 yrs
           WHEN h.r_exp < 80 THEN 2 + MOD(h.r_exp, 3)         -- 20 pct: 2-4 yrs
           WHEN h.r_exp < 93 THEN 5 + MOD(h.r_exp, 5)         -- 13 pct: 5-9 yrs
           ELSE 10 + MOD(h.r_exp, 8)                          --  7 pct: 10-17 yrs
       END,
       willing_to_relocate = (h.r_rel < 38)                   -- 38 pct mobile
  FROM h
 WHERE a.id = h.id
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    dsn = os.environ.get("DATABASE_URL") or "postgresql://postgres:postgres@localhost:54322/postgres"
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    with conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM public.applicants WHERE email LIKE ANY(%s)", (list(DEMO_DOMAINS),))
        n = cur.fetchone()[0]
        if n == 0:
            print("No demo applicants found; nothing to do.")
            return 0
        print(f"Demo applicants in scope: {n}")
        if args.dry_run:
            print("Dry run, no writes.")
            conn.rollback()
            return 0
        cur.execute(UPDATE_SQL, (list(DEMO_DOMAINS),))
        print(f"Updated {cur.rowcount} rows.")
        cur.execute(
            """SELECT CASE WHEN years_experience IS NULL THEN 'not on file'
                           WHEN years_experience <= 1 THEN '0-1'
                           WHEN years_experience <= 4 THEN '2-4'
                           WHEN years_experience <= 9 THEN '5-9'
                           ELSE '10+' END AS bucket, count(*)
                 FROM public.applicants WHERE email LIKE ANY(%s)
             GROUP BY 1 ORDER BY 2 DESC""",
            (list(DEMO_DOMAINS),),
        )
        print("\n  years_experience distribution")
        for bucket, ct in cur.fetchall():
            print(f"    {bucket:12} {ct:4}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
