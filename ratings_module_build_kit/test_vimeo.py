"""
test_vimeo.py — unit tests for the Vimeo transcript module (no network; httpx MockTransport).
Run:  python -m unittest test_vimeo -v
"""
import unittest
from unittest.mock import patch

import httpx

import vimeo as V

TRACKS = {
    "data": [
        {"type": "subtitles", "language": "es", "active": False, "link": "https://cdn.example/es.vtt"},
        {"type": "captions", "language": "en-US", "active": True, "link": "https://cdn.example/en.vtt"},
        {"type": "chapters", "language": "en", "active": True, "link": "https://cdn.example/ch.vtt"},
    ]
}
VTT = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHello class.\n"


def make_client(handler, token="tok", retries=2):
    return V.VimeoClient(V.VimeoConfig(access_token=token, max_retries=retries),
                         transport=httpx.MockTransport(handler))


class TestProgressiveSource(unittest.TestCase):
    """get_progressive_source = runtime capability detection for the video-frames stage."""

    def test_empty_play_returns_none(self):
        # Today's verified reality: token lacks the video_files scope → play is empty → None.
        def handler(req):
            return httpx.Response(200, json={"play": [], "duration": 8776})
        self.assertIsNone(make_client(handler).get_progressive_source("https://vimeo.com/9"))

    def test_picks_smallest_rendition_at_least_360p(self):
        def handler(req):
            return httpx.Response(200, json={"duration": 100, "play": {"progressive": [
                {"link": "https://cdn/1080.mp4", "height": 1080, "width": 1920},
                {"link": "https://cdn/360.mp4", "height": 360, "width": 640},
                {"link": "https://cdn/240.mp4", "height": 240, "width": 426},
            ]}})
        src = make_client(handler).get_progressive_source("https://vimeo.com/9")
        self.assertEqual(src["link"], "https://cdn/360.mp4")   # smallest ≥360p, not the 240p
        self.assertEqual(src["duration"], 100)

    def test_unlisted_hash_retry_on_404(self):
        calls = []
        def handler(req):
            calls.append(str(req.url))
            if ":abc123" in str(req.url):
                return httpx.Response(200, json={"duration": 60, "play": {"progressive": [
                    {"link": "https://cdn/v.mp4", "height": 540, "width": 960}]}})
            return httpx.Response(404)
        src = make_client(handler).get_progressive_source("https://vimeo.com/9/abc123")
        self.assertIsNotNone(src)
        self.assertTrue(any("/videos/9:abc123" in c for c in calls))   # the hash form was used

    def test_403_returns_none_not_raise(self):
        def handler(req):
            return httpx.Response(403, json={"error": "no access"})
        self.assertIsNone(make_client(handler).get_progressive_source("https://vimeo.com/9"))


class TestParse(unittest.TestCase):
    def test_forms(self):
        cases = {
            "https://vimeo.com/123456789": ("123456789", None),
            "https://vimeo.com/123456789/abcdef": ("123456789", "abcdef"),
            "https://player.vimeo.com/video/123456789": ("123456789", None),
            "https://vimeo.com/channels/ch/123456789": ("123456789", None),
            "https://vimeo.com/event/55/video/123456789": ("123456789", None),
            "https://vimeo.com/123456789?h=zzz111": ("123456789", "zzz111"),
            "987654321": ("987654321", None),
        }
        for url, expected in cases.items():
            self.assertEqual(V.parse_vimeo_ref(url), expected, url)

    def test_bad(self):
        with self.assertRaises(V.VimeoError):
            V.parse_vimeo_ref("https://youtube.com/watch?v=x")
        with self.assertRaises(V.VimeoError):
            V.parse_vimeo_ref("")


class TestPick(unittest.TestCase):
    def test_prefers_active_english_captions(self):
        self.assertEqual(V._pick_track(TRACKS["data"])["language"], "en-US")

    def test_none_when_no_captions(self):
        self.assertIsNone(V._pick_track([]))
        self.assertIsNone(V._pick_track([{"type": "chapters", "link": "x"}]))


class TestFetch(unittest.TestCase):
    def test_happy_path(self):
        def handler(req):
            if req.url.path.endswith("/texttracks"):
                return httpx.Response(200, json=TRACKS)
            if req.url.path.endswith("en.vtt"):
                return httpx.Response(200, text=VTT)
            return httpx.Response(404)

        info = make_client(handler).fetch_transcript("https://vimeo.com/123")
        self.assertEqual(info["video_id"], "123")
        self.assertEqual(info["language"], "en-US")
        self.assertIn("Hello class", info["text"])

    def test_no_captions(self):
        with self.assertRaises(V.VimeoNoCaptions):
            make_client(lambda req: httpx.Response(200, json={"data": []})).fetch_transcript("https://vimeo.com/1")

    def test_empty_caption_file(self):
        def handler(req):
            if req.url.path.endswith("/texttracks"):
                return httpx.Response(200, json=TRACKS)
            return httpx.Response(200, text="   ")

        with self.assertRaises(V.VimeoNoCaptions):
            make_client(handler).fetch_transcript("https://vimeo.com/1")

    def test_auth_error(self):
        with self.assertRaises(V.VimeoAuthError):
            make_client(lambda req: httpx.Response(401, json={"error": "no"})).fetch_transcript("https://vimeo.com/1")

    def test_not_found(self):
        with self.assertRaises(V.VimeoError):
            make_client(lambda req: httpx.Response(404)).fetch_transcript("https://vimeo.com/1")

    @patch("vimeo.time.sleep", lambda *_a: None)
    def test_retry_then_success(self):
        calls = {"n": 0}

        def handler(req):
            if req.url.path.endswith("/texttracks"):
                calls["n"] += 1
                return httpx.Response(503) if calls["n"] == 1 else httpx.Response(200, json=TRACKS)
            return httpx.Response(200, text=VTT)

        info = make_client(handler).fetch_transcript("https://vimeo.com/123")
        self.assertEqual(calls["n"], 2)
        self.assertIn("Hello", info["text"])


if __name__ == "__main__":
    unittest.main()
