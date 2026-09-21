"""
store.py — the worker's write-back to Supabase for BACKGROUND (async) analyses.

The sync `/analyze` stays stateless (returns JSON, no DB). The async pipeline needs to save the
result itself when the background job finishes, so it writes directly to Postgres via psycopg2 +
DATABASE_URL. Only the async path uses this.
"""
from __future__ import annotations

import logging
import os

import psycopg2
from psycopg2.extras import Json


log = logging.getLogger("store")


def _connect():
    url = os.environ.get("DATABASE_URL", "").replace("postgresql+psycopg2://", "postgresql://")
    if not url:
        raise RuntimeError("DATABASE_URL is not set — the worker cannot persist async results")
    return psycopg2.connect(url, connect_timeout=15)


def persist_analysis(class_id: str, result: dict, meta: dict, transcript_text: str, source: str) -> None:
    """Write transcript + analysis + draft feedback, flip the class to draft_ready, and audit it."""
    conn = _connect()
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
        conn = _connect()
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
