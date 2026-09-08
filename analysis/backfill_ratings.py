"""One-off local backfill: the static ratings workbook -> class_ratings (Jan 1 - Aug 31 2026).

Uses the SAME store + decision code the hourly sync will use, so what the pages show now is
exactly what the live sync will produce. Idempotent - rerunning just refreshes the rows.

Rows go in date order (ratings_data.load sorts them): the store reads each instructor's track
record from their EARLIER rows in the table, so on a fresh table the order is what makes that
record exist. The Yes/No vote flows through as yes_votes/no_votes; the store turns it into
approval_pct and the rule v2 read-out (health_score, health_band, flag_reasons).
"""
import datetime as dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "ratings_module_build_kit"))

import config  # noqa: E402  (ratings_module_build_kit/config.py - loads .env for DATABASE_URL)

config.load_env(os.path.join(ROOT, "ratings_module_build_kit", ".env"))

import ratings_store as ST  # noqa: E402
from ratings_data import load  # noqa: E402

rows = load(dt.datetime(2026, 1, 1), dt.datetime(2026, 8, 31, 23, 59, 59))
print(f"workbook rows: {len(rows)}")

conn = ST.connect()
cur = conn.cursor()
run_id = ST.start_run(cur, "sheet", "backfill")
aliases = ST.load_aliases(cur)
instructors = ST.load_instructor_ids(cur)

upserted = flagged = 0
unmapped: list[str] = []
for r in rows:
    canonical = {
        "source": "sheet",
        "course_label": r["course"],
        "cohort_text": r.get("cohort_text") or "",
        "topic": r["topic"],
        "instructor": r["instructor"],
        "class_date": r["date"].date(),
        "session_kind": r["kind"],
        "rating": round(float(r["rating"]), 2),
        "num_ratings": int(r["responses"]) if r.get("responses") is not None else None,
        "attended": int(r["attended"]) if r.get("attended") else None,
        "yes_votes": int(r["yes"]) if r.get("yes") is not None else None,
        "no_votes": int(r["no"]) if r.get("no") is not None else None,
    }
    course_id = aliases.get(canonical["course_label"])
    if course_id is None:
        unmapped.append(canonical["course_label"])
    _, dec, _ = ST.upsert_rating(cur, canonical, course_id,
                                 instructors.get(canonical["instructor"]))
    upserted += 1
    if dec in ("video", "transcript"):
        flagged += 1

ST.finish_run(cur, run_id, status="ok", rows_fetched=len(rows), rows_upserted=upserted,
              rows_flagged=flagged, unmapped_labels=unmapped)
conn.commit()

# Verification - the Instructor-Approval study's Jan-Aug numbers are the reference
# (decision none 2232 / watch 109 / video 192 / transcript 247; bands urgent 81 / look 125 /
# borderline 233 on 2,780 workbook rows; the table holds a few fewer after natural-key merges).
cur.execute("select decision, count(*) from class_ratings group by decision order by 2 desc")
print("by decision:", cur.fetchall())
cur.execute("select health_band, count(*) from class_ratings group by health_band order by 2 desc")
print("by band:", cur.fetchall())
cur.execute("select count(*) filter (where approval_pct is not null), "
            "count(*) filter (where track_avg is not null), "
            "count(*) filter (where health_score is not null) from class_ratings")
print("rows with approval / track record / health score:", cur.fetchone())
cur.execute("select count(*) from class_ratings where course_id is null")
print("unmapped rows:", cur.fetchone()[0])
cur.execute("select count(*) from class_ratings")
print("total in table:", cur.fetchone()[0])
conn.close()
