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
             "instructor_summary": "Your explanations were clear and engaging. The final topics felt rushed. "
                                   "This session averaged 4.1/5. Try a mid-class time-check. Overall a solid session.",
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

    def test_missing_instructor_summary(self):
        self.assertTrue(E.validate_result(self._result(instructor_summary="")))


class TestSeverityHelpers(unittest.TestCase):
    def test_rank_ordering(self):
        self.assertLess(E.severity_rank("minor"), E.severity_rank("moderate"))
        self.assertLess(E.severity_rank("moderate"), E.severity_rank("major"))
        self.assertEqual(E.severity_rank("nonsense"), -1)

    def test_one_level_down_clamps_at_minor(self):
        self.assertEqual(E.one_level_down("major"), "moderate")
        self.assertEqual(E.one_level_down("moderate"), "minor")
        self.assertEqual(E.one_level_down("minor"), "minor")


class TestQuoteCheck(unittest.TestCase):
    TX = "Alright everyone — today we cover “decision trees”, and then ensembles."

    def test_quote_present_normalises_whitespace_and_curly_quotes(self):
        self.assertTrue(E.quote_present(self.TX, 'today we cover "decision trees"'))
        self.assertTrue(E.quote_present(self.TX, "TODAY   we cover decision trees"))

    def test_absent_quote_false(self):
        self.assertFalse(E.quote_present(self.TX, "we will skip the ensembles"))
        self.assertFalse(E.quote_present(self.TX, ""))

    def test_excerpt_around_window(self):
        cues = [E.Cue(i, i * 60, i * 60 + 5, f"line {i}") for i in range(10)]
        out = E.excerpt_around(cues, "00:05:00", window_s=120)
        self.assertIn("line 5", out)
        self.assertIn("line 3", out)      # 2 min before
        self.assertNotIn("line 8", out)   # 3 min after — outside the window
        self.assertEqual(E.excerpt_around(cues, "garbage"), "")


def _cand(i, flag="pace", severity="major", quote="we're out of time"):
    return {"id": i, "flag": flag, "severity": severity, "confidence": "high",
            "evidence": [{"timestamp": "00:10:00", "quote": quote}]}


def _verdict(i, verdict="uphold", corrected=None, anchor="tie-break low", reason="checked"):
    v = {"id": i, "verdict": verdict, "anchor_rule": anchor, "reason": reason}
    if corrected:
        v["corrected_severity"] = corrected
    return v


class TestVerdictValidation(unittest.TestCase):
    def test_good_verdicts_pass(self):
        cands = [_cand(0), _cand(1, severity="moderate")]
        obj = {"verdicts": [_verdict(0), _verdict(1, "downgrade", "minor")]}
        self.assertEqual(E.validate_verdicts(obj, cands), [])

    def test_missing_candidate_id_fails(self):
        self.assertTrue(E.validate_verdicts({"verdicts": [_verdict(0)]}, [_cand(0), _cand(1)]))

    def test_extra_invented_id_fails(self):
        self.assertTrue(E.validate_verdicts({"verdicts": [_verdict(0), _verdict(9)]}, [_cand(0)]))

    def test_unknown_verdict_fails(self):
        self.assertTrue(E.validate_verdicts({"verdicts": [_verdict(0, "escalate")]}, [_cand(0)]))

    def test_downgrade_severity_handling(self):
        cands = [_cand(0, severity="moderate")]
        # a real downgrade validates
        self.assertEqual(E.validate_verdicts({"verdicts": [_verdict(0, "downgrade", "minor")]}, cands), [])
        # a missing corrected_severity is still an error (the model must say what it means)
        self.assertTrue(E.validate_verdicts({"verdicts": [_verdict(0, "downgrade")]}, cands))
        # a "downgrade" that is not lower is ACCEPTED here and normalised to uphold by apply_verdicts —
        # rejecting it used to burn the repair attempt and lose verification for the whole class.
        self.assertEqual(E.validate_verdicts({"verdicts": [_verdict(0, "downgrade", "major")]}, cands), [])

    def test_empty_reason_or_anchor_fails(self):
        self.assertTrue(E.validate_verdicts({"verdicts": [_verdict(0, reason=" ")]}, [_cand(0)]))
        self.assertTrue(E.validate_verdicts({"verdicts": [_verdict(0, anchor="")]}, [_cand(0)]))


class TestApplyVerdicts(unittest.TestCase):
    def _result(self, flags):
        return {"overall": "x", "feedback": "f", "instructor_summary": "s", "flags": flags,
                "reclass": {"recommended": "no", "reason": "r"}}

    def test_uphold_keeps_flag_and_records(self):
        res = self._result([{"flag": "pace", "severity": "major", "confidence": "high",
                             "evidence": [{"timestamp": "00:10:00", "quote": "q"}]}])
        out, review = E.apply_verdicts(res, [_verdict(0)], "live_class")
        self.assertEqual(len(out["flags"]), 1)
        self.assertEqual(review[0]["verdict"], "uphold")
        self.assertEqual(review[0]["to_severity"], "major")

    def test_downgrade_major_to_moderate(self):
        res = self._result([{"flag": "pace", "severity": "major", "confidence": "high",
                             "evidence": [{"timestamp": "00:10:00", "quote": "q"}]}])
        out, review = E.apply_verdicts(res, [_verdict(0, "downgrade", "moderate")], "live_class")
        self.assertEqual(out["flags"][0]["severity"], "moderate")
        self.assertEqual(review[0]["to_severity"], "moderate")

    def test_two_level_downgrade_clamped_to_one(self):
        res = self._result([{"flag": "pace", "severity": "major", "confidence": "high",
                             "evidence": [{"timestamp": "00:10:00", "quote": "q"}]}])
        out, review = E.apply_verdicts(res, [_verdict(0, "downgrade", "minor")], "live_class")
        self.assertEqual(out["flags"][0]["severity"], "moderate")   # clamped
        self.assertEqual(review[0]["skeptic_wanted"], "minor")      # but recorded

    def test_ars_correctness_floor_blocks_downgrade(self):
        res = self._result([{"flag": "correctness", "severity": "major", "confidence": "high",
                             "evidence": [{"timestamp": "00:10:00", "quote": "q"}]}])
        out, review = E.apply_verdicts(res, [_verdict(0, "downgrade", "moderate")], "ars")
        self.assertEqual(out["flags"][0]["severity"], "major")      # floor wins
        self.assertEqual(review[0]["verdict"], "uphold")
        self.assertIn("floor", review[0]["reason"])

    def test_drop_removes_flag_but_keeps_review_record(self):
        res = self._result([{"flag": "pace", "severity": "major", "confidence": "high",
                             "evidence": [{"timestamp": "00:10:00", "quote": "q"}]}])
        out, review = E.apply_verdicts(res, [_verdict(0, "drop", reason="learner speaking")], "live_class")
        self.assertEqual(out["flags"], [])
        self.assertEqual(review[0]["verdict"], "drop")
        self.assertIsNone(review[0]["to_severity"])

    def test_input_result_not_mutated(self):
        res = self._result([{"flag": "pace", "severity": "major", "confidence": "high",
                             "evidence": [{"timestamp": "00:10:00", "quote": "q"}]}])
        E.apply_verdicts(res, [_verdict(0, "drop")], "live_class")
        self.assertEqual(res["flags"][0]["severity"], "major")      # original untouched

    def test_confidence_and_evidence_untouched(self):
        res = self._result([{"flag": "pace", "severity": "major", "confidence": "high",
                             "evidence": [{"timestamp": "00:10:00", "quote": "q"}]}])
        out, _ = E.apply_verdicts(res, [_verdict(0, "downgrade", "moderate")], "live_class")
        self.assertEqual(out["flags"][0]["confidence"], "high")
        self.assertEqual(out["flags"][0]["evidence"][0]["quote"], "q")


class TestMergeConservative(unittest.TestCase):
    def test_drop_beats_downgrade_beats_uphold(self):
        v1 = [_verdict(0, "uphold"), _verdict(1, "downgrade", "moderate"), _verdict(2, "drop")]
        v2 = [_verdict(0, "downgrade", "moderate"), _verdict(1, "drop"), _verdict(2, "uphold")]
        merged = {v["id"]: v["verdict"] for v in E.merge_conservative(v1, v2)}
        self.assertEqual(merged, {0: "downgrade", 1: "drop", 2: "drop"})

    def test_second_vote_never_adds_ids(self):
        merged = E.merge_conservative([_verdict(0)], [_verdict(0, "drop"), _verdict(5, "drop")])
        self.assertEqual([v["id"] for v in merged], [0])


class TestReclassGating(unittest.TestCase):
    def _res(self, recommended, flags):
        return {"flags": flags, "reclass": {"recommended": recommended, "reason": "orig reason"}}

    def _major(self, flag):
        return {"flag": flag, "severity": "major", "confidence": "high",
                "evidence": [{"timestamp": "00:01:00", "quote": "q"}]}

    def test_yes_with_upheld_content_major_stays_yes(self):
        out = E.gate_reclass(self._res("yes", [self._major("coverage")]))
        self.assertEqual(out["reclass"]["recommended"], "yes")

    def test_yes_with_only_engagement_major_softens_to_maybe(self):
        out = E.gate_reclass(self._res("yes", [self._major("engagement")]))
        self.assertEqual(out["reclass"]["recommended"], "maybe")
        self.assertEqual(out["reclass"]["softened_from"], "yes")
        self.assertIn("orig reason", out["reclass"]["reason"])   # original preserved

    def test_yes_with_zero_flags_softens(self):
        out = E.gate_reclass(self._res("yes", []))
        self.assertEqual(out["reclass"]["recommended"], "maybe")

    def test_maybe_never_upgraded(self):
        out = E.gate_reclass(self._res("maybe", [self._major("coverage")]))
        self.assertEqual(out["reclass"]["recommended"], "maybe")
        self.assertNotIn("softened_from", out["reclass"])

    def test_no_untouched(self):
        out = E.gate_reclass(self._res("no", []))
        self.assertEqual(out["reclass"]["recommended"], "no")


class TestSelectCandidates(unittest.TestCase):
    def test_majors_and_moderates_selected_minors_skipped(self):
        res = {"flags": [{"flag": "pace", "severity": "major"},
                         {"flag": "clarity", "severity": "minor"},
                         {"flag": "coverage", "severity": "moderate"}],
               "reclass": {"recommended": "no"}}
        ids = [c["id"] for c in E.select_review_candidates(res)]
        self.assertEqual(ids, [0, 2])

    def test_deciding_flag_force_included_on_yes(self):
        res = {"flags": [{"flag": "coverage", "severity": "minor"}],
               "reclass": {"recommended": "yes", "deciding_flags": ["coverage"]}}
        self.assertEqual([c["id"] for c in E.select_review_candidates(res)], [0])


class TestResultValidationReview(unittest.TestCase):
    def _base(self):
        return {"overall": "o", "feedback": "f", "instructor_summary": "s", "flags": [],
                "reclass": {"recommended": "no", "reason": "r"}}

    def test_review_optional(self):
        self.assertEqual(E.validate_result(self._base()), [])

    def test_result_with_review_list_passes(self):
        r = self._base()
        r["review"] = [{"flag": "pace", "verdict": "downgrade", "from_severity": "major",
                        "to_severity": "moderate", "anchor_rule": "a", "reason": "b"}]
        self.assertEqual(E.validate_result(r), [])

    def test_bad_review_verdict_fails(self):
        r = self._base()
        r["review"] = [{"flag": "pace", "verdict": "escalate", "from_severity": "major",
                        "to_severity": None, "reason": "x"}]
        self.assertTrue(E.validate_result(r))

    def test_bad_softened_from_fails(self):
        r = self._base()
        r["reclass"]["softened_from"] = "no"
        self.assertTrue(E.validate_result(r))


if __name__ == "__main__":
    unittest.main()


class TestVerificationIsNonFatal(unittest.TestCase):
    """The self-check is a quality enhancement — it must never destroy an analysis."""

    def test_bogus_downgrade_is_treated_as_uphold(self):
        res = {"overall": "o", "feedback": "f", "instructor_summary": "s",
               "flags": [{"flag": "pace", "severity": "moderate", "confidence": "high",
                          "evidence": [{"timestamp": "00:10:00", "quote": "q"}]}],
               "reclass": {"recommended": "no", "reason": "r"}}
        # skeptic says "downgrade" but hands back a HIGHER severity — must never raise it
        bad = [{"id": 0, "verdict": "downgrade", "corrected_severity": "major",
                "anchor_rule": "a", "reason": "b"}]
        out, review = E.apply_verdicts(res, bad, "live_class")
        self.assertEqual(out["flags"][0]["severity"], "moderate")   # unchanged
        self.assertEqual(review[0]["verdict"], "uphold")

    def test_equal_severity_downgrade_is_uphold(self):
        res = {"overall": "o", "feedback": "f", "instructor_summary": "s",
               "flags": [{"flag": "pace", "severity": "moderate", "confidence": "high",
                          "evidence": [{"timestamp": "00:10:00", "quote": "q"}]}],
               "reclass": {"recommended": "no", "reason": "r"}}
        out, review = E.apply_verdicts(res, [{"id": 0, "verdict": "downgrade",
                                              "corrected_severity": "moderate",
                                              "anchor_rule": "a", "reason": "b"}], "live_class")
        self.assertEqual(out["flags"][0]["severity"], "moderate")
        self.assertEqual(review[0]["verdict"], "uphold")


class TestInstructorSummaryTidy(unittest.TestCase):
    """The note the instructor RECEIVES: no timestamps, at most 5 bullets."""

    NOTE = (
        "Good energy throughout at [00:05:00] - this session averaged 4.1/5.\n"
        "- Problems 3 and 5 were skipped ([00:20:00], [00:25:30]). Fix: budget time per problem.\n"
        "- Problem 1 was rushed ([00:02:00]-[00:04:00]). Fix: explain the key lines.\n"
        "- Reasoning was deferred to the notebook at 00:06:00. Fix: state the principle first.\n"
        "- No recap (00:25:30). Fix: close with the takeaway.\n"
        "- Pacing drifted around [01:02:03]. Fix: watch the clock.\n"
        "- A sixth, least important point. Fix: drop me.\n"
    )

    def test_strips_every_timestamp_form(self):
        out = E.tidy_instructor_summary(self.NOTE)
        self.assertNotRegex(out, r"\d{1,2}:\d{2}")

    def test_keeps_the_rating(self):
        self.assertIn("4.1/5", E.tidy_instructor_summary(self.NOTE))

    def test_caps_bullets_and_keeps_the_most_important(self):
        out = E.tidy_instructor_summary(self.NOTE)
        bullets = [l for l in out.splitlines() if l.startswith("- ")]
        self.assertEqual(len(bullets), E.SUMMARY_MAX_BULLETS)
        self.assertIn("Problems 3 and 5", bullets[0])       # first (most important) survives
        self.assertNotIn("sixth", out)                       # the overflow bullet is dropped

    def test_no_orphan_punctuation_left_behind(self):
        out = E.tidy_instructor_summary(self.NOTE)
        self.assertNotIn("(,", out)
        self.assertNotIn("( )", out)
        self.assertNotIn(" .", out)
        self.assertNotIn("()", out)

    def test_short_note_passes_through_unchanged(self):
        note = "Solid session - averaged 4.4/5.\n- Pace was fast. Fix: slow down."
        self.assertEqual(E.tidy_instructor_summary(note), note)

    def test_empty_input_is_safe(self):
        self.assertEqual(E.tidy_instructor_summary(""), "")
        self.assertEqual(E.tidy_instructor_summary(None), None)


class TestSdkDriftGuard(unittest.TestCase):
    """anthropic 1.x dropped `temperature` from Messages.create() and killed every analysis in
    production. A keyword the installed SDK doesn't know must degrade, not take the tool down."""

    class _Msg:
        class usage:
            input_tokens = 10
            output_tokens = 5
        content = [type("B", (), {"type": "text", "text": "hi"})()]

    def setUp(self):
        E._UNSUPPORTED_KWARGS.clear()

    def tearDown(self):
        E._UNSUPPORTED_KWARGS.clear()

    def _client(self, reject: str | None):
        outer = self

        class Messages:
            def __init__(self):
                self.calls = []

            def create(self, **kw):
                self.calls.append(kw)
                if reject and reject in kw:
                    raise TypeError(
                        f"Messages.create() got an unexpected keyword argument '{reject}'")
                return outer._Msg()

        class Client:
            def __init__(self):
                self.messages = Messages()

        return Client()

    def test_retries_without_the_rejected_keyword(self):
        c = self._client("temperature")
        out = E._call(c, "sys", "user", 100, E.Usage())
        self.assertEqual(out, "hi")                       # the analysis still completes
        self.assertIn("temperature", c.messages.calls[0])  # tried it once
        self.assertNotIn("temperature", c.messages.calls[1])  # then dropped it

    def test_remembers_so_it_only_fails_once(self):
        c = self._client("temperature")
        E._call(c, "sys", "user", 100, E.Usage())
        E._call(c, "sys", "user", 100, E.Usage())
        self.assertEqual(len(c.messages.calls), 3)        # 2 for the first call, 1 for the second
        self.assertNotIn("temperature", c.messages.calls[2])

    def test_usage_is_still_accounted(self):
        c, u = self._client("temperature"), E.Usage()
        E._call(c, "sys", "user", 100, u)
        self.assertEqual((u.input_tokens, u.output_tokens, u.calls), (10, 5, 1))

    def test_a_working_sdk_is_untouched(self):
        c = self._client(None)
        E._call(c, "sys", "user", 100, E.Usage())
        self.assertEqual(len(c.messages.calls), 1)
        self.assertIn("temperature", c.messages.calls[0])

    def test_unrelated_type_errors_still_raise(self):
        class Client:
            class messages:
                @staticmethod
                def create(**kw):
                    raise TypeError("something else entirely")
        with self.assertRaises(TypeError):
            E._call(Client(), "sys", "user", 100, E.Usage())
