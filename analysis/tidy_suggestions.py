"""Tidy the pending duplicate-name suggestions after a sync or a seeding run.

Two spellings of one person can be suggested in both directions (the sync matched the full name
against a thin first-name record; the study matched the first name against the full name). Only
one can be accepted, and the survivor should be the FULLER name - "Shreyansh" into "Shreyansh
Khanna", never the reverse. For every mirrored pair this keeps the direction whose target has the
fuller name, carries the higher confidence across (the lower one when either side carries a
same-day warning - two different classes on one day may mean two people), and drops the mirror.
Scores above 1.0 (a bonus stacked on a high rule) are capped at 0.99.

    python analysis/tidy_suggestions.py --dry-run
    python analysis/tidy_suggestions.py --apply
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "ratings_module_build_kit"))
import config  # noqa: E402

config.load_env()
import ratings_store as ST  # noqa: E402

PAIRS = """
with p as (
  select s.id, s.raw_name, s.raw_norm, s.score, s.method, s.candidate_instructor_id cand,
         ci.name cand_name, ci.normalized_name cand_norm, ri.id raw_record
    from instructor_match_suggestions s
    join instructors ci on ci.id = s.candidate_instructor_id
    left join instructors ri on ri.normalized_name = s.raw_norm and ri.merged_into is null
   where s.status = 'pending')
select a.id, a.raw_name, a.cand_name, a.score, a.method,
       b.id, b.raw_name, b.cand_name, b.score, b.method
  from p a join p b on b.raw_norm = a.cand_norm and b.cand = a.raw_record and a.id < b.id
 order by a.raw_name"""


def fullness(name: str) -> tuple[int, int]:
    return (len(name.split()), len(name))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    conn = ST.connect()
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute(PAIRS)
    pairs = cur.fetchall()
    print(f"mirrored pairs: {len(pairs)}")
    for a_id, a_raw, a_cand, a_score, a_method, b_id, b_raw, b_cand, b_score, b_method in pairs:
        # keep the suggestion whose TARGET is the fuller name
        keep, drop = ((a_id, a_raw, a_cand, a_score, a_method), (b_id, b_raw, b_cand, b_score, b_method)) \
            if fullness(a_cand) >= fullness(b_cand) else \
            ((b_id, b_raw, b_cand, b_score, b_method), (a_id, a_raw, a_cand, a_score, a_method))
        warned = "same_day" in (a_method or "") or "same_day" in (b_method or "")
        score = min(a_score, b_score) if warned else max(a_score, b_score)
        score = min(score, 0.99)
        print(f"  keep {keep[1]!r:<24} -> {keep[2]!r:<26} {float(score):.2f}"
              f"{'  (same-day warning kept)' if warned else ''}   drop {drop[1]!r} -> {drop[2]!r}")
        if args.apply:
            cur.execute("""update instructor_match_suggestions
                              set score = %s, evidence = coalesce(evidence, '{}'::jsonb) || %s::jsonb, last_seen_at = now()
                            where id = %s""",
                        (score, '{"mirror_dropped": "%s -> %s (%s)"%s}' % (
                            drop[1].replace('"', ""), drop[2].replace('"', ""), drop[4],
                            ', "same_day_warning": true' if warned else ""), keep[0]))
            cur.execute("delete from instructor_match_suggestions where id = %s", (drop[0],))
    cur.execute("select count(*) from instructor_match_suggestions where score > 0.99")
    over = cur.fetchone()[0]
    print(f"scores above 0.99: {over}")
    if args.apply:
        cur.execute("update instructor_match_suggestions set score = 0.99 where score > 0.99")
        conn.commit()
        cur.execute("select status, count(*) from instructor_match_suggestions group by 1")
        print("after:", dict(cur.fetchall()))
    else:
        conn.rollback()
    conn.close()


if __name__ == "__main__":
    main()
