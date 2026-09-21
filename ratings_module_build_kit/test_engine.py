"""
test_engine.py — tests for the parts that run without the API (parsing, chunking, validation).
Run:  python -m unittest test_engine -v
The LLM stages are covered by the eval harness (needs ANTHROPIC_API_KEY + labelled classes).
"""
import json, os, tempfile, unittest
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


class TestBadTimestampsCannotHangTheWorker(unittest.TestCase):
    """One cue stamped days into the future used to make chunk_by_time step through millions of
    empty windows while the class sat on "analyzing"."""

    def test_a_far_future_cue_is_dropped_and_the_rest_chunk_normally(self):
        cues = [E.Cue(i, i * 60, i * 60 + 1, f"line {i}") for i in range(60)]
        cues.append(E.Cue(999, 999_999 * 3600, 999_999 * 3600 + 1, "stray"))
        chunks = E.chunk_by_time(cues, window_min=30, overlap_min=2)
        self.assertLessEqual(len(chunks), 3)
        self.assertNotIn("stray", [c.text for w in chunks for c in w])

    def test_a_class_within_twelve_hours_keeps_every_cue(self):
        cues = [E.Cue(i, i * 600, i * 600 + 1, f"line {i}") for i in range(30)]   # 5 hours
        chunks = E.chunk_by_time(cues, window_min=30, overlap_min=2)
        self.assertEqual({c.text for w in chunks for c in w}, {c.text for c in cues})


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


class TestReclassReasonIsHonest(unittest.TestCase):
    """The PM reads the re-class reason. After verification deletes a finding, the reason must not
    still recite it - that is what made a 'maybe' look arbitrary in the first four real analyses."""

    def _major(self, flag):
        return {"flag": flag, "severity": "major", "confidence": "high",
                "evidence": [{"timestamp": "00:01:00", "quote": "q"}]}

    def test_softening_note_names_what_survived(self):
        res = {"flags": [self._major("engagement"),
                         {"flag": "coverage", "severity": "moderate", "confidence": "high",
                          "evidence": [{"timestamp": "00:02:00", "quote": "q"}]}],
               "reclass": {"recommended": "yes", "reason": "three wrong statements"}}
        out = E.gate_reclass(res)
        self.assertEqual(out["reclass"]["recommended"], "maybe")
        self.assertIn("what did survive: coverage", out["reclass"]["reason"])

    def test_softening_note_when_nothing_survived(self):
        res = {"flags": [self._major("engagement")],
               "reclass": {"recommended": "yes", "reason": "r"}}
        out = E.gate_reclass(res)
        # The note must not claim a verification happened - it is written by the gate, which runs
        # whether or not the skeptic ever did.
        self.assertIn("no major content finding was left standing", out["reclass"]["reason"])
        self.assertNotIn("survived verification", out["reclass"]["reason"])
        self.assertNotIn("what did survive", out["reclass"]["reason"])

    def test_a_hedged_finding_cannot_ask_learners_to_re_attend(self):
        """A major the model itself marked low-confidence is not enough for a re-teach."""
        f = self._major("coverage")
        f["confidence"] = "low"
        out = E.gate_reclass({"flags": [f], "reclass": {"recommended": "yes", "reason": "r"}})
        self.assertEqual(out["reclass"]["recommended"], "maybe")
        self.assertIn("low confidence", out["reclass"]["reason"])

    def test_a_confident_finding_still_carries_a_yes(self):
        out = E.gate_reclass({"flags": [self._major("coverage")],
                              "reclass": {"recommended": "yes", "reason": "r"}})
        self.assertEqual(out["reclass"]["recommended"], "yes")

    def test_deciding_flags_never_name_a_deleted_finding(self):
        res = {"flags": [self._major("coverage")],
               "reclass": {"recommended": "yes", "reason": "r",
                           "deciding_flags": ["coverage", "correctness"]}}
        out = E.gate_reclass(res)
        self.assertEqual(out["reclass"]["deciding_flags"], ["coverage"])

    def test_the_floor_applies_on_the_way_in(self):
        """An ARS correctness finding that arrives below the floor is raised to it."""
        f = self._major("correctness")
        f["severity"] = "moderate"
        out = E.apply_floors({"flags": [f]}, "ars")
        self.assertEqual(out["flags"][0]["severity"], "major")
        self.assertEqual(out["flags"][0]["floor_applied_from"], "moderate")

    def test_a_floored_finding_cannot_be_dropped_on_a_judgement_call(self):
        res = {"flags": [self._major("correctness")],
               "reclass": {"recommended": "yes", "reason": "r"}}
        out, rev = E.apply_verdicts(
            res, [{"id": 0, "verdict": "drop", "anchor_rule": "severity",
                   "reason": "this feels harsher than the moment deserves"}], "ars")
        self.assertEqual(len(out["flags"]), 1)          # kept
        self.assertEqual(rev[0]["verdict"], "uphold")

    def test_a_floored_finding_can_still_be_dropped_on_attribution(self):
        res = {"flags": [self._major("correctness")],
               "reclass": {"recommended": "yes", "reason": "r"}}
        out, rev = E.apply_verdicts(
            res, [{"id": 0, "verdict": "drop", "anchor_rule": "attribution",
                   "reason": "the quote is a learner speaking, not the instructor"}], "ars")
        self.assertEqual(out["flags"], [])
        self.assertEqual(rev[0]["verdict"], "drop")

    # ── the reason is rewritten against surviving flags ──────────────────────
    class _Msg:
        class usage:
            input_tokens = 10
            output_tokens = 5
        content = [type("B", (), {"type": "text", "text": json.dumps({
            "feedback": "rewritten feedback",
            "instructor_summary": "Rated 4.1. \n- One point + Fix: do this.",
            "reclass_reason": "Only a moderate coverage gap survived; the PM should spot-check.",
        })})()]

    def _client(self):
        outer = self

        class Messages:
            def __init__(self):
                self.calls = []

            def create(self, **kw):
                self.calls.append(kw)
                return outer._Msg()

        class Client:
            def __init__(self):
                self.messages = Messages()

        return Client()

    def test_reason_is_rewritten_and_marked_when_softened(self):
        result = {"flags": [{"flag": "coverage", "severity": "moderate", "confidence": "high",
                             "evidence": [{"timestamp": "00:02:00", "quote": "q"}]}],
                  "feedback": "old feedback",
                  "instructor_summary": "old summary",
                  "reclass": {"recommended": "maybe", "softened_from": "yes",
                              "reason": "three provably incorrect statements"}}
        changed = [{"flag": "correctness", "verdict": "drop", "from_severity": "major",
                    "anchor_rule": "quote does not support", "reason": "instructor self-corrected"}]
        out = E._reconcile_prose(self._client(), result, changed, E.Usage())
        self.assertNotIn("three provably incorrect", out["reclass"]["reason"])
        self.assertIn("moderate coverage gap", out["reclass"]["reason"])
        self.assertTrue(out["reclass"]["reason"].startswith("[was 'yes' before verification]"))
        self.assertEqual(out["reclass"]["recommended"], "maybe")     # code decides, prose does not

    def test_reason_is_rewritten_without_the_marker_when_not_softened(self):
        result = {"flags": [], "feedback": "f", "instructor_summary": "s",
                  "reclass": {"recommended": "no", "reason": "old"}}
        out = E._reconcile_prose(self._client(), result, [], E.Usage())
        self.assertNotIn("[was 'yes'", out["reclass"]["reason"])
        self.assertEqual(out["reclass"]["recommended"], "no")

    def test_a_failed_rewrite_keeps_the_original_texts(self):
        class Boom:
            class messages:
                @staticmethod
                def create(**kw):
                    raise RuntimeError("api down")

        result = {"flags": [], "feedback": "f", "instructor_summary": "s",
                  "reclass": {"recommended": "maybe", "reason": "original"}}
        out = E._reconcile_prose(Boom(), result, [], E.Usage())
        self.assertEqual(out["reclass"]["reason"], "original")
        self.assertEqual(out["feedback"], "f")


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
        # exercised via _create_message directly: _call no longer sends any optional kwargs,
        # but the guard must still protect whatever we pass in the future
        c = self._client("fancy_knob")
        msg = E._create_message(c, model="m", max_tokens=10, messages=[], fancy_knob=1)
        self.assertEqual(msg.content[0].text, "hi")        # the call still completes
        self.assertIn("fancy_knob", c.messages.calls[0])   # tried it once
        self.assertNotIn("fancy_knob", c.messages.calls[1])  # then dropped it

    def test_remembers_so_it_only_fails_once(self):
        c = self._client("fancy_knob")
        E._create_message(c, model="m", max_tokens=10, messages=[], fancy_knob=1)
        E._create_message(c, model="m", max_tokens=10, messages=[], fancy_knob=1)
        self.assertEqual(len(c.messages.calls), 3)        # 2 for the first call, 1 for the second
        self.assertNotIn("fancy_knob", c.messages.calls[2])

    def test_usage_is_still_accounted(self):
        c, u = self._client(None), E.Usage()
        E._call(c, "sys", "user", 100, u)
        self.assertEqual((u.input_tokens, u.output_tokens, u.calls), (10, 5, 1))

    def test_call_sends_no_sampling_or_thinking_params(self):
        """Sonnet 5 rejects non-default temperature/top_p/top_k with an HTTP 400 - the guard
        can't catch that (it's a server error, not a TypeError), so we must never send them."""
        c = self._client(None)
        E._call(c, "sys", "user", 100, E.Usage())
        self.assertEqual(len(c.messages.calls), 1)
        for banned in ("temperature", "top_p", "top_k", "thinking"):
            self.assertNotIn(banned, c.messages.calls[0])

    def test_unrelated_type_errors_still_raise(self):
        class Client:
            class messages:
                @staticmethod
                def create(**kw):
                    raise TypeError("something else entirely")
        with self.assertRaises(TypeError):
            E._call(Client(), "sys", "user", 100, E.Usage())


class TestMaterialsAgent(unittest.TestCase):
    """The materials agent: attached decks/notebooks become clean Markdown context, and a
    conversion failure can never kill an analysis."""

    class _Msg:
        class usage:
            input_tokens = 100
            output_tokens = 50
        content = [type("B", (), {"type": "text", "text": "## deck.pptx\n- Topic A\n- Topic B"})()]

    def _client(self, fail=False):
        outer = self

        class Messages:
            def __init__(self):
                self.calls = []

            def create(self, **kw):
                self.calls.append(kw)
                if fail:
                    raise RuntimeError("api down")
                return outer._Msg()

        class Client:
            def __init__(self):
                self.messages = Messages()

        return Client()

    def test_small_materials_skip_the_model(self):
        c = self._client()
        out = E._materials_markdown(c, "short outline", E.Usage())
        self.assertEqual(out, "short outline")
        self.assertEqual(len(c.messages.calls), 0)        # no call, no cost

    def test_large_materials_are_converted_to_markdown(self):
        c = self._client()
        out = E._materials_markdown(c, "x" * 5000, E.Usage())
        self.assertIn("## deck.pptx", out)
        self.assertEqual(len(c.messages.calls), 1)
        self.assertEqual(c.messages.calls[0]["max_tokens"], E.CFG.max_tokens_materials)

    def test_conversion_failure_never_raises(self):
        c = self._client(fail=True)
        out = E._materials_markdown(c, "y" * 5000, E.Usage())
        self.assertTrue(out.startswith("y"))              # truncated raw text, not an exception
        self.assertLessEqual(len(out), E.MATERIALS_MD_SKIP)

    def test_input_is_capped(self):
        c = self._client()
        E._materials_markdown(c, "z" * 200_000, E.Usage())
        sent = c.messages.calls[0]["messages"][0]["content"]
        self.assertLess(len(sent), E.MATERIALS_MAX_CHARS + 200)

    def test_prompt_demands_fidelity(self):
        s = E.MATERIALS_MD_SYS
        self.assertIn("Markdown", s)
        self.assertIn("never invent", s)
        self.assertIn("never silently drop a whole section", s)



class TestTranscriptIsNeverSilentlyLost(unittest.TestCase):
    """Every one of these used to discard most or all of a class with no error at all."""

    @staticmethod
    def _vtt(rows):
        out = ["WEBVTT", ""]
        for a, b, t in rows:
            out += [f"{a} --> {b}", t, ""]
        return "\n".join(out)

    def test_one_out_of_order_cue_does_not_discard_the_class(self):
        rows = [(f"00:{i:02d}:00.000", f"00:{i:02d}:30.000", f"line {i}") for i in range(0, 50, 2)]
        rows.append(("00:00:15.000", "00:00:20.000", "thanks for joining, see you next week"))
        cues = E.parse_cues(self._vtt(rows))
        covered = {id(c) for w in E.chunk_by_time(cues) for c in w}
        self.assertEqual(len(covered), len(cues))

    def test_every_cue_lands_in_exactly_one_window(self):
        cues = [E.Cue(i, i * 60, i * 60 + 30, f"t{i}") for i in range(200)]
        windows = E.chunk_by_time(cues)
        seen = [c.idx for w in windows for c in w]
        self.assertEqual(sorted(set(seen)), [c.idx for c in cues])

    def test_hours_are_optional_in_webvtt(self):
        cues = E.parse_cues(self._vtt([("00:50.500", "00:53.200", "the gradient of relu at zero")]))
        self.assertEqual(len(cues), 1)
        self.assertAlmostEqual(cues[0].start, 50.5)

    def test_a_bare_seconds_timestamp_parses(self):
        self.assertAlmostEqual(E._ts_to_seconds("12.250"), 12.25)

    def test_a_nonsense_timestamp_is_rejected_loudly(self):
        with self.assertRaises(ValueError):
            E._ts_to_seconds("1:2:3:4")

    def test_blocks_without_blank_lines_still_split(self):
        raw = ("WEBVTT\n1\n00:00:00.000 --> 00:00:05.000\nfirst\n"
               "2\n00:00:05.000 --> 00:00:10.000\nsecond\n"
               "3\n00:00:10.000 --> 00:00:15.000\nthird\n")
        cues = E.parse_cues(raw)
        self.assertEqual([c.text for c in cues], ["first", "second", "third"])

    def test_teaching_words_are_not_people(self):
        rows = [("00:00:00.000", "00:00:05.000", "Note: the derivative of x squared is 2x."),
                ("00:00:05.000", "00:00:10.000", "Output: 42"),
                ("00:00:10.000", "00:00:15.000", "Note: remember to scale the features."),
                ("00:00:15.000", "00:00:20.000", "Output: 108"),
                ("00:00:20.000", "00:00:25.000", "Priya: I am lost on recursion."),
                ("00:00:25.000", "00:00:30.000", "Priya: could you repeat that?")]
        cues = E.parse_cues(self._vtt(rows))
        self.assertEqual(sorted({c.speaker for c in cues if c.speaker}), ["Priya"])
        self.assertIn("Note:", cues[0].text)          # the word is not deleted from the transcript

    def test_the_session_map_covers_the_whole_class(self):
        cues = [E.Cue(i, i * 4, i * 4 + 4, "a fairly ordinary sentence of teaching " * 3)
                for i in range(2000)]
        slices = E._map_slices(cues)
        self.assertEqual(slices[-1][-1].end, cues[-1].end)
        self.assertEqual(sum(len(s) for s in slices), len(cues))


class TestTheNoteTheInstructorReceives(unittest.TestCase):

    FLAGS = [{"flag": "camera", "severity": "minor"}, {"flag": "pace", "severity": "minor"},
             {"flag": "structure", "severity": "minor"}, {"flag": "logistics", "severity": "minor"},
             {"flag": "engagement", "severity": "minor"},
             {"flag": "correctness", "severity": "major"}]

    NOTE = ("Averaged 4.1 out of 5.\n"
            "- Camera was off for the first ten minutes. Fix: turn it on.\n"
            "- The pace was quick in places. Fix: slow down.\n"
            "- The structure could be clearer. Fix: signpost each part.\n"
            "- There was a logistics hiccup. Fix: pre-open the notebook.\n"
            "- Engagement was low. Fix: check in every ten minutes.\n"
            "- You said quicksort is O(n log n) in the worst case, which is incorrect.\n"
            "  Fix: correct the record next class.\n")

    def test_the_serious_point_survives_the_cap(self):
        out = E.tidy_instructor_summary(self.NOTE, self.FLAGS)
        self.assertIn("quicksort", out)

    def test_the_cap_still_holds(self):
        out = E.tidy_instructor_summary(self.NOTE, self.FLAGS)
        self.assertEqual(sum(1 for l in out.splitlines() if l.strip().startswith("- ")),
                         E.SUMMARY_MAX_BULLETS)

    def test_numbered_bullets_are_counted(self):
        note = "Averaged 4.1.\n" + "".join(f"{i}. Point {i}.\n" for i in range(1, 9))
        kept = [l for l in E.tidy_instructor_summary(note).splitlines() if l.strip()[:1].isdigit()]
        self.assertEqual(len(kept), E.SUMMARY_MAX_BULLETS)

    def test_en_dash_bullets_are_counted(self):
        note = "Averaged 4.1.\n" + "".join(f"\u2013 Point {i}.\n" for i in range(1, 9))
        kept = [l for l in E.tidy_instructor_summary(note).splitlines()
                if l.strip().startswith("\u2013")]
        self.assertEqual(len(kept), E.SUMMARY_MAX_BULLETS)

    def test_a_trimmed_bullet_takes_its_fix_line_with_it(self):
        note = "Averaged 4.1.\n" + "".join(
            f"- Point {i} about delivery.\n  Fix: do thing {i}.\n" for i in range(1, 9))
        out = E.tidy_instructor_summary(note)
        for i in (6, 7, 8):
            self.assertNotIn(f"do thing {i}", out)
        for i in (1, 2, 3, 4, 5):
            self.assertIn(f"do thing {i}", out)

    def test_the_re_class_decision_never_reaches_the_instructor(self):
        note = ("- This class will be re-taught to the cohort. Fix: prepare a make-up session.\n"
                "- The recap was skipped. Fix: leave two minutes.")
        out = E.tidy_instructor_summary(note)
        self.assertNotIn("re-taught", out.lower())
        self.assertNotIn("make-up session", out.lower())
        self.assertIn("recap", out)

    def test_ordinary_numbers_are_not_mistaken_for_timestamps(self):
        for sentence in ("Apply the 80:20 rule and cover the core path first.",
                         "The class was scheduled at 10:30 but you started late.",
                         "This session averaged 4:55 out of 5."):
            self.assertEqual(E.tidy_instructor_summary(sentence), sentence)

    def test_real_timestamps_are_still_removed(self):
        self.assertEqual(E.tidy_instructor_summary("You paused at [00:12:34] for a long time."),
                         "You paused for a long time.")
        self.assertNotIn("00:12:34",
                         E.tidy_instructor_summary("The gap ran 00:12:34-00:15:02 with no audio."))


class TestPromptsOnlyAskForFlagsTheClassCanReturn(unittest.TestCase):
    """Derived from the flag sets, so it survives any rewording - unlike asserting prompt prose."""

    def test_no_prompt_names_an_illegal_flag(self):
        import re as _re
        every = set(E.FLAGS_LIVE) | set(E.FLAGS_ARS)
        for ct in sorted(E.CLASS_TYPES):
            legal = set(E.flags_for(ct))
            for has_video in (False, True):
                for label, prompt in (
                        ("extract", E.build_extract_user("ctx", "seg", ct, has_video)),
                        ("synth", E.build_synth_user("ctx", "[]", ct, has_video))):
                    named = {f for f in every if _re.search(r"\b" + f + r"\b", prompt)}
                    self.assertEqual(named - legal, set(),
                                     f"{label} prompt for {ct} (video={has_video}) names a flag "
                                     f"the class cannot return")

    def test_no_placeholder_is_left_unresolved(self):
        for ct in sorted(E.CLASS_TYPES):
            for has_video in (False, True):
                self.assertNotIn("[[", E.build_extract_user("ctx", "seg", ct, has_video))

    def test_the_deciding_flags_exist_for_the_class(self):
        for ct in sorted(E.CLASS_TYPES):
            self.assertTrue(E.content_delivery_flags(ct))
            self.assertLessEqual(E.content_delivery_flags(ct), set(E.flags_for(ct)))


class TestTheContextTellsTheTruth(unittest.TestCase):

    def test_a_well_rated_class_is_not_called_low_rated(self):
        ctx = E.build_context("C", "T", "I", "4.87", "(not provided)")
        self.assertIn("NOT flagged", ctx)
        self.assertNotIn("below the 4.55 line, which is why", ctx)

    def test_a_low_rated_class_still_says_so(self):
        self.assertIn("below the 4.55 line", E.build_context("C", "T", "I", "3.30", "(not provided)"))

    def test_an_unknown_rating_makes_no_claim(self):
        ctx = E.build_context("C", "T", "I", "(unspecified)", "(not provided)")
        self.assertIn("not known", ctx)

    def test_a_missing_agenda_forbids_coverage_judgements(self):
        ctx = E.build_context("C", "T", "I", "3.3", "(not provided)")
        self.assertIn("NOT PROVIDED", ctx)
        self.assertIn("do not judge whether", ctx)

    def test_a_real_agenda_is_passed_through(self):
        ctx = E.build_context("C", "T", "I", "3.3", "1. Recap 45m\n2. RAG 45m")
        self.assertIn("RAG 45m", ctx)
        self.assertNotIn("NOT PROVIDED", ctx)


if __name__ == "__main__":
    unittest.main()
