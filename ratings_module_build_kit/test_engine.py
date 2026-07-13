"""
test_engine.py — tests for the parts that run without the API (parsing, chunking, validation).
Run:  python -m unittest test_engine -v
The LLM stages are covered by the eval harness (needs ANTHROPIC_API_KEY + labelled classes).
"""
import os, tempfile, unittest
import engine as E

SAMPLE_SRT = """1
00:43:39,000 --> 00:43:41,000
Hello, everyone.

2
00:43:41,500 --> 00:43:45,000
Before I go on, can everyone see me?

3
01:20:00,000 --> 01:20:04,000
Let's open the notebook and write some pandas.
"""

VTT = """WEBVTT

1
00:00:01.000 --> 00:00:03.000
<v Instructor>Welcome.</v>

2
00:00:03.500 --> 00:00:06.000
Today we cover indexing.
"""


class TestParsing(unittest.TestCase):
    def _write(self, text, suffix=".srt"):
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.write(fd, text.encode("utf-8")); os.close(fd)
        self.addCleanup(os.remove, path)
        return path

    def test_srt_basic(self):
        cues = E.parse_transcript(self._write(SAMPLE_SRT))
        self.assertEqual(len(cues), 3)
        self.assertEqual(cues[0].text, "Hello, everyone.")
        self.assertAlmostEqual(cues[0].start, 43 * 60 + 39)

    def test_vtt_voice_tag_becomes_speaker(self):
        cues = E.parse_transcript(self._write(VTT, ".vtt"))
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0].text, "Welcome.")           # WEBVTT header + <v> tag removed from text
        self.assertEqual(cues[0].speaker, "Instructor")      # ...but the speaker is PRESERVED
        self.assertIsNone(cues[1].speaker)                   # unlabelled line -> no speaker

    def test_timestamp_roundtrip(self):
        self.assertEqual(E._seconds_to_ts(E._ts_to_seconds("01:02:03,500")), "01:02:03")

    def test_est_tokens_positive(self):
        cues = E.parse_transcript(self._write(SAMPLE_SRT))
        self.assertGreater(E.est_tokens(cues), 0)


class TestSpeakers(unittest.TestCase):
    """These transcripts have BOTH the instructor and learners — the parser must keep who is speaking."""

    def test_recurring_name_prefix_is_speaker(self):
        vtt = ("WEBVTT\n\n"
               "00:00:01.000 --> 00:00:03.000\nRahul: Why stratified k-fold?\n\n"
               "00:00:04.000 --> 00:00:06.000\nBecause the classes are imbalanced.\n\n"
               "00:00:07.000 --> 00:00:09.000\nRahul: Got it, thanks.\n")
        cues = E.parse_cues(vtt)
        self.assertEqual(cues[0].speaker, "Rahul")               # recurring "Name:" -> speaker
        self.assertEqual(cues[0].text, "Why stratified k-fold?")  # prefix stripped from text
        self.assertIsNone(cues[1].speaker)                       # unlabelled -> instructor (inferred later)

    def test_oneoff_prefix_not_treated_as_speaker(self):
        vtt = ("WEBVTT\n\n"
               "00:00:01.000 --> 00:00:03.000\nProblem: describe the dataset, not a speaker.\n")
        cues = E.parse_cues(vtt)
        self.assertIsNone(cues[0].speaker)                       # appears once -> NOT promoted
        self.assertTrue(cues[0].text.startswith("Problem:"))

    def test_format_segment_keeps_speaker(self):
        seg = [E.Cue(1, 0, 2, "Hi", "Instructor"), E.Cue(2, 3, 5, "A question?", "Rahul")]
        out = E.format_segment(seg)
        self.assertIn("Instructor: Hi", out)
        self.assertIn("Rahul: A question?", out)


class TestChunking(unittest.TestCase):
    def setUp(self):
        # 0..120 min, one cue per minute
        self.cues = [E.Cue(i, i * 60, i * 60 + 1, f"line {i}") for i in range(121)]

    def test_window_count(self):
        chunks = E.chunk_by_time(self.cues, window_min=30, overlap_min=2)
        self.assertEqual(len(chunks), 5)                      # 0-30, 30-60, 60-90, 90-120, 120
        self.assertEqual(chunks[0][0].start, 0)

    def test_overlap_present(self):
        chunks = E.chunk_by_time(self.cues, window_min=30, overlap_min=2)
        starts = [c.start for c in chunks[1]]
        self.assertIn(28 * 60, starts)                        # 2-min overlap pulls in earlier cues

    def test_empty(self):
        self.assertEqual(E.chunk_by_time([]), [])


class TestFindingsValidation(unittest.TestCase):
    def _finding(self, **over):
        f = {"flag": "pace", "observation": "rushed the end", "severity": "moderate",
             "evidence": [{"timestamp": "01:00:00", "quote": "we're almost out of time"}],
             "confidence": "high"}
        f.update(over); return f

    def test_good(self):
        self.assertEqual(E.validate_findings({"findings": [self._finding()]}), [])

    def test_empty_findings_ok(self):
        self.assertEqual(E.validate_findings({"findings": []}), [])

    def test_unknown_flag(self):
        self.assertTrue(E.validate_findings({"findings": [self._finding(flag="vibes")]}))

    def test_bad_severity(self):
        self.assertTrue(E.validate_findings({"findings": [self._finding(severity="huge")]}))

    def test_missing_evidence(self):
        self.assertTrue(E.validate_findings({"findings": [self._finding(evidence=[])]}))


class TestResultValidation(unittest.TestCase):
    def _result(self, **over):
        r = {"overall": "rushed coverage", "feedback": "Nice energy; watch the pace near the end.",
             "flags": [{"flag": "coverage", "severity": "major", "confidence": "high",
                        "evidence": [{"timestamp": "04:30:00", "quote": "we'll do the rest next class"}]}],
             "reclass": {"recommended": "yes", "reason": "last two topics not covered",
                         "deciding_flags": ["coverage"]}}
        r.update(over); return r

    def test_good(self):
        self.assertEqual(E.validate_result(self._result()), [])

    def test_missing_reclass(self):
        r = self._result(); del r["reclass"]
        self.assertTrue(E.validate_result(r))

    def test_bad_reclass_value(self):
        self.assertTrue(E.validate_result(self._result(reclass={"recommended": "perhaps", "reason": "x"})))

    def test_missing_feedback(self):
        self.assertTrue(E.validate_result(self._result(feedback="")))


if __name__ == "__main__":
    unittest.main()
