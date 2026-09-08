"""One-off: repair class_ratings rows whose `topic` is a session-kind code ("Live Class",
"Test Review Session") — the Agentic tab's 'Topic' column bug — by looking the real class name up
in the workbook. Done IN PLACE so review state, overrides and analysis links survive; the natural
key (class_date, topic, instructor, session_kind) changes with the topic, so when the corrected key
already exists the kind-code duplicate is removed instead.

Run once after migration 0017 and before the first workbook re-sync. Safe to re-run.
"""
import datetime as dt
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "ratings_module_build_kit"))
import config  # noqa: E402
config.load_env()
import ratings_store  # noqa: E402
from ratings_data import load, KIND_CODES  # noqa: E402

LO, HI = dt.datetime(2026, 1, 1), dt.datetime(2026, 12, 31, 23, 59, 59)
KINDS = tuple(k.title() for k in KIND_CODES) + ("Live Class", "Test Review Session")


def key(date, instructor, kind, rating, responses, attended):
    return (date, instructor.strip(), kind, round(float(rating), 2), int(responses or 0), int(attended or 0))


def main():
    rows = load(LO, HI, strict=False)
    book = defaultdict(set)
    for r in rows:
        if r["topic"].lower() in KIND_CODES:
            continue
        book[key(r["date"].date(), r["instructor"], r["kind"], r["rating"], r["responses"], r["attended"])].add(r["topic"])

    conn = ratings_store.connect()
    cur = conn.cursor()
    cur.execute("""select id, class_date, instructor, session_kind, rating, num_ratings, attended, topic
                     from class_ratings where topic = any(%s)""", (list(KINDS),))
    bad = cur.fetchall()
    print("rows with a kind code as topic:", len(bad))
    fixed = merged = ambiguous = missing = 0
    for rid, d, instr, kind, rating, n, att, topic in bad:
        k = key(d, instr, kind, rating, n, att)
        names = book.get(k, set())
        if len(names) != 1:
            ambiguous += 1 if names else 0
            missing += 0 if names else 1
            continue
        name = next(iter(names))
        cur.execute("select id from class_ratings where class_date=%s and topic=%s and instructor=%s and session_kind=%s and id<>%s",
                    (d, name, instr, kind, rid))
        clash = cur.fetchone()
        if clash:
            # the corrected row already exists (a same-day repeat) - drop the kind-code duplicate
            cur.execute("delete from class_ratings where id=%s", (rid,))
            merged += 1
        else:
            cur.execute("update class_ratings set topic=%s, topic_id=null, updated_at=now() where id=%s", (name, rid))
            fixed += 1
    conn.commit()
    cur.execute("select count(*) from class_ratings where topic = any(%s)", (list(KINDS),))
    left = cur.fetchone()[0]
    print(f"fixed {fixed} · removed {merged} duplicates · ambiguous {ambiguous} · not in workbook {missing} · still kind-coded {left}")
    # re-link topics to the seeded topic table by normalised name where possible
    cur.execute("""update class_ratings cr set topic_id = t.id
                     from topics t
                    where cr.topic_id is null and cr.course_id = t.course_id
                      and public.normalize_topic_name(cr.topic) = t.name_norm""")
    print("topic ids linked:", cur.rowcount)
    conn.commit()


if __name__ == "__main__":
    main()
