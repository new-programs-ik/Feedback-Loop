"""test_ratings_sync.py - the ratings platform, fully offline.
Sheet parsing via httpx.MockTransport; sync orchestration with a fake store; Slack payloads.
Run: python -m unittest test_ratings_sync -v
"""
import datetime as dt
import json
import unittest
from unittest import mock

import httpx

import notify as N
import sheet_source as SS

TAB1 = "MLSU_Live_Class_Poll"
TAB2 = "Agentic_AI_Live_Class_Poll"


def sheet_payload(values1, values2=None):
    ranges = [{"range": TAB1, "values": values1}]
    if values2 is not None:
        ranges.append({"range": TAB2, "values": values2})
    return {"valueRanges": ranges}


HEADER = ["Topic Code", "Type", "Cohorts", "Topic", "Cohorts", "Instructor", "Session Date",
          "Overall Average", "Responses", "# Students Attended", "% Rated"]


def row(date="2026-08-24", type_="Agentic AI Live Class", cohort="Applied Agentic AI - Aug",
        topic="MCP Deep Dive", instructor="Jane Doe", rating=4.31, resp=12, att=25):
    return ["Live Class", type_, cohort, topic, cohort, instructor, date, rating, resp, att, ""]


def make_source(payload, env=None, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer tok-123"
        return httpx.Response(status, json=payload)

    return SS.SheetRatingsSource(
        env or {"RATINGS_SHEET_ID": "sheet-1", "RATINGS_SHEET_TABS": f"{TAB1},{TAB2}"},
        transport=httpx.MockTransport(handler),
        token_provider=lambda env_: "tok-123",
    )


class TestSheetSource(unittest.TestCase):
    def test_parses_both_tabs(self):
        src = make_source(sheet_payload([HEADER, row()], [HEADER, row(topic="RAG Agents")]))
        rows = src.fetch_rows()
        self.assertEqual(len(rows), 2)
        r = rows[0]
        self.assertEqual(r["course_label"], "Applied Agentic AI")
        self.assertEqual(r["session_kind"], "Live Class")
        self.assertEqual(r["class_date"], dt.date(2026, 8, 24))
        self.assertEqual(r["rating"], 4.31)
        self.assertEqual(r["num_ratings"], 12)
        self.assertEqual(r["attended"], 25)

    def test_header_reorder_is_harmless(self):
        hdr = list(reversed(HEADER))
        rr = list(reversed(row()))
        src = make_source(sheet_payload([hdr, rr]))
        self.assertEqual(len(src.fetch_rows()), 1)

    def test_renamed_required_column_fails_loudly(self):
        hdr = [("Avg Score" if h == "Overall Average" else h) for h in HEADER]
        src = make_source(sheet_payload([hdr, row()]))
        with self.assertRaises(SS.SheetSourceError) as ctx:
            src.fetch_rows()
        self.assertIn("Overall Average", str(ctx.exception))

    def test_class_column_satisfies_topic(self):
        hdr = [("Class" if h == "Topic" else h) for h in HEADER]
        src = make_source(sheet_payload([hdr, row()]))
        self.assertEqual(src.fetch_rows()[0]["topic"], "MCP Deep Dive")

    def test_data_hygiene(self):
        rows = [
            HEADER,
            row(rating="No Ratings"),          # non-numeric rating -> skipped
            row(att=0),                         # zero attended -> skipped
            row(resp=30, att=10),               # responses > attended -> skipped
            row(topic="Keep Me"),
        ]
        src = make_source(sheet_payload(rows))
        out = src.fetch_rows()
        self.assertEqual([r["topic"] for r in out], ["Keep Me"])

    def test_cross_tab_dedupe(self):
        src = make_source(sheet_payload([HEADER, row()], [HEADER, row()]))
        self.assertEqual(len(src.fetch_rows()), 1)

    def test_missing_sheet_id_is_loud(self):
        src = SS.SheetRatingsSource({"RATINGS_SHEET_ID": ""}, token_provider=lambda e: "t")
        with self.assertRaises(SS.SheetSourceError):
            src.fetch_rows()

    def test_403_names_the_sharing_problem(self):
        src = make_source({}, status=403)
        with self.assertRaises(SS.SheetSourceError) as ctx:
            src.fetch_rows()
        self.assertIn("not shared", str(ctx.exception))


class TestSyncOrchestration(unittest.TestCase):
    """run_sync with the store mocked out - checks decisions, aliasing, dedupe of notifications."""

    class FakeSource:
        name = "sheet"

        def __init__(self, rows):
            self.rows = rows

        def fetch_rows(self):
            return self.rows

    def _run(self, rows, aliases, pending=None, record_returns=True):
        import ratings_sync as RSY
        calls = {"upserts": [], "notified": [], "finish": None}

        fake_st = mock.MagicMock()
        fake_st.connect.return_value = mock.MagicMock()
        fake_st.running_run_exists.return_value = False
        fake_st.start_run.return_value = "run-1"
        fake_st.load_aliases.return_value = aliases
        fake_st.load_instructor_ids.return_value = {"Jane Doe": "inst-1"}

        def upsert(cur, row, verdict, course_id, instructor_id):
            calls["upserts"].append((row["topic"], verdict, course_id, instructor_id))
            return ("cr-" + row["topic"], verdict, "new")

        fake_st.upsert_rating.side_effect = upsert
        fake_st.rows_needing_notification.return_value = pending or []
        fake_st.record_notification.return_value = record_returns

        def finish(cur, run_id, **kw):
            calls["finish"] = kw

        fake_st.finish_run.side_effect = finish

        fake_notify = mock.MagicMock()
        fake_notify.slack_configured.return_value = bool(pending)
        fake_notify.lookup_user_id.return_value = "U123"
        fake_notify.post_flag_message.return_value = (True, "111.222", "")

        with mock.patch.object(RSY, "ST", fake_st), mock.patch.object(RSY, "N", fake_notify):
            summary = RSY.run_sync("manual", env={}, source=self.FakeSource(rows))
        return summary, calls, fake_notify

    def _row(self, topic="T1", rating=4.2, resp=10, att=20, label="Applied Agentic AI"):
        return {"course_label": label, "cohort_text": "c", "topic": topic, "instructor": "Jane Doe",
                "class_date": dt.date(2026, 8, 24), "session_kind": "Live Class",
                "rating": rating, "num_ratings": resp, "attended": att}

    def test_decisions_and_aliases_flow_through(self):
        summary, calls, _ = self._run(
            [self._row(topic="Video", rating=4.2, resp=10, att=20),        # 50% -> video
             self._row(topic="Fine", rating=4.8),                           # -> none
             self._row(topic="Lost", label="Other / unmapped")],            # unmapped
            aliases={"Applied Agentic AI": "course-1"})
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["rows_upserted"], 3)
        self.assertEqual(summary["rows_flagged"], 2)   # Video + Lost (4.2 at 50% both flagged)
        self.assertIn("Other / unmapped", summary["unmapped_labels"])
        by_topic = {t: (v, c, i) for t, v, c, i in calls["upserts"]}
        self.assertEqual(by_topic["Video"][0], "video")
        self.assertEqual(by_topic["Fine"][0], "none")
        self.assertIsNone(by_topic["Lost"][1])          # unmapped -> course_id None
        self.assertEqual(by_topic["Video"][1], "course-1")   # aliased course id flows through
        self.assertEqual(by_topic["Video"][2], "inst-1")     # exact-name instructor match

    def test_notification_dedupe_gate(self):
        pending = [{"id": "cr-1", "topic": "T", "instructor": "Jane Doe",
                    "class_date": dt.date(2026, 8, 24), "session_kind": "Live Class",
                    "rating": 4.2, "num_ratings": 10, "attended": 20, "participation_pct": 50.0,
                    "decision": "video", "course_name": "Applied Agentic AI",
                    "handler_name": "Bishal", "handler_email": "b@ik.com",
                    "slack_user_id": None, "handler_id": "h-1"}]
        summary, _, fake_notify = self._run([self._row()], {"Applied Agentic AI": "c1"},
                                            pending=pending, record_returns=False)
        # record_notification lost the race -> nothing is posted
        fake_notify.post_flag_message.assert_not_called()
        self.assertEqual(summary["notifications_sent"], 0)

    def test_notification_sent_when_gate_won(self):
        pending = [{"id": "cr-1", "topic": "T", "instructor": "Jane Doe",
                    "class_date": dt.date(2026, 8, 24), "session_kind": "Live Class",
                    "rating": 4.2, "num_ratings": 10, "attended": 20, "participation_pct": 50.0,
                    "decision": "video", "course_name": "Applied Agentic AI",
                    "handler_name": "Bishal", "handler_email": "b@ik.com",
                    "slack_user_id": None, "handler_id": "h-1"}]
        summary, _, fake_notify = self._run([self._row()], {"Applied Agentic AI": "c1"},
                                            pending=pending, record_returns=True)
        fake_notify.post_flag_message.assert_called_once()
        self.assertEqual(summary["notifications_sent"], 1)

    def test_source_failure_marks_run_failed_and_alerts(self):
        import ratings_sync as RSY

        class BoomSource:
            name = "sheet"

            def fetch_rows(self):
                raise SS.SheetSourceError("tab 'X' is missing required column(s) ['Topic']")

        fake_st = mock.MagicMock()
        fake_st.connect.return_value = mock.MagicMock()
        fake_st.running_run_exists.return_value = False
        fake_st.start_run.return_value = "run-9"
        fake_notify = mock.MagicMock()
        with mock.patch.object(RSY, "ST", fake_st), mock.patch.object(RSY, "N", fake_notify):
            summary = RSY.run_sync("cron", env={}, source=BoomSource())
        self.assertEqual(summary["status"], "failed")
        self.assertIn("missing required column", summary["error"])
        kw = fake_st.finish_run.call_args.kwargs
        self.assertEqual(kw["status"], "failed")
        fake_notify.post_sync_alert.assert_called_once()


class TestSlackPayload(unittest.TestCase):
    ROW = {"id": "cr-1", "topic": "MCP Deep Dive", "instructor": "Jane Doe",
           "class_date": dt.date(2026, 9, 1), "session_kind": "Live Class", "rating": 4.31,
           "num_ratings": 12, "attended": 25, "participation_pct": 48.0, "decision": "video",
           "course_name": "Applied Agentic AI", "handler_name": "Bishal",
           "handler_email": "b@ik.com", "slack_user_id": "U777", "handler_id": "h-1"}

    def test_blocks_carry_the_facts_and_the_link_button(self):
        blocks = N.flag_blocks(self.ROW, "https://app/ratings?focus=cr-1", "U777")
        text = json.dumps(blocks)
        for needle in ("Video analysis", "Applied Agentic AI", "MCP Deep Dive",
                       "12 of 25 rated (48%)", "<@U777>", "ratings?focus=cr-1"):
            self.assertIn(needle, text)
        self.assertEqual(blocks[-2]["elements"][0]["type"], "button")   # URL button, no webhook

    def test_post_failure_never_raises(self):
        def handler(request):
            return httpx.Response(500)
        ok, ts, err = N.post_flag_message(
            self.ROW, env={"SLACK_BOT_TOKEN": "x", "SLACK_PM_CHANNEL_ID": "C1", "UI_URL": "https://app"},
            transport=httpx.MockTransport(handler))
        self.assertFalse(ok)
        self.assertTrue(err)


if __name__ == "__main__":
    unittest.main()
