"""
store.py — the worker's write-back to Supabase for BACKGROUND (async) analyses.

The sync `/analyze` stays stateless (returns JSON, no DB). The async pipeline needs to save the
result itself when the background job finishes, so it writes directly to Postgres via psycopg2 +
DATABASE_URL. Only the async path uses this.
"""
from __future__ import annotations

import logging
import os
import time

import psycopg2
from psycopg2.extras import Json


log = logging.getLogger("store")

_sleep = time.sleep                       # patched by the tests
PATIENT_WAITS = (2, 4, 8, 15, 15, 30, 30)  # seconds between tries when nobody is waiting on us


def _connect(attempts: int = 3, connect_timeout: int = 8, waits: tuple[float, ...] = (2, 5)):
    """A connection, after up to `attempts` tries.

    The database is in Singapore and the worker is in Oregon; a connection that fails on the
    first try usually succeeds on the second. With one try and no retry, every such blip became
    a 503 on the website and the whole class became 'failed' (22 Sep 2026: four in five minutes).
    Only connection errors are retried; a missing URL or a bad password fails at once.
    """
    url = os.environ.get("DATABASE_URL", "").replace("postgresql+psycopg2://", "postgresql://")
    if not url:
        raise RuntimeError("DATABASE_URL is not set — the worker cannot persist async results")
    last: Exception | None = None
    for i in range(max(1, attempts)):
        try:
            return psycopg2.connect(url, connect_timeout=connect_timeout)
        except psycopg2.OperationalError as e:
            last = e
            if i + 1 >= attempts:
                break
            wait = waits[min(i, len(waits) - 1)] if waits else 1
            log.warning("database connection failed (try %d of %d): %s; retrying in %ss",
                        i + 1, attempts, str(e).strip()[:160], wait)
            _sleep(wait)
    assert last is not None
    raise last


_PING: tuple[str, float] | None = None


def ping(cache_s: int = 60) -> str:
    """'ok' or 'unreachable': can the worker reach the database right now? One quick try, cached
    briefly, so /health answers the question a person has when an analysis will not start."""
    global _PING
    now = time.monotonic()
    if _PING and now - _PING[1] < cache_s:
        return _PING[0]
    try:
        conn = _connect(attempts=1, connect_timeout=5)
        try:
            cur = conn.cursor()
            cur.execute("select 1")
            cur.fetchone()
        finally:
            conn.close()
        state = "ok"
    except Exception as e:
        log.warning("database ping failed: %s", str(e).strip()[:160])
        state = "unreachable"
    _PING = (state, now)
    return state


def persist_analysis(class_id: str, result: dict, meta: dict, transcript_text: str, source: str) -> None:
    """Write transcript + analysis + draft feedback, flip the class to draft_ready, and audit it."""
    # A finished analysis is paid for; nobody is waiting on this call, so it waits for the database.
    conn = _connect(attempts=8, connect_timeout=10, waits=PATIENT_WAITS)
    cur = conn.cursor()
    try:
        if transcript_text and transcript_text.strip():
            cur.execute(
                "insert into transcripts(class_id, content, format, source) values (%s,%s,'vtt',%s) "
                "on conflict (class_id) do update set content=excluded.content, source=excluded.source, fetched_at=now()",
                (class_id, transcript_text, source))
        reclass = (result.get("reclass") or {}).get("recommended")
        reason = (result.get("reclass") or {}).get("reason")
        cur.execute(
            "insert into analyses(class_id, model, result, reclass, reclass_reason, tokens_in, tokens_out, cost_usd) "
            "values (%s,%s,%s,%s,%s,%s,%s,%s) returning id",
            (class_id, meta.get("model"), Json(result), reclass, reason,
             meta.get("tokens_in"), meta.get("tokens_out"), meta.get("cost_usd")))
        analysis_id = cur.fetchone()[0]
        cur.execute(
            "insert into feedback(class_id, analysis_id, draft_text, summary_draft_text, status) "
            "values (%s,%s,%s,%s,'draft')",
            (class_id, analysis_id, result.get("feedback", ""), result.get("instructor_summary", "")))
        cur.execute("update classes set status='draft_ready', updated_at=now() where id=%s", (class_id,))
        cur.execute(
            "insert into audit_log(class_id, actor_label, action, detail) values (%s,'worker','analyzed',%s)",
            (class_id, Json({"cost_usd": meta.get("cost_usd"), "reclass": reclass})))
        conn.commit()
    finally:
        conn.close()


def consume_sync_token(token: str) -> bool:
    """Spend a scheduler token: True once, for a real token under ten minutes old, never again.

    The scheduler (pg_cron, migration 0027) mints a token per run and posts it to the worker in
    place of the shared key, which it does not hold. Marking it used inside the same statement
    that checks it means two requests with the same token cannot both win.
    """
    if not token or not isinstance(token, str) or len(token) > 128:
        return False
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("update sync_triggers set used_at = now() "
                    " where token = %s and used_at is null and created_at > now() - interval '10 minutes' "
                    " returning id", (token,))
        won = cur.fetchone() is not None
        conn.commit()
        return won
    except Exception:
        log.exception("could not check a scheduler token; refusing it")
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                log.exception("could not close the connection after checking a scheduler token")


class StoreUnavailable(RuntimeError):
    """The database could not be asked. The caller must not guess."""


CLAIMABLE = ("scheduled", "failed")


def claim_for_analysis(class_id: str) -> bool:
    """Take the class for analysis, or return False because it is not ours to take.

    There was no lock at all: the Retry button appears while a job may still be running, and
    each click started another full analysis. Both paid, both wrote a row, and the review page
    picked one run's findings and the other run's draft with nothing joining them.

    Only a class the website has just scheduled (or one that failed) can be claimed: re-running a
    finished class would add a second draft under an approved note. A database error used to
    count as a successful claim - the worker then paid for an analysis it could not save.
    """
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("update classes set status='analyzing', updated_at=now() "
                    " where id=%s and status = any(%s) returning id", (class_id, list(CLAIMABLE)))
        won = cur.fetchone() is not None
        conn.commit()
        return won
    except Exception as e:
        log.exception("could not claim class %s for analysis", class_id)
        raise StoreUnavailable(str(e)[:200]) from e
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                log.exception("could not close the connection after claiming class %s", class_id)


def mark_failed(class_id: str, message: str, cost_usd: float | None = None) -> None:
    """Flag a class whose background analysis failed, so the UI can show it (recoverable — retry).

    Two things used to go wrong here. Every error was swallowed with a bare `pass` and no log, so a
    class deleted while its analysis was running left no record anywhere that money had been spent.
    And `conn.close()` sat inside the `try`, so the connection leaked on exactly those failures.
    The status update is also guarded now: a stale job must not drag a class that a newer run has
    already finished back to 'failed'.
    """
    conn = None
    try:
        conn = _connect(attempts=4, waits=(2, 5, 10))
        cur = conn.cursor()
        cur.execute("update classes set status='failed', updated_at=now() "
                    "where id=%s and status='analyzing'", (class_id,))
        moved = cur.rowcount
        detail = {"where": "analyze", "message": str(message)[:400]}
        if cost_usd:
            detail["cost_usd"] = round(float(cost_usd), 4)
        if not moved:
            detail["note"] = "class was no longer 'analyzing'; status left as it was"
        cur.execute(
            "insert into audit_log(class_id, actor_label, action, detail) values (%s,'worker','error',%s)",
            (class_id, Json(detail)))
        conn.commit()
    except Exception:
        # Nothing here can be allowed to raise into the caller, but it must not vanish either.
        log.exception("could not record the failure of class %s (message was: %s)",
                      class_id, str(message)[:200])
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                log.exception("could not close the connection after marking class %s failed", class_id)


def requeue_running(class_ids: list[str]) -> int:
    """The worker is stopping with these jobs still running (a deploy, a restart): put the classes
    back to 'scheduled' so the next instance resumes them, and say so in the audit trail.
    Quick and best-effort - a stopping process has seconds, not minutes."""
    if not class_ids:
        return 0
    conn = None
    try:
        conn = _connect(attempts=1, connect_timeout=5)
        cur = conn.cursor()
        cur.execute("update classes set status='scheduled', updated_at=now() "
                    "where id = any(%s::uuid[]) and status='analyzing' returning id", (list(class_ids),))
        moved = [str(r[0]) for r in cur.fetchall()]
        for cid in moved:
            cur.execute(
                "insert into audit_log(class_id, actor_label, action, detail) values (%s,'worker','queued',%s)",
                (cid, Json({"where": "analyze", "message": "the worker was restarted mid-analysis (a deploy); "
                                                          "the class is queued again and resumes on its own"})))
        conn.commit()
        return len(moved)
    except Exception:
        log.exception("could not queue %d running class(es) again before stopping", len(class_ids))
        return 0
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                log.exception("could not close the connection after queueing classes again")


RESUME_COLUMNS = ("class_id", "vimeo_url", "course", "topic", "instructor", "rating", "agenda", "class_type")


def scheduled_to_resume(min_age_s: int = 60, limit: int = 3) -> list[dict]:
    """Classes the website queued that no job took: the worker was asleep, unreachable, could not
    reach the database, or was restarted mid-run. Only rows old enough that the website's own
    request has surely come and gone, and that the stopping instance is surely dead (the platform
    kills it within about thirty seconds of the stop signal). Raises when the database cannot be
    asked; the caller decides what that means."""
    conn = _connect(attempts=1, connect_timeout=5)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            select c.id::text, c.vimeo_link, coalesce(co.name, '(unspecified)'), c.topic,
                   coalesce(i.name, '(unspecified)'), c.rating::text, coalesce(c.agenda, ''), c.session_type
              from classes c
              left join courses co on co.id = c.course_id
              left join instructors i on i.id = c.instructor_id
             where c.status = 'scheduled'
               and c.updated_at < now() - make_interval(secs => %s)
               and c.vimeo_link is not null and c.vimeo_link <> ''
             order by c.updated_at asc
             limit %s
            """, (min_age_s, limit))
        return [dict(zip(RESUME_COLUMNS, r)) for r in cur.fetchall()]
    finally:
        conn.close()


def record_resume(class_id: str) -> None:
    """One audit line: the worker took this class on its own, not because the website asked."""
    conn = None
    try:
        conn = _connect(attempts=1, connect_timeout=5)
        cur = conn.cursor()
        cur.execute(
            "insert into audit_log(class_id, actor_label, action, detail) values (%s,'worker','retried',%s)",
            (class_id, Json({"where": "resume", "message": "picked up by the worker on its own: the website's "
                                                          "request did not reach it, or the worker was restarted"})))
        conn.commit()
    except Exception:
        log.exception("could not record the resume of class %s", class_id)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                log.exception("could not close the connection after recording a resume")
