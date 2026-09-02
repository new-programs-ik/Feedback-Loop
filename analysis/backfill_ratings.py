"""One-off local backfill: the static ratings workbook -> class_ratings (Jan 1 - Aug 31 2026).

Uses the SAME store + decision code the hourly sync will use, so what the pages show now is
exactly what the live sync will produce. Idempotent - rerunning just refreshes the rows.
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

import decision as D  # noqa: E402
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
    }
    course_id = aliases.get(canonical["course_label"])
    if course_id is None:
        unmapped.append(canonical["course_label"])
    verdict = D.decide(canonical["rating"], canonical["num_ratings"], canonical["attended"])
    _, dec, _ = ST.upsert_rating(cur, canonical, verdict, course_id,
                                 instructors.get(canonical["instructor"]))
    upserted += 1
    if dec in ("video", "transcript"):
        flagged += 1

ST.finish_run(cur, run_id, status="ok", rows_fetched=len(rows), rows_upserted=upserted,
              rows_flagged=flagged, unmapped_labels=unmapped)
conn.commit()

cur.execute("select decision, count(*) from class_ratings group by decision order by 2 desc")
print("by decision:", cur.fetchall())
cur.execute("select count(*) from class_ratings where course_id is null")
print("unmapped rows:", cur.fetchone()[0])
cur.execute("select count(*) from class_ratings")
print("total in table:", cur.fetchone()[0])
conn.close()
