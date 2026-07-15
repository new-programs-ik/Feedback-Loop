"""
store.py — the worker's write-back to Supabase for BACKGROUND (async) analyses.

The sync `/analyze` stays stateless (returns JSON, no DB). The async pipeline needs to save the
result itself when the background job finishes, so it writes directly to Postgres via psycopg2 +
DATABASE_URL. Only the async path uses this.
"""
from __future__ import annotations

import os

import psycopg2
from psycopg2.extras import Json


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


def mark_failed(class_id: str, message: str) -> None:
    """Flag a class whose background analysis failed, so the UI can show it (recoverable — retry)."""
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("update classes set status='needs_transcript', updated_at=now() where id=%s", (class_id,))
        cur.execute(
            "insert into audit_log(class_id, actor_label, action, detail) values (%s,'worker','error',%s)",
            (class_id, Json({"where": "analyze", "message": str(message)[:400]})))
        conn.commit()
        conn.close()
    except Exception:
        pass
