"""ratings_sync.py - one sync run, start to finish.

fetch the sheet
  -> per row: parse cohorts -> upsert cohorts -> resolve the instructor (aliases, exact spelling)
     -> resolve the topic -> upsert the class row (the DATABASE scores it in the same statement)
     -> tally bands
  -> after the loop: duplicate-name suggestions for unresolved instructors, topics for class
     names the topic table did not know, Slack cards to the course's people, metrics into
     sync_runs, a best-effort ${UI_URL}/api/revalidate ping.

Every run is recorded in sync_runs (the UI banner reads it); any failure marks the run failed AND
pings the PM Slack channel, so a silently-drifting sheet gets noticed the same hour. Parsers never
stop a run: what they cannot parse or resolve is counted and listed in the summary.
"""
from __future__ import annotations

import logging
import os
import time
from collections import Counter, defaultdict

import httpx

import cohort_parse as CP
import course_rules as CR
import decision as D
import instructor_match as IM
import notify as N
import ratings_source as RS
import ratings_store as ST

log = logging.getLogger("ratings_sync")

# Slack guard rails: the sheet is the whole history, so without these the first run after a
# handler is assigned would post one card per historical flagged class.
NOTIFY_MAX_AGE_DAYS = 10
NOTIFY_MAX_PER_RUN = 25


def _int_env(env: dict, key: str, default: int) -> int:
    try:
        return int(env.get(key) or default)
    except (TypeError, ValueError):
        return default


def ping_revalidate(env: dict, run_id: str, summary: dict | None = None,
                    transport: httpx.BaseTransport | None = None) -> bool:
    """POST ${UI_URL}/api/revalidate (bearer WORKER_API_KEY) so the web app drops its caches.
    Best-effort: failures are logged and ignored."""
    ui = (env.get("UI_URL") or "").rstrip("/")
    if not ui:
        return False
    headers = {}
    if env.get("WORKER_API_KEY"):
        headers["Authorization"] = f"Bearer {env['WORKER_API_KEY']}"
    try:
        with httpx.Client(timeout=10, transport=transport) as client:
            r = client.post(f"{ui}/api/revalidate", headers=headers,
                            json={"reason": "ratings-sync", "run_id": run_id,
                                  "rows_upserted": (summary or {}).get("rows_upserted")})
        ok = r.status_code < 400
        (log.info if ok else log.warning)("revalidate ping -> %s", r.status_code)
        return ok
    except Exception:
        log.warning("revalidate ping failed", exc_info=True)
        return False


def run_sync(trigger: str = "manual", env: dict | None = None, source=None, full: bool = False) -> dict:
    """Returns a summary dict (also written to sync_runs). Raises only if the DB is unreachable.

    Rows whose sheet values have not changed since the last run are skipped (see
    ST.row_fingerprint); `full=True` or RATINGS_SYNC_FULL=1 pushes every row through anyway.
    """
    env = env if env is not None else dict(os.environ)
    t0 = time.monotonic()
    full = full or (env.get("RATINGS_SYNC_FULL") or "").strip().lower() in ("1", "true", "yes")

    conn = ST.connect()
    conn.autocommit = False
    cur = conn.cursor()

    # A run that died with the worker (restart, redeploy) would otherwise show as running forever.
    try:
        stale = ST.mark_stale_runs(cur)
        if stale:
            log.warning("marked %d earlier sync run(s) as failed: the worker died mid-run", stale)
            conn.commit()
    except Exception:
        conn.rollback()
        log.exception("could not mark stale sync runs; continuing")

    if ST.running_run_exists(cur):
        conn.commit()
        conn.close()
        log.info("sync skipped - another run is in progress")
        return {"status": "skipped", "reason": "another sync is already running"}

    # An analysis runs inside the worker process. If that process is restarted or killed mid-job no
    # exception is ever raised, so the class sits on "analyzing" forever and only a manual Retry
    # gets it back. The hourly sync is the one thing that reliably runs, so it does the sweeping.
    try:
        released = ST.reset_stuck_analyses(cur)
        if released:
            log.warning("released %d class(es) stuck mid-analysis", released)
            conn.commit()
    except Exception:
        conn.rollback()
        log.exception("could not sweep classes stuck mid-analysis; continuing with the sync")

    src_name = source.name if source else (env.get("RATINGS_SOURCE") or "sheet")
    run_id = ST.start_run(cur, src_name, trigger)
    conn.commit()                                   # make the guard row visible immediately

    fetched = upserted = scored = flagged = notified = unchanged = retired = 0
    seen_keys: set = set()
    unmapped: list[str] = []
    bands: Counter = Counter()
    stats: Counter = Counter()
    unparsed: Counter = Counter()
    unresolved: Counter = Counter()
    topics_unmapped: Counter = Counter()
    suggestions_created = 0
    config_version = None
    try:
        src = source or RS.build_source(env)
        rows = src.fetch_rows()
        fetched = len(rows)

        cfg = ST.active_scoring_config(cur)
        if not cfg:
            raise RuntimeError("no active scoring config - activate a scoring version (Admin > Scoring) "
                               "before syncing")
        config_version = cfg.get("version")
        track_cfg = (cfg.get("config") or {}).get("track") or {}
        min_track = int(track_cfg.get("min_classes") or D.T_MIN_CLASSES)

        aliases = ST.load_aliases(cur)
        courses = ST.load_courses(cur)
        resolver = ST.load_instructor_resolver(cur)
        # What is already stored, keyed like the upsert, so unchanged rows cost nothing.
        state = {} if full else ST.load_row_state(cur)
        cohort_cache: dict = {}
        topic_cache: dict = {}
        context: dict = defaultdict(list)           # name / instructor id -> classes (for suggestions)

        # Oldest first: a cohort's week numbers count from the first class seen for it.
        for row in sorted(rows, key=lambda r: r["class_date"]):
            course_id = aliases.get(row["course_label"])
            if course_id is None:
                unmapped.append(row["course_label"])

            report = CP.parse_cohorts_report(row.get("cohort_text") or "", CR.course_of,
                                             region=row.get("region"))
            for seg in report.unparsed:
                unparsed[seg] += 1
            instructor_id, canonical = resolver(row["instructor"])
            if row["instructor"] and instructor_id is None:
                unresolved[row["instructor"]] += 1
            ref = IM.ClassRef(course_id, row["class_date"], row["topic"], row["session_kind"])
            context[IM.normalize(row["instructor"])].append(ref)
            if instructor_id:
                context[instructor_id].append(ref)

            seen_keys.add(ST.row_key(row))
            # Nothing about this class changed on the sheet: keep its stored verdict in the totals
            # and move on without touching the database.
            known = state.get(ST.row_key(row))
            if known is not None and known[0] == ST.row_fingerprint(row):
                _, band, action, was_scored = known
                unchanged += 1
                bands[band or "no_band"] += 1
                if was_scored:
                    scored += 1
                if action in ("video", "transcript"):
                    flagged += 1
                continue

            cohort_ids = [c for c in ST.upsert_cohorts(cur, report.cohorts, course_id, aliases=aliases,
                                                       courses=courses, cache=cohort_cache,
                                                       stats=stats, source=src.name) if c]
            topic_id = ST.resolve_topic(cur, course_id, row["topic"], cache=topic_cache,
                                        unmapped=topics_unmapped)

            res = ST.upsert_rating(cur, {**row, "source": src.name}, course_id, instructor_id,
                                   instructor_canonical=canonical, cohort_ids=cohort_ids,
                                   topic_id=topic_id, min_track_classes=min_track)
            upserted += 1
            if res.score is not None:
                scored += 1
            bands[res.band or "no_band"] += 1
            if res.decision in ("video", "transcript"):
                flagged += 1
        conn.commit()

        # Rows the sheet no longer has (a corrected spelling makes a new row) go, unless someone
        # acted on them. Only when the sheet actually answered: an empty fetch must not empty the table.
        if fetched:
            retired = ST.retire_rows_missing_from_sheet(cur, seen_keys, src.name)
            if retired:
                log.warning("removed %d row(s) the sheet no longer has", retired)
            conn.commit()

        # Duplicate-name suggestions for the spellings nobody resolved (a human accepts them).
        if unresolved:
            suggestions = IM.suggest(list(unresolved), resolver.candidates(), context)
            suggestions_created = ST.write_suggestions(cur, suggestions)
            conn.commit()

        # Class names the topic table did not know become topics (the seed's own rule), so the
        # module pages never wait on a manual re-seed after the Class-column fix.
        topic_stats = ST.ensure_topics(cur, topics_unmapped) if topics_unmapped else {}
        conn.commit()

        # Notifications: flagged + new + never pinged, recent only, capped per run.
        if N.slack_configured(env):
            pending_rows = ST.rows_needing_notification(
                cur, max_age_days=_int_env(env, "NOTIFY_MAX_AGE_DAYS", NOTIFY_MAX_AGE_DAYS),
                limit=_int_env(env, "NOTIFY_MAX_PER_RUN", NOTIFY_MAX_PER_RUN))
            for pending in pending_rows:
                for person in pending.get("recipients") or []:
                    if not person.get("slack_user_id") and person.get("email"):
                        uid = N.lookup_user_id(person["email"], env)
                        if uid:
                            person["slack_user_id"] = uid
                            if person.get("source") == "handler":
                                ST.cache_slack_user(cur, person["id"], uid)
                            else:
                                ST.cache_member_slack_user(cur, person["id"], uid)
                recipient = ", ".join(p.get("email") or p.get("name") or "" for p in pending.get("recipients") or [])
                if not ST.record_notification(cur, pending["id"], recipient=recipient or "channel (no owner)"):
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

        duration_ms = int((time.monotonic() - t0) * 1000)
        log.info("sync: %d rows from the sheet, %d written, %d unchanged, %d retired, %.1fs",
                 fetched, upserted, unchanged, retired, duration_ms / 1000)
        ST.finish_run(cur, run_id, status="ok", rows_fetched=fetched, rows_upserted=upserted,
                      rows_flagged=flagged, notifications_sent=notified, unmapped_labels=unmapped,
                      rows_scored=scored, scoring_config_version=config_version,
                      band_counts=dict(bands), cohorts_created=stats["cohorts_created"],
                      cohorts_unparsed=sum(unparsed.values()), instructors_unresolved=len(unresolved),
                      suggestions_created=suggestions_created, topics_unmapped=len(topics_unmapped),
                      duration_ms=duration_ms, rows_unchanged=unchanged)
        conn.commit()
        ST.remember_config_version(config_version)

        summary = {
            "status": "ok", "run_id": run_id, "rows_fetched": fetched, "rows_upserted": upserted,
            "rows_unchanged": unchanged, "rows_retired": retired,
            "rows_scored": scored, "rows_flagged": flagged, "notifications_sent": notified,
            "unmapped_labels": sorted(set(unmapped)), "scoring_config_version": config_version,
            "band_counts": dict(bands), "cohorts_created": stats["cohorts_created"],
            "cohorts_unparsed": sum(unparsed.values()),
            "unparsed_segments": [s for s, _ in unparsed.most_common(50)],
            "instructors_unresolved": len(unresolved),
            "unresolved_names": [n for n, _ in unresolved.most_common(100)],
            "suggestions_created": suggestions_created,
            "topics_unmapped": len(topics_unmapped),
            "unmapped_topics": [t for (_, t), _ in topics_unmapped.most_common(50)],
            "topics_created": topic_stats.get("topics_created", 0),
            "topic_rows_backfilled": topic_stats.get("rows_backfilled", 0),
            "duration_ms": duration_ms,
        }
        log.info("sync ok: %s", {k: v for k, v in summary.items()
                                 if k not in ("unresolved_names", "unparsed_segments", "unmapped_topics")})
        ping_revalidate(env, run_id, summary)
        return summary

    except Exception as e:
        conn.rollback()
        log.exception("ratings sync failed")
        try:
            ST.finish_run(cur, run_id, status="failed", rows_fetched=fetched,
                          rows_upserted=upserted, error=str(e)[:800],
                          scoring_config_version=config_version,
                          duration_ms=int((time.monotonic() - t0) * 1000))
            conn.commit()
        except Exception:
            conn.rollback()
        N.post_sync_alert(f":warning: Ratings sync FAILED ({trigger}): {str(e)[:300]}", env)
        return {"status": "failed", "run_id": run_id, "error": str(e)}
    finally:
        conn.close()
