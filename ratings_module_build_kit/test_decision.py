"""test_decision.py - locks the team rule's exact boundaries. Run: python -m unittest test_decision"""
import unittest
from unittest import mock

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


class TestRuleV2(unittest.TestCase):
    """decide_v2 - the two bars, the voice floor, the bands, the depth routes, the no-penalty defaults."""

    def test_approval_bar_is_80_inclusive(self):
        ok = D.decide_v2(4.8, 10, 20, approval_pct=80.0)
        self.assertEqual((ok.decision, ok.flag_reasons), ("none", ()))
        low = D.decide_v2(4.8, 10, 20, approval_pct=79.9)
        self.assertNotEqual(low.decision, "none")
        self.assertEqual(low.flag_reasons, ("approval",))

    def test_rating_line_is_4_55_inclusive(self):
        self.assertEqual(D.decide_v2(4.55, 20, 25, approval_pct=100).decision, "none")
        v = D.decide_v2(4.54, 20, 25, approval_pct=100)
        self.assertNotEqual(v.decision, "none")
        self.assertEqual(v.flag_reasons, ("rating",))

    def test_voice_floor_is_5(self):
        thin = D.decide_v2(3.2, 4, 10, approval_pct=50)
        self.assertEqual((thin.decision, thin.health_band), ("watch", None))
        self.assertEqual(thin.flag_reasons, ("rating", "approval"))     # the reasons still show
        self.assertEqual(D.decide_v2(3.2, 5, 10, approval_pct=50).decision, "video")
        # under 5 voices with both bars fine -> none, not watch
        self.assertEqual(D.decide_v2(4.9, 2, 10, approval_pct=100).decision, "none")

    def test_urgent_goes_to_video_even_at_low_reach(self):
        v = D.decide_v2(3.6, 5, 25, approval_pct=50)      # 20% reach; R 5, A 25, T 100 -> 20.5
        self.assertEqual((v.health_band, v.decision), ("urgent", "video"))
        self.assertEqual(v.flag_reasons, ("rating", "approval"))

    def test_borderline_goes_to_transcript_even_at_high_reach(self):
        v = D.decide_v2(4.5, 12, 20, approval_pct=100)    # 60% reach; R 95 -> 97
        self.assertEqual((v.health_band, v.decision), ("borderline", "transcript"))

    def test_middle_band_uses_reach(self):
        # R 65 with the other two at 100 -> 79 -> 'look' -> the 40% bar decides
        self.assertEqual(D.decide_v2(4.2, 8, 20).decision, "video")          # exactly 40%
        self.assertEqual(D.decide_v2(4.2, 7, 20).decision, "transcript")     # 35%
        self.assertEqual(D.decide_v2(4.2, 8, 20).health_band, "look")

    def test_depth_by_score_off_is_reach_only(self):
        with mock.patch.object(D, "DEPTH_BY_SCORE", False):
            urgent = D.decide_v2(3.6, 5, 25, approval_pct=50)                # 20% reach
            self.assertEqual((urgent.decision, urgent.health_band), ("transcript", "urgent"))
            border = D.decide_v2(4.5, 12, 20, approval_pct=100)              # 60% reach
            self.assertEqual((border.decision, border.health_band), ("video", "borderline"))

    def test_unknown_signals_are_no_penalty(self):
        self.assertEqual(D.score_approval(None), 100.0)
        self.assertEqual(D.score_track(None), 100.0)
        v = D.decide_v2(4.8, 10, 20)                                         # no vote, no history
        self.assertEqual((v.decision, v.health_score, v.flag_reasons), ("none", 100.0, ()))
        # a bad rating with no vote data: health drops on the rating alone
        self.assertEqual(D.decide_v2(4.2, 10, 20).health_score, 79.0)

    def test_escalation_beats_everything(self):
        v = D.decide_v2(4.9, 1, 100, escalated=True, approval_pct=100)
        self.assertEqual((v.decision, v.flag_reasons, v.health_band), ("video", ("escalated",), "borderline"))
        both = D.decide_v2(3.6, 5, 25, escalated=True, approval_pct=50)
        self.assertEqual(both.flag_reasons, ("rating", "approval", "escalated"))

    def test_missing_data_degrades_to_watch(self):
        v = D.decide_v2(None, 10, 20, approval_pct=50)
        self.assertEqual((v.decision, v.health_score, v.health_band), ("watch", None, None))
        self.assertEqual(D.decide_v2(None, 10, 20, escalated=True).decision, "video")
        self.assertEqual(D.decide_v2(4.2, None, 20).decision, "watch")
        self.assertEqual(D.decide_v2(4.2, 10, 0).decision, "watch")         # 'look' needs the reach
        self.assertEqual(D.decide_v2(4.2, 10, None).decision, "watch")
        # ... but an urgent class needs no reach to go to video
        self.assertEqual(D.decide_v2(3.6, 10, None, approval_pct=50).decision, "video")

    def test_component_score_boundaries(self):
        self.assertEqual(D.score_rating(4.55), 100.0)
        self.assertEqual(D.score_rating(3.55), 0.0)
        self.assertEqual(D.score_rating(3.0), 0.0)          # clamped
        self.assertEqual(D.score_rating(5.0), 100.0)        # clamped
        self.assertAlmostEqual(D.score_rating(4.05), 50.0)
        self.assertEqual(D.score_approval(80), 100.0)
        self.assertEqual(D.score_approval(40), 0.0)
        self.assertEqual(D.score_approval(0), 0.0)
        self.assertAlmostEqual(D.score_approval(60), 50.0)
        self.assertEqual(D.score_track(4.55), 100.0)
        self.assertEqual(D.score_track(4.05), 0.0)
        self.assertAlmostEqual(D.score_track(4.30), 50.0)

    def test_health_weights_and_bands(self):
        self.assertAlmostEqual(D.health_score(3.55, 40, 4.05), 0.0)      # every floor
        self.assertAlmostEqual(D.health_score(4.55, 80, 4.55), 100.0)    # every bar
        self.assertAlmostEqual(D.health_score(3.55, 80, 4.55), 40.0)     # rating carries 60
        self.assertAlmostEqual(D.health_score(4.55, 40, 4.55), 75.0)     # approval carries 25
        self.assertAlmostEqual(D.health_score(4.55, 80, 4.05), 85.0)     # track record carries 15
        self.assertEqual(D.health_band(69.9), "urgent")
        self.assertEqual(D.health_band(70), "look")
        self.assertEqual(D.health_band(89.9), "look")
        self.assertEqual(D.health_band(90), "borderline")

    def test_band_reads_the_unrounded_score(self):
        # the study's one edge case: 89.99 is 'look' although it is stored as 90.0
        v = D.decide_v2(4.3833, 12, 25, approval_pct=83.33)
        self.assertEqual(v.health_score, 90.0)
        self.assertEqual((v.health_band, v.decision), ("look", "video"))

    def test_approval_pct(self):
        self.assertEqual(D.approval_pct(13, 2), 86.67)
        self.assertEqual(D.approval_pct(4, 1), 80.0)
        self.assertEqual(D.approval_pct(0, 5), 0.0)
        self.assertIsNone(D.approval_pct(0, 0))
        self.assertIsNone(D.approval_pct(None, 3))
        self.assertIsNone(D.approval_pct(3, None))

    def test_the_study_examples(self):
        # 13 yes / 2 no at 4.5: under the line, approval fine -> queued on the rating, borderline
        v = D.decide_v2(4.5, 15, 30, approval_pct=D.approval_pct(13, 2))
        self.assertEqual((v.flag_reasons, v.health_band, v.decision), (("rating",), "borderline", "transcript"))
        # polite rating, but they would not have the instructor back -> queued on approval alone
        v = D.decide_v2(4.7, 10, 20, approval_pct=60)                       # 60 + 15 + 10 = 85
        self.assertEqual((v.flag_reasons, v.health_band, v.decision), (("approval",), "look", "video"))
        # repeat offender: a fine-looking class, but the instructor's history drags the score
        v = D.decide_v2(4.5, 10, 20, approval_pct=80, track_avg=4.05)       # 57 + 30 + 0 = 87
        self.assertEqual((v.health_band, v.decision), ("look", "video"))


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
