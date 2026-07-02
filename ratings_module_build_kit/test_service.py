"""
test_service.py — endpoint tests for the analysis worker (FastAPI TestClient).
The engine + Vimeo are mocked, so no API key or network is needed.
Run:  python -m unittest test_service -v
"""
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


if __name__ == "__main__":
    unittest.main()
