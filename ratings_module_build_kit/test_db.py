"""
test_db.py — unit tests for the Postgres data-access layer (db.py).

These are *logic* tests: they run against an in-memory SQLite database (shared across
connections via StaticPool) so no Postgres server is needed. The same db.py code runs
against Postgres in production via DATABASE_URL.

Run:  python -m unittest test_db -v
"""
import datetime
import os
import re
import unittest

from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

import db

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_SQL = os.path.join(HERE, "schema.sql")


def _make_engine():
    """A fresh in-memory SQLite shared by all connections, with FK + CHECK enforcement on."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return engine


# A realistic engine result blob (shape matches engine.py's output).
RESULT = {
    "overall": "Rushed the final two agenda items; otherwise clear.",
    "flags": [
        {"flag": "coverage", "severity": "major", "confidence": "high",
         "evidence": [{"timestamp": "03:55:00", "quote": "we'll do the rest next class"}]},
        {"flag": "pace", "severity": "moderate", "confidence": "medium",
         "evidence": [{"timestamp": "03:40:00", "quote": "we're almost out of time"}]},
    ],
    "feedback": "Great energy and clear early on. Watch the pace near the end (03:40) so the "
                "last topics get full coverage.",
    "reclass": {"recommended": "yes", "reason": "Last two planned topics were not covered (03:55).",
                "deciding_flags": ["coverage"]},
}
META = {"model": "claude-sonnet-4-6", "tokens_in": 12000, "tokens_out": 1500, "cost_usd": 0.2613}


class DBTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()
        db.set_engine(self.engine)
        db.create_all(self.engine)

    def tearDown(self):
        db.set_engine(None)
        self.engine.dispose()

    def _seed_class(self, **over):
        kw = dict(course="Python for ML", cohort="C12", instructor="Justin",
                  topic="pandas indexing", class_date="2026-06-22", rating=4.47,
                  num_ratings=18, vimeo_link="https://vimeo.com/abc")
        kw.update(over)
        return db.upsert_class(kw.pop("course"), **kw)


class TestUpsertClass(DBTestCase):
    def test_insert_returns_id(self):
        cid = self._seed_class()
        self.assertIsInstance(cid, int)
        row = db.get_class(cid)
        self.assertEqual(row["course"], "Python for ML")
        self.assertEqual(row["status"], "needs_transcript")     # default
        self.assertEqual(float(row["rating"]), 4.47)
        self.assertEqual(row["class_date"], datetime.date(2026, 6, 22))

    def test_idempotent_same_natural_key(self):
        a = self._seed_class()
        b = self._seed_class()                                   # same key again (a re-pull)
        self.assertEqual(a, b)                                   # not queued twice
        self.assertEqual(len(db.list_queue()), 1)

    def test_upsert_updates_mutable_fields_only(self):
        cid = self._seed_class(rating=4.47, num_ratings=18)
        db.set_status(cid, "draft_ready")
        # A re-pull with a corrected rating must update the rating but NOT reset status.
        again = self._seed_class(rating=4.10, num_ratings=20)
        self.assertEqual(cid, again)
        row = db.get_class(cid)
        self.assertEqual(float(row["rating"]), 4.10)
        self.assertEqual(row["num_ratings"], 20)
        self.assertEqual(row["status"], "draft_ready")          # preserved

    def test_null_fields_dedupe(self):
        a = db.upsert_class("Course X", cohort=None, instructor=None, topic=None, class_date=None)
        b = db.upsert_class("Course X", cohort=None, instructor=None, topic=None, class_date=None)
        self.assertEqual(a, b)                                   # NULL-safe dedupe

    def test_distinct_classes_separate_rows(self):
        a = self._seed_class(instructor="Justin")
        b = self._seed_class(instructor="Maria")                # same course, different instructor
        self.assertNotEqual(a, b)
        self.assertEqual(len(db.list_queue()), 2)

    def test_invalid_status_rejected(self):
        with self.assertRaises(ValueError):
            self._seed_class(status="bogus")

    def test_missing_course_rejected(self):
        with self.assertRaises(ValueError):
            db.upsert_class("")


class TestStatus(DBTestCase):
    def test_set_status(self):
        cid = self._seed_class()
        db.set_status(cid, "analyzing")
        self.assertEqual(db.get_class(cid)["status"], "analyzing")

    def test_set_status_invalid(self):
        cid = self._seed_class()
        with self.assertRaises(ValueError):
            db.set_status(cid, "nope")

    def test_set_status_unknown_class(self):
        with self.assertRaises(KeyError):
            db.set_status(999999, "analyzing")


class TestAnalysisAndDraft(DBTestCase):
    def test_save_analysis_denormalises_reclass(self):
        cid = self._seed_class()
        aid = db.save_analysis(cid, RESULT, META)
        rec = db.get_class(cid)["analysis"]
        self.assertEqual(rec["id"], aid)
        self.assertEqual(rec["reclass"], "yes")
        self.assertIn("not covered", rec["reclass_reason"])
        self.assertEqual(rec["model"], "claude-sonnet-4-6")
        self.assertEqual(rec["tokens_in"], 12000)
        self.assertEqual(float(rec["cost_usd"]), 0.2613)
        # Full engine JSON is preserved as a dict.
        self.assertEqual(rec["result"]["flags"][0]["flag"], "coverage")
        self.assertEqual(rec["result"]["reclass"]["deciding_flags"], ["coverage"])

    def test_save_analysis_bad_reclass(self):
        cid = self._seed_class()
        bad = dict(RESULT, reclass={"recommended": "perhaps", "reason": "x"})
        with self.assertRaises(ValueError):
            db.save_analysis(cid, bad, META)

    def test_save_draft(self):
        cid = self._seed_class()
        aid = db.save_analysis(cid, RESULT, META)
        fid = db.save_draft(cid, aid, RESULT["feedback"])
        fb = db.get_class(cid)["feedback"]
        self.assertEqual(fb["id"], fid)
        self.assertEqual(fb["status"], "draft")
        self.assertEqual(fb["draft_text"], RESULT["feedback"])
        self.assertIsNone(fb["edited_text"])

    def test_save_draft_empty_rejected(self):
        cid = self._seed_class()
        with self.assertRaises(ValueError):
            db.save_draft(cid, None, "   ")


class TestFeedbackEditApproveSend(DBTestCase):
    def _ready(self):
        cid = self._seed_class()
        aid = db.save_analysis(cid, RESULT, META)
        db.save_draft(cid, aid, RESULT["feedback"])
        db.set_status(cid, "draft_ready")
        return cid

    def test_edit_preserves_draft(self):
        cid = self._ready()
        db.update_feedback(cid, "Edited by the PM: nicer wording.", actor="pm@ik.com")
        fb = db.get_class(cid)["feedback"]
        self.assertEqual(fb["draft_text"], RESULT["feedback"])        # draft untouched
        self.assertEqual(fb["edited_text"], "Edited by the PM: nicer wording.")
        actions = [r["action"] for r in db.get_audit(cid)]
        self.assertIn("edited", actions)

    def test_approve_returns_edited_text(self):
        cid = self._ready()
        db.update_feedback(cid, "PM's improved version.", actor="pm@ik.com")
        send_text = db.approve(cid, "pm@ik.com")
        self.assertEqual(send_text, "PM's improved version.")        # edit wins over draft
        self.assertEqual(db.get_class(cid)["status"], "approved")
        fb = db.get_class(cid)["feedback"]
        self.assertEqual(fb["status"], "approved")
        self.assertEqual(fb["approved_by"], "pm@ik.com")
        self.assertIsNotNone(fb["approved_at"])

    def test_approve_falls_back_to_draft(self):
        cid = self._ready()
        send_text = db.approve(cid, "pm@ik.com")                     # no edit made
        self.assertEqual(send_text, RESULT["feedback"])

    def test_mark_sent(self):
        cid = self._ready()
        db.approve(cid, "pm@ik.com")
        db.mark_sent(cid)
        self.assertEqual(db.get_class(cid)["status"], "sent")
        fb = db.get_class(cid)["feedback"]
        self.assertEqual(fb["status"], "sent")
        self.assertIsNotNone(fb["sent_at"])

    def test_approve_without_feedback_raises(self):
        cid = self._seed_class()
        with self.assertRaises(KeyError):
            db.approve(cid, "pm@ik.com")


class TestAuditLog(DBTestCase):
    def test_log_and_read(self):
        cid = self._seed_class()
        db.log(cid, "engine", "pulled", {"source": "metabase"})
        db.log(cid, "engine", "analyzed", {"cost_usd": 0.26})
        rows = db.get_audit(cid)
        self.assertEqual([r["action"] for r in rows], ["pulled", "analyzed"])
        self.assertEqual(rows[0]["detail"], {"source": "metabase"})   # JSON round-trips
        self.assertEqual(rows[0]["actor"], "engine")

    def test_log_requires_actor_and_action(self):
        cid = self._seed_class()
        with self.assertRaises(ValueError):
            db.log(cid, "", "pulled")
        with self.assertRaises(ValueError):
            db.log(cid, "engine", "")

    def test_log_allows_null_class(self):
        # Engine/system-level events not tied to a specific class.
        rid = db.log(None, "n8n", "error", {"where": "ingest"})
        self.assertIsInstance(rid, int)


class TestQueueReads(DBTestCase):
    def test_list_queue_shape_and_reclass(self):
        cid = self._seed_class()
        db.save_analysis(cid, RESULT, META)
        db.save_draft(cid, None, RESULT["feedback"])
        db.set_status(cid, "draft_ready")
        rows = db.list_queue()
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["course"], "Python for ML")
        self.assertEqual(r["status"], "draft_ready")
        self.assertEqual(r["reclass"], "yes")                         # from latest analysis
        self.assertEqual(r["feedback_status"], "draft")

    def test_list_queue_filters_my_courses(self):
        self._seed_class(course="Python for ML", instructor="A")
        self._seed_class(course="System Design", instructor="B")
        mine = db.list_queue(courses=["Python for ML"])
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["course"], "Python for ML")

    def test_list_queue_empty_courses_returns_nothing(self):
        self._seed_class()
        self.assertEqual(db.list_queue(courses=[]), [])               # PM owns no courses

    def test_list_queue_status_filter(self):
        a = self._seed_class(instructor="A")
        self._seed_class(instructor="B")
        db.set_status(a, "draft_ready")
        self.assertEqual(len(db.list_queue(status="draft_ready")), 1)
        self.assertEqual(len(db.list_queue(status="needs_transcript")), 1)

    def test_get_class_missing(self):
        self.assertIsNone(db.get_class(123456))


class TestFullLifecycle(DBTestCase):
    def test_end_to_end_audit_trail(self):
        cid = self._seed_class()
        db.log(cid, "engine", "pulled", {"source": "metabase"})
        aid = db.save_analysis(cid, RESULT, META)
        db.save_draft(cid, aid, RESULT["feedback"])
        db.set_status(cid, "draft_ready")
        db.log(cid, "engine", "analyzed", {"cost_usd": META["cost_usd"]})
        db.update_feedback(cid, "PM polish.", actor="pm@ik.com")
        db.approve(cid, "pm@ik.com")
        db.mark_sent(cid)

        klass = db.get_class(cid)
        self.assertEqual(klass["status"], "sent")
        self.assertEqual(klass["feedback"]["draft_text"], RESULT["feedback"])  # never overwritten
        self.assertEqual(klass["feedback"]["edited_text"], "PM polish.")

        actions = [r["action"] for r in db.get_audit(cid)]
        for expected in ("pulled", "analyzed", "edited", "approved", "sent"):
            self.assertIn(expected, actions)


def _columns_from_schema_sql(text: str) -> dict[str, set[str]]:
    """Crude-but-robust parse of schema.sql: {table_name: {column names}}.

    Column lines lead with an identifier; constraint/continuation lines lead with a
    SQL keyword and are skipped. This lets us assert db.py's metadata stays in lock-step
    with the production DDL without standing up Postgres.
    """
    skip = {"unique", "check", "primary", "foreign", "constraint", "references", ")", ");"}
    tables: dict[str, set[str]] = {}
    for m in re.finditer(r"create table if not exists\s+(\w+)\s*\((.*?)\n\)\s*;",
                         text, flags=re.S | re.I):
        name, body = m.group(1), m.group(2)
        cols: set[str] = set()
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("--"):
                continue
            token = re.split(r"[\s(]", line, maxsplit=1)[0].lower()
            if token in skip:
                continue
            cols.add(token)
        tables[name] = cols
    return tables


class TestSchemaParity(unittest.TestCase):
    """db.py defines a second copy of the schema (for SQLite tests); keep it == schema.sql."""

    def test_columns_match_schema_sql(self):
        with open(SCHEMA_SQL, encoding="utf-8") as fh:
            sql_tables = _columns_from_schema_sql(fh.read())
        for name in ("classes", "analyses", "feedback", "audit_log"):
            self.assertIn(name, sql_tables, f"{name} not found in schema.sql")
            meta_cols = set(db.metadata.tables[name].columns.keys())
            self.assertEqual(
                meta_cols, sql_tables[name],
                f"db.py metadata for '{name}' has drifted from schema.sql: "
                f"only-in-db={meta_cols - sql_tables[name]}, "
                f"only-in-sql={sql_tables[name] - meta_cols}",
            )


if __name__ == "__main__":
    unittest.main()
