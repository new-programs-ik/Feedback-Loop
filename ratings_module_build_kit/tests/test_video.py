"""
test_video.py — the video-analysis stage, fully offline (no network, no ffmpeg, no API key).
The subprocess seam (_run_ffmpeg), httpx (MockTransport), and the anthropic client are all mocked.
Run:  python -m pytest tests/test_video.py
"""
import json
import subprocess
import time
from unittest import mock
import unittest
from unittest.mock import patch

import httpx

from feedback import video as VD


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
        with patch("recordings.vimeo.get_progressive_source",
                   return_value={"link": "https://cdn/v.mp4", "duration": 500}):
            src = VD.resolve_video_source("https://vimeo.com/9", "https://other/x.mp4", 100)
        self.assertEqual(src.kind, "vimeo_progressive")
        self.assertEqual(src.duration_s, 500)

    def test_vimeo_none_falls_to_video_url(self):
        with patch("recordings.vimeo.get_progressive_source", return_value=None):
            src = VD.resolve_video_source("https://vimeo.com/9", "https://other/x.mp4", 100)
        self.assertEqual(src.kind, "direct")

    def test_nothing_gives_none(self):
        with patch("recordings.vimeo.get_progressive_source", return_value=None):
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
        out = VD.observe_frames(_FakeClient([reply]), frames, "topic", VD.E.Usage())
        self.assertEqual(len(out), 2)

    def test_malformed_batch_repaired_then_dropped(self):
        frames = [(10.0, JPEG)]
        out = VD.observe_frames(_FakeClient(["not json", "still not json"]), frames, "t",
                                VD.E.Usage())
        self.assertEqual(out, [])                              # dropped after one repair try


class TestVisualTrack(unittest.TestCase):
    def test_spans_titles_anomalies_honesty(self):
        obs = [
            _seen(150, cam=True, scr=True, ct="slides", title="Decision Trees"),
            _seen(300, cam=True, scr=True, ct="slides"),
            _seen(450, cam=False, scr=True, ct="notebook", anomalies=["error_on_screen"]),
            _seen(600, cam=False, scr=True, ct="notebook", title="Decision Trees"),   # dup title
            _seen(750, cam=False, scr=True, ct="notebook"),
            _seen(900, cam=False, scr=True, ct="notebook"),
        ]
        track = VD.compress_to_visual_track(obs, 6, 150)
        self.assertIn("[00:02:30-00:05:00] camera ON | screen shared | slides", track)
        self.assertIn("[00:07:30-00:15:00] camera OFF | screen shared | notebook", track)
        self.assertEqual(track.count("Decision Trees"), 1)     # deduped
        self.assertIn("error_on_screen", track)
        self.assertIn("interpolated", track)                   # honesty line

    def test_empty(self):
        self.assertEqual(VD.compress_to_visual_track([], 0, 150), "")


class TestNeverRaise(unittest.TestCase):
    """analyze_video's contract: any failure → ('', meta with video_error). It must never raise."""

    def test_no_source(self):
        with patch("recordings.vimeo.get_progressive_source", return_value=None):
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
        out = VD.observe_frames(_FakeClient([reply]), frames, "t", VD.E.Usage())
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


def _jpeg(tag: bytes) -> bytes:
    """A stand-in image: starts and ends the way a JPEG does, different bytes per tag."""
    return b"\xff\xd8\xff\xe0" + tag * 40 + b"\xff\xd9"


class _CountingClient:
    """Answers each vision call with one numbered description per image it was shown."""

    def __init__(self, camera=True):
        self.messages = self
        self.calls: list[dict] = []
        self.camera = camera

    def create(self, **kw):
        blocks = kw["messages"][0]["content"]
        n = sum(1 for b in blocks if b.get("type") == "image")
        self.calls.append({"images": n, "kw": kw,
                           "labels": [b["text"] for b in blocks if b.get("type") == "text"]})
        return _FakeMsg(json.dumps({"frames": [
            {"n": i + 1, "camera_on": self.camera, "screen_shared": True, "content_type": "slides"}
            for i in range(n)]}))


class TestOneScreenshotAMinute(unittest.TestCase):
    """Until 1 Oct 2026 a class got 40 screenshots however long it ran, and nothing after the
    fourth hour was looked at: one every six minutes on a four-hour class. A camera off for an
    hour could show as two screenshots, or none."""

    def test_the_spoken_class_is_covered_end_to_end(self):
        interval, n = VD.plan_scan(4338.0, 20656.0)             # a real class: 01:12:18 to 05:44:16
        self.assertEqual(interval, 120.0)                       # one every two minutes by default
        self.assertEqual(n, 136)
        minute = VD.VideoConfig.from_env({"VIDEO_DENSE_INTERVAL_S": "60"})
        self.assertEqual(VD.plan_scan(4338.0, 20656.0, minute), (60.0, 272))

    def test_a_very_long_class_is_spaced_wider_never_cut_short(self):
        interval, n = VD.plan_scan(0, 20 * 3600)
        self.assertEqual(interval, 150.0)                       # 480 screenshots over twenty hours
        self.assertGreaterEqual(n * interval, 20 * 3600)        # ...and they reach the end

    def test_nothing_to_look_at_plans_nothing(self):
        self.assertEqual(VD.plan_scan(100, 100)[1], 0)

    def test_images_come_off_the_pipe_one_at_a_time(self):
        a, b, c = _jpeg(b"a"), _jpeg(b"b"), _jpeg(b"c")
        buf = bytearray(a + b + c[:20])
        self.assertEqual(VD.take_jpegs(buf), [a, b])
        self.assertEqual(bytes(buf), c[:20])                    # the unfinished one waits for more

    def _scan(self, images, code=0):
        src = VD.VideoSource(kind="direct", url="https://x/y.mp4", duration_s=9000)
        seen = {}

        def fake(args, timeout_s, on_chunk):
            seen["args"] = args
            blob = b"".join(images)
            for i in range(0, len(blob), 37):                   # arrives in arbitrary pieces
                on_chunk(blob[i:i + 37])
            return code, "boom" if code else ""
        with patch.object(VD, "ffmpeg_path", return_value="ffmpeg"), \
             patch.object(VD, "_stream_ffmpeg", side_effect=fake):
            frames, interval = VD.scan_frames(src, 600.0, 780.0, time.monotonic() + 60)
        return frames, interval, seen["args"]

    def test_the_recording_is_read_once_and_only_its_key_frames(self):
        frames, interval, args = self._scan([_jpeg(b"a"), _jpeg(b"b"), _jpeg(b"c"), _jpeg(b"d")])
        self.assertEqual([t for t, _ in frames], [600.0, 720.0])   # real times, two minutes apart
        self.assertEqual(args.count("-i"), 1)
        self.assertIn("nokey", args)
        self.assertIn("600.0", args)                            # starts where the class starts

    def test_what_was_read_before_a_failure_is_kept(self):
        frames, _, _ = self._scan([_jpeg(b"a"), _jpeg(b"b")], code=1)
        self.assertEqual(len(frames), 2)

    def test_a_read_that_gives_nothing_says_so(self):
        with self.assertRaises(VD.VideoStageError):
            self._scan([], code=1)

    def test_the_same_picture_is_not_paid_for_twice(self):
        a, b = _jpeg(b"a"), _jpeg(b"b")
        frames = [(0.0, a), (60.0, a), (120.0, b), (180.0, b), (240.0, b)]
        client = _CountingClient()
        obs, reused = VD.observe_once_each(client, frames, "t", VD.E.Usage())
        self.assertEqual(sum(c["images"] for c in client.calls), 2)
        self.assertEqual(reused, 3)
        self.assertEqual([o["at"] for o in obs], [0.0, 60.0, 120.0, 180.0, 240.0])

    def test_every_frame_is_numbered_and_a_description_on_the_wrong_frame_is_refused(self):
        client = _CountingClient()
        VD.observe_frames(client, [(0.0, _jpeg(b"a")), (60.0, _jpeg(b"b"))], "t",
                          VD.E.Usage())
        self.assertTrue(any(lab.startswith("FRAME 1 at") for lab in client.calls[0]["labels"]))
        self.assertTrue(any(lab.startswith("FRAME 2 at") for lab in client.calls[0]["labels"]))
        ok = {"frames": [{"n": 1, "camera_on": True}, {"n": 2, "camera_on": False}]}
        swapped = {"frames": [{"n": 2, "camera_on": False}, {"n": 1, "camera_on": True}]}
        self.assertEqual(VD._validate_observations(ok, 2), [])
        self.assertTrue(VD._validate_observations(swapped, 2))
        self.assertEqual(VD._validate_observations({"frames": [{}, {}]}, 2), [])   # no number: accepted

    def test_each_screenshot_gets_a_call_of_its_own(self):
        """Shown several at once, the model put the right description on the wrong picture."""
        frames = [(i * 120.0, _jpeg(bytes([65 + i]))) for i in range(9)]
        client = _CountingClient()
        usage = VD.E.Usage()
        obs, _ = VD.observe_once_each(client, frames, "t", usage)
        self.assertEqual([c["images"] for c in client.calls], [1] * 9)
        self.assertEqual([o["at"] for o in obs], [i * 120.0 for i in range(9)])   # back in order
        self.assertEqual(usage.calls, 9)                                          # all counted

    def test_one_failed_call_costs_one_screenshot(self):
        frames = [(i * 120.0, _jpeg(bytes([65 + i]))) for i in range(4)]

        class Flaky(_CountingClient):
            def create(self, **kw):
                if "FRAME 1 at [00:04:00]" in json.dumps(kw["messages"]):
                    raise RuntimeError("overloaded")
                return super().create(**kw)
        obs, _ = VD.observe_once_each(Flaky(), frames, "t", VD.E.Usage())
        self.assertEqual([o["at"] for o in obs], [0.0, 120.0, 360.0])

    def test_the_instructions_are_cached_and_the_cache_is_priced(self):
        client = _CountingClient()
        VD.observe_frames(client, [(0.0, _jpeg(b"a"))], "t", VD.E.Usage())
        system = client.calls[0]["kw"]["system"]
        self.assertEqual(system[0]["cache_control"], {"type": "ephemeral"})
        u = VD.E.Usage()
        u.cache_write_tokens, u.cache_read_tokens = 1_000_000, 1_000_000
        self.assertAlmostEqual(VD.cost_usd(u, "claude-sonnet-5"), 2.0 * 1.25 + 2.0 * 0.1)

    def test_looking_is_not_reasoning(self):
        client = _CountingClient()
        VD.observe_frames(client, [(0.0, _jpeg(b"a"))], "t", VD.E.Usage())
        self.assertEqual(client.calls[0]["kw"]["thinking"], {"type": "disabled"})
        VD.observe_frames(client, [(0.0, _jpeg(b"a"))], "t", VD.E.Usage(),
                          model="claude-haiku-4-5")
        self.assertNotIn("thinking", client.calls[1]["kw"])
        self.assertEqual(client.calls[1]["kw"]["model"], "claude-haiku-4-5")

    def test_another_model_is_priced_at_its_own_rate(self):
        u = VD.E.Usage()
        u.input_tokens, u.output_tokens = 1_000_000, 100_000
        self.assertAlmostEqual(VD.cost_usd(u, "claude-haiku-4-5"), 1.5)
        self.assertAlmostEqual(VD.cost_usd(u, "claude-sonnet-5"), 3.0)

    def test_an_old_frame_cap_on_the_server_does_not_thin_the_every_minute_pass(self):
        cfg = VD.VideoConfig.from_env({"VIDEO_MAX_FRAMES": "40"})
        self.assertEqual(cfg.max_frames, 40)                    # the fallback sampler only
        self.assertEqual(VD.plan_scan(0, 4 * 3600, cfg)[1], 121)


class TestTheTrackSaysHowLong(unittest.TestCase):
    def test_a_camera_off_for_an_hour_is_stated_as_an_hour(self):
        obs = [_seen(i * 60.0, cam=not (30 <= i < 90)) for i in range(240)]     # off 00:30-01:29
        track = VD.compress_to_visual_track(obs, 240, 60)
        self.assertIn("CAMERA: a camera picture was on screen in 180 of 240 screenshots (75%).", track)
        self.assertIn("NO camera picture in ANY screenshot for 10 minutes or more: "
                      "[00:30:00-01:29:00] about 60 min.", track)
        self.assertIn("[00:30:00-01:29:00] camera OFF | screen shared | slides", track)
        self.assertIn("SCREEN: something was being shared in 240 of 240", track)

    def test_a_stretch_nobody_saw_does_not_join_two_off_stretches(self):
        obs = ([_seen(i * 60.0, cam=False) for i in range(12)] + [_seen(720.0)]
               + [_seen(2400 + i * 60.0, cam=False) for i in range(11)])
        track = VD.compress_to_visual_track(obs, 60, 60)
        self.assertIn("[00:00:00-00:11:00] about 12 min; [00:40:00-00:50:00] about 11 min.", track)

    def test_a_class_that_keeps_switching_content_still_gets_a_readable_track(self):
        obs = [_seen(i * 60.0, ct="slides" if i % 2 else "notebook") for i in range(200)]
        track = VD.compress_to_visual_track(obs, 200, 60)
        self.assertIn("VISUAL STATES (camera | screen):", track)
        self.assertLess(track.count("\n"), 30)
        self.assertIn("ON SCREEN: notebook 50%, slides 50%.", track)

    def test_repeats_are_declared(self):
        obs = [_seen(i * 60.0) for i in range(6)]
        self.assertIn("3 of them showed exactly the picture before them",
                      VD.compress_to_visual_track(obs, 6, 60, reused=3))


class TestOneScreenshotWithoutTheCameraProvesNothing(unittest.TestCase):
    """A recording shows the instructor's tile only while they are speaking. On a real class it
    came and went 34 times in twenty minutes and was in 78% of screenshots with the camera on
    throughout - so the old 40-screenshot track reported "camera OFF" for a fifth of any class."""

    def _flicker(self, n=120):
        return [_seen(i * 120.0, cam=(i % 5 != 0)) for i in range(n)]      # gone in one of five

    def test_a_tile_that_comes_and_goes_is_a_camera_that_is_on(self):
        track = VD.compress_to_visual_track(self._flicker(), 120, 120)
        self.assertNotIn("camera OFF", track)
        self.assertIn("[00:00:00-03:58:00] camera ON | screen shared | slides", track)
        self.assertIn("a camera picture was on screen in 96 of 120 screenshots (80%)", track)
        self.assertIn("There was no stretch of 10 minutes or more without a camera picture.", track)

    def test_ten_minutes_without_it_in_every_screenshot_is_reported(self):
        obs = self._flicker()
        for o in obs[40:46]:                                               # 01:20 to 01:30, all six
            o["camera_on"] = False
        track = VD.compress_to_visual_track(obs, 120, 120)
        self.assertIn("NO camera picture in ANY screenshot for 10 minutes or more: "
                      "[01:20:00-01:30:00] about 12 min.", track)
        self.assertIn("[01:20:00-01:30:00] camera OFF | screen shared | slides", track)

    def test_eight_minutes_is_not_called_a_stretch(self):
        obs = [_seen(i * 120.0, cam=not (40 <= i < 44)) for i in range(120)]
        track = VD.compress_to_visual_track(obs, 120, 120)
        self.assertNotIn("camera OFF", track)

    def test_a_recording_with_no_tile_at_all_cannot_say_the_camera_was_off(self):
        """Some recordings are made of the shared screen alone. Three hours of "camera off" from
        one of those would be a finding about the recording settings, not about the instructor."""
        obs = [_seen(i * 120.0, cam=False) for i in range(90)]
        track = VD.compress_to_visual_track(obs, 90, 120)
        self.assertIn("CANNOT show whether the instructor's camera was on", track)
        self.assertNotIn("camera OFF", track)
        self.assertIn("camera ? | screen shared", track)

    def test_a_camera_never_seen_with_nothing_shared_is_off(self):
        obs = [_seen(i * 120.0, cam=False, scr=False, ct="other") for i in range(30)]
        track = VD.compress_to_visual_track(obs, 30, 120)
        self.assertIn("camera OFF | no screen", track)
        self.assertIn("[00:00:00-00:58:00] about 60 min.", track)


class TestTheStageLooksAtTheClassNotTheWaitingRoom(unittest.TestCase):
    def _run(self, scan):
        src = VD.VideoSource(kind="direct", url="https://x/y.mp4", duration_s=25704.0)   # 7.14 h
        frames = [(4338.0 + i * 60.0, _jpeg(bytes([65 + i % 20]))) for i in range(40)]
        with patch.object(VD, "ffmpeg_path", return_value="ffmpeg"), \
             patch.object(VD, "resolve_video_source", return_value=src), \
             patch.object(VD, "probe_source", return_value={"ranges": True, "looks_like_media": True}), \
             patch.object(VD, "scan_frames", side_effect=scan(frames)) as sc, \
             patch.object(VD, "extract_frames", return_value=frames[:10]) as ex, \
             patch.object(VD.E, "_client", return_value=_CountingClient()):
            track, meta = VD.analyze_video(None, "https://x/y.mp4", 20596.0, "t", start_hint_s=4398.0)
        return track, meta, sc, ex

    def test_only_the_spoken_stretch_is_read(self):
        track, meta, sc, ex = self._run(lambda frames: lambda *a, **k: (frames, 60.0))
        self.assertEqual(sc.call_args.args[1:3], (4338.0, 20656.0))    # a minute either side
        self.assertEqual(meta["video_mode"], "every_minute")
        self.assertEqual(meta["frames_sampled"], 136)
        self.assertEqual(meta["video_interval_s"], 60)
        ex.assert_not_called()

    def test_a_file_that_cannot_be_read_in_one_pass_falls_back_to_seeking(self):
        def scan(frames):
            def boom(*a, **k):
                raise VD.VideoStageError("exit 1")
            return boom
        track, meta, sc, ex = self._run(scan)
        self.assertEqual(meta["video_mode"], "seek")
        ex.assert_called_once()
        self.assertGreaterEqual(ex.call_args.args[1][0], 4338.0)        # still inside the class
        self.assertLessEqual(ex.call_args.args[1][-1], 20656.0)


if __name__ == "__main__":
    unittest.main()
