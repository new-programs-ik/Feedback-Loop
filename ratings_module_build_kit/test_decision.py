"""test_decision.py - locks the team rule's exact boundaries. Run: python -m unittest test_decision"""
import unittest

import course_rules as CR
import decision as D


class TestDecisionRule(unittest.TestCase):
    def test_escalation_beats_everything(self):
        self.assertEqual(D.decide(4.9, 1, 100, escalated=True), "video")

    def test_line_is_4_55_inclusive(self):
        self.assertEqual(D.decide(4.55, 20, 25), "none")     # AT the line -> fine
        self.assertEqual(D.decide(4.56, 2, 25), "none")
        self.assertNotEqual(D.decide(4.54, 20, 25), "none")  # just under -> needs a look

    def test_voice_floor_is_5(self):
        self.assertEqual(D.decide(3.2, 4, 10), "watch")      # 4 voices, even at 40%
        self.assertEqual(D.decide(3.2, 5, 10), "video")      # 5 voices at 50%

    def test_participation_bar_is_40(self):
        self.assertEqual(D.decide(4.3, 8, 20), "video")      # exactly 40.0%
        self.assertEqual(D.decide(4.3, 7, 20), "transcript") # 35%
        self.assertEqual(D.decide(4.3, 39, 100), "transcript")  # 39%
        self.assertEqual(D.decide(4.3, 40, 100), "video")

    def test_missing_data_degrades_to_watch(self):
        self.assertEqual(D.decide(None, 10, 20), "watch")
        self.assertEqual(D.decide(4.2, None, 20), "watch")
        self.assertEqual(D.decide(4.2, 10, 0), "watch")
        self.assertEqual(D.decide(4.2, 10, None), "watch")

    def test_the_two_study_examples(self):
        # thin sample, bad score: 5 of 15 (33%) -> transcript
        self.assertEqual(D.decide(3.20, 5, 15), "transcript")
        # representative and still bad: 13 of 26 (50%) -> video
        self.assertEqual(D.decide(3.55, 13, 26), "video")


class TestCourseRules(unittest.TestCase):
    def test_first_match_wins_on_glued_cohorts(self):
        self.assertEqual(
            CR.course_of("Agentic AI SWE Deprecated, Forward Deployed Engineering - Early", ""),
            "FDE (Forward Deployed Engineering)")

    def test_pwc_beats_agentic(self):
        self.assertEqual(CR.course_of("PwC x IK Agentic AI Accelerator - IND", ""),
                         "PwC x IK Agentic AI Accelerator")

    def test_type_fallbacks(self):
        self.assertEqual(CR.course_of("", "India Transformative GenAI Live Class"),
                         "Transformative GenAI")
        self.assertEqual(CR.course_of("-", "ML Switchup Live Class"),
                         "ML SwitchUp (unmapped cohort)")

    def test_kinds(self):
        self.assertEqual(CR.kind_of("India ML Switchup Review Class"), "Test Review")
        self.assertEqual(CR.kind_of("Agentic AI Live Class"), "Live Class")
        self.assertEqual(CR.kind_of(""), "Other")


if __name__ == "__main__":
    unittest.main()
