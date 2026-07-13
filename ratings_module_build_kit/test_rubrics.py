"""
test_rubrics.py — class-type-aware rubrics (live_class vs ARS) + the revise validator paths.
No API key needed. Run:  python -m unittest test_rubrics -v
"""
import unittest

import engine as E


class TestFlagSets(unittest.TestCase):
    def test_sets(self):
        self.assertIn("coding_time", E.FLAGS_LIVE)
        self.assertIn("problem_coverage", E.FLAGS_ARS)
        self.assertNotIn("problem_coverage", E.FLAGS_LIVE)
        self.assertNotIn("agenda_balance", E.FLAGS_ARS)
        self.assertEqual(E.FLAGS, E.FLAGS_LIVE | E.FLAGS_ARS)

    def test_flags_for(self):
        self.assertEqual(E.flags_for("ars"), E.FLAGS_ARS)
        self.assertEqual(E.flags_for("live_class"), E.FLAGS_LIVE)


class TestScopedValidation(unittest.TestCase):
    def _finding(self, flag):
        return {"flag": flag, "observation": "x", "severity": "major",
                "evidence": [{"timestamp": "00:10:00", "quote": "we'll skip this one"}],
                "confidence": "high"}

    def test_ars_flag_valid_only_for_ars(self):
        f = self._finding("problem_coverage")
        self.assertEqual(E.validate_findings({"findings": [f]}, E.FLAGS_ARS), [])
        self.assertTrue(E.validate_findings({"findings": [f]}, E.FLAGS_LIVE))

    def test_default_allows_union(self):
        f = self._finding("problem_coverage")
        self.assertEqual(E.validate_findings({"findings": [f]}), [])


class TestPrompts(unittest.TestCase):
    def test_extract_uses_right_rubric(self):
        live = E.build_extract_user("ctx", "seg", "live_class")
        ars = E.build_extract_user("ctx", "seg", "ars")
        self.assertIn("LIVE CLASS", live)
        self.assertIn("ASSIGNMENT REVIEW SESSION", ars)
        self.assertIn("problem_coverage", ars)
        self.assertNotIn("problem_coverage", live)

    def test_synth_style_rules(self):
        s = E.build_synth_user("ctx", "[]", "live_class")
        self.assertIn("150-250 words", s)
        self.assertIn("NEVER harsh", s)
        a = E.build_synth_user("ctx", "[]", "ars")
        self.assertIn("PROBLEMS reviewed", a)
        self.assertIn("canonical", a)

    def test_ars_complexity_conditional(self):
        self.assertIn("If the session involves no code, do NOT raise this", E.RUBRIC_ARS)


class TestMultiSpeaker(unittest.TestCase):
    """The engine must treat the transcript as a real conversation (instructor + learners), not
    instructor-only text, and must understand the whole flow before flagging."""

    def test_rubrics_are_multispeaker_and_attribute(self):
        for r in (E.RUBRIC_LIVE, E.RUBRIC_ARS):
            self.assertIn("LEARNER", r.upper())            # learners are acknowledged
            self.assertIn("INSTRUCTOR ONLY", r)            # but only the instructor is judged
            self.assertIn("WHOLE-SESSION MAP", r)          # judge in full-session context

    def test_no_instructor_only_premise(self):
        # the old, wrong assumption ("instructor's speech only") must be gone from both rubrics
        for r in (E.RUBRIC_LIVE, E.RUBRIC_ARS):
            self.assertNotIn("INSTRUCTOR's speech only", r)
            self.assertNotIn("Learner questions are usually NOT present", r)

    def test_conversation_map_pass_exists(self):
        self.assertTrue(hasattr(E, "map_conversation"))
        self.assertIn("map", E.CONV_MAP_SYS.lower())
        self.assertIn("INSTRUCTOR", E.CONV_MAP_SYS)
        self.assertIn("LEARNER", E.CONV_MAP_SYS)

    def test_extract_prompt_asks_for_attribution(self):
        u = E.build_extract_user("ctx", "[00:00:00] hello", "live_class")
        self.assertIn("attribute", u.lower())
        self.assertIn("ONLY the instructor", u)

    def test_synth_drops_learner_and_resolved(self):
        s = E.build_synth_user("ctx", "[]", "live_class")
        self.assertIn("LEARNER speaking", s)
        self.assertIn("RESOLVED", s)


class TestClassTypeGuard(unittest.TestCase):
    def test_bad_class_type_raises(self):
        cues = [E.Cue(1, 0, 1, "hello")]
        with self.assertRaises(ValueError):
            E.analyse_cues(cues, "ctx", "workshop")


class TestReviseGuards(unittest.TestCase):
    def test_empty_inputs(self):
        with self.assertRaises(ValueError):
            E.revise_feedback("", "make it shorter")
        with self.assertRaises(ValueError):
            E.revise_feedback("some feedback", "   ")


if __name__ == "__main__":
    unittest.main()
