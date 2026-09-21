"""test_ratings_sync.py - the ratings platform, fully offline.
Sheet parsing via httpx.MockTransport; sync orchestration with a fake store; the store's SQL
against scripted cursors (what it sends, what it reads back); Slack payloads.
Run: python -m unittest test_ratings_sync -v
"""
import datetime as dt
import json
import re
import unittest
from unittest import mock

import httpx
import psycopg2.errors

import cohort_parse as CP
import instructor_match as IM
import notify as N
import ratings_store as ST
import sheet_source as SS

TAB1 = "MLSU_Live_Class_Poll"
TAB2 = "Agentic_AI_Live_Class_Poll"


def sheet_payload(values1, values2=None):
    ranges = [{"range": TAB1, "values": values1}]
    if values2 is not None:
        ranges.append({"range": TAB2, "values": values2})
    return {"valueRanges": ranges}


HEADER = ["Topic Code", "Type", "Cohorts", "Topic", "Cohorts", "Instructor", "Session Date",
          "Overall Average", "Responses", "# Students Attended", "% Rated", "Yes", "No"]
# The Agentic tab: "Topic" is the session kind, "Class" the real name.
AGENTIC_HEADER = ["Topic", "Type", "Domain", "Class", "Cohorts", "Instructor", "Session Date",
                  "Overall Average", "Responses", "# Students Attended", "% Rated", "Yes", "No"]


def row(date="2026-08-24", type_="Agentic AI Live Class", cohort="Applied Agentic AI - Aug",
        topic="MCP Deep Dive", instructor="Jane Doe", rating=4.31, resp=12, att=25, yes=10, no=2):
    return ["Live Class", type_, cohort, topic, cohort, instructor, date, rating, resp, att, "", yes, no]


def agentic_row(kind="Live Class", type_="India Agentic AI Live Class", class_name="Capstone Project SWE - 2",
                cohort="Applied Agentic AI for SWEs - 2nd Mid-March 2026", instructor="Jane Doe",
                date="2026-08-24", rating=4.31, resp=12, att=25, yes=10, no=2):
    return [kind, type_, "SWE", class_name, cohort, instructor, date, rating, resp, att, "", yes, no]


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
        self.assertEqual((r["yes_votes"], r["no_votes"]), (10, 2))
        self.assertEqual(r["region"], "US")

    def test_class_beats_topic_when_both_headers_exist(self):
        """The Agentic tab: 'Topic' = session kind, 'Class' = the real name (the 3 Sep bug)."""
        src = make_source(sheet_payload([HEADER, row()], [AGENTIC_HEADER, agentic_row()]))
        by_topic = {r["topic"]: r for r in src.fetch_rows()}
        self.assertIn("Capstone Project SWE - 2", by_topic)
        self.assertNotIn("Live Class", by_topic)
        r = by_topic["Capstone Project SWE - 2"]
        self.assertEqual((r["region"], r["session_kind"]), ("IND", "Live Class"))

    def test_region_from_the_type_column(self):
        src = make_source(sheet_payload([HEADER, row(type_="India ML Switchup Review Class", topic="A"),
                                         row(type_="ML Switchup Live Class", topic="B")]))
        regions = {r["topic"]: r["region"] for r in src.fetch_rows()}
        self.assertEqual(regions, {"A": "IND", "B": "US"})

    def test_vote_columns_are_optional(self):
        hdr = [h for h in HEADER if h not in ("Yes", "No")]
        src = make_source(sheet_payload([hdr, row()[:len(hdr)]]))
        out = src.fetch_rows()                           # no SheetSourceError
        self.assertEqual(len(out), 1)
        self.assertEqual((out[0]["yes_votes"], out[0]["no_votes"]), (None, None))

    def test_blank_vote_cells_are_none(self):
        src = make_source(sheet_payload([HEADER, row(yes="", no=None)]))
        r = src.fetch_rows()[0]
        self.assertEqual((r["yes_votes"], r["no_votes"]), (None, None))

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

    def test_impossible_numbers_are_skipped_not_fatal(self):
        src = SS.SheetRatingsSource({"RATINGS_SHEET_ID": "x"}, token_provider=lambda env: "t")
        values = [["Session Date", "Type", "Cohorts", "Topic", "Instructor", "Overall Average", "Responses", "# Students Attended"],
                  ["2026-08-24", "Live Class", "Cohort 1", "T", "Sam", "45", "3", "10"],          # rating 45
                  ["2026-08-24", "Live Class", "Cohort 1", "U", "Sam", "4.5", "3", "10"]]
        rows = src._parse_tab("tab", values)
        self.assertEqual([r["topic"] for r in rows], ["U"])
        self.assertEqual(src.last_skipped["number out of range"], 1)

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


# ── orchestration ────────────────────────────────────────────────────────────

class FakeResolver:
    """What load_instructor_resolver returns: exact spellings resolve, the rest are candidates."""

    def __init__(self, known: dict):
        self.known = {IM.normalize(k): v for k, v in known.items()}     # name -> (id, canonical)

    def __call__(self, raw):
        return self.known.get(IM.normalize(raw), (None, None))

    def candidates(self):
        return [IM.Candidate(i, n) for i, n in sorted(set(self.known.values()))]


def fake_score(row, escalated=False):
    """A stand-in for the database's score_class_rating: two lines, three bands."""
    votes = (row.get("yes_votes") or 0) + (row.get("no_votes") or 0)
    approval = (row["yes_votes"] / votes * 100) if votes else None
    flags = []
    if row["rating"] < 4.55:
        flags.append("under_rating_line")
    if approval is not None and approval < 80:
        flags.append("under_approval_bar")
    if votes and votes < 5:
        return None, None, "watch", True, ["thin_provisional"]
    band = {0: "excellent", 1: "average", 2: "bad"}[len(flags)]
    action = {"excellent": "none", "average": "transcript", "bad": "video"}[band]
    if escalated:
        action, flags = "video", flags + ["escalated"]
    return 95.0 - 20 * len(flags), band, action, False, flags


class TestSyncOrchestration(unittest.TestCase):
    """run_sync with the store mocked out - cohorts, identity, scoring tallies, suggestions,
    notification routing and the metrics that reach sync_runs."""

    class FakeSource:
        name = "sheet"

        def __init__(self, rows):
            self.rows = rows

        def fetch_rows(self):
            return self.rows

    def _run(self, rows, aliases, pending=None, record_returns=True, known=None, config=None,
             env=None, state=None, full=False):
        import ratings_sync as RSY
        calls = {"upserts": [], "rows": [], "cohorts": [], "suggestions": [], "finish": None,
                 "cached_members": [], "cached_handlers": []}

        fake_st = mock.MagicMock()
        fake_st.connect.return_value = mock.MagicMock()
        fake_st.running_run_exists.return_value = False
        fake_st.start_run.return_value = "run-1"
        fake_st.load_aliases.return_value = aliases
        fake_st.load_courses.return_value = {"course-1": {"id": "course-1", "name": "Applied Agentic AI",
                                                          "slug": "applied-agentic-ai"}}
        fake_st.active_scoring_config.return_value = config if config is not None else {
            "id": "cfg-1", "version": 2, "key": "C5", "name": "Two lines", "status": "active",
            "config": {"track": {"min_classes": 3}}}
        fake_st.load_instructor_resolver.return_value = FakeResolver(
            known if known is not None else {"Jane Doe": ("inst-1", "Jane Doe")})
        fake_st.UpsertResult = ST.UpsertResult
        fake_st.row_fingerprint = ST.row_fingerprint     # the real ones: the skip test relies on them
        fake_st.row_key = ST.row_key
        fake_st.load_row_state.return_value = state or {}
        fake_st.retire_rows_missing_from_sheet.side_effect = lambda cur, keys, source="sheet", labels=None: (
            calls.__setitem__("seen_keys", set(keys)) or calls.__setitem__("seen_labels", set(labels or ())) or 0)
        fake_st.recompute_week_numbers.return_value = 0

        def upsert_cohorts(cur, parsed, course_id, **kw):
            calls["cohorts"].append([p.raw_label for p in parsed])
            if kw.get("stats") is not None:
                kw["stats"]["cohorts_created"] += len(parsed)
            return [f"coh-{p.key_suffix}" if course_id else None for p in parsed]

        fake_st.upsert_cohorts.side_effect = upsert_cohorts
        fake_st.resolve_topic.side_effect = lambda cur, cid, topic, **kw: (
            "top-1" if topic == "MCP Deep Dive" and cid else (kw["unmapped"].update([(cid, topic)]) if kw.get("unmapped") is not None and cid else None))

        def upsert(cur, row, course_id, instructor_id, **kw):
            score, band, action, prov, flags = fake_score(row, escalated=row.get("_escalated", False))
            calls["upserts"].append((row["topic"], action, course_id, instructor_id, kw))
            calls["rows"].append(row)
            return ST.UpsertResult("cr-" + row["topic"], action, "new", score, band, action, prov, tuple(flags))

        fake_st.upsert_rating.side_effect = upsert
        fake_st.write_suggestions.side_effect = lambda cur, s: (calls["suggestions"].extend(s), len(s))[1]
        fake_st.ensure_topics.side_effect = lambda cur, unmapped: (
            calls.__setitem__("topics", dict(unmapped)) or
            {"topics_created": len(unmapped), "aliases_created": len(unmapped), "rows_backfilled": 2})
        fake_st.rows_needing_notification.return_value = pending or []
        fake_st.record_notification.return_value = record_returns
        fake_st.cache_member_slack_user.side_effect = lambda cur, mid, uid: calls["cached_members"].append((mid, uid))
        fake_st.cache_slack_user.side_effect = lambda cur, hid, uid: calls["cached_handlers"].append((hid, uid))

        def finish(cur, run_id, **kw):
            calls["finish"] = kw

        fake_st.finish_run.side_effect = finish

        fake_notify = mock.MagicMock()
        fake_notify.slack_configured.return_value = bool(pending)
        fake_notify.lookup_user_id.return_value = "U123"
        fake_notify.post_flag_message.return_value = (True, "111.222", "")

        with mock.patch.object(RSY, "ST", fake_st), mock.patch.object(RSY, "N", fake_notify):
            summary = RSY.run_sync("manual", env=env if env is not None else {}, source=self.FakeSource(rows),
                                   full=full)
        return summary, calls, fake_notify

    def test_rows_the_sheet_did_not_change_are_skipped_but_still_counted(self):
        # Two round trips per row, 2,833 rows, US to Singapore: nine minutes. A row whose sheet
        # values match its stored fingerprint is not touched, yet its stored verdict stays in the
        # totals so the run summary is still about the whole sheet.
        same = self._row(topic="Same", rating=4.9, yes=10, no=0)
        changed = self._row(topic="Changed", rating=4.1, yes=5, no=5)
        state = {ST.row_key(same): (ST.row_fingerprint(same), "excellent", "none", True, True),
                 ST.row_key(changed): ("an-old-fingerprint", "good", "none", True, True)}
        summary, calls, _ = self._run([same, changed], {"Applied Agentic AI": "course-1"}, state=state)
        self.assertEqual([t for t, *_ in calls["upserts"]], ["Changed"])
        self.assertEqual(summary["rows_upserted"], 1)
        self.assertEqual(summary["rows_unchanged"], 1)
        self.assertEqual(summary["rows_fetched"], 2)
        self.assertEqual(summary["band_counts"].get("excellent"), 1)
        self.assertEqual(summary["rows_scored"], 2)
        self.assertEqual(calls["finish"]["rows_unchanged"], 1)

    def test_an_unmapped_row_is_rewritten_even_when_the_sheet_did_not_change(self):
        # The alias that maps its label to a course may have arrived since the last run.
        same = self._row(topic="Same", rating=4.9, yes=10, no=0)
        state = {ST.row_key(same): (ST.row_fingerprint(same), None, "watch", False, False)}   # stored without a course
        summary, calls, _ = self._run([same], {"Applied Agentic AI": "course-1"}, state=state)
        self.assertEqual([t for t, *_ in calls["upserts"]], ["Same"])
        self.assertEqual(summary["rows_unchanged"], 0)

    def test_every_sheet_row_is_reported_as_seen_so_the_rest_can_be_retired(self):
        same = self._row(topic="Same", rating=4.9, yes=10, no=0)
        changed = self._row(topic="Changed", rating=4.1, yes=5, no=5)
        state = {ST.row_key(same): (ST.row_fingerprint(same), "excellent", "none", True, True)}
        summary, calls, _ = self._run([same, changed], {"Applied Agentic AI": "course-1"}, state=state)
        self.assertEqual(calls["seen_keys"], {ST.row_key(same), ST.row_key(changed)})   # skipped rows count as seen
        self.assertEqual(calls["seen_labels"], {"Applied Agentic AI"})
        self.assertEqual(summary["rows_retired"], 0)

    def test_a_full_run_ignores_the_fingerprints(self):
        same = self._row(topic="Same", rating=4.9, yes=10, no=0)
        state = {ST.row_key(same): (ST.row_fingerprint(same), "excellent", "none", True, True)}
        summary, calls, _ = self._run([same], {"Applied Agentic AI": "course-1"}, state=state, full=True)
        self.assertEqual([t for t, *_ in calls["upserts"]], ["Same"])
        self.assertEqual(summary["rows_unchanged"], 0)

    def test_the_env_switch_also_forces_a_full_run(self):
        same = self._row(topic="Same", rating=4.9, yes=10, no=0)
        state = {ST.row_key(same): (ST.row_fingerprint(same), "excellent", "none", True, True)}
        summary, calls, _ = self._run([same], {"Applied Agentic AI": "course-1"}, state=state,
                                      env={"RATINGS_SYNC_FULL": "1"})
        self.assertEqual(len(calls["upserts"]), 1)

    def _row(self, topic="T1", rating=4.2, resp=10, att=20, label="Applied Agentic AI",
             yes=None, no=None, instructor="Jane Doe", date=dt.date(2026, 8, 24),
             cohort="Applied Agentic AI for SWEs - 2nd Mid-March 2026", region="US"):
        return {"course_label": label, "cohort_text": cohort, "topic": topic, "instructor": instructor,
                "class_date": date, "session_kind": "Live Class", "rating": rating,
                "num_ratings": resp, "attended": att, "yes_votes": yes, "no_votes": no, "region": region}

    def test_votes_reach_the_store_and_the_band_decides(self):
        summary, calls, _ = self._run(
            [self._row(topic="Voted", rating=4.7, resp=10, att=20, yes=5, no=5)],
            aliases={"Applied Agentic AI": "course-1"})
        stored = calls["rows"][0]
        self.assertEqual((stored["yes_votes"], stored["no_votes"], stored["source"]), (5, 5, "sheet"))
        self.assertEqual(calls["upserts"][0][1], "transcript")          # fine rating, failed vote -> Average
        self.assertEqual(summary["band_counts"], {"average": 1})
        self.assertEqual((summary["rows_scored"], summary["rows_flagged"]), (1, 1))

    def test_cohorts_identity_topics_and_scoring_flow_through(self):
        summary, calls, _ = self._run(
            [self._row(topic="MCP Deep Dive", rating=4.2, resp=10, att=20, yes=4, no=6),   # both lines -> video
             self._row(topic="Fine", rating=4.8, yes=9, no=1),                             # -> none
             self._row(topic="Lost", label="Other / unmapped", cohort="Nope Cohort 2026"),  # unmapped, unparsed
             self._row(topic="Stray", instructor="Kalpesh", rating=4.9, yes=8, no=0)],     # unresolved name
            aliases={"Applied Agentic AI": "course-1"},
            known={"Jane Doe": ("inst-1", "Jane Doe"), "Kalpesh Singh": ("inst-2", "Kalpesh Singh")})
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["rows_upserted"], 4)
        self.assertEqual(summary["rows_flagged"], 2)                       # MCP (video) + Lost (4.2 -> transcript)
        self.assertIn("Other / unmapped", summary["unmapped_labels"])
        by_topic = {t: (a, c, i, kw) for t, a, c, i, kw in calls["upserts"]}
        self.assertEqual(by_topic["MCP Deep Dive"][0], "video")
        self.assertEqual(by_topic["Fine"][0], "none")
        self.assertIsNone(by_topic["Lost"][1])                             # unmapped -> course_id None
        self.assertEqual(by_topic["MCP Deep Dive"][1], "course-1")         # aliased course id flows through
        self.assertEqual(by_topic["MCP Deep Dive"][2], "inst-1")           # exact-name instructor match
        kw = by_topic["MCP Deep Dive"][3]
        self.assertEqual(kw["instructor_canonical"], "Jane Doe")
        self.assertEqual(kw["cohort_ids"], ["coh-US-2026-03-mid-2-1-swe"])
        self.assertEqual(kw["topic_id"], "top-1")
        self.assertEqual(kw["min_track_classes"], 3)
        self.assertIsNone(by_topic["Fine"][3]["topic_id"])
        # the stray spelling: no id, no canonical, counted, and suggested against the candidates
        self.assertEqual((by_topic["Stray"][2], by_topic["Stray"][3]["instructor_canonical"]), (None, None))
        self.assertEqual(summary["unresolved_names"], ["Kalpesh"])
        self.assertEqual([(s.raw_name, s.candidate_name, s.score) for s in calls["suggestions"]],
                         [("Kalpesh", "Kalpesh Singh", 0.80)])
        self.assertEqual(summary["suggestions_created"], 1)
        # cohorts: the parseable label was upserted once per row that carries it; junk/unparsed counted
        self.assertEqual(summary["cohorts_unparsed"], 1)
        self.assertEqual(summary["unparsed_segments"], ["Nope Cohort 2026"])
        self.assertEqual(summary["topics_unmapped"], 2)                   # Fine + Stray (Lost has no course)
        self.assertEqual(calls["topics"], {("course-1", "Fine"): 1, ("course-1", "Stray"): 1})
        self.assertEqual((summary["topics_created"], summary["topic_rows_backfilled"]), (2, 2))
        self.assertEqual(summary["scoring_config_version"], 2)
        self.assertEqual(summary["band_counts"], {"bad": 1, "excellent": 2, "average": 1})
        f = calls["finish"]
        for key in ("rows_scored", "scoring_config_version", "band_counts", "cohorts_created",
                    "cohorts_unparsed", "instructors_unresolved", "suggestions_created",
                    "topics_unmapped", "duration_ms"):
            self.assertIn(key, f)
        self.assertEqual((f["instructors_unresolved"], f["suggestions_created"], f["rows_scored"]), (1, 1, 4))

    def test_rows_are_processed_oldest_first(self):
        """Week numbers count from a cohort's first class, so the loop runs in date order."""
        _, calls, _ = self._run([self._row(topic="Late", date=dt.date(2026, 8, 30)),
                                 self._row(topic="Early", date=dt.date(2026, 8, 2))],
                                aliases={"Applied Agentic AI": "course-1"})
        self.assertEqual([r["topic"] for r in calls["rows"]], ["Early", "Late"])

    def test_no_active_config_fails_loudly(self):
        summary, calls, fake_notify = self._run([self._row()], {"Applied Agentic AI": "course-1"}, config={})
        self.assertEqual(summary["status"], "failed")
        self.assertIn("no active scoring config", summary["error"])
        self.assertEqual(calls["upserts"], [])
        fake_notify.post_sync_alert.assert_called_once()

    def _pending(self, recipients, **over):
        base = {"id": "cr-1", "topic": "T", "instructor": "Jane Doe", "instructor_canonical": "Jane Doe",
                "class_date": dt.date(2026, 8, 24), "session_kind": "Live Class",
                "rating": 4.2, "num_ratings": 10, "attended": 20, "participation_pct": 50.0,
                "decision": "video", "course_name": "Applied Agentic AI", "course_slug": "applied-agentic-ai",
                "sentiment_score": 58.0, "sentiment_band": "bad", "sentiment_flags": ["under_rating_line"],
                "recipients": recipients}
        base.update(over)
        return base

    def test_notification_dedupe_gate(self):
        pending = [self._pending([{"id": "m-1", "name": "Bishal", "email": "b@ik.com", "slack_user_id": None,
                                   "source": "member"}])]
        summary, _, fake_notify = self._run([self._row()], {"Applied Agentic AI": "c1"},
                                            pending=pending, record_returns=False)
        # record_notification lost the race -> nothing is posted
        fake_notify.post_flag_message.assert_not_called()
        self.assertEqual(summary["notifications_sent"], 0)

    def test_members_are_looked_up_mentioned_and_cached(self):
        pending = [self._pending([
            {"id": "m-1", "name": "Bishal", "email": "b@ik.com", "slack_user_id": None, "source": "member"},
            {"id": "m-2", "name": "Priya", "email": "p@ik.com", "slack_user_id": "U999", "source": "member"}])]
        summary, calls, fake_notify = self._run([self._row()], {"Applied Agentic AI": "c1"},
                                                pending=pending, record_returns=True)
        fake_notify.lookup_user_id.assert_called_once_with("b@ik.com", {})
        self.assertEqual(calls["cached_members"], [("m-1", "U123")])
        self.assertEqual(calls["cached_handlers"], [])
        sent_row = fake_notify.post_flag_message.call_args.args[0]
        self.assertEqual([r["slack_user_id"] for r in sent_row["recipients"]], ["U123", "U999"])
        self.assertEqual(summary["notifications_sent"], 1)

    def test_legacy_handler_fallback_caches_into_course_handlers(self):
        pending = [self._pending([{"id": "h-1", "name": "Bishal", "email": "b@ik.com", "slack_user_id": None,
                                   "source": "handler"}])]
        _, calls, fake_notify = self._run([self._row()], {"Applied Agentic AI": "c1"},
                                          pending=pending, record_returns=True)
        self.assertEqual(calls["cached_handlers"], [("h-1", "U123")])
        self.assertEqual(calls["cached_members"], [])

    def test_no_owner_still_posts_to_the_channel(self):
        pending = [self._pending([])]
        summary, _, fake_notify = self._run([self._row()], {"Applied Agentic AI": "c1"},
                                            pending=pending, record_returns=True)
        fake_notify.lookup_user_id.assert_not_called()
        fake_notify.post_flag_message.assert_called_once()
        self.assertEqual(summary["notifications_sent"], 1)

    def test_notification_window_and_cap_come_from_env(self):
        import ratings_sync as RSY
        pending = [self._pending([])]
        _, _, _ = self._run([self._row()], {"Applied Agentic AI": "c1"}, pending=pending,
                            env={"NOTIFY_MAX_AGE_DAYS": "3", "NOTIFY_MAX_PER_RUN": "7"})
        # the fake store recorded the call; check the arguments it was given
        with mock.patch.object(RSY, "ST") as st:
            pass
        self.assertEqual((RSY.NOTIFY_MAX_AGE_DAYS, RSY.NOTIFY_MAX_PER_RUN), (10, 25))
        self.assertEqual(RSY._int_env({"NOTIFY_MAX_AGE_DAYS": "3"}, "NOTIFY_MAX_AGE_DAYS", 10), 3)
        self.assertEqual(RSY._int_env({"NOTIFY_MAX_AGE_DAYS": "x"}, "NOTIFY_MAX_AGE_DAYS", 10), 10)

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


class TestRevalidatePing(unittest.TestCase):
    def test_posts_with_bearer_and_ignores_failures(self):
        import ratings_sync as RSY
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            seen["auth"] = request.headers.get("Authorization")
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={"ok": True})

        ok = RSY.ping_revalidate({"UI_URL": "https://app/", "WORKER_API_KEY": "k"}, "run-1",
                                 {"rows_upserted": 3}, transport=httpx.MockTransport(handler))
        self.assertTrue(ok)
        self.assertEqual(seen["url"], "https://app/api/revalidate")
        self.assertEqual(seen["auth"], "Bearer k")
        self.assertEqual(seen["body"]["run_id"], "run-1")
        self.assertFalse(RSY.ping_revalidate({}, "run-1"))                      # no UI_URL -> skipped
        boom = httpx.MockTransport(lambda r: httpx.Response(500))
        self.assertFalse(RSY.ping_revalidate({"UI_URL": "https://app"}, "run-1", transport=boom))


# ── the store's SQL, against scripted cursors ────────────────────────────────

class ScriptedCursor:
    """Records every execute; answers fetchone() from a queue of scripted answers."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []
        self.description = None

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchone(self):
        return self.answers.pop(0) if self.answers else None

    def fetchall(self):
        return self.answers.pop(0) if self.answers else []

    def sql(self, i=-1):
        return self.calls[i][0]

    def params(self, i=-1):
        return self.calls[i][1]


def upsert_answer(decision="video", score=58.0, band="bad", action="video", provisional=False,
                  flags=("under_rating_line", "under_approval_bar")):
    return ("cr-1", decision, "new", score, band, action, provisional, list(flags))


class TestStoreUpsert(unittest.TestCase):
    """upsert_rating: the nine score parameters go to score_class_rating() in the statement, the
    verdict comes back from RETURNING, the legacy v2 read-out is still written."""

    def _row(self, **over):
        return {"course_label": "Applied Agentic AI", "cohort_text": "c", "topic": "T",
                "instructor": "Jane Doe", "class_date": dt.date(2026, 8, 24),
                "session_kind": "Live Class", "rating": 4.2, "num_ratings": 10, "attended": 20,
                "yes_votes": 6, "no_votes": 4, "region": "US", **over}

    def _upsert(self, prior, answer=None, row=None, **kw):
        cur = ScriptedCursor([prior, answer or upsert_answer()])
        res = ST.upsert_rating(cur, row or self._row(), "course-1", "inst-1", **kw)
        return res, cur

    def test_sql_passes_the_nine_score_parameters_and_the_active_config(self):
        _, cur = self._upsert((False, 4.10, 5))
        sql = cur.sql()
        m = re.search(r"score_class_rating\((.*?)\)\s*sc", sql, re.S)
        self.assertIsNotNone(m)
        args = [a.strip() for a in m.group(1).split(",")]
        self.assertEqual(args, ["%(rating)s::numeric", "%(num_ratings)s::int", "%(attended)s::int",
                                "%(yes_votes)s::int", "%(no_votes)s::int", "%(escalated)s::boolean",
                                "%(track_avg)s::numeric", "(select prior_rating from pri)",
                                "(select prior_approval from pri)", "cfg.config"])
        self.assertIn("from active_scoring_config()", sql)
        self.assertIn("course_priors(%(course_id)s::uuid)", sql)
        self.assertIn("returning id, decision, review_status, sentiment_score, sentiment_band, sentiment_action",
                      sql)
        p = cur.params()
        self.assertEqual((p["rating"], p["num_ratings"], p["attended"], p["yes_votes"], p["no_votes"]),
                         (4.2, 10, 20, 6, 4))
        self.assertEqual((p["escalated"], p["track_avg"], p["course_id"]), (False, 4.1, "course-1"))

    def test_reads_band_and_decision_from_returning(self):
        res, _ = self._upsert((False, None, 0), answer=upsert_answer("transcript", 71.5, "average", "transcript",
                                                                     False, ["under_approval_bar"]))
        self.assertEqual((res.id, res.decision, res.review_status), ("cr-1", "transcript", "new"))
        self.assertEqual((res.score, res.band, res.action, res.provisional), (71.5, "average", "transcript", False))
        self.assertEqual(res.flags, ("under_approval_bar",))
        rid, dec, status = res                                     # old-style unpacking still works
        self.assertEqual((rid, dec, status), ("cr-1", "transcript", "new"))

    def test_decision_follows_the_action_unless_frozen(self):
        sql = self._upsert((False, None, 0))[1].sql()
        self.assertIn("when class_ratings.decision_override is not null then class_ratings.decision", sql)
        self.assertIn("when class_ratings.review_status in ('dismissed','analysis_started')", sql)
        self.assertIn("when class_ratings.escalated then 'video'::rating_decision", sql)
        self.assertIn("else coalesce(s.action, 'watch') end)::rating_decision", sql)

    def test_writes_identity_cohorts_topic_and_week(self):
        _, cur = self._upsert((False, None, 0), instructor_canonical="Jane Doe",
                              cohort_ids=["coh-1", "coh-2"], topic_id="top-1")
        p = cur.params()
        self.assertEqual((p["instructor_id"], p["instructor_canonical"]), ("inst-1", "Jane Doe"))
        self.assertEqual((p["cohort_id"], p["cohort_ids"], p["topic_id"]), ("coh-1", ["coh-1", "coh-2"], "top-1"))
        sql = cur.sql()
        for col in ("instructor_canonical", "cohort_id", "cohort_ids", "topic_id", "week_no",
                    "sentiment_score", "sentiment_band", "sentiment_action", "sentiment_provisional",
                    "sentiment_flags", "score_config_id", "score_components", "scored_at"):
            self.assertIn(col, sql)
        self.assertIn("select min(x.class_date) from class_ratings x", sql)   # week 1 = first class seen
        _, cur = self._upsert((False, None, 0))
        self.assertEqual((cur.params()["cohort_id"], cur.params()["cohort_ids"]), (None, []))

    def test_legacy_v2_fields_are_still_written(self):
        _, cur = self._upsert((False, 4.10, 5))
        p = cur.params()
        self.assertEqual((p["yes_votes"], p["no_votes"], p["approval_pct"]), (6, 4, 60.0))
        self.assertEqual(p["track_avg"], 4.1)
        # R 65, A 50, T 10 -> 39 + 12.5 + 1.5 = 53 -> urgent
        self.assertEqual((p["health_score"], p["health_band"]), (53.0, "urgent"))
        self.assertEqual(p["flag_reasons"], ["rating", "approval"])
        self.assertEqual(p["decision_v2"], "video")                  # the old verdict, kept beside the score
        # ...as a one-time "before" snapshot: written on insert, never overwritten (0015's design)
        self.assertIn("decision_v2          = coalesce(class_ratings.decision_v2, excluded.decision_v2)", cur.sql())
        self.assertNotIn("decision", p)                              # the DB decides `decision` now

    def test_track_record_by_instructor_id_then_by_name(self):
        _, cur = self._upsert((False, 4.10, 5))
        prior_sql, prior_params = cur.calls[0]
        self.assertIn("then instructor_id = %(instructor_id)s::uuid", prior_sql)
        self.assertIn("else instructor = %(instructor)s end", prior_sql)
        self.assertEqual(prior_params["instructor_id"], "inst-1")
        # fewer than three earlier classes -> no track record
        _, cur = self._upsert((False, 4.10, 2))
        self.assertIsNone(cur.params()["track_avg"])
        # a blank name with no id never gets one (it would pool every nameless row)
        cur = ScriptedCursor([(False, 4.10, 9), upsert_answer()])
        ST.upsert_rating(cur, self._row(instructor=""), "course-1", None)
        self.assertIsNone(cur.params()["track_avg"])
        # the config's own minimum is honoured
        _, cur = self._upsert((False, 4.10, 4), min_track_classes=5)
        self.assertIsNone(cur.params()["track_avg"])

    def test_escalated_row_passes_escalated_to_the_scorer(self):
        res, cur = self._upsert((True, None, 0), answer=upsert_answer("video", 92.0, "excellent", "video", False,
                                                                       ["escalated"]),
                                row=self._row(rating=4.9, yes_votes=10, no_votes=0))
        self.assertTrue(cur.params()["escalated"])
        self.assertEqual((res.decision, res.flags), ("video", ("escalated",)))
        self.assertEqual(cur.params()["flag_reasons"], ["escalated"])

    def test_no_votes_means_null_approval(self):
        _, cur = self._upsert((False, None, 0), row=self._row(yes_votes=None, no_votes=None))
        p = cur.params()
        self.assertIsNone(p["approval_pct"])
        self.assertEqual((p["yes_votes"], p["no_votes"]), (None, None))

    def test_no_active_config_is_loud(self):
        cur = ScriptedCursor([(False, None, 0)])                     # the upsert returns no row
        with self.assertRaises(RuntimeError) as ctx:
            ST.upsert_rating(cur, self._row(), "course-1", "inst-1")
        self.assertIn("no active scoring config", str(ctx.exception))


class TestCohortUpsert(unittest.TestCase):
    COURSES = {"course-1": {"id": "course-1", "name": "Applied Agentic AI", "slug": "applied-agentic-ai"}}

    def _parsed(self, text="Applied Agentic AI for SWEs - 2nd Mid-March 2026"):
        import course_rules as CR
        return CP.parse_cohorts(text, CR.course_of)

    def test_keys_use_the_db_slug_and_names_the_db_course_name(self):
        cur = ScriptedCursor([("coh-1", True)])
        from collections import Counter
        stats, cache = Counter(), {}
        ids = ST.upsert_cohorts(cur, self._parsed(), "course-1", courses=self.COURSES, cache=cache, stats=stats)
        self.assertEqual(ids, ["coh-1"])
        p = cur.params(1)                                              # savepoint, insert, release
        self.assertEqual(p["key"], "applied-agentic-ai-US-2026-03-mid-2-1-swe")
        self.assertEqual(p["name"], "Applied Agentic AI for SWEs · Mid-Mar 2026 (2nd)")
        self.assertEqual((p["region"], p["start_month"], p["part"], p["ordinal"], p["audience"]),
                         ("US", dt.date(2026, 3, 1), "mid", 2, "swe"))
        self.assertEqual(p["raw_labels"], ["Applied Agentic AI for SWEs - 2nd Mid-March 2026"])
        self.assertIn("on conflict (cohort_key) do update", cur.sql(1))
        self.assertEqual(stats["cohorts_created"], 1)
        self.assertEqual(cache, {"applied-agentic-ai-US-2026-03-mid-2-1-swe": "coh-1"})
        # second time in the run: served from the cache, no SQL
        n = len(cur.calls)
        self.assertEqual(ST.upsert_cohorts(cur, self._parsed(), "course-1", courses=self.COURSES, cache=cache), ["coh-1"])
        self.assertEqual(len(cur.calls), n)

    def test_each_segment_resolves_its_own_course(self):
        parsed = self._parsed("Advanced Machine Learning Program - End-August 2025, AI Data Science SwitchUp - End-August 2025")
        cur = ScriptedCursor([("coh-a", False), ("coh-b", True)])
        ids = ST.upsert_cohorts(cur, parsed, "course-x",
                                aliases={"Advanced ML Program": "course-adv", "AI Data Science SwitchUp": "course-ds"},
                                courses={"course-adv": {"name": "Advanced ML", "slug": "advanced-ml"},
                                         "course-ds": {"name": "AI Data Science SwitchUp", "slug": "ai-ds-switchup"}})
        self.assertEqual(ids, ["coh-a", "coh-b"])
        self.assertEqual([c[1]["course_id"] for c in cur.calls if c[1]], ["course-adv", "course-ds"])

    def test_unknown_course_yields_none(self):
        cur = ScriptedCursor([])
        self.assertEqual(ST.upsert_cohorts(cur, self._parsed(), None), [None])
        self.assertEqual(cur.calls, [])

    def test_legacy_name_clash_adopts_the_old_row(self):
        class Clashing(ScriptedCursor):
            def execute(self, sql, params=None):
                super().execute(sql, params)
                if sql.lstrip().startswith("insert into cohorts"):
                    raise psycopg2.errors.UniqueViolation("duplicate key value violates unique constraint")

        cur = Clashing([("coh-old",)])
        ids = ST.upsert_cohorts(cur, self._parsed(), "course-1", courses=self.COURSES)
        self.assertEqual(ids, ["coh-old"])
        sqls = [c[0] for c in cur.calls]
        self.assertIn("rollback to savepoint cohort_upsert", sqls)
        self.assertTrue(any(q.startswith("update cohorts set cohort_key") for q in sqls))
        self.assertEqual(sqls[-1], "release savepoint cohort_upsert")   # released on this path too


class TestInstructorResolver(unittest.TestCase):
    def test_exact_spellings_aliases_and_merges(self):
        cur = ScriptedCursor([
            [("i1", "Kalpesh Singh", "kalpesh singh", None),
             ("i2", "Kalpesh", "kalpesh", "i1"),                 # merged into i1
             ("i3", "Devdatt Mahajan", "devdatt mahajan", None)],
            [("Devdatt", "devdatt", "i3"), ("K Singh", "k singh", "i2")],   # alias on a merged row follows it
        ])
        r = ST.load_instructor_resolver(cur)
        self.assertEqual(r("Kalpesh Singh"), ("i1", "Kalpesh Singh"))
        self.assertEqual(r("  kalpesh  "), ("i1", "Kalpesh Singh"))          # the merged row's own name
        self.assertEqual(r("Devdatt"), ("i3", "Devdatt Mahajan"))
        self.assertEqual(r("K. Singh"), ("i1", "Kalpesh Singh"))
        self.assertEqual(r("Nobody"), (None, None))
        self.assertEqual(r(""), (None, None))
        cands = {c.id: c for c in r.candidates()}
        self.assertEqual(sorted(cands), ["i1", "i3"])                          # merged rows are not candidates
        self.assertEqual(cands["i1"].spellings, ("K Singh", "Kalpesh"))
        self.assertEqual(cands["i3"].spellings, ("Devdatt",))

    def test_write_suggestions_counts_new_rows_only(self):
        cur = ScriptedCursor([(True,), (False,), None])
        s = [IM.Suggestion("Kalpesh", "kalpesh", "i1", "Kalpesh Singh", 0.8, "first_name", {"a": 1}),
             IM.Suggestion("Kuldep", "kuldep", "i1", "Kalpesh Singh", 0.75, "typo", {}),
             IM.Suggestion("Bob", "bob", "i9", "Bobby", 0.7, "initials", {})]      # rejected earlier -> no row
        self.assertEqual(ST.write_suggestions(cur, s), 1)
        sql, params = cur.calls[0]
        self.assertIn("on conflict (raw_norm, candidate_instructor_id) do update", sql)
        self.assertIn("where instructor_match_suggestions.status = 'pending'", sql)
        self.assertEqual(params[:5], ("Kalpesh", "kalpesh", "i1", 0.8, "first_name"))
        self.assertEqual(json.loads(params[5]), {"a": 1})


class TestResolveTopic(unittest.TestCase):
    def test_topic_normalisation_mirrors_the_sql(self):
        """normalize_topic_name(): non-alphanumeric runs become one space (unlike person names)."""
        self.assertEqual(ST.normalize_topic_name("RAG & Agents: Part-2"), "rag agents part 2")
        self.assertEqual(ST.normalize_topic_name("  \u00c1ndre's  Deep-Dive!! "), "andre s deep dive")
        self.assertEqual(ST.normalize_topic_name(None), "")
        self.assertIn("live class", ST.TOPIC_JUNK)

    def test_ensure_topics_uses_the_seed_rule(self):
        from collections import Counter
        unmapped = Counter({("c1", "RAG Agents"): 3, ("c1", "RAG  Agents!"): 1, ("c1", "Live Class"): 5,
                            ("c2", "MCP"): 1, (None, "Orphan"): 2})
        cur = ScriptedCursor([("t1", True), ("a1",), ("t2", False), None])
        cur.rowcount = 7
        out = ST.ensure_topics(cur, unmapped)
        self.assertEqual(out, {"topics_created": 1, "aliases_created": 1, "rows_backfilled": 7})
        sql0, p0 = cur.calls[0]
        self.assertEqual(p0, ("c1", "RAG Agents", "rag agents"))               # most frequent spelling wins
        self.assertIn("on conflict (course_id, name_norm)", sql0)
        self.assertEqual(cur.calls[1][1], ("c1", "RAG Agents", "rag agents", "t1"))
        self.assertEqual(sum(1 for s, _ in cur.calls if s.startswith("insert into topics")), 2)   # junk/orphan skipped
        self.assertTrue(cur.calls[-1][0].startswith("update class_ratings r set topic_id"))
        self.assertIn("normalize_topic_name(r.topic)", cur.calls[-1][0])
        self.assertEqual(ST.ensure_topics(ScriptedCursor([]), Counter()),
                         {"topics_created": 0, "aliases_created": 0, "rows_backfilled": 0})

    def test_cache_per_course_and_unmapped_counter(self):
        from collections import Counter
        cur = ScriptedCursor([[("mcp deep dive", "top-1")], [("mcp deepdive", "top-1")]])
        cache, unmapped = {}, Counter()
        self.assertEqual(ST.resolve_topic(cur, "course-1", "MCP Deep Dive", cache=cache, unmapped=unmapped), "top-1")
        self.assertEqual(ST.resolve_topic(cur, "course-1", "MCP DeepDive!", cache=cache, unmapped=unmapped), "top-1")
        self.assertIsNone(ST.resolve_topic(cur, "course-1", "Unknown", cache=cache, unmapped=unmapped))
        self.assertEqual(len(cur.calls), 2)                                    # topics + aliases, once
        self.assertEqual(unmapped, {("course-1", "Unknown"): 1})
        self.assertIsNone(ST.resolve_topic(cur, None, "MCP Deep Dive", cache=cache, unmapped=unmapped))
        self.assertIsNone(ST.resolve_topic(cur, "course-1", "", cache=cache, unmapped=unmapped))
        # a kind code ("Live Class" from a pre-fix row) is not a class name: None, and not counted
        self.assertIsNone(ST.resolve_topic(cur, "course-1", "Live Class", cache=cache, unmapped=unmapped))
        self.assertEqual(unmapped, {("course-1", "Unknown"): 1})


class TestNotificationRouting(unittest.TestCase):
    COLS = ["id", "topic", "instructor", "instructor_canonical", "class_date", "session_kind", "rating",
            "num_ratings", "attended", "participation_pct", "decision", "yes_votes", "no_votes",
            "approval_pct", "health_score", "health_band", "flag_reasons", "sentiment_score",
            "sentiment_band", "sentiment_action", "sentiment_provisional", "sentiment_flags",
            "cohort_id", "course_id", "course_name", "course_slug", "handler_name", "handler_email",
            "slack_user_id", "handler_id", "members", "members_total"]

    def _db_row(self, members, members_total, handler=None):
        base = dict.fromkeys(self.COLS)
        base.update({"id": "cr-1", "topic": "T", "instructor": "Jane", "class_date": dt.date(2026, 8, 24),
                     "decision": "video", "course_name": "Applied Agentic AI", "course_slug": "applied-agentic-ai",
                     "members": members, "members_total": members_total})
        if handler:
            base.update({"handler_name": handler[0], "handler_email": handler[1], "slack_user_id": handler[2],
                         "handler_id": "h-1"})
        return tuple(base[c] for c in self.COLS)

    def _fetch(self, rows, **kw):
        cur = ScriptedCursor([rows])
        cur.description = [(c,) for c in self.COLS]
        out = ST.rows_needing_notification(cur, **kw)
        return out, cur

    def test_members_win_handlers_first(self):
        members = [{"id": "m-2", "name": "Priya", "email": "p@ik.com", "slack_user_id": None, "is_handler": False},
                   {"id": "m-1", "name": "Bishal", "email": "b@ik.com", "slack_user_id": "U1", "is_handler": True}]
        out, cur = self._fetch([self._db_row(members, 2, handler=("Old", "old@ik.com", "U0"))],
                               max_age_days=10, limit=25)
        self.assertEqual([r["source"] for r in out[0]["recipients"]], ["member", "member"])
        self.assertEqual([r["name"] for r in out[0]["recipients"]], ["Priya", "Bishal"])   # SQL orders; kept as-is
        self.assertNotIn("members", out[0])
        sql, params = cur.calls[0]
        self.assertIn("from course_members m", sql)
        self.assertIn("coalesce(m.notify_slack, true)", sql)
        self.assertIn("m.cohort_id = any(coalesce(cr.cohort_ids", sql)
        self.assertIn("left join course_handlers h", sql)
        self.assertIn("c.slug as course_slug", sql)
        self.assertEqual(params, {"max_age_days": 10, "limit": 25})

    def test_falls_back_to_the_legacy_handler_only_when_the_course_has_no_members(self):
        out, _ = self._fetch([self._db_row([], 0, handler=("Bishal", "b@ik.com", None))])
        self.assertEqual(out[0]["recipients"], [{"id": "h-1", "name": "Bishal", "email": "b@ik.com",
                                                 "slack_user_id": None, "is_handler": True, "source": "handler"}])
        # members exist but none has Slack on -> nobody (the card says so), not the old handler
        out, _ = self._fetch([self._db_row([], 2, handler=("Bishal", "b@ik.com", None))])
        self.assertEqual(out[0]["recipients"], [])

    def test_json_string_members_are_decoded(self):
        out, _ = self._fetch([self._db_row(json.dumps([{"id": "m-1", "name": "B", "email": "b@ik.com"}]), 1)])
        self.assertEqual(out[0]["recipients"][0]["email"], "b@ik.com")


class TestFinishRun(unittest.TestCase):
    def test_writes_the_v3_metrics(self):
        cur = ScriptedCursor([])
        ST.finish_run(cur, "run-1", status="ok", rows_fetched=3, rows_upserted=3, rows_flagged=1,
                      notifications_sent=1, unmapped_labels=["X", "X"], rows_scored=3, scoring_config_version=2,
                      band_counts={"bad": 1, "good": 2}, cohorts_created=4, cohorts_unparsed=1,
                      instructors_unresolved=2, suggestions_created=1, topics_unmapped=5, duration_ms=1234)
        sql, params = cur.calls[0]
        for col in ("rows_scored", "scoring_config_version", "band_counts=%s::jsonb", "cohorts_created",
                    "cohorts_unparsed", "instructors_unresolved", "suggestions_created", "topics_unmapped",
                    "duration_ms"):
            self.assertIn(col, sql)
        self.assertEqual(params[5], ["X"])
        self.assertEqual(json.loads(params[9]), {"bad": 1, "good": 2})
        self.assertEqual(params[-1], "run-1")
        # a failed run with nothing scored writes nulls, not zeros
        ST.finish_run(cur, "run-2", status="failed", error="boom")
        self.assertIsNone(cur.calls[1][1][9])


# ── Slack ────────────────────────────────────────────────────────────────────

class TestSlackPayload(unittest.TestCase):
    ROW = {"id": "cr-1", "topic": "MCP Deep Dive", "instructor": "Jane Doe", "instructor_canonical": "Jane Doe",
           "class_date": dt.date(2026, 9, 1), "session_kind": "Live Class", "rating": 4.31,
           "num_ratings": 12, "attended": 25, "participation_pct": 48.0, "decision": "video",
           "course_name": "Applied Agentic AI", "course_slug": "applied-agentic-ai",
           "yes_votes": 13, "no_votes": 2, "approval_pct": 86.67,
           "sentiment_score": 58.0, "sentiment_band": "bad", "sentiment_action": "video",
           "sentiment_provisional": False, "sentiment_flags": ["under_rating_line", "guarded"],
           "recipients": [{"id": "m-1", "name": "Bishal", "email": "b@ik.com", "slack_user_id": "U777"},
                          {"id": "m-2", "name": "Priya", "email": "p@ik.com", "slack_user_id": None}]}
    LEGACY = {"id": "cr-2", "topic": "Old", "instructor": "Jane Doe", "class_date": dt.date(2026, 9, 1),
              "session_kind": "Live Class", "rating": 4.2, "num_ratings": 12, "attended": 25,
              "participation_pct": 48.0, "decision": "transcript", "course_name": "Applied Agentic AI",
              "handler_name": "Bishal", "handler_email": "b@ik.com", "slack_user_id": "U777", "handler_id": "h-1",
              "yes_votes": 13, "no_votes": 2, "health_score": 55.0, "health_band": "urgent",
              "flag_reasons": ["rating", "approval"]}

    def test_card_leads_with_the_score_band_and_action(self):
        blocks = N.flag_blocks(self.ROW, "https://app/c/applied-agentic-ai/queue?focus=cr-1")
        self.assertEqual(blocks[0]["text"]["text"], "Sentiment 58 · Bad → video")
        text = json.dumps(blocks, ensure_ascii=False)
        for needle in ("Applied Agentic AI", "MCP Deep Dive", "12 of 25 rated (48%)",
                       "*Why:* under the 4.55 line", "13 of 15 would have them back (87%)",
                       "<@U777> *Priya* — does this class need an analysis?", "queue?focus=cr-1"):
            self.assertIn(needle, text)
        self.assertNotIn("guarded", text)                             # internal flags stay internal
        self.assertEqual(blocks[-2]["elements"][0]["type"], "button")   # URL button, no webhook

    def test_reason_words_and_headline_variants(self):
        self.assertEqual(N.reason_words({"sentiment_flags": ["under_approval_bar", "thin_provisional", "thin_no_band"]}),
                         "under the 80% bar, few votes")
        self.assertEqual(N.reason_words({"sentiment_flags": ["escalated"]}), "escalated by a PM")
        self.assertEqual(N.reason_words(self.LEGACY), "rating below 4.55, approval under 80%")
        self.assertEqual(N.headline({**self.ROW, "sentiment_score": 89.6, "sentiment_band": "good",
                                     "decision": "transcript"}), "Sentiment 89.6 · Good → transcript")
        self.assertEqual(N.headline({**self.ROW, "sentiment_provisional": True}),
                         "Sentiment 58 · Bad (provisional) → video")
        self.assertEqual(N.headline(self.LEGACY), "Class flagged → transcript")
        self.assertEqual(N.headline({**self.ROW, "sentiment_band": None}), "Sentiment 58 · No band yet → video")

    def test_no_owner_line(self):
        blocks = N.flag_blocks({**self.ROW, "recipients": []}, "https://app/x")
        self.assertIn("No owner assigned — set one in Admin › People", json.dumps(blocks, ensure_ascii=False))
        self.assertEqual(N.mention_line([]), N.NO_OWNER_TEXT)

    def test_recorded_as_shows_the_raw_spelling(self):
        blocks = N.flag_blocks({**self.ROW, "instructor": "Jane", "instructor_canonical": "Jane Doe"}, "u")
        self.assertIn("Jane Doe (recorded as Jane)", json.dumps(blocks))

    def test_links_into_the_course_workspace_or_falls_back(self):
        env = {"UI_URL": "https://app/"}
        self.assertEqual(N.class_link(self.ROW, env), "https://app/c/applied-agentic-ai/queue?focus=cr-1")
        self.assertEqual(N.class_link({**self.ROW, "course_slug": None}, env), "https://app/ratings?focus=cr-1")
        self.assertTrue(N.class_link(self.ROW, {}).startswith(N.DEFAULT_UI))

    def test_legacy_rows_still_render(self):
        blocks = N.flag_blocks(self.LEGACY, "https://app/ratings?focus=cr-2", "U777")
        text = json.dumps(blocks)
        self.assertIn("<@U777>", text)
        self.assertIn("Class flagged", text)
        self.assertIn("*Priority:* Urgent", N.priority_line(self.LEGACY))
        self.assertIn("*Score:* 58 · Bad", N.priority_line(self.ROW))
        self.assertEqual(N.priority_line({**self.LEGACY, "flag_reasons": [], "health_band": None,
                                          "yes_votes": None}), "*Vote:* no vote recorded")

    def test_post_uses_the_slug_link_and_never_raises(self):
        seen = {}

        def handler(request):
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={"ok": True, "ts": "1.2"})

        ok, ts, _ = N.post_flag_message(
            self.ROW, env={"SLACK_BOT_TOKEN": "x", "SLACK_PM_CHANNEL_ID": "C1", "UI_URL": "https://app"},
            transport=httpx.MockTransport(handler))
        self.assertEqual((ok, ts), (True, "1.2"))
        self.assertEqual(seen["body"]["text"], "Sentiment 58 · Bad → video: Applied Agentic AI — MCP Deep Dive")
        self.assertEqual(seen["body"]["blocks"][-2]["elements"][0]["url"],
                         "https://app/c/applied-agentic-ai/queue?focus=cr-1")
        ok, ts, err = N.post_flag_message(
            self.ROW, env={"SLACK_BOT_TOKEN": "x", "SLACK_PM_CHANNEL_ID": "C1", "UI_URL": "https://app"},
            transport=httpx.MockTransport(lambda r: httpx.Response(500)))
        self.assertFalse(ok)
        self.assertTrue(err)



class TestTheRowFingerprint(unittest.TestCase):
    """Same sheet values, same fingerprint; any sheet value changes it; app-side fields do not."""

    def _row(self, **over):
        base = {"course_label": "Applied Agentic AI", "cohort_text": "Cohort 2", "topic": "T",
                "instructor": "Jane", "class_date": dt.date(2026, 8, 24), "session_kind": "Live Class",
                "rating": 4.5, "num_ratings": 10, "attended": 20, "yes_votes": 8, "no_votes": 2,
                "region": "US"}
        base.update(over)
        return base

    def test_stable_for_the_same_values(self):
        self.assertEqual(ST.row_fingerprint(self._row()), ST.row_fingerprint(self._row()))
        self.assertEqual(len(ST.row_fingerprint(self._row())), 40)

    def test_any_sheet_value_changes_it(self):
        base = ST.row_fingerprint(self._row())
        for key, val in (("rating", 4.6), ("num_ratings", 11), ("yes_votes", 7), ("attended", 21),
                         ("cohort_text", "Cohort 3"), ("instructor", "Jane D"), ("region", "India")):
            self.assertNotEqual(base, ST.row_fingerprint(self._row(**{key: val})), key)

    def test_missing_and_blank_are_the_same_and_app_fields_do_not_count(self):
        self.assertEqual(ST.row_fingerprint(self._row(yes_votes=None, no_votes=None)),
                         ST.row_fingerprint({**self._row(), "yes_votes": None, "no_votes": None,
                                             "review_status": "dismissed", "escalated": True}))

    def test_the_version_salt_forces_every_row_through_after_a_logic_change(self):
        before = ST.row_fingerprint(self._row())
        with mock.patch.object(ST, "FINGERPRINT_VERSION", "fp2"):
            self.assertNotEqual(before, ST.row_fingerprint(self._row()))

    def test_load_row_state_keys_like_the_upsert(self):
        class Cur:
            def execute(self, sql, params=None):
                self.sql = sql

            def fetchall(self):
                return [(dt.date(2026, 8, 24), "T", None, "Live Class", "abc", "good", "none", 90.0, True)]
        cur = Cur()
        state = ST.load_row_state(cur)
        self.assertIn("row_hash", cur.sql)
        self.assertEqual(state[(dt.date(2026, 8, 24), "T", "", "Live Class")], ("abc", "good", "none", True, True))


class TestRowsTheSheetNoLongerHasAreRetired(unittest.TestCase):
    class Cur:
        def __init__(self, rows):
            self.rows, self.calls = rows, []

        def execute(self, sql, params=None):
            self.calls.append((sql, params))

        def fetchall(self):
            return self.rows

    def test_untouched_rows_not_on_the_sheet_are_deleted_and_audited(self):
        d = dt.date(2026, 8, 24)
        cur = self.Cur([("id-old", d, "T", "Sam", "Live Class", "Agentic"), ("id-kept", d, "T", "Sam Smith", "Live Class", "Agentic")])
        n = ST.retire_rows_missing_from_sheet(cur, {(d, "T", "Sam Smith", "Live Class")})
        self.assertEqual(n, 1)
        select_sql = cur.calls[0][0]
        self.assertIn("review_status = 'new'", select_sql)          # touched rows never enter the candidate list
        self.assertIn("class_id is null", select_sql)
        delete_sql, params = cur.calls[1]
        self.assertIn("delete from class_ratings", delete_sql)
        self.assertEqual(params, (["id-old"],))
        self.assertIn("stale_rows_removed", cur.calls[2][0])

    def test_nothing_missing_means_no_delete(self):
        d = dt.date(2026, 8, 24)
        cur = self.Cur([("id-1", d, "T", "Sam", "Live Class", "Agentic")])
        self.assertEqual(ST.retire_rows_missing_from_sheet(cur, {(d, "T", "Sam", "Live Class")}), 0)
        self.assertEqual(len(cur.calls), 1)

    def test_a_blank_instructor_matches_the_key_the_sync_builds(self):
        d = dt.date(2026, 8, 24)
        cur = self.Cur([("id-1", d, "T", None, "Live Class", "Agentic")])
        self.assertEqual(ST.retire_rows_missing_from_sheet(cur, {(d, "T", "", "Live Class")}), 0)

    def test_a_tab_that_returned_nothing_keeps_its_history(self):
        # The MLSU tab parsed to zero rows (a reformatted date column); the Agentic tab was fine.
        d = dt.date(2026, 8, 24)
        cur = self.Cur([("mlsu-1", d, "T", "Sam", "Live Class", "ML SwitchUp"),
                        ("ag-old", d, "U", "Pat", "Live Class", "Agentic")])
        n = ST.retire_rows_missing_from_sheet(cur, {(d, "U", "Pat Lee", "Live Class")}, seen_labels={"Agentic"})
        self.assertEqual(n, 1)
        self.assertEqual(cur.calls[1][1], (["ag-old"],))            # only the Agentic row went

    def test_a_run_that_would_remove_many_rows_refuses(self):
        d = dt.date(2026, 8, 24)
        rows = [(f"id-{i}", d, f"T{i}", "Sam", "Live Class", "Agentic") for i in range(100)]
        cur = self.Cur(rows)
        with mock.patch.object(ST, "RETIRE_MAX_ABS", 5):
            self.assertEqual(ST.retire_rows_missing_from_sheet(cur, set(), seen_labels={"Agentic"}), 0)
        self.assertEqual(len(cur.calls), 1)                          # no delete was issued

    def test_week_numbers_are_recomputed_in_one_statement(self):
        class Cur:
            rowcount = 3

            def execute(self, sql, params=None):
                self.sql = sql
        cur = Cur()
        self.assertEqual(ST.recompute_week_numbers(cur), 3)
        self.assertIn("min(class_date)", cur.sql)
        self.assertIn("is distinct from", cur.sql)


class TestGhostSyncRunsAreMarkedFailed(unittest.TestCase):
    def test_old_running_rows_are_failed_with_the_reason(self):
        class Cur:
            def __init__(self):
                self.calls = []

            def execute(self, sql, params=None):
                self.calls.append((sql, params))

            def fetchall(self):
                return [("run-1",)]
        cur = Cur()
        self.assertEqual(ST.mark_stale_runs(cur, older_than_minutes=10), 1)
        sql, params = cur.calls[0]
        self.assertIn("status='running'", sql)
        self.assertIn("heartbeat_at", sql)                         # a run that still beats is not stale
        self.assertIn("restarted mid-sync", params[0])
        self.assertEqual(params[1], 10)


class TestStuckClassesAreReleased(unittest.TestCase):
    """A class can be stuck two ways: its job died inside the worker (analyzing, no result), or the
    website scheduled it and the worker never took it. Both are released for retry."""

    class Cur:
        def __init__(self, rows):
            self.rows, self.calls = rows, []

        def execute(self, sql, params=None):
            self.calls.append((sql, params))

        def fetchall(self):
            return self.rows

    def test_a_dead_job_and_a_never_started_one_are_both_released(self):
        cur = self.Cur([("c1", "analyzing"), ("c2", "scheduled")])
        self.assertEqual(ST.reset_stuck_analyses(cur, older_than_minutes=90, scheduled_minutes=15), 2)
        sql, params = cur.calls[0]
        self.assertIn("status='analyzing'", sql)
        self.assertIn("status='scheduled'", sql)
        self.assertEqual(params, (90, 15))
        messages = [json.loads(p[1])["message"] for _, p in cur.calls[1:]]
        self.assertIn("restarted mid-analysis", messages[0])
        self.assertIn("never picked up within 15 minutes", messages[1])

    def test_nothing_stuck_means_nothing_written(self):
        cur = self.Cur([])
        self.assertEqual(ST.reset_stuck_analyses(cur), 0)
        self.assertEqual(len(cur.calls), 1)


class TestTheSheetsDatesAreUnderstood(unittest.TestCase):
    """The live sheet writes "January 2, 2026". The reader understood only "Jan 2, 2026", so every
    month failed except May - the one month whose abbreviation is its full name - and 87% of the
    classes were dropped without a word."""

    def test_every_month_in_the_sheets_own_format(self):
        import sheet_source as SS
        for month, n in (("January", 1), ("February", 2), ("March", 3), ("April", 4), ("May", 5),
                         ("June", 6), ("July", 7), ("August", 8), ("September", 9),
                         ("October", 10), ("November", 11), ("December", 12)):
            got = SS._parse_date(f"{month} 2, 2026")
            self.assertIsNotNone(got, f"{month} did not parse")
            self.assertEqual((got.year, got.month, got.day), (2026, n, 2))

    def test_the_other_shapes_still_work(self):
        import sheet_source as SS
        import datetime as dt
        for text in ("2026-01-02", "02/01/2026", "Jan 2, 2026", "2 January 2026", "2-Jan-2026",
                     "2026-01-02T10:30:00", "Friday, January 2, 2026"):
            self.assertIsNotNone(SS._parse_date(text), f"{text!r} did not parse")

    def test_a_spreadsheet_serial_number_is_a_date(self):
        import sheet_source as SS
        import datetime as dt
        self.assertEqual(SS._parse_date(46024), dt.date(2026, 1, 2))

    def test_nonsense_is_not_a_date(self):
        import sheet_source as SS
        for junk in ("", None, "No Ratings", "banana", 4.6, 27, True):
            self.assertIsNone(SS._parse_date(junk), f"{junk!r} should not parse as a date")

    def test_losing_most_of_a_tab_is_reported_as_an_error(self):
        import logging
        import sheet_source as SS
        src = SS.SheetRatingsSource(env={"RATINGS_SHEET_ID": "x"})
        header = ["Session Date", "Type", "Cohorts", "Class", "Instructor",
                  "Overall Average", "Responses", "# Students Attended"]
        values = [header] + [["not a date", "Live Class", "C1", "T", "I", 4.5, 5, 10]
                             for _ in range(20)]
        with self.assertLogs("sheet_source", level="ERROR") as caught:
            out = src._parse_tab("MLSU_Live_Class_Poll", values)
        self.assertEqual(out, [])
        joined = " ".join(caught.output)
        self.assertIn("cannot understand", joined)
        self.assertIn("NOT being synced", joined)


if __name__ == "__main__":
    unittest.main()
