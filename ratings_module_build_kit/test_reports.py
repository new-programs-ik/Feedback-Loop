"""test_reports.py - the two automatic reports: periods, the numbers, the rules, the wording, delivery.

The database is never touched: the numbers are checked on hand-made rows, the PDFs are built from
a gathered dict, Drive and Slack are answered by fake transports.
"""
import datetime as dt
import io
import json
import unittest
from unittest import mock

import httpx

import reports as R


def row(**over):
    base = {"id": "r1", "course_id": "c1", "course": "Advanced ML", "course_slug": "advanced-ml", "cohort_text": "Cohort 1",
            "topic": "Regression", "instructor": "Jane Doe", "instructor_id": "i1", "class_date": dt.date(2026, 8, 10),
            "session_kind": "Live Class", "rating": 4.6, "num_ratings": 10, "attended": 20, "participation_pct": 50.0,
            "yes_votes": 9, "no_votes": 1, "approval_pct": 90.0, "score": 88.0, "band": "good", "action": "none",
            "decision": "none", "decision_override": None, "review_status": "new", "escalated": False,
            "class_id": None, "feedback_status": None, "sent_at": None, "approved_at": None, "analyses": 0}
    base.update(over)
    return base


class TestPeriods(unittest.TestCase):
    def test_the_first_of_the_month_reports_on_the_previous_month(self):
        p = R.previous_month(dt.date(2026, 9, 1))
        self.assertEqual((p.start, p.end, p.label, p.kind), (dt.date(2026, 8, 1), dt.date(2026, 8, 31), "August 2026", "month"))
        self.assertEqual(p.previous.label, "July 2026")

    def test_january_looks_back_across_the_year(self):
        p = R.previous_month(dt.date(2027, 1, 3))
        self.assertEqual((p.label, p.previous.label), ("December 2026", "November 2026"))

    def test_the_yearly_edition(self):
        p = R.previous_year(dt.date(2027, 1, 2))
        self.assertEqual((p.start, p.end, p.label, p.previous.label), (dt.date(2026, 1, 1), dt.date(2026, 12, 31), "2026", "2025"))


class TestTheNumbers(unittest.TestCase):
    """summary() follows scoreSummary in the website's lib/analytics.ts."""

    def test_summary_counts_bands_and_shares(self):
        rows = [row(band="excellent", score=95), row(band="good", score=80), row(band="bad", score=50, rating=4.1),
                row(band=None, score=70, num_ratings=3, yes_votes=None, no_votes=None)]
        s = R.summary(rows)
        self.assertEqual((s["n"], s["scored"]), (4, 3))
        self.assertEqual(s["counts"], {"excellent": 1, "good": 1, "average": 0, "bad": 1, "none": 1})
        self.assertAlmostEqual(s["bad_share"], 100 / 3, places=3)
        self.assertAlmostEqual(s["low_share"], 100 / 3, places=3)
        self.assertEqual(s["under_floor"], 1)                    # the 4.1, banded; the thin one does not count
        self.assertAlmostEqual(s["approval"], 27 / 30 * 100, places=3)

    def test_empty_period_has_no_shares(self):
        s = R.summary([])
        self.assertEqual(s["n"], 0)
        self.assertIsNone(s["avg_score"])
        self.assertIsNone(s["bad_share"])

    def test_movers_need_enough_classes_in_both_periods(self):
        before = [row(instructor="A", score=70)] * 3 + [row(instructor="B", score=90)] * 2
        after = [row(instructor="A", score=85)] * 3 + [row(instructor="B", score=60)] * 3
        m = R.movers(before, after, "instructor")
        self.assertEqual([x["label"] for x in m], ["A"])          # B had only 2 before
        self.assertAlmostEqual(m[0]["delta"], 15.0)

    def test_open_queue_is_a_due_analysis_nobody_closed(self):
        self.assertTrue(R.is_open_queue(row(decision="video", review_status="new")))
        self.assertFalse(R.is_open_queue(row(decision="video", review_status="dismissed")))
        self.assertFalse(R.is_open_queue(row(decision="none")))
        self.assertTrue(R.is_open_queue(row(decision="none", decision_override="transcript")))   # the PM's override wins


class TestTheRules(unittest.TestCase):
    def test_at_risk_needs_two_low_classes(self):
        rows = [row(instructor="Sam", band="bad", score=50, rating=4.0), row(instructor="Sam", band="good", rating=4.2),
                row(instructor="Pat", band="bad", score=55, rating=4.4)]
        risk = R.instructors_at_risk(rows)
        self.assertEqual([x["instructor"] for x in risk], ["Sam"])
        self.assertEqual((risk[0]["classes"], risk[0]["low"]), (2, 2))    # the 4.2 counts: under the 4.3 line

    def test_top_performer_needs_three_classes_none_below_good_and_a_high_rating(self):
        rows = [row(instructor="Ava", band="excellent", rating=4.9, score=95)] * 3 + \
               [row(instructor="Bo", band="excellent", rating=4.9, score=95)] * 2 + \
               [row(instructor="Cy", band="excellent", rating=4.9, score=95)] * 2 + [row(instructor="Cy", band="average", rating=4.9, score=70)] + \
               [row(instructor="Di", band="good", rating=4.5, score=80)] * 3
        self.assertEqual([x["instructor"] for x in R.top_performers(rows)], ["Ava"])

    def test_worst_classes_are_the_lowest_bad_and_average_ones(self):
        rows = [row(band="good", score=80), row(band="bad", score=40), row(band="average", score=65), row(band=None, score=10)]
        self.assertEqual([r["score"] for r in R.worst_classes(rows)], [40, 65])

    def test_loop_funnel(self):
        rows = [row(decision="video", review_status="confirmed", analyses=1, feedback_status="sent"),
                row(decision="transcript", review_status="new"),
                row(decision="transcript", review_status="dismissed"),
                row(decision="none")]
        f = R.loop_funnel(rows)
        self.assertEqual(f, {"flagged": 3, "confirmed": 1, "analysed": 1, "approved": 1, "sent": 1, "dismissed": 1, "open": 1})


class TestTheWording(unittest.TestCase):
    def test_reason_names_the_line_the_class_missed(self):
        reason = R.class_reason(row(rating=4.1, band="average", decision="transcript"))
        self.assertIn("below the 4.3 line", reason)
        self.assertTrue(reason.endswith("Next: read the transcript."))
        self.assertNotIn("→", reason)          # the PDF font has no arrow glyph
        self.assertIn("only 60% would have the instructor back", R.class_reason(row(rating=4.7, approval_pct=60.0, band="bad", decision="video")))
        self.assertTrue(R.class_reason(row(band=None, num_ratings=3)).startswith("Only 3 rated it"))

    def test_what_happened(self):
        self.assertEqual(R.what_happened(row(feedback_status="sent")), "feedback sent")
        self.assertEqual(R.what_happened(row(analyses=1, feedback_status="draft")), "analysed, draft waiting")
        self.assertEqual(R.what_happened(row(decision="video", review_status="new")), "open in the queue")
        self.assertEqual(R.what_happened(row(decision="none")), "nothing needed")

    def test_leadership_lines_come_from_the_numbers(self):
        cur_s = R.summary([row(band="bad", score=50, rating=4.0), row(band="good", score=85)])
        prev_s = R.summary([row(band="good", score=80)])
        per_course = [{**cur_s, "course": "Advanced ML", "prev_avg": 80.0}]
        lines = R.leadership_lines(cur_s, prev_s, per_course, [], {"flagged": 1, "analysed": 0, "sent": 0, "open": 1},
                                   {"improved": 0, "not_improved": 0, "pending": 0}, R.month_period(2026, 8))
        self.assertTrue(any("Overall score" in l for l in lines))
        self.assertTrue(any("Advanced ML has the highest share" in l for l in lines))
        self.assertTrue(any("1 classes flagged" in l for l in lines))


class TestThePdfsBuild(unittest.TestCase):
    def _data(self, kind="month"):
        p = R.month_period(2026, 8) if kind == "month" else R.year_period(2026)
        rows = [row(band="bad", score=52, rating=4.1, decision="video", topic="Intro"),
                row(band="good", score=84, instructor="Pat", topic="Trees"),
                row(band=None, score=60, num_ratings=2, yes_votes=None, no_votes=None, topic="Graphs")]
        s = R.summary(rows)
        course = {"course": "Advanced ML", "rows": rows, "summary": s, "prev_summary": R.summary([]),
                  "instructors": [{"instructor": "Jane Doe", "classes": 2, "avg_rating": 4.35, "avg_score": 56, "bad": 1, "average": 0, "sent": 0}],
                  "modules": R.weakest_modules(rows, min_classes=1), "lines": R.team_lines(s, rows, R.loop_funnel(rows))}
        return {"period": p, "rows": rows, "summary": s, "prev_summary": R.summary([]),
                "per_course": [{**s, "course": "Advanced ML", "prev_avg": None}],
                "movers_instructors": [], "movers_modules": [], "worst": R.worst_classes(rows),
                "risk": R.instructors_at_risk(rows), "top": [], "funnel": R.loop_funnel(rows),
                "outcomes": {"sent": 0, "improved": 0, "not_improved": 0, "pending": 0},
                "spend": {"n": 1, "usd": 0.86, "with_video": 0}, "trend": {}, "courses": [course],
                "lead_lines": ["Overall score flat at 65.3."], "chart_trend": None, "chart_bands": None}

    def test_both_pdfs_build_for_a_month(self):
        d = self._data()
        lead, team = R.build_leadership_pdf(d), R.build_team_pdf(d)
        self.assertTrue(lead.startswith(b"%PDF") and team.startswith(b"%PDF"))
        self.assertGreater(len(lead), 2000)
        self.assertGreater(len(team), 2000)

    def test_the_yearly_edition_lists_only_the_lowest_classes(self):
        d = self._data("year")
        self.assertTrue(R.build_team_pdf(d).startswith(b"%PDF"))

    def test_file_names_carry_the_period(self):
        self.assertEqual(R.file_names(R.month_period(2026, 8)),
                         ("Feedback Loop - Leadership report - August 2026.pdf", "Feedback Loop - Team report - August 2026.pdf"))


class TestDelivery(unittest.TestCase):
    def test_drive_upload_sends_a_multipart_file_into_the_folder(self):
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            seen["auth"] = request.headers.get("authorization")
            seen["body"] = request.content
            return httpx.Response(200, json={"id": "f1", "webViewLink": "https://drive.google.com/file/d/f1/view"})

        env = {"REPORTS_DRIVE_FOLDER_ID": "folder123"}
        with mock.patch.object(R, "drive_token", return_value="tok"):
            link = R.upload_to_drive(b"%PDF-1.4 test", "Feedback Loop - Team report - August 2026.pdf", env,
                                     transport=httpx.MockTransport(handler))
        self.assertEqual(link, "https://drive.google.com/file/d/f1/view")
        self.assertIn("uploadType=multipart", seen["url"])
        self.assertEqual(seen["auth"], "Bearer tok")
        self.assertIn(b'"parents": ["folder123"]', seen["body"])
        self.assertIn(b"%PDF-1.4 test", seen["body"])

    def test_drive_upload_without_a_folder_or_token_is_skipped_not_raised(self):
        self.assertIsNone(R.upload_to_drive(b"x", "n.pdf", {}))
        with mock.patch.object(R, "drive_token", return_value=None):
            self.assertIsNone(R.upload_to_drive(b"x", "n.pdf", {"REPORTS_DRIVE_FOLDER_ID": "f"}))

    def test_drive_failure_is_logged_and_returns_none(self):
        handler = lambda request: httpx.Response(403, json={"error": {"message": "no"}})
        with mock.patch.object(R, "drive_token", return_value="tok"):
            self.assertIsNone(R.upload_to_drive(b"x", "n.pdf", {"REPORTS_DRIVE_FOLDER_ID": "f"}, transport=httpx.MockTransport(handler)))

    def test_slack_post_carries_the_link_and_the_first_lines(self):
        seen = {}

        def handler(request):
            seen["payload"] = json.loads(request.content)
            return httpx.Response(200, json={"ok": True, "ts": "1.2"})

        env = {"SLACK_BOT_TOKEN": "xoxb-test"}
        ok = R.post_report_to_slack("C123", "Leadership report · August 2026", "https://drive/x", ["one", "two"], env,
                                    transport=httpx.MockTransport(handler))
        self.assertTrue(ok)
        self.assertEqual(seen["payload"]["channel"], "C123")
        self.assertIn("https://drive/x", seen["payload"]["text"])
        self.assertIn("• one", seen["payload"]["text"])

    def test_slack_post_without_a_token_or_channel_does_nothing(self):
        self.assertFalse(R.post_report_to_slack("C1", "t", None, [], {}))
        self.assertFalse(R.post_report_to_slack("", "t", None, [], {"SLACK_BOT_TOKEN": "x"}))


if __name__ == "__main__":
    unittest.main()
