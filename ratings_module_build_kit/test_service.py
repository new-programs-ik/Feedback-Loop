"""
test_service.py — endpoint tests for the analysis worker (FastAPI TestClient).
The engine + Vimeo are mocked, so no API key or network is needed.
Run:  python -m unittest test_service -v
"""
import base64
import json
import os
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import service

client = TestClient(service.app)

# /health reports the active scoring-config version from the database; keep the suite offline.
_version_patch = patch.object(service.RST, "cached_config_version", return_value=2)


# These tests exercise the endpoints themselves, not the lock on the door, so they run as a local
# machine with no key configured would. The lock has its own tests below.
_auth_patch = patch.object(service, "ALLOW_NO_AUTH", True)

# The claim asks the database, and the suite has none: a failed claim is now a 503 (the worker no
# longer guesses "yes" on a database error), so the endpoint tests take the claim as granted.
# TestOneAnalysisPerClass overrides this per test.
_claim_patch = patch.object(service.ST, "claim_for_analysis", return_value=True)
REAL_CLAIM = service.ST.claim_for_analysis          # captured before the patch starts, for the test of the claim itself


def setUpModule():
    _version_patch.start()
    _auth_patch.start()
    _claim_patch.start()


def tearDownModule():
    _version_patch.stop()
    _auth_patch.stop()
    _claim_patch.stop()


SRT = "1\n00:00:01,000 --> 00:00:03,000\nHello everyone.\n"
RESULT = {
    "overall": "rushed the end",
    "flags": [{"flag": "pace", "severity": "minor", "confidence": "low",
               "evidence": [{"timestamp": "00:00:01", "quote": "almost out of time"}]}],
    "feedback": "Nice energy; watch the pace.",
    "reclass": {"recommended": "yes", "reason": "coverage gap", "deciding_flags": ["pace"]},
}
META = {"model": "claude-sonnet-4-6", "tokens_in": 10, "tokens_out": 5, "cost_usd": 0.01}
VINFO = {"text": SRT, "video_id": "9", "language": "en", "type": "captions", "format": "vtt"}


class TestService(unittest.TestCase):
    def test_health(self):
        r = client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertIn("model", r.json())

    def test_health_identifies_the_running_build(self):
        """Which build is live? Unanswerable during the 2026-08-27 SDK outage — now it isn't."""
        body = client.get("/health").json()
        self.assertIn("commit", body)                 # RENDER_GIT_COMMIT, or "local"
        self.assertTrue(body["anthropic_sdk"])        # the SDK version actually installed
        self.assertNotEqual(body["anthropic_sdk"], "missing")

    def test_health_reports_the_scoring_version_and_rule_v3(self):
        body = client.get("/health").json()
        self.assertEqual(body["rule_version"], "v3")
        self.assertEqual(body["scoring_config_version"], 2)      # patched: what active_scoring_config() says
        with patch.object(service.RST, "cached_config_version", return_value=None):
            self.assertIsNone(client.get("/health").json()["scoring_config_version"])   # none active / DB down


    def test_dry_run(self):
        r = client.post("/dry-run", json={"transcript": SRT})
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()["cues"], 1)

    def test_dry_run_needs_transcript(self):
        r = client.post("/dry-run", json={"vimeo_url": "https://vimeo.com/1"})
        self.assertEqual(r.status_code, 422)

    def test_analyze_requires_a_source(self):
        r = client.post("/analyze", json={"course": "ML"})
        self.assertEqual(r.status_code, 422)

    def test_analyze_with_transcript(self):
        with patch.object(service.E, "analyse_cues", return_value=(RESULT, META)) as m:
            r = client.post("/analyze", json={"transcript": SRT, "course": "ML", "instructor": "Jo"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["transcript_source"], "upload")
        self.assertEqual(body["result"]["reclass"]["recommended"], "yes")
        m.assert_called_once()

    def test_analyze_with_vimeo(self):
        with patch.object(service.V, "fetch_transcript", return_value=VINFO), \
             patch.object(service.E, "analyse_cues", return_value=(RESULT, META)):
            r = client.post("/analyze", json={"vimeo_url": "https://vimeo.com/9", "course": "ML"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["transcript_source"], "vimeo")

    def test_analyze_vimeo_no_captions_is_422(self):
        with patch.object(service.V, "fetch_transcript", side_effect=service.V.VimeoNoCaptions("none")):
            r = client.post("/analyze", json={"vimeo_url": "https://vimeo.com/9"})
        self.assertEqual(r.status_code, 422)

    def test_analyze_vimeo_auth_error_is_502(self):
        with patch.object(service.V, "fetch_transcript", side_effect=service.V.VimeoAuthError("bad token")):
            r = client.post("/analyze", json={"vimeo_url": "https://vimeo.com/9"})
        self.assertEqual(r.status_code, 502)

    def test_transcript_endpoint(self):
        with patch.object(service.V, "fetch_transcript", return_value=VINFO):
            r = client.post("/transcript", json={"vimeo_url": "https://vimeo.com/9"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["video_id"], "9")
        self.assertIn("Hello", body["text"])

    def test_analyze_passes_class_type(self):
        with patch.object(service.E, "analyse_cues", return_value=(RESULT, META)) as m:
            r = client.post("/analyze", json={"transcript": SRT, "class_type": "ars"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(m.call_args.args[2], "ars")           # class_type forwarded to the engine
        self.assertIn("Assignment Review Session", m.call_args.args[1])  # context mentions ARS

    def test_analyze_rejects_bad_class_type(self):
        r = client.post("/analyze", json={"transcript": SRT, "class_type": "workshop"})
        self.assertEqual(r.status_code, 422)

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://test"})
    def test_analyze_async_accepts_and_runs_job(self):
        with patch.object(service.E, "analyse_cues", return_value=(RESULT, META)), \
             patch.object(service.ST, "persist_analysis") as persist:
            r = client.post("/analyze-async", json={"class_id": "c-123", "transcript": SRT})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "accepted")
        persist.assert_called_once()                       # background job ran + persisted
        self.assertEqual(persist.call_args.args[0], "c-123")  # to the right class

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://test"})
    def test_analyze_async_failure_marks_class(self):
        with patch.object(service.E, "analyse_cues", side_effect=RuntimeError("boom")), \
             patch.object(service.ST, "mark_failed") as failed:
            r = client.post("/analyze-async", json={"class_id": "c-9", "transcript": SRT})
        self.assertEqual(r.status_code, 200)
        failed.assert_called_once()

    def test_analyze_video_off_never_calls_video_stage(self):
        with patch.object(service.E, "analyse_cues", return_value=(dict(RESULT), META)), \
             patch.object(service.VD, "analyze_video") as vd:
            r = client.post("/analyze", json={"transcript": SRT})
        self.assertEqual(r.status_code, 200)
        vd.assert_not_called()
        self.assertFalse(r.json()["video"]["video_used"])

    def test_analyze_video_on_forwards_visual_track(self):
        with patch.object(service.E, "analyse_cues", return_value=(dict(RESULT), dict(META))) as m, \
             patch.object(service.VD, "analyze_video",
                          return_value=("VISUAL STATES ...", {"video_used": True, "frames_analyzed": 12,
                                                             "video_tokens_in": 10000, "video_tokens_out": 900,
                                                             "video_cost_usd": 0.05})) as vd:
            r = client.post("/analyze", json={"transcript": SRT, "analyze_video": True,
                                              "video_url": "https://x/y.mp4"})
        self.assertEqual(r.status_code, 200)
        vd.assert_called_once()
        self.assertEqual(m.call_args.kwargs.get("visual_track"), "VISUAL STATES ...")
        body = r.json()
        self.assertTrue(body["video"]["video_used"])
        self.assertEqual(body["meta"]["tokens_in"], 10 + 10000)   # video tokens rolled up
        self.assertAlmostEqual(body["meta"]["cost_usd"], 0.01 + 0.05, places=4)

    def test_video_error_never_fails_the_analysis(self):
        with patch.object(service.E, "analyse_cues", return_value=(dict(RESULT), dict(META))), \
             patch.object(service.VD, "analyze_video",
                          return_value=("", {"video_used": False, "video_error": "no playable video source"})):
            r = client.post("/analyze", json={"transcript": SRT, "analyze_video": True})
        self.assertEqual(r.status_code, 200)                      # analysis still succeeds
        self.assertIn("no playable", r.json()["video"]["video_error"])

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://test"})
    def test_async_with_video_persists_video_meta(self):
        with patch.object(service.E, "analyse_cues", return_value=(dict(RESULT), dict(META))), \
             patch.object(service.VD, "analyze_video",
                          return_value=("track", {"video_used": True, "video_cost_usd": 0.05,
                                                  "video_tokens_in": 1, "video_tokens_out": 1})), \
             patch.object(service.ST, "persist_analysis") as persist:
            r = client.post("/analyze-async", json={"class_id": "c-7", "transcript": SRT,
                                                    "analyze_video": True, "video_url": "https://x/y.mp4"})
        self.assertEqual(r.status_code, 200)
        persist.assert_called_once()
        stored_result = persist.call_args.args[1]
        self.assertTrue(stored_result["video"]["video_used"])     # video meta rides in result jsonb

    def test_revise_endpoint(self):
        with patch.object(service.E, "revise_feedback", return_value=("Shorter text.", META)) as m:
            r = client.post("/revise", json={"feedback": "Long text.", "instruction": "make it shorter"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["feedback"], "Shorter text.")
        m.assert_called_once()

    def test_revise_empty_is_422(self):
        with patch.object(service.E, "revise_feedback", side_effect=ValueError("no feedback text to revise")):
            r = client.post("/revise", json={"feedback": "", "instruction": "x"})
        self.assertEqual(r.status_code, 422)


class TestMaterials(unittest.TestCase):
    def test_extract_txt(self):
        self.assertEqual(service.extract_text("notes.txt", b"Topic A\nTopic B"), "Topic A\nTopic B")

    def test_extract_ipynb(self):
        nb = {"cells": [
            {"cell_type": "markdown", "source": ["# Decision Trees\n", "Gini impurity"]},
            {"cell_type": "code", "source": ["fit(X, y)"]},
        ]}
        out = service.extract_text("lab.ipynb", json.dumps(nb).encode())
        self.assertIn("Decision Trees", out)
        self.assertIn("```\nfit(X, y)\n```", out)

    def test_extract_unsupported_is_422(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as cm:
            service.extract_text("deck.key", b"xx")
        self.assertEqual(cm.exception.status_code, 422)

    def test_analyze_passes_multiple_materials(self):
        f1 = base64.b64encode("Planned: trees, gini, ensembles".encode()).decode()
        f2 = base64.b64encode("Notebook: fit(X, y) accuracy".encode()).decode()
        with patch.object(service.E, "analyse_cues", return_value=(RESULT, META)) as m:
            r = client.post("/analyze", json={
                "transcript": SRT, "materials_text": "Agenda outline",
                "materials_files": [
                    {"filename": "slides.txt", "b64": f1},
                    {"filename": "lab.txt", "b64": f2},
                ],
            })
        self.assertEqual(r.status_code, 200)
        self.assertGreater(r.json()["materials_chars"], 0)
        materials_arg = m.call_args.args[3]
        self.assertIn("Agenda outline", materials_arg)
        self.assertIn("gini", materials_arg)      # from file 1
        self.assertIn("Notebook", materials_arg)  # from file 2

    def test_bad_base64_is_422(self):
        r = client.post("/analyze", json={
            "transcript": SRT, "materials_files": [{"filename": "x.txt", "b64": "!!!not-b64!!!"}]})
        self.assertEqual(r.status_code, 422)



class TestTheWorkerIsNotOpenToEveryone(unittest.TestCase):
    """With no key configured the worker used to accept every request from anyone who found its
    address - write an analysis against any class, and spend our model budget doing it."""

    def test_no_key_and_no_local_override_refuses(self):
        with patch.object(service, "WORKER_API_KEY", ""), \
             patch.object(service, "ALLOW_NO_AUTH", False):
            r = client.post("/analyze-async", json={"class_id": "x", "transcript": SRT})
            self.assertEqual(r.status_code, 503)
            self.assertIn("WORKER_API_KEY", r.json()["detail"])

    def test_a_wrong_key_is_refused(self):
        with patch.object(service, "WORKER_API_KEY", "the-real-key"), \
             patch.object(service, "ALLOW_NO_AUTH", False):
            r = client.post("/analyze-async", json={"class_id": "x", "transcript": SRT},
                            headers={"Authorization": "Bearer not-the-key"})
            self.assertEqual(r.status_code, 401)

    def test_no_header_at_all_is_refused(self):
        with patch.object(service, "WORKER_API_KEY", "the-real-key"), \
             patch.object(service, "ALLOW_NO_AUTH", False):
            r = client.post("/analyze-async", json={"class_id": "x", "transcript": SRT})
            self.assertEqual(r.status_code, 401)

    def test_the_right_key_is_accepted(self):
        with patch.object(service, "WORKER_API_KEY", "the-real-key"), \
             patch.object(service, "ALLOW_NO_AUTH", False), \
             patch.object(service, "BackgroundTasks", create=True):
            r = client.post("/analyze-async", json={"class_id": "x", "transcript": SRT},
                            headers={"Authorization": "Bearer the-real-key"})
            self.assertNotIn(r.status_code, (401, 503))



class TestOneAnalysisPerClass(unittest.TestCase):
    """The Retry button appears while a job may still be running. Each press used to start another
    full analysis: both paid for, both saved, and the review page could mix the two."""

    def test_a_second_request_while_one_is_running_is_refused_with_409(self):
        # A refusal used to be a 200. The website took 200 as success and sent the PM to a page
        # that spun forever. A refusal is an error to the caller, so it is a 409.
        with patch.object(service.ST, "claim_for_analysis", return_value=False) as claim,              patch.object(service, "_run_analysis_job") as job,              patch.object(service, "_sweep_stuck", return_value=0):
            r = client.post("/analyze-async", json={"class_id": "c1", "transcript": SRT})
            self.assertEqual(r.status_code, 409)
            self.assertEqual(r.json()["status"], "already running")
            claim.assert_called_once_with("c1")
            job.assert_not_called()

    def test_the_first_request_is_accepted(self):
        with patch.object(service.ST, "claim_for_analysis", return_value=True),              patch.object(service, "_run_analysis_job"),              patch.object(service, "_sweep_stuck", return_value=0):
            r = client.post("/analyze-async", json={"class_id": "c1", "transcript": SRT})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["status"], "accepted")

    def test_stuck_classes_are_released_before_a_job_is_claimed(self):
        # The sweep used to live only in the sync, which was broken for a fortnight.
        with patch.object(service.ST, "claim_for_analysis", return_value=True),              patch.object(service, "_run_analysis_job"),              patch.object(service, "_sweep_stuck", return_value=0) as sweep:
            client.post("/analyze-async", json={"class_id": "c1", "transcript": SRT})
            sweep.assert_called_once()

    def test_a_sweep_that_cannot_reach_the_database_never_blocks_a_job(self):
        with patch.object(service.ST, "_connect", side_effect=RuntimeError("no database")):
            self.assertEqual(service._sweep_stuck(), 0)


class TestTheScheduledSyncNeedsAFreshToken(unittest.TestCase):
    """The database schedules the sync and cannot hold the worker's key, so it mints a single-use
    token per run. The endpoint takes that token and nothing else."""

    def test_a_fresh_token_starts_the_sync(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://x"}), \
             patch.object(service.ST, "consume_sync_token", return_value=True) as consume, \
             patch("ratings_sync.run_sync") as run:
            token = "ab" * 32                                   # the shape the scheduler mints
            r = client.post("/sync-ratings/cron", json={"token": token, "trigger": "cron"})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json(), {"status": "accepted", "trigger": "cron"})
            consume.assert_called_once_with(token)
            run.assert_called_once_with("cron", full=False)

    def test_a_used_unknown_or_old_token_is_refused(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://x"}), \
             patch.object(service.ST, "consume_sync_token", return_value=False), \
             patch("ratings_sync.run_sync") as run:
            r = client.post("/sync-ratings/cron", json={"token": "cd" * 32})
            self.assertEqual(r.status_code, 401)
            run.assert_not_called()

    def test_no_token_at_all_is_refused_without_asking_the_database(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://x"}), \
             patch.object(service.ST, "_connect", side_effect=AssertionError("must not connect")):
            r = client.post("/sync-ratings/cron", json={})
            self.assertEqual(r.status_code, 401)

    def test_the_endpoint_does_not_take_the_worker_key_either(self):
        # It is not behind require_worker_auth on purpose; the token is the credential.
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://x"}), \
             patch.object(service.ST, "consume_sync_token", return_value=False):
            r = client.post("/sync-ratings/cron", json={"token": "x"},
                            headers={"Authorization": "Bearer whatever"})
            self.assertEqual(r.status_code, 401)


class TestTheDatabaseIsRetriedBeforeItIsCalledUnreachable(unittest.TestCase):
    """22 Sep 2026: four connection failures in five minutes, one try each, four 503s, one class
    marked failed four times. A blip is retried; only a real outage is reported."""

    def test_a_connection_that_fails_then_succeeds_is_not_a_failure(self):
        conn = object()
        timeouts = []

        def connect(url, connect_timeout):
            timeouts.append(connect_timeout)
            if len(timeouts) < 3:
                raise service.ST.psycopg2.OperationalError("could not connect")
            return conn

        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://x"}), \
             patch.object(service.ST.psycopg2, "connect", side_effect=connect), \
             patch.object(service.ST, "_sleep") as sleep:
            self.assertIs(service.ST._connect(attempts=3, waits=(2, 5)), conn)
        self.assertEqual(timeouts, [8, 8, 8])
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [2, 5])

    def test_it_gives_up_after_the_last_try(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://x"}), \
             patch.object(service.ST.psycopg2, "connect",
                          side_effect=service.ST.psycopg2.OperationalError("down")) as connect, \
             patch.object(service.ST, "_sleep"):
            with self.assertRaises(service.ST.psycopg2.OperationalError):
                service.ST._connect(attempts=3)
        self.assertEqual(connect.call_count, 3)

    def test_a_missing_url_is_not_retried(self):
        with patch.dict(os.environ, {"DATABASE_URL": ""}), patch.object(service.ST.psycopg2, "connect") as connect:
            with self.assertRaises(RuntimeError):
                service.ST._connect()
        connect.assert_not_called()

    def test_health_says_whether_the_database_can_be_reached(self):
        with patch.object(service.ST, "ping", return_value="unreachable"):
            r = client.get("/health")
        self.assertEqual(r.json()["database"], "unreachable")
        self.assertIn("jobs_running", r.json())


class TestJobsSurviveARestart(unittest.TestCase):
    """The platform restarts the worker on every deploy. A class the website queued and nobody
    took, or one a restart interrupted, is picked up by the worker on its own."""

    ROW = {"class_id": "c9", "vimeo_url": "https://vimeo.com/1", "course": "Advanced ML",
           "topic": "ML Architectures", "instructor": "Sarfaraz", "rating": "4.62", "agenda": "",
           "class_type": "live_class"}

    def setUp(self):
        service.RUNNING.clear()

    def test_a_queued_class_nobody_took_is_resumed(self):
        with patch.object(service.ST, "scheduled_to_resume", return_value=[dict(self.ROW)]), \
             patch.object(service.ST, "claim_for_analysis", return_value=True) as claim, \
             patch.object(service.ST, "record_resume") as note, \
             patch.object(service, "_run_analysis_job") as job:
            self.assertEqual(service._resume_scheduled(), 1)
        claim.assert_called_once_with("c9")
        note.assert_called_once_with("c9")
        req = job.call_args.args[0]
        self.assertEqual((req.class_id, req.vimeo_url, req.course, req.topic, req.instructor, req.rating, req.class_type),
                         ("c9", "https://vimeo.com/1", "Advanced ML", "ML Architectures", "Sarfaraz", "4.62", "live_class"))
        self.assertEqual(req.agenda, "(not provided)")

    def test_nothing_is_resumed_while_a_job_runs_here(self):
        service.RUNNING.add("busy")
        with patch.object(service.ST, "scheduled_to_resume") as look, patch.object(service, "_run_analysis_job") as job:
            self.assertEqual(service._resume_scheduled(), 0)
        look.assert_not_called()
        job.assert_not_called()

    def test_a_class_someone_else_took_is_left_alone(self):
        with patch.object(service.ST, "scheduled_to_resume", return_value=[dict(self.ROW)]), \
             patch.object(service.ST, "claim_for_analysis", return_value=False), \
             patch.object(service, "_run_analysis_job") as job:
            self.assertEqual(service._resume_scheduled(), 0)
        job.assert_not_called()

    def test_a_database_that_cannot_be_asked_means_try_later_not_crash(self):
        with patch.object(service.ST, "scheduled_to_resume", side_effect=RuntimeError("down")), \
             patch.object(service, "_run_analysis_job") as job:
            self.assertEqual(service._resume_scheduled(), 0)
        job.assert_not_called()

    def test_the_switch_turns_it_off(self):
        with patch.dict(os.environ, {"RESUME_SCHEDULED": "0"}), \
             patch.object(service.ST, "scheduled_to_resume") as look:
            self.assertEqual(service._resume_scheduled(), 0)
        look.assert_not_called()

    def test_a_stopping_worker_queues_its_running_classes_again(self):
        service.RUNNING.update({"c2", "c1"})
        with patch.object(service.ST, "requeue_running", return_value=2) as requeue:
            self.assertEqual(service._requeue_running(), 2)
        requeue.assert_called_once_with(["c1", "c2"])
        service.RUNNING.clear()
        with patch.object(service.ST, "requeue_running") as requeue:
            self.assertEqual(service._requeue_running(), 0)
        requeue.assert_not_called()

    def test_the_job_registers_itself_while_it_runs(self):
        seen = {}

        def persist(class_id, *a, **k):
            seen["during"] = set(service.RUNNING)

        req = service.AnalyzeAsyncRequest(class_id="c5", transcript=SRT)
        with patch.object(service, "gather_materials", return_value=None), \
             patch.object(service, "_run_video_stage", return_value=(None, {})), \
             patch.object(service.E, "analyse_cues", return_value=({}, {"cost_usd": 0})), \
             patch.object(service, "_merge_video_meta"), \
             patch.object(service.ST, "persist_analysis", side_effect=persist), \
             patch.object(service, "KeepAwake"):
            service._run_analysis_job(req)
        self.assertEqual(seen["during"], {"c5"})
        self.assertEqual(service.RUNNING, set())

    def test_queued_rows_come_back_as_named_fields(self):
        class Cur:
            def execute(self, sql, params):
                self.sql, self.params = sql, params

            def fetchall(self):
                return [("c9", "https://vimeo.com/1", "Advanced ML", "ML Architectures", "Sarfaraz", "4.62", "", "ars")]

        class Conn:
            cur = Cur()

            def cursor(self):
                return self.cur

            def close(self):
                pass

        conn = Conn()
        with patch.object(service.ST, "_connect", return_value=conn):
            rows = service.ST.scheduled_to_resume(min_age_s=60)
        self.assertEqual(rows[0]["class_type"], "ars")
        self.assertEqual(rows[0]["topic"], "ML Architectures")
        self.assertIn("status = 'scheduled'", conn.cur.sql)
        self.assertEqual(conn.cur.params, (60, 3))


class TestAFailureIsExplainedInWords(unittest.TestCase):
    """22 Sep 2026: the page showed the AI provider's JSON error verbatim. The reason and what to
    do are said in words; the technical text goes to the audit row."""

    def test_known_failures_get_words_and_an_action(self):
        cases = {
            "Error code: 400 - {'error': {'message': 'Your credit balance is too low to access the Anthropic API.'}}": "Claude API fund is empty",
            "Error code: 429 - rate_limit_error": "rate-limited",
            "Error code: 529 - overloaded_error": "overloaded",
            "VimeoError: no text track on this video": "no transcript on Vimeo",
            "GET https://api.vimeo.com/videos/1 → 404": "could not be fetched from Vimeo",
        }
        for text, expected in cases.items():
            self.assertIn(expected, service.plain_failure(RuntimeError(text)), text)

    def test_an_unknown_failure_keeps_its_own_words(self):
        self.assertEqual(service.plain_failure(RuntimeError("something odd")), "something odd")
        self.assertEqual(service.plain_failure(RuntimeError("")), "RuntimeError")

    def test_the_job_records_the_words_and_keeps_the_technical_text(self):
        req = service.AnalyzeAsyncRequest(class_id="c7", transcript=SRT)
        with patch.object(service, "gather_materials", return_value=None), \
             patch.object(service, "_run_video_stage", side_effect=RuntimeError("Error code: 400 - credit balance is too low")), \
             patch.object(service.ST, "mark_failed") as failed, patch.object(service, "KeepAwake"):
            service._run_analysis_job(req)
        args, kwargs = failed.call_args
        self.assertEqual(args[0], "c7")
        self.assertIn("Claude API fund is empty", args[1])
        self.assertIn("not a fault in the system", args[1])
        self.assertIn("credit balance is too low", kwargs["technical"])
        self.assertEqual(kwargs["kind"], "no_credit")
        self.assertIsNone(service.failure_kind(RuntimeError("something odd")))


class TestRequestsThatUsedToBreakTheWorker(unittest.TestCase):
    def test_a_non_ascii_key_is_a_401_not_a_500(self):
        # The HTTP client will not even send non-ASCII header bytes, so the check is called directly:
        # compare_digest on str raised TypeError for such input, which surfaced as a 500.
        from fastapi import HTTPException
        with patch.object(service, "WORKER_API_KEY", "the-real-key"), patch.object(service, "ALLOW_NO_AUTH", False):
            with self.assertRaises(HTTPException) as ctx:
                service.require_worker_auth("Bearer clé-ünïcode")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_an_oversized_body_is_refused_before_it_is_read(self):
        r = client.post("/dry-run", json={"transcript": SRT},
                        headers={"Content-Length": str(service.MAX_BODY_BYTES + 1)})
        self.assertEqual(r.status_code, 413)

    def test_a_database_that_cannot_be_asked_is_a_503_not_a_paid_run(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://x"}),              patch.object(service.ST, "claim_for_analysis", side_effect=service.ST.StoreUnavailable("down")),              patch.object(service, "_run_analysis_job") as job, patch.object(service, "_sweep_stuck", return_value=0):
            r = client.post("/analyze-async", json={"class_id": "c1", "transcript": SRT})
        self.assertEqual(r.status_code, 503)
        job.assert_not_called()

    def test_the_claim_only_takes_scheduled_or_failed_classes(self):
        seen = {}

        class Cur:
            def execute(self, sql, params=None):
                seen["sql"], seen["params"] = sql, params

            def fetchone(self):
                return ("id",)

        class Conn:
            def cursor(self):
                return Cur()

            def commit(self):
                pass

            def close(self):
                pass

        with patch.object(service.ST, "_connect", return_value=Conn()):
            self.assertTrue(REAL_CLAIM("c1"))
        # `status::text`: the column is an enum and the list arrives as text[] (see the store).
        # supabase/test_worker_sql.py runs this statement against the real database.
        self.assertIn("status::text = any(", seen["sql"])
        self.assertEqual(seen["params"], ("c1", ["scheduled", "failed"]))

    def test_a_malformed_scheduler_token_never_reaches_the_database(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://x"}),              patch.object(service.ST, "consume_sync_token", side_effect=AssertionError("must not be asked")):
            for bad in ("abc", "x" * 64, "AB" * 32, ""):
                r = client.post("/sync-ratings/cron", json={"token": bad})
                self.assertEqual(r.status_code, 401, bad)

    def test_token_guesses_are_throttled(self):
        service._CRON_ATTEMPTS.clear()
        for i in range(service.CRON_ATTEMPTS_PER_MINUTE):
            self.assertTrue(service._cron_attempts_allowed(now=1000.0 + i))
        self.assertFalse(service._cron_attempts_allowed(now=1000.0 + service.CRON_ATTEMPTS_PER_MINUTE))
        self.assertTrue(service._cron_attempts_allowed(now=1000.0 + 61.0 + service.CRON_ATTEMPTS_PER_MINUTE))
        service._CRON_ATTEMPTS.clear()


class TestTheWorkerStaysAwakeWhileItWorks(unittest.TestCase):
    """A hosted instance with no inbound traffic is put to sleep, and a background analysis is ten
    to fifteen minutes of exactly that: the job died silently and the class sat on "analyzing"
    (8-16 Sep 2026). While work is in flight the worker now calls its own /health."""

    def test_it_pings_its_own_health_until_the_work_is_done(self):
        seen = []

        class FakeClient:
            def __init__(self, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return None

            def get(self, url):
                seen.append(url)

        with patch.dict(os.environ, {"SELF_URL": "https://worker.example.com/"}), \
                patch("httpx.Client", FakeClient):
            with service.KeepAwake(every_s=0.01):
                deadline = time.time() + 2
                while not seen and time.time() < deadline:
                    time.sleep(0.01)
        self.assertTrue(seen, "no ping was sent while the job ran")
        self.assertEqual(seen[0], "https://worker.example.com/health")

    def test_it_stops_pinging_once_the_work_is_done(self):
        with patch.dict(os.environ, {"SELF_URL": "https://worker.example.com"}):
            keeper = service.KeepAwake(every_s=30)
            with keeper:
                thread = keeper._thread
                self.assertIsNotNone(thread)
        self.assertFalse(thread.is_alive(), "the ping thread outlived the analysis")

    def test_without_an_address_it_simply_does_not_ping(self):
        env = {k: v for k, v in os.environ.items() if k not in ("SELF_URL", "RENDER_EXTERNAL_URL")}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(service.self_url(), "")
            with service.KeepAwake(every_s=0.01) as keeper:
                self.assertIsNone(keeper._thread)

    def test_a_failed_ping_never_touches_the_analysis(self):
        def explode(**kw):
            raise RuntimeError("network down")

        with patch.dict(os.environ, {"SELF_URL": "https://worker.example.com"}), \
                patch("httpx.Client", explode):
            with service.KeepAwake(every_s=0.01):
                time.sleep(0.05)      # the loop raises in its own thread; nothing reaches us

    def test_the_platform_address_is_used_when_no_override_is_set(self):
        env = {k: v for k, v in os.environ.items() if k != "SELF_URL"}
        env["RENDER_EXTERNAL_URL"] = "https://feedback-loop-worker.onrender.com/"
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(service.self_url(), "https://feedback-loop-worker.onrender.com")


if __name__ == "__main__":
    unittest.main()
