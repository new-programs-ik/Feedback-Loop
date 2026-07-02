"""
db.py — Postgres data-access layer for the Ratings & Feedback module (§6.2).

The system of record is the Postgres store defined in ``schema.sql`` (apply that file
to the production database). This module is a *thin* access layer over it, written with
SQLAlchemy Core so the exact same code runs against:

  * **Postgres** in production  — ``DATABASE_URL=postgresql+psycopg2://...``
  * **SQLite**   in unit tests  — ``sqlite:///...`` (logic tests, no server needed)

The SQLAlchemy ``MetaData`` below mirrors ``schema.sql`` so tests can ``create_all()`` an
equivalent schema on SQLite. In production the tables already exist (created by
``schema.sql``); this layer only reads and writes — it does not own the DDL.

Design notes
------------
* Every write runs inside a transaction (``engine.begin()``), so a failure rolls back —
  nothing is half-written (a production requirement, §11). Functions accept an optional
  ``conn=`` so several writes can be composed into one atomic transaction by the caller
  (the service does this when it persists an analysis + draft together).
* Idempotency: ``upsert_class`` dedupes on the natural key (course, cohort, instructor,
  topic, class_date). It selects-then-writes and treats the DB ``UNIQUE`` constraint as a
  race backstop (re-selects on ``IntegrityError``).
* Resilience: the engine is created with ``pool_pre_ping=True`` (drops dead pooled
  connections instead of erroring) and a connect timeout — the DB-layer equivalent of the
  retries/timeouts we put on the HTTP calls.
* Secrets: the connection string comes from ``DATABASE_URL`` — never hardcoded.
"""
from __future__ import annotations

import datetime as _dt
import logging
import os
from contextlib import contextmanager
from typing import Any, Iterable, Iterator, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    Table,
    Text,
    TIMESTAMP,
    UniqueConstraint,
    create_engine,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger("ratings_db")

# ───────────────────────────────────────────────────────────────────── constants
# Kept in sync with the CHECK constraints in schema.sql.
CLASS_STATUSES = {
    "needs_transcript", "analyzing", "draft_ready", "approved", "sent", "no_action",
}
FEEDBACK_STATUSES = {"draft", "approved", "sent", "discarded"}
RECLASS_VALUES = {"yes", "no", "maybe"}

# ─────────────────────────────────────────────────────────────────────── schema
# A BIGINT primary key on Postgres, but a plain INTEGER on SQLite so that SQLite's
# rowid auto-increment kicks in during tests.
_BIGPK = BigInteger().with_variant(Integer, "sqlite")
_BIGFK = BigInteger().with_variant(Integer, "sqlite")

metadata = MetaData()

classes = Table(
    "classes", metadata,
    Column("id", _BIGPK, primary_key=True, autoincrement=True),
    Column("course", Text, nullable=False),
    Column("cohort", Text),
    Column("instructor", Text),
    Column("topic", Text),
    Column("class_date", Date),
    Column("rating", Numeric(3, 2)),
    Column("num_ratings", Integer),
    Column("vimeo_link", Text),
    Column("status", Text, nullable=False, server_default="needs_transcript"),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint(
        "status in ('needs_transcript','analyzing','draft_ready','approved','sent','no_action')",
        name="classes_status_check",
    ),
    UniqueConstraint("course", "cohort", "instructor", "topic", "class_date",
                     name="classes_natural_key"),
)

analyses = Table(
    "analyses", metadata,
    Column("id", _BIGPK, primary_key=True, autoincrement=True),
    Column("class_id", _BIGFK, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
    Column("model", Text, nullable=False),
    Column("result", JSON, nullable=False),
    Column("reclass", Text),
    Column("reclass_reason", Text),
    Column("tokens_in", Integer),
    Column("tokens_out", Integer),
    Column("cost_usd", Numeric(8, 4)),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("reclass in ('yes','no','maybe')", name="analyses_reclass_check"),
)

feedback = Table(
    "feedback", metadata,
    Column("id", _BIGPK, primary_key=True, autoincrement=True),
    Column("class_id", _BIGFK, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
    Column("analysis_id", _BIGFK, ForeignKey("analyses.id", ondelete="SET NULL")),
    Column("draft_text", Text, nullable=False),
    Column("edited_text", Text),
    Column("status", Text, nullable=False, server_default="draft"),
    Column("approved_by", Text),
    Column("approved_at", TIMESTAMP(timezone=True)),
    Column("sent_at", TIMESTAMP(timezone=True)),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("status in ('draft','approved','sent','discarded')", name="feedback_status_check"),
)

audit_log = Table(
    "audit_log", metadata,
    Column("id", _BIGPK, primary_key=True, autoincrement=True),
    Column("class_id", _BIGFK, ForeignKey("classes.id", ondelete="SET NULL")),
    Column("actor", Text, nullable=False),
    Column("action", Text, nullable=False),
    Column("detail", JSON),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=func.now()),
)

Index("idx_classes_status", classes.c.status)
Index("idx_analyses_class", analyses.c.class_id)
Index("idx_feedback_class", feedback.c.class_id)
Index("idx_audit_class", audit_log.c.class_id)

# ──────────────────────────────────────────────────────────────── engine handling
_ENGINE: Optional[Engine] = None


def make_engine(database_url: Optional[str] = None, **kwargs: Any) -> Engine:
    """Build a SQLAlchemy Engine. Reads ``DATABASE_URL`` from the env if not given.

    ``pool_pre_ping`` discards dead pooled connections (the DB equivalent of a retry on a
    transient drop); a short connect timeout keeps a wedged DB from hanging a request.
    """
    url = database_url or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set (and no url passed to make_engine)")
    opts: dict[str, Any] = {"pool_pre_ping": True, "future": True}
    if url.startswith("postgresql"):
        # libpq honours connect_timeout (seconds); fail fast instead of hanging.
        opts.setdefault("connect_args", {"connect_timeout": 10})
    opts.update(kwargs)
    logger.info("creating DB engine for %s", _safe_url(url))
    return create_engine(url, **opts)


def _safe_url(url: str) -> str:
    """Redact credentials before logging a connection string."""
    try:
        from sqlalchemy.engine import make_url
        u = make_url(url)
        return str(u.set(password="***")) if u.password else url
    except Exception:
        return url.split("@")[-1] if "@" in url else url


def get_engine() -> Engine:
    """Return the process-wide engine, creating it from ``DATABASE_URL`` on first use."""
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = make_engine()
    return _ENGINE


def set_engine(engine: Optional[Engine]) -> None:
    """Install an engine explicitly (used by tests to point at SQLite)."""
    global _ENGINE
    _ENGINE = engine


def create_all(engine: Optional[Engine] = None) -> None:
    """Create the tables from the metadata. For tests / local SQLite only —
    production schema comes from ``schema.sql``."""
    metadata.create_all(engine or get_engine())


def drop_all(engine: Optional[Engine] = None) -> None:
    metadata.drop_all(engine or get_engine())


def health() -> bool:
    """Cheap liveness check for /health and the n8n health workflow."""
    with get_engine().connect() as conn:
        conn.execute(select(1))
    return True


# ─────────────────────────────────────────────────────────────────────── helpers
@contextmanager
def _txn(conn: Optional[Connection]) -> Iterator[Connection]:
    """Yield a transactional connection.

    If the caller passes a ``conn`` they own the transaction (lets several writes be
    composed atomically); otherwise we open and commit our own.
    """
    if conn is not None:
        yield conn
    else:
        with get_engine().begin() as own:
            yield own


@contextmanager
def _read(conn: Optional[Connection]) -> Iterator[Connection]:
    if conn is not None:
        yield conn
    else:
        with get_engine().connect() as own:
            yield own


def _coerce_date(value: Any) -> Optional[_dt.date]:
    if value is None or isinstance(value, _dt.date):
        return value
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, str):
        # Accept YYYY-MM-DD (and full ISO timestamps).
        return _dt.date.fromisoformat(value[:10])
    raise TypeError(f"class_date must be a date or ISO string, got {type(value).__name__}")


def _scalar_pk(result: Any) -> int:
    return int(result.inserted_primary_key[0])


# ───────────────────────────────────────────────────────────────────── write API
def _class_key_where(key: dict):
    """WHERE clause matching a class on its natural key (NULL-safe: None → IS NULL)."""
    return [classes.c[k].is_(v) if v is None else classes.c[k] == v for k, v in key.items()]


def upsert_class(
    course: str,
    *,
    cohort: Optional[str] = None,
    instructor: Optional[str] = None,
    topic: Optional[str] = None,
    class_date: Any = None,
    rating: Any = None,
    num_ratings: Optional[int] = None,
    vimeo_link: Optional[str] = None,
    status: Optional[str] = None,
    conn: Optional[Connection] = None,
) -> int:
    """Insert a low-rated class, or update the mutable fields if it already exists.

    Dedupes on the natural key (course, cohort, instructor, topic, class_date) so the same
    class is never queued twice across weekly pulls (§2 idempotency). Returns the row id.
    """
    if not course:
        raise ValueError("course is required")
    if status is not None and status not in CLASS_STATUSES:
        raise ValueError(f"invalid status: {status!r}")
    cdate = _coerce_date(class_date)
    key = dict(course=course, cohort=cohort, instructor=instructor, topic=topic, class_date=cdate)
    mutable = dict(rating=rating, num_ratings=num_ratings, vimeo_link=vimeo_link)
    if status is not None:
        mutable["status"] = status

    def _do(c: Connection) -> int:
        existing = c.execute(select(classes.c.id).where(*_class_key_where(key))).first()
        if existing:
            c.execute(update(classes).where(classes.c.id == existing[0])
                      .values(**mutable, updated_at=func.now()))
            return int(existing[0])
        res = c.execute(insert(classes).values(**key, **mutable))
        return _scalar_pk(res)

    # Caller-owned transaction: do it inline (caller controls atomicity & retry).
    if conn is not None:
        return _do(conn)

    # Self-managed: on a lost insert race the UNIQUE constraint fires — the prior
    # transaction has already rolled back, so re-select the winner on a fresh connection.
    eng = get_engine()
    try:
        with eng.begin() as c:
            return _do(c)
    except IntegrityError:
        logger.warning("upsert_class lost an insert race; re-selecting existing row")
        with eng.connect() as c:
            row = c.execute(select(classes.c.id).where(*_class_key_where(key))).first()
        if row:
            return int(row[0])
        raise


def set_status(class_id: int, status: str, *, conn: Optional[Connection] = None) -> None:
    """Move a class to a new lifecycle status (§2 state machine)."""
    if status not in CLASS_STATUSES:
        raise ValueError(f"invalid status: {status!r}")
    with _txn(conn) as c:
        result = c.execute(
            update(classes).where(classes.c.id == class_id)
            .values(status=status, updated_at=func.now())
        )
        if result.rowcount == 0:
            raise KeyError(f"no class with id {class_id}")


def save_analysis(class_id: int, result: dict, meta: dict, *, conn: Optional[Connection] = None) -> int:
    """Persist one engine run: the full JSON in ``result``, with ``reclass`` and cost/tokens
    denormalised for easy querying (§5). Returns the new analyses.id."""
    reclass_obj = (result or {}).get("reclass") or {}
    reclass = reclass_obj.get("recommended")
    if reclass is not None and reclass not in RECLASS_VALUES:
        raise ValueError(f"invalid reclass value: {reclass!r}")
    with _txn(conn) as c:
        res = c.execute(insert(analyses).values(
            class_id=class_id,
            model=meta.get("model", "unknown"),
            result=result,
            reclass=reclass,
            reclass_reason=reclass_obj.get("reason"),
            tokens_in=meta.get("tokens_in"),
            tokens_out=meta.get("tokens_out"),
            cost_usd=meta.get("cost_usd"),
        ))
        return _scalar_pk(res)


def save_draft(class_id: int, analysis_id: Optional[int], draft_text: str,
               *, conn: Optional[Connection] = None) -> int:
    """Store the engine's instructor-feedback draft. The draft is never overwritten — PM
    edits land in ``edited_text`` so the draft-vs-edit diff stays as the accuracy signal (§5)."""
    if not draft_text or not draft_text.strip():
        raise ValueError("draft_text is required")
    with _txn(conn) as c:
        res = c.execute(insert(feedback).values(
            class_id=class_id, analysis_id=analysis_id, draft_text=draft_text, status="draft",
        ))
        return _scalar_pk(res)


def update_feedback(class_id: int, edited_text: str, *, actor: str = "pm",
                    conn: Optional[Connection] = None) -> None:
    """Record a PM's edit to the latest draft (writes ``edited_text``, leaves the draft intact)
    and append an ``edited`` audit row."""
    with _txn(conn) as c:
        fid = _latest_feedback_id(c, class_id)
        if fid is None:
            raise KeyError(f"no feedback row for class {class_id}")
        c.execute(update(feedback).where(feedback.c.id == fid).values(edited_text=edited_text))
        _log(c, class_id, actor, "edited", {"chars": len(edited_text or "")})


def approve(class_id: int, pm: str, *, conn: Optional[Connection] = None) -> str:
    """PM approves the feedback. Marks the feedback + class ``approved`` and returns the text
    n8n should deliver (the PM's edit if present, otherwise the draft). Atomic + audited."""
    with _txn(conn) as c:
        row = c.execute(
            select(feedback.c.id, feedback.c.draft_text, feedback.c.edited_text)
            .where(feedback.c.class_id == class_id)
            .order_by(feedback.c.id.desc()).limit(1)
        ).first()
        if row is None:
            raise KeyError(f"no feedback row for class {class_id}")
        fid, draft_text, edited_text = row
        send_text = (edited_text if (edited_text and edited_text.strip()) else draft_text)
        c.execute(update(feedback).where(feedback.c.id == fid)
                  .values(status="approved", approved_by=pm, approved_at=func.now()))
        c.execute(update(classes).where(classes.c.id == class_id)
                  .values(status="approved", updated_at=func.now()))
        _log(c, class_id, pm, "approved", {"feedback_id": fid, "edited": bool(edited_text)})
        return send_text


def mark_sent(class_id: int, *, actor: str = "n8n", conn: Optional[Connection] = None) -> None:
    """Mark the approved feedback as delivered (after n8n's Discord DM succeeds). Atomic + audited."""
    with _txn(conn) as c:
        fid = _latest_feedback_id(c, class_id)
        if fid is None:
            raise KeyError(f"no feedback row for class {class_id}")
        c.execute(update(feedback).where(feedback.c.id == fid)
                  .values(status="sent", sent_at=func.now()))
        c.execute(update(classes).where(classes.c.id == class_id)
                  .values(status="sent", updated_at=func.now()))
        _log(c, class_id, actor, "sent", {"feedback_id": fid})


def log(class_id: Optional[int], actor: str, action: str, detail: Any = None,
        *, conn: Optional[Connection] = None) -> int:
    """Append a row to the audit log (§5). ``detail`` is stored as JSON."""
    with _txn(conn) as c:
        return _log(c, class_id, actor, action, detail)


def _log(c: Connection, class_id: Optional[int], actor: str, action: str, detail: Any) -> int:
    if not actor or not action:
        raise ValueError("actor and action are required for an audit row")
    res = c.execute(insert(audit_log).values(
        class_id=class_id, actor=actor, action=action, detail=detail))
    return _scalar_pk(res)


def _latest_feedback_id(c: Connection, class_id: int) -> Optional[int]:
    row = c.execute(
        select(feedback.c.id).where(feedback.c.class_id == class_id)
        .order_by(feedback.c.id.desc()).limit(1)
    ).first()
    return int(row[0]) if row else None


# ──────────────────────────────────────────────────────────────────── read API
def _latest_analysis_subq():
    """Subquery: the id of the most recent analysis per class."""
    return (select(analyses.c.class_id, func.max(analyses.c.id).label("aid"))
            .group_by(analyses.c.class_id).subquery())


def _latest_feedback_subq():
    return (select(feedback.c.class_id, func.max(feedback.c.id).label("fid"))
            .group_by(feedback.c.class_id).subquery())


def list_queue(courses: Optional[Iterable[str]] = None, status: Optional[str] = None,
               *, conn: Optional[Connection] = None) -> list[dict]:
    """Queue view for the PM UI (§6.4 screen 1): one row per class with its rating, status,
    the re-class flag from the latest analysis, and the latest feedback status.

    ``courses`` filters to a PM's assigned courses ("my courses"); ``status`` filters by
    lifecycle status.
    """
    la = _latest_analysis_subq()
    lf = _latest_feedback_subq()
    q = (
        select(
            classes.c.id, classes.c.course, classes.c.cohort, classes.c.instructor,
            classes.c.topic, classes.c.class_date, classes.c.rating, classes.c.num_ratings,
            classes.c.vimeo_link, classes.c.status, classes.c.created_at,
            analyses.c.reclass, analyses.c.reclass_reason,
            feedback.c.status.label("feedback_status"),
            feedback.c.edited_text.isnot(None).label("edited"),
        )
        .select_from(
            classes
            .outerjoin(la, la.c.class_id == classes.c.id)
            .outerjoin(analyses, analyses.c.id == la.c.aid)
            .outerjoin(lf, lf.c.class_id == classes.c.id)
            .outerjoin(feedback, feedback.c.id == lf.c.fid)
        )
        .order_by(classes.c.created_at.desc(), classes.c.id.desc())
    )
    courses = list(courses) if courses is not None else None
    if courses is not None:
        if not courses:
            return []  # an empty assignment list means "no courses" → no rows
        q = q.where(classes.c.course.in_(courses))
    if status is not None:
        q = q.where(classes.c.status == status)
    with _read(conn) as c:
        return [dict(r) for r in c.execute(q).mappings().all()]


def get_class(class_id: int, *, conn: Optional[Connection] = None) -> Optional[dict]:
    """Full record for the review screen (§6.4 screen 3): the class, its latest analysis
    (full engine JSON, incl. flags + re-class call), and the latest feedback (draft + edit)."""
    with _read(conn) as c:
        crow = c.execute(select(classes).where(classes.c.id == class_id)).mappings().first()
        if crow is None:
            return None
        out: dict[str, Any] = dict(crow)
        arow = c.execute(
            select(analyses).where(analyses.c.class_id == class_id)
            .order_by(analyses.c.id.desc()).limit(1)
        ).mappings().first()
        out["analysis"] = dict(arow) if arow else None
        frow = c.execute(
            select(feedback).where(feedback.c.class_id == class_id)
            .order_by(feedback.c.id.desc()).limit(1)
        ).mappings().first()
        out["feedback"] = dict(frow) if frow else None
        return out


def get_audit(class_id: int, *, conn: Optional[Connection] = None) -> list[dict]:
    """The audit trail for one class, oldest first."""
    with _read(conn) as c:
        rows = c.execute(
            select(audit_log).where(audit_log.c.class_id == class_id)
            .order_by(audit_log.c.id.asc())
        ).mappings().all()
        return [dict(r) for r in rows]
