"""
test_service.py — endpoint tests for the analysis worker (FastAPI TestClient).
The engine + Vimeo are mocked, so no API key or network is needed.
Run:  python -m unittest test_service -v
"""
import base64
import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import service

client = TestClient(service.app)

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
        with patch.object(service.E, "analyse_text", return_value=(RESULT, META)) as m:
            r = client.post("/analyze", json={"transcript": SRT, "course": "ML", "instructor": "Jo"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["transcript_source"], "upload")
        self.assertEqual(body["result"]["reclass"]["recommended"], "yes")
        m.assert_called_once()

    def test_analyze_with_vimeo(self):
        with patch.object(service.V, "fetch_transcript", return_value=VINFO), \
             patch.object(service.E, "analyse_text", return_value=(RESULT, META)):
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
        with patch.object(service.E, "analyse_text", return_value=(RESULT, META)) as m:
            r = client.post("/analyze", json={"transcript": SRT, "class_type": "ars"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(m.call_args.args[2], "ars")           # class_type forwarded to the engine
        self.assertIn("Assignment Review Session", m.call_args.args[1])  # context mentions ARS

    def test_analyze_rejects_bad_class_type(self):
        r = client.post("/analyze", json={"transcript": SRT, "class_type": "workshop"})
        self.assertEqual(r.status_code, 422)

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
        with patch.object(service.E, "analyse_text", return_value=(RESULT, META)) as m:
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


if __name__ == "__main__":
    unittest.main()
