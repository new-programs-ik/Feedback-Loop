"""ratings_store.py - persistence for the ratings sync (psycopg2, DATABASE_URL, same as store.py).

All statements are idempotent upserts on the natural key. A PM's manual state is sacred: rows
with a decision_override, or already dismissed / analysis_started, keep their decision when the
sheet re-syncs - the sync updates their numbers but never re-opens a closed call.

The verdict (rule v2, decision.decide_v2) is computed HERE rather than by the caller, because one
of its inputs - the instructor's track record - is the average of their earlier rows in this very
table. The health read-out (score, band, reasons) always refreshes; only `decision` is frozen by
the PM-state rule above.
"""
from __future__ import annotations

import os
from typing import Optional

import psycopg2

import decision as D


def connect():
    url = os.environ.get("DATABASE_URL", "").replace("postgresql+psycopg2://", "postgresql://")
    if not url:
        raise RuntimeError("DATABASE_URL is not set - the ratings sync cannot run")
    return psycopg2.connect(url, connect_timeout=15)


def load_aliases(cur) -> dict[str, str]:
    cur.execute("select alias, course_id from course_aliases")
    return {alias: cid for alias, cid in cur.fetchall()}


def load_instructor_ids(cur) -> dict[str, str]:
    """Exact-name matching only - a wrong link is worse than a null one."""
    cur.execute("select name, id from instructors")
    return {name: iid for name, iid in cur.fetchall()}


def start_run(cur, source: str, trigger: str) -> str:
    cur.execute(
        "insert into sync_runs(source, trigger, status) values (%s,%s,'running') returning id",
        (source, trigger))
    return cur.fetchone()[0]


def finish_run(cur, run_id: str, *, status: str, rows_fetched: int = 0, rows_upserted: int = 0,
               rows_flagged: int = 0, notifications_sent: int = 0,
               unmapped_labels: Optional[list[str]] = None, error: str = "") -> None:
    cur.execute(
        "update sync_runs set status=%s, rows_fetched=%s, rows_upserted=%s, rows_flagged=%s, "
        "notifications_sent=%s, unmapped_labels=%s, error=nullif(%s,''), finished_at=now() "
        "where id=%s",
        (status, rows_fetched, rows_upserted, rows_flagged, notifications_sent,
         sorted(set(unmapped_labels or [])) or None, error, run_id))


def running_run_exists(cur, max_age_minutes: int = 10) -> bool:
    """Concurrent-run guard: a 'running' row younger than the cutoff means skip this trigger."""
    cur.execute(
        "select 1 from sync_runs where status='running' "
        "and started_at > now() - make_interval(mins => %s) limit 1",
        (max_age_minutes,))
    return cur.fetchone() is not None


def prior_state(cur, row: dict) -> tuple[bool, Optional[float]]:
    """What the table already knows that the verdict needs, in one round trip:
    - the PM's escalation toggle on this row (false for a row never seen), and
    - the instructor's track record: their average rating over classes dated strictly before
      this one, None until there are T_MIN_CLASSES of them. A blank instructor name gets no
      track record (it would pool every nameless row into one phantom instructor)."""
    cur.execute(
        """
        select coalesce((select escalated from class_ratings
                          where class_date=%(class_date)s and topic=%(topic)s
                            and instructor=%(instructor)s and session_kind=%(session_kind)s), false),
               (select avg(rating) from class_ratings
                 where instructor=%(instructor)s and class_date < %(class_date)s),
               (select count(*) from class_ratings
                 where instructor=%(instructor)s and class_date < %(class_date)s)
        """, row)
    escalated, avg, n = cur.fetchone()
    track = round(float(avg), 2) if row.get("instructor") and n >= D.T_MIN_CLASSES else None
    return bool(escalated), track


def upsert_rating(cur, row: dict, course_id: Optional[str],
                  instructor_id: Optional[str]) -> tuple[str, str, str]:
    """Insert or refresh one class_ratings row. Returns (id, decision_now, review_status)."""
    pct = (round(row["num_ratings"] / row["attended"] * 100, 1)
           if row.get("num_ratings") is not None and row.get("attended") else None)
    approval = D.approval_pct(row.get("yes_votes"), row.get("no_votes"))
    escalated, track = prior_state(cur, row)
    v = D.decide_v2(row["rating"], row.get("num_ratings"), row.get("attended"),
                    escalated=escalated, approval_pct=approval, track_avg=track)
    cur.execute(
        """
        insert into class_ratings
          (source, course_label, course_id, cohort_text, topic, instructor, instructor_id,
           class_date, session_kind, rating, num_ratings, attended, participation_pct,
           yes_votes, no_votes, approval_pct, track_avg, health_score, health_band, flag_reasons,
           decision)
        values (%(source)s, %(course_label)s, %(course_id)s, %(cohort_text)s, %(topic)s,
                %(instructor)s, %(instructor_id)s, %(class_date)s, %(session_kind)s, %(rating)s,
                %(num_ratings)s, %(attended)s, %(pct)s,
                %(yes_votes)s, %(no_votes)s, %(approval_pct)s, %(track_avg)s, %(health_score)s,
                %(health_band)s, %(flag_reasons)s, %(decision)s)
        on conflict (class_date, topic, instructor, session_kind) do update set
          source            = excluded.source,
          course_label      = excluded.course_label,
          course_id         = coalesce(excluded.course_id, class_ratings.course_id),
          cohort_text       = excluded.cohort_text,
          instructor_id     = coalesce(excluded.instructor_id, class_ratings.instructor_id),
          rating            = excluded.rating,
          num_ratings       = excluded.num_ratings,
          attended          = excluded.attended,
          participation_pct = excluded.participation_pct,
          -- the vote and the health read-out always follow the latest numbers:
          yes_votes         = excluded.yes_votes,
          no_votes          = excluded.no_votes,
          approval_pct      = excluded.approval_pct,
          track_avg         = excluded.track_avg,
          health_score      = excluded.health_score,
          health_band       = excluded.health_band,
          flag_reasons      = excluded.flag_reasons,
          -- the sync's verdict applies only while the row is untouched by a human:
          decision = case
            when class_ratings.decision_override is not null then class_ratings.decision
            when class_ratings.review_status in ('dismissed','analysis_started') then class_ratings.decision
            when class_ratings.escalated then 'video'::rating_decision
            else excluded.decision
          end,
          synced_at = now(), updated_at = now()
        returning id, decision, review_status
        """,
        {**row, "source": row.get("source", "sheet"), "course_id": course_id,
         "instructor_id": instructor_id, "pct": pct,
         "yes_votes": row.get("yes_votes"), "no_votes": row.get("no_votes"),
         "approval_pct": approval, "track_avg": track,
         "health_score": v.health_score, "health_band": v.health_band,
         "flag_reasons": list(v.flag_reasons), "decision": v.decision},
    )
    rid, dec, status = cur.fetchone()
    return str(rid), dec, status


def rows_needing_notification(cur) -> list[dict]:
    """Flagged, still 'new', course has a handler, and Slack was never sent for them."""
    cur.execute(
        """
        select cr.id, cr.topic, cr.instructor, cr.class_date, cr.session_kind, cr.rating,
               cr.num_ratings, cr.attended, cr.participation_pct, cr.decision,
               cr.yes_votes, cr.no_votes, cr.approval_pct, cr.health_score, cr.health_band,
               cr.flag_reasons,
               c.name as course_name, h.handler_name, h.handler_email, h.slack_user_id, h.id as handler_id
        from class_ratings cr
        join courses c on c.id = cr.course_id
        join course_handlers h on h.course_id = cr.course_id
        left join rating_notifications n
               on n.class_rating_id = cr.id and n.channel = 'slack'
        where cr.decision in ('video','transcript')
          and cr.review_status = 'new'
          and n.id is null
        order by cr.class_date desc
        """)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def record_notification(cur, class_rating_id: str, *, channel: str = "slack",
                        recipient: str = "", status: str = "sent",
                        slack_ts: str = "", error: str = "") -> bool:
    """The dedupe gate: only the caller whose INSERT wins may actually send/mark. Returns won."""
    cur.execute(
        "insert into rating_notifications(class_rating_id, channel, recipient, status, slack_ts, error) "
        "values (%s,%s,%s,%s,nullif(%s,''),nullif(%s,'')) "
        "on conflict (class_rating_id, channel) do nothing returning id",
        (class_rating_id, channel, recipient, status, slack_ts, error))
    return cur.fetchone() is not None


def mark_notified(cur, class_rating_id: str) -> None:
    cur.execute(
        "update class_ratings set review_status='notified', updated_at=now() "
        "where id=%s and review_status='new'", (class_rating_id,))


def cache_slack_user(cur, handler_id: str, slack_user_id: str) -> None:
    cur.execute("update course_handlers set slack_user_id=%s, updated_at=now() where id=%s",
                (slack_user_id, handler_id))
