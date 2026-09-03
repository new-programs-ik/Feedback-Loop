"""ratings_sync.py - one sync run, start to finish.

fetch (sheet or metabase) -> upsert all (the store applies rule v2 per row) -> notify newly-flagged
handlers.
Every run is recorded in sync_runs (the UI banner reads it); any failure marks the run failed
AND pings the PM Slack channel, so a silently-drifting sheet gets noticed the same hour.
"""
from __future__ import annotations

import logging

import notify as N
import ratings_source as RS
import ratings_store as ST

log = logging.getLogger("ratings_sync")


def run_sync(trigger: str = "manual", env: dict | None = None, source=None) -> dict:
    """Returns a summary dict (also written to sync_runs). Raises only if the DB is unreachable."""
    import os
    env = env if env is not None else dict(os.environ)

    conn = ST.connect()
    conn.autocommit = False
    cur = conn.cursor()

    if ST.running_run_exists(cur):
        conn.commit()
        conn.close()
        log.info("sync skipped - another run is in progress")
        return {"status": "skipped", "reason": "another sync is already running"}

    run_id = ST.start_run(cur, (source.name if source else env.get("RATINGS_SOURCE") or "sheet"), trigger)
    conn.commit()                                   # make the guard row visible immediately

    fetched = upserted = flagged = notified = 0
    unmapped: list[str] = []
    try:
        src = source or RS.build_source(env)
        rows = src.fetch_rows()
        fetched = len(rows)

        aliases = ST.load_aliases(cur)
        instructors = ST.load_instructor_ids(cur)
        for row in rows:
            course_id = aliases.get(row["course_label"])
            if course_id is None:
                unmapped.append(row["course_label"])
            _, dec, _status = ST.upsert_rating(
                cur, {**row, "source": src.name}, course_id, instructors.get(row["instructor"]))
            upserted += 1
            if dec in ("video", "transcript"):
                flagged += 1
        conn.commit()

        # Notifications: only rows that are flagged + new + have a handler + never pinged.
        if N.slack_configured(env):
            for pending in ST.rows_needing_notification(cur):
                if not pending.get("slack_user_id") and pending.get("handler_email"):
                    uid = N.lookup_user_id(pending["handler_email"], env)
                    if uid:
                        ST.cache_slack_user(cur, pending["handler_id"], uid)
                        pending["slack_user_id"] = uid
                if not ST.record_notification(cur, pending["id"],
                                              recipient=pending.get("handler_email") or ""):
                    continue                        # someone else already sent it
                ok, ts, err = N.post_flag_message(pending, env)
                if ok:
                    ST.mark_notified(cur, pending["id"])
                    cur.execute(
                        "update rating_notifications set slack_ts=%s where class_rating_id=%s and channel='slack'",
                        (ts, pending["id"]))
                    notified += 1
                else:
                    cur.execute(
                        "update rating_notifications set status='failed', error=%s "
                        "where class_rating_id=%s and channel='slack'", (err[:400], pending["id"]))
                conn.commit()

        ST.finish_run(cur, run_id, status="ok", rows_fetched=fetched, rows_upserted=upserted,
                      rows_flagged=flagged, notifications_sent=notified, unmapped_labels=unmapped)
        conn.commit()
        summary = {"status": "ok", "run_id": run_id, "rows_fetched": fetched,
                   "rows_upserted": upserted, "rows_flagged": flagged,
                   "notifications_sent": notified, "unmapped_labels": sorted(set(unmapped))}
        log.info("sync ok: %s", summary)
        return summary

    except Exception as e:
        conn.rollback()
        log.exception("ratings sync failed")
        try:
            ST.finish_run(cur, run_id, status="failed", rows_fetched=fetched,
                          rows_upserted=upserted, error=str(e)[:800])
            conn.commit()
        except Exception:
            conn.rollback()
        N.post_sync_alert(f":warning: Ratings sync FAILED ({trigger}): {str(e)[:300]}", env)
        return {"status": "failed", "run_id": run_id, "error": str(e)}
    finally:
        conn.close()
