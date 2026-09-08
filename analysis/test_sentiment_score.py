"""Permanent unit test for the scoring contract: the 44 edge cases under C5 (plan 4e), asserting
what analysis/sentiment_score.py ACTUALLY does today. Where the contract differs from the plan's
expectation the test still asserts the contract (the study reports the difference as a finding;
the lead changes the contract, then this test) - see FINDING comments.

Run:  python -m unittest analysis.test_sentiment_score   (from the repo root)
  or: python analysis/test_sentiment_score.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sentiment_score import CONFIGS, score, round2  # noqa: E402
from sentiment_edge_cases import CASES  # noqa: E402

C5 = CONFIGS["C5"]
C0 = CONFIGS["C0"]
BY_ID = {c["id"]: c for c in CASES}

# The contract's behaviour under C5, case by case: (band, action, provisional, flags that must be
# present, score or None). A None score means "no score at all" (rejected / no rating).
EXPECTED_C5 = {
    # FINDING (minor): with zero ratings the guard blends nothing with the course prior, so the class
    # is scored AS the course prior (83.33 here) - hidden behind "no band", but stored.
    "E01": (None, "watch", False, ("zero_responses", "no_attendance", "no_vote", "thin_no_band"), 83.33),
    "E02": (None, "watch", False, ("thin_no_band",), None),
    "E03": (None, "watch", False, ("thin_no_band",), None),
    "E04": ("excellent", "none", False, ("guarded", "no_track"), None),
    "E05": ("bad", "video", False, ("guarded", "under_approval_bar"), None),
    "E06": ("average", "transcript", False, ("no_vote", "guarded", "under_rating_line"), None),
    "E07": ("average", "transcript", False, ("rating_vote_disagree", "guarded", "under_approval_bar"), None),
    "E08": ("good", "none", False, ("reach_clamped", "guarded"), None),
    "E09": ("bad", "video", False, ("guarded", "under_rating_line"), None),
    "E10": ("average", "transcript", False, ("rating_vote_disagree", "guarded", "under_approval_bar"), None),
    "E11": (None, "watch", False, ("no_rating",), None),
    "E12": ("good", "none", False, ("no_attendance", "guarded"), None),
    "E13": (None, "watch", False, ("invalid_num_ratings",), None),
    "E14": (None, "watch", False, ("invalid_rating",), None),
    "E15": ("good", "none", False, ("guarded", "no_track"), None),
    "E16": ("good", "none", False, ("guarded", "no_track"), None),
    "E17": ("excellent", "watch", True, ("guarded", "thin_provisional"), None),
    "E18": ("excellent", "watch", True, ("guarded", "thin_provisional"), None),
    "E19": ("good", "none", False, ("guarded",), None),
    "E20": ("good", "none", False, ("guarded",), None),
    "E21": ("good", "none", False, ("guarded",), None),
    "E22": ("average", "transcript", False, ("guarded", "under_approval_bar"), None),
    "E23": ("good", "watch", True, ("guarded", "thin_provisional"), None),
    "E24": ("good", "none", False, ("guarded",), None),
    "E25": ("average", "transcript", False, ("guarded", "under_approval_bar"), None),
    "E26": ("excellent", "none", False, (), 90.0),
    "E27": ("good", "none", False, (), None),
    "E28": ("good", "none", False, (), 75.0),
    "E29": ("average", "transcript", False, (), None),
    "E30": ("average", "transcript", False, ("under_rating_line",), 60.0),
    "E31": ("bad", "video", False, ("under_rating_line",), None),
    "E32": ("good", "none", False, ("guarded",), None),
    "E33": ("good", "none", False, ("guarded", "no_track"), None),
    "E34": ("good", "none", False, ("guarded",), None),
    "E35": ("excellent", "video", False, ("guarded", "escalated"), None),
    "E36": ("excellent", "none", False, ("guarded",), None),
    "E37": ("average", "transcript", False, ("guarded", "under_rating_line"), None),
    "E38": ("average", "transcript", False, ("votes_ne_responses", "guarded", "under_approval_bar"), None),
    "E39": ("good", "watch", True, ("no_track", "thin_provisional"), None),
    "E40": ("good", "none", False, ("no_vote", "guarded", "no_track"), None),
    "E41": (None, "watch", False, ("no_rating",), None),
    "E42": (None, "watch", False, ("rating_zero",), None),
    "E43": ("good", "none", False, (), 85.0),
    # FINDING: the plan says a 4.54 with 5+ votes can never sit above Average; the contract checks
    # the GUARDED rating (4.59 here), so the class clears the line and is shown as Good.
    "E44": ("good", "none", False, ("guarded",), None),
}


class EdgeCasesUnderC5(unittest.TestCase):
    def test_every_case_has_an_expectation(self):
        self.assertEqual(set(EXPECTED_C5), set(BY_ID))

    def test_cases(self):
        for cid, (band, action, prov, flags, sc) in EXPECTED_C5.items():
            with self.subTest(cid=cid, label=BY_ID[cid]["label"]):
                x = score(BY_ID[cid]["inputs"], C5)
                self.assertEqual(x["band"], band)
                self.assertEqual(x["action"], action)
                self.assertEqual(x["provisional"], prov)
                for f in flags:
                    self.assertIn(f, x["flags"])
                if sc is not None:
                    self.assertEqual(x["score"], sc)

    def test_no_score_cases_have_no_components(self):
        for cid in ("E11", "E13", "E14", "E41", "E42"):
            x = score(BY_ID[cid]["inputs"], C5)
            self.assertIsNone(x["score"])
            self.assertEqual(x["components"], {})

    def test_determinism(self):
        a, b = score(BY_ID["E16"]["inputs"], C5), score(BY_ID["E16"]["inputs"], C5)
        self.assertEqual(a, b)

    def test_guard_lifts_the_line_finding(self):
        """The failing case for the lead: raw 4.54 (under the line) clears it once guarded."""
        x = score(BY_ID["E44"]["inputs"], C5)
        self.assertLess(BY_ID["E44"]["inputs"]["rating"], C5["caps"]["rating_line"])
        self.assertGreaterEqual(x["adjusted"]["rating"], C5["caps"]["rating_line"])
        self.assertNotIn("under_rating_line", x["flags"])
        self.assertEqual(x["band"], "good")

    def test_guard_passes_3of4_and_7of9_not_15of20(self):
        self.assertNotIn("under_approval_bar", score(BY_ID["E23"]["inputs"], C5)["flags"])
        self.assertNotIn("under_approval_bar", score(BY_ID["E24"]["inputs"], C5)["flags"])
        self.assertIn("under_approval_bar", score(BY_ID["E25"]["inputs"], C5)["flags"])

    def test_band_edges_read_the_rounded_score(self):
        self.assertEqual(round2(89.995), 90.0)
        self.assertEqual(round2(89.994), 89.99)
        self.assertEqual(score(BY_ID["E26"]["inputs"], C5)["band"], "excellent")
        self.assertEqual(score(BY_ID["E27"]["inputs"], C5)["band"], "good")

    def test_manager_original_still_punishes_the_famous_case(self):
        x = score(BY_ID["E18"]["inputs"], C0)
        self.assertEqual((x["band"], x["action"]), ("bad", "video"))
        y = score(BY_ID["E18"]["inputs"], C5)
        self.assertEqual((y["band"], y["action"], y["provisional"]), ("excellent", "watch", True))

    def test_responses_target_only_matters_when_sample_is_on(self):
        nine = dict(BY_ID["E32"]["inputs"], num_ratings=9, yes_votes=9)
        self.assertEqual(score(nine, C0)["components"]["sample"], 0.0)
        self.assertEqual(score(BY_ID["E32"]["inputs"], C0)["components"]["sample"], 100.0)
        self.assertIsNone(score(BY_ID["E32"]["inputs"], C5)["components"]["sample"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
