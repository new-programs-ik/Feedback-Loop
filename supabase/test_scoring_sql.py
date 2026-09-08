"""test_scoring_sql.py — the database scoring function against the shared fixture.

Runs every case in supabase/fixtures/scoring_cases.json through public.score_class_rating()
(migration 0015) and compares score (2 dp), band, action, provisional and the flags AS A SET
with what the reference scorer (analysis/sentiment_score.py) produced. Any mismatch fails.

Usage (from the repo root; DATABASE_URL comes from ratings_module_build_kit/.env):
  ./ratings_module_build_kit/.venv/Scripts/python supabase/test_scoring_sql.py
  ...                                              supabase/test_scoring_sql.py -q   # failures only
"""
from __future__ import annotations

import json
import os
import sys
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "ratings_module_build_kit"))

import config  # noqa: E402  (ratings_module_build_kit/config.py — loads .env for DATABASE_URL)

config.load_env(os.path.join(ROOT, "ratings_module_build_kit", ".env"))

import psycopg2  # noqa: E402

CASES = os.path.join(HERE, "fixtures", "scoring_cases.json")
CONFIGS = os.path.join(HERE, "fixtures", "scoring_configs.json")

SQL = """
select score, band, action, provisional, flags
from public.score_class_rating(
  %(rating)s::numeric, %(num_ratings)s::int, %(attended)s::int, %(yes_votes)s::int, %(no_votes)s::int,
  %(escalated)s::boolean, %(track_avg)s::numeric, %(prior_rating)s::numeric, %(prior_approval)s::numeric,
  %(config)s::jsonb)
"""


def connect():
    url = os.environ.get("DATABASE_URL", "").replace("postgresql+psycopg2://", "postgresql://")
    if not url:
        raise SystemExit("DATABASE_URL not set (env or ratings_module_build_kit/.env)")
    return psycopg2.connect(url, connect_timeout=15)


def _dec(v):
    """Fixture scores are floats printed at 2 dp; compare as exact decimals."""
    return None if v is None else Decimal(str(v)).quantize(Decimal("0.01"))


def _int(v):
    if v is None:
        return None
    f = float(v)
    return int(f) if f == int(f) else f


def run_cases(cur, verbose: bool = True) -> tuple[int, int]:
    """Runs every fixture case on an open cursor. Returns (passed, failed)."""
    fixture = json.load(open(CASES, encoding="utf-8"))
    configs = json.load(open(CONFIGS, encoding="utf-8"))
    passed = failed = 0
    for case in fixture["cases"]:
        inp = case["inputs"]
        params = {
            "rating": inp.get("rating"),
            "num_ratings": _int(inp.get("num_ratings")),
            "attended": _int(inp.get("attended")),
            "yes_votes": _int(inp.get("yes_votes")),
            "no_votes": _int(inp.get("no_votes")),
            "escalated": inp.get("escalated"),
            "track_avg": inp.get("track_avg"),
            "prior_rating": inp.get("prior_rating"),
            "prior_approval": inp.get("prior_approval"),
            "config": json.dumps(configs[case["config"]]),
        }
        cur.execute(SQL, params)
        score, band, action, provisional, flags = cur.fetchone()
        exp = case["expected"]
        got = {"score": _dec(score), "band": band, "action": action,
               "provisional": bool(provisional), "flags": set(flags or [])}
        want = {"score": _dec(exp["score"]), "band": exp["band"], "action": exp["action"],
                "provisional": bool(exp["provisional"]), "flags": set(exp["flags"])}
        diffs = [k for k in want if got[k] != want[k]]
        if diffs:
            failed += 1
            print(f"FAIL {case['id']:8} {case['label']}")
            for k in diffs:
                print(f"       {k}: expected {want[k]!r}, got {got[k]!r}")
        else:
            passed += 1
            if verbose:
                s = "-" if got["score"] is None else f"{got['score']}"
                print(f"ok   {case['id']:8} {s:>7} {str(band):9} {action:10} "
                      f"{'prov' if provisional else '    '} {case['label']}")
    return passed, failed


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    verbose = "-q" not in argv
    conn = connect()
    try:
        with conn.cursor() as cur:
            passed, failed = run_cases(cur, verbose=verbose)
    finally:
        conn.rollback()
        conn.close()
    total = passed + failed
    print(f"\n{passed}/{total} cases pass" + (f" — {failed} FAILED" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
