"""
test_video.py — the video-analysis stage, fully offline (no network, no ffmpeg, no API key).
The subprocess seam (_run_ffmpeg), httpx (MockTransport), and the anthropic client are all mocked.
Run:  python -m unittest test_video -v
"""
import json
import subprocess
import time
from unittest import mock
import unittest
from unittest.mock import patch

import httpx

import video as VD


JPEG = b"\xff\xd8\xff\xe0" + b"x" * 100   # minimal fake JPEG bytes


class TestSampling(unittest.TestCase):
    def test_real_class_2p4h(self):
        times = VD.sample_times(8776)
        self.assertEqual(len(times), 60)                     # interval clamps to 8776/60≈146s → cap
        self.assertAlmostEqual(times[0], 73.1, places=0)     # starts at interval/2
        self.assertLess(times[-1], 8776)

    def test_short_video_min_interval(self):
        times = VD.sample_times(600)                          # 10 min at the 120s min interval
        self.assertEqual(len(times), 5)                       # 60,180,300,420,540
        self.assertTrue(all(times[i+1] - times[i] >= 119 for i in range(len(times)-1)))

    def test_caps_at_max_duration(self):
        times = VD.sample_times(10 * 3600)                    # 10h → capped to 4h of sampling
        self.assertLessEqual(times[-1], 4 * 3600)
        self.assertLessEqual(len(times), VD.VCFG.max_frames)

    def test_zero_duration(self):
        self.assertEqual(VD.sample_times(0), [])


class TestSourceResolution(unittest.TestCase):
    def test_drive_link_rewritten(self):
        src = VD.resolve_video_source(None,
            "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/view", 100)
        self.assertEqual(src.kind, "drive")
        self.assertIn("drive.usercontent.google.com/download", src.url)
        self.assertIn("confirm=t", src.url)

    def test_drive_folder_rejected(self):
        with self.assertRaises(VD.VideoStageError):
            VD._drive_direct_url("https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz012345")

    def test_direct_url_passthrough(self):
        src = VD.resolve_video_source(None, "https://cdn.example.com/class.mp4", 100)
        self.assertEqual(src.kind, "direct")
        self.assertEqual(src.url, "https://cdn.example.com/class.mp4")

    def test_vimeo_probe_used_first(self):
        with patch("vimeo.get_progressive_source",
                   return_value={"link": "https://cdn/v.mp4", "duration": 500}):
            src = VD.resolve_video_source("https://vimeo.com/9", "https://other/x.mp4", 100)
        self.assertEqual(src.kind, "vimeo_progressive")
        self.assertEqual(src.duration_s, 500)

    def test_vimeo_none_falls_to_video_url(self):
        with patch("vimeo.get_progressive_source", return_value=None):
            src = VD.resolve_video_source("https://vimeo.com/9", "https://other/x.mp4", 100)
        self.assertEqual(src.kind, "direct")

    def test_nothing_gives_none(self):
        with patch("vimeo.get_progressive_source", return_value=None):
            self.assertIsNone(VD.resolve_video_source("https://vimeo.com/9", None, 100))
        self.assertIsNone(VD.resolve_video_source(None, "", 100))


class TestProbe(unittest.TestCase):
    def _probe(self, handler):
        with httpx.Client(transport=httpx.MockTransport(handler)) as c:
            return VD.probe_source("https://host/video.mp4", client=c)

    def test_ranges_and_media(self):
        def handler(req):
            self.assertIn("bytes=0-1023", req.headers.get("range", ""))
            return httpx.Response(206, headers={"content-range": "bytes 0-1023/900000",
                                                "content-type": "video/mp4"},
                                  content=b"\x00\x00\x00\x18ftypmp42" + b"0" * 100)
        p = self._probe(handler)
        self.assertTrue(p["ranges"] and p["looks_like_media"])
        self.assertEqual(p["size"], 900000)

    def test_no_ranges(self):
        def handler(req):
            return httpx.Response(200, headers={"content-type": "video/mp4",
                                                "content-length": "12345"}, content=b"\x00" * 64)
        p = self._probe(handler)
        self.assertFalse(p["ranges"])

    def test_html_login_detected(self):
        def handler(req):
            return httpx.Response(200, headers={"content-type": "text/html"},
                                  content=b"<html><body>Sign in to continue</body></html>")
        p = self._probe(handler)
        self.assertTrue(p["html_login"])
        self.assertFalse(p["looks_like_media"])


class TestExtraction(unittest.TestCase):
    SRC = VD.VideoSource("https://host/v.mp4", "direct", 1000)

    def test_frames_extracted_and_failures_skipped(self):
        calls = []
        def fake(args, timeout_s):
            calls.append(args)
            if len(calls) == 2:
                raise VD.VideoStageError("seek failed")
            return JPEG
        with patch.object(VD, "_run_ffmpeg", side_effect=fake), \
             patch.object(VD, "ffmpeg_path", return_value="ffmpeg"):
            frames = VD.extract_frames(self.SRC, [10.0] * 12, time.monotonic() + 60)
        self.assertEqual(len(frames), 11)                      # one skipped

    def test_consecutive_failures_abort(self):
        def fake(args, timeout_s):
            raise VD.VideoStageError("dead source")
        with patch.object(VD, "_run_ffmpeg", side_effect=fake), \
             patch.object(VD, "ffmpeg_path", return_value="ffmpeg"):
            with self.assertRaises(VD.VideoStageError):        # aborts, then <min_frames
                VD.extract_frames(self.SRC, [10.0] * 20, time.monotonic() + 60)

    def test_deadline_stops_extraction(self):
        with patch.object(VD, "_run_ffmpeg", return_value=JPEG), \
             patch.object(VD, "ffmpeg_path", return_value="ffmpeg"):
            with self.assertRaises(VD.VideoStageError):        # deadline in the past → 0 frames
                VD.extract_frames(self.SRC, [10.0] * 20, time.monotonic() - 1)

    def test_timeout_counts_as_failure(self):
        def fake(args, timeout_s):
            raise subprocess.TimeoutExpired("ffmpeg", timeout_s)
        with patch.object(VD, "_run_ffmpeg", side_effect=fake), \
             patch.object(VD, "ffmpeg_path", return_value="ffmpeg"):
            with self.assertRaises(VD.VideoStageError):
                VD.extract_frames(self.SRC, [10.0] * 6, time.monotonic() + 60)


class _FakeMsg:
    def __init__(self, text):
        self.content = [type("B", (), {"type": "text", "text": text})()]
        self.usage = type("U", (), {"input_tokens": 100, "output_tokens": 50})()


class _FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.messages = self

    def create(self, **kw):
        return _FakeMsg(self.replies.pop(0))


def _obs(ts, cam=True, scr=True, ct="slides", title=None, anomalies=None):
    """A frame description as the MODEL sends it: no timestamp, because the code owns the time."""
    return {"camera_on": cam, "screen_shared": scr, "content_type": ct,
            "heading_or_slide_title": title, "anomalies": anomalies or []}


def _seen(at, cam=True, scr=True, ct="slides", title=None, anomalies=None):
    """A frame description after the code has stamped the real frame time onto it."""
    o = _obs(None, cam, scr, ct, title, anomalies)
    o["at"] = at
    return o


class TestObserveFrames(unittest.TestCase):
    def test_batches_parsed(self):
        frames = [(10.0, JPEG), (20.0, JPEG)]
        reply = json.dumps({"frames": [_obs("00:00:10"), _obs("00:00:20")]})
        out = VD.observe_frames(_FakeClient([reply]), frames, "topic", __import__("engine").Usage())
        self.assertEqual(len(out), 2)

    def test_malformed_batch_repaired_then_dropped(self):
        frames = [(10.0, JPEG)]
        out = VD.observe_frames(_FakeClient(["not json", "still not json"]), frames, "t",
                                __import__("engine").Usage())
        self.assertEqual(out, [])                              # dropped after one repair try


class TestVisualTrack(unittest.TestCase):
    def test_spans_titles_anomalies_honesty(self):
        obs = [
            _seen(150, cam=True, scr=True, ct="slides", title="Decision Trees"),
            _seen(300, cam=True, scr=True, ct="slides"),
            _seen(450, cam=False, scr=True, ct="notebook", anomalies=["error_on_screen"]),
            _seen(600, cam=False, scr=True, ct="notebook", title="Decision Trees"),   # dup title
        ]
        track = VD.compress_to_visual_track(obs, 4, 150)
        self.assertIn("[00:02:30-00:05:00] camera ON | screen shared | slides", track)
        self.assertIn("[00:07:30-00:10:00] camera OFF | screen shared | notebook", track)
        self.assertEqual(track.count("Decision Trees"), 1)     # deduped
        self.assertIn("error_on_screen", track)
        self.assertIn("interpolated", track)                   # honesty line

    def test_empty(self):
        self.assertEqual(VD.compress_to_visual_track([], 0, 150), "")


class TestNeverRaise(unittest.TestCase):
    """analyze_video's contract: any failure → ('', meta with video_error). It must never raise."""

    def test_no_source(self):
        with patch("vimeo.get_progressive_source", return_value=None):
            track, meta = VD.analyze_video("https://vimeo.com/9", None, 1000)
        self.assertEqual(track, "")
        self.assertFalse(meta["video_used"])
        self.assertIn("video_files", meta["video_error"])      # actionable message

    def test_disabled_env(self):
        with patch.dict("os.environ", {"VIDEO_DISABLED": "1"}):
            track, meta = VD.analyze_video(None, "https://x/y.mp4", 1000)
        self.assertIn("disabled", meta["video_error"])

    def test_no_ffmpeg(self):
        with patch.object(VD, "ffmpeg_path", return_value=None):
            track, meta = VD.analyze_video(None, "https://x/y.mp4", 1000)
        self.assertIn("ffmpeg", meta["video_error"])

    def test_unexpected_exception_contained(self):
        with patch.object(VD, "ffmpeg_path", return_value="ffmpeg"), \
             patch.object(VD, "resolve_video_source", side_effect=RuntimeError("boom")):
            track, meta = VD.analyze_video(None, "https://x/y.mp4", 1000)
        self.assertEqual(track, "")
        self.assertIn("unexpected", meta["video_error"])



class TestTheTrackOnlyClaimsWhatWasSeen(unittest.TestCase):
    """Everything here used to be asserted as fact on the strength of a string the model typed."""

    def test_span_times_come_from_the_frames_not_the_model(self):
        """The model is not asked for a timestamp at all; the code stamps the real frame time."""
        frames = [(150.0, JPEG), (300.0, JPEG)]
        reply = json.dumps({"frames": [_obs(None), _obs(None)]})
        out = VD.observe_frames(_FakeClient([reply]), frames, "t", __import__("engine").Usage())
        self.assertEqual([o["at"] for o in out], [150.0, 300.0])

    def test_a_gap_where_a_batch_was_dropped_is_shown_not_bridged(self):
        obs = [_seen(0), _seen(150), _seen(900), _seen(1050)]      # 12 minutes missing in the middle
        track = VD.compress_to_visual_track(obs, 8, 150)
        self.assertIn("NOT OBSERVED", track)
        self.assertIn("[00:02:30-00:15:00]", track)

    def test_a_string_where_a_true_or_false_was_expected_does_not_destroy_the_track(self):
        cleaned = VD.clean_observation({"camera_on": "true", "screen_shared": "no",
                                        "content_type": "SLIDES", "anomalies": "blank"})
        self.assertIs(cleaned["camera_on"], True)
        self.assertIs(cleaned["screen_shared"], False)
        self.assertEqual(cleaned["content_type"], "slides")
        self.assertEqual(cleaned["anomalies"], ["blank"])

    def test_a_value_we_do_not_understand_becomes_unknown(self):
        cleaned = VD.clean_observation({"camera_on": "maybe", "content_type": "hologram"})
        self.assertIsNone(cleaned["camera_on"])
        self.assertIsNone(cleaned["content_type"])
        self.assertIn("camera ?", VD.compress_to_visual_track([dict(cleaned, at=0)], 1, 150))

    def test_a_track_that_saw_nothing_is_not_a_track(self):
        nothing = [{"at": i * 150.0, "camera_on": None, "screen_shared": None} for i in range(8)]
        self.assertFalse(VD.track_is_informative(nothing, 60))
        real = [{"at": i * 150.0, "camera_on": True, "screen_shared": True} for i in range(40)]
        self.assertTrue(VD.track_is_informative(real, 60))

    def test_a_truncated_heading_list_says_so(self):
        obs = [_seen(i * 60.0, title=f"Heading number {i}") for i in range(40)]
        track = VD.compress_to_visual_track(obs, 40, 60)
        self.assertIn("more headings not listed", track)
        self.assertIn("do not conclude a topic never appeared", track)

    def test_the_video_url_never_reaches_an_error_message(self):
        url = ("https://vod-progressive.example.net/exp=1757400000~hmac=SECRETabc123/hd.mp4"
               "?token=BEARER-xyz")
        msg = VD.redact(f"Error opening input file {url}. ffmpeg exited")
        self.assertNotIn("BEARER-xyz", msg)
        self.assertNotIn("hmac", msg)
        self.assertIn("<video url>", msg)

    def test_a_short_class_is_not_reported_as_an_unreadable_recording(self):
        times = VD.sample_times(600)                       # a ten-minute class
        self.assertLess(len(times), VD.VCFG.min_frames + 4)
        src = VD.VideoSource(kind="direct", url="x", duration_s=600)
        with mock.patch.object(VD, "extract_frame", return_value=JPEG):
            with self.assertRaises(VD.VideoStageError) as cm:
                VD.extract_frames(src, [1.0], time.monotonic() + 60)
        self.assertIn("too short to sample usefully", str(cm.exception))
        self.assertIn("the recording itself is fine", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
