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
