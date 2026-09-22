"""test_worker_sql.py — the worker's SQL against the real database, with nothing written.

The worker's unit tests run without a database, so they can only check the *text* of a
statement. On 21 September 2026 a statement that read fine (`status = any(%s)`) was refused by
Postgres on every run (the column is an enum, the list arrives as text[]), and the worker
reported that refusal as "the database could not be reached" for a day. This check runs the
real functions against the real database inside one transaction that is always rolled back:
every statement is executed, nothing is kept.

Usage (from the repo root; DATABASE_URL comes from ratings_module_build_kit/.env):
  ./ratings_module_build_kit/.venv/Scripts/python supabase/test_worker_sql.py
"""
from __future__ import annotations

import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "ratings_module_build_kit"))

import config  # noqa: E402

config.load_env(os.path.join(ROOT, "ratings_module_build_kit", ".env"))

import psycopg2  # noqa: E402

import ratings_store as RST  # noqa: E402
import store as ST  # noqa: E402


class NoCommit:
    """The worker's functions open a connection and commit; here they get this instead, so
    every statement runs on the one transaction that is rolled back at the end."""

    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return self._conn.cursor()

    def commit(self):
        pass

    def rollback(self):
        self._conn.rollback()

    def close(self):
        pass


def main() -> int:
    url = os.environ.get("DATABASE_URL", "").replace("postgresql+psycopg2://", "postgresql://")
    if not url:
        raise SystemExit("DATABASE_URL not set (env or ratings_module_build_kit/.env)")
    conn = psycopg2.connect(url, connect_timeout=15)
    conn.autocommit = False
    ST._connect = lambda *a, **k: NoCommit(conn)   # type: ignore[assignment]
    cur = conn.cursor()
    failures = 0
    checks = 0

    def check(name, fn):
        nonlocal failures, checks
        checks += 1
        cur.execute("savepoint c")
        try:
            out = fn()
            print(f"  ok   {name}" + (f"  -> {out}" if out is not None else ""))
        except Exception as e:  # noqa: BLE001 - report and carry on
            failures += 1
            first = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
            print(f"  FAIL {name}: {first[:200]}")
            if "-v" in sys.argv:
                traceback.print_exc()
            cur.execute("rollback to savepoint c")
        else:
            cur.execute("release savepoint c")

    try:
        cur.execute("select id from courses order by name limit 1")
        course = cur.fetchone()
        if not course:
            raise SystemExit("no course in the database; nothing to check against")
        cur.execute(
            "insert into classes(course_id, topic, class_date, session_type, rating, vimeo_link, status) "
            "values (%s, 'sql check (rolled back)', current_date, 'live_class', 4.5, 'https://vimeo.com/0', 'scheduled') "
            "returning id::text", (course[0],))
        cid = cur.fetchone()[0]
        print(f"temporary class {cid[:8]}… inside a transaction that is rolled back at the end")

        def claim_then_refuse():
            first = ST.claim_for_analysis(cid)
            second = ST.claim_for_analysis(cid)
            assert first is True and second is False, (first, second)
            cur.execute("select status::text from classes where id=%s", (cid,))
            assert cur.fetchone()[0] == "analyzing"
            return "claimed once, refused the second time"

        check("claim_for_analysis (scheduled -> analyzing, then refused)", claim_then_refuse)

        def requeue():
            n = ST.requeue_running([cid])
            assert n == 1, n
            cur.execute("select status::text from classes where id=%s", (cid,))
            assert cur.fetchone()[0] == "scheduled"
            return "analyzing -> scheduled, audit row written"

        check("requeue_running (a stopping worker)", requeue)

        def resume_rows():
            cur.execute("update classes set updated_at = now() - interval '2 minutes' where id=%s", (cid,))
            rows = ST.scheduled_to_resume(min_age_s=60, limit=50)
            ids = [r["class_id"] for r in rows]
            assert cid in ids, ids
            row = next(r for r in rows if r["class_id"] == cid)
            assert set(row) == set(ST.RESUME_COLUMNS), row.keys()
            return f"{len(rows)} queued class(es) found, ours among them"

        check("scheduled_to_resume (queued classes the worker picks up)", resume_rows)
        check("record_resume (audit line)", lambda: ST.record_resume(cid))

        def fail_it():
            assert ST.claim_for_analysis(cid) is True
            ST.mark_failed(cid, "sql check", cost_usd=0.01)
            cur.execute("select status::text from classes where id=%s", (cid,))
            assert cur.fetchone()[0] == "failed"
            return "analyzing -> failed, audit row written"

        check("mark_failed (a job that raised)", fail_it)
        check("claim_for_analysis (failed -> analyzing again)", lambda: ST.claim_for_analysis(cid) and "claimed")
        check("reset_stuck_analyses (the sweep)", lambda: RST.reset_stuck_analyses(cur))
        check("consume_sync_token (unknown token refused)", lambda: ST.consume_sync_token("ab" * 32) is False and "refused")

        cur.execute("select id::text from class_ratings order by class_date desc limit 1")
        cr = cur.fetchone()
        if cr:
            check("rows_needing_notification", lambda: len(RST.rows_needing_notification(cur, max_age_days=10, limit=5)))
            check("record_notification (the claim) + finish_notification",
                  lambda: (RST.record_notification(cur, cr[0], recipient="sql check"),
                           RST.finish_notification(cur, cr[0], ok=False, error="sql check"))[0])
        check("mark_stale_runs / running_run_exists (the sync's guard)",
              lambda: (RST.mark_stale_runs(cur), RST.running_run_exists(cur))[1])
    finally:
        conn.rollback()
        conn.close()

    print(f"{checks - failures} of {checks} checks passed; nothing was written")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
