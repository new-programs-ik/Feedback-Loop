"""
test_service.py — endpoint tests for the analysis worker (FastAPI TestClient).
The engine + Vimeo are mocked, so no API key or network is needed.
Run:  python -m unittest test_service -v
"""
import base64
import json
import os
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


def setUpModule():
    _version_patch.start()
    _auth_patch.start()


def tearDownModule():
    _version_patch.stop()
    _auth_patch.stop()


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

    def test_sync_learners_is_501_until_a_source_exists(self):
        with patch.dict(os.environ, {"LEARNER_SOURCE": ""}):
            r = client.post("/sync-learners", json={})
        self.assertEqual(r.status_code, 501)
        self.assertIn("no learner-level data source", r.json()["detail"])
        with patch.dict(os.environ, {"LEARNER_SOURCE": "csv"}):
            r = client.post("/sync-learners")
        self.assertEqual(r.status_code, 501)
        self.assertIn("names no implementation", r.json()["detail"])

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

    def test_a_second_request_while_one_is_running_is_refused(self):
        with patch.object(service.ST, "claim_for_analysis", return_value=False) as claim,              patch.object(service, "_run_analysis_job") as job:
            r = client.post("/analyze-async", json={"class_id": "c1", "transcript": SRT})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["status"], "already running")
            claim.assert_called_once_with("c1")
            job.assert_not_called()

    def test_the_first_request_is_accepted(self):
        with patch.object(service.ST, "claim_for_analysis", return_value=True),              patch.object(service, "_run_analysis_job"):
            r = client.post("/analyze-async", json={"class_id": "c1", "transcript": SRT})
            self.assertEqual(r.json()["status"], "accepted")


if __name__ == "__main__":
    unittest.main()
