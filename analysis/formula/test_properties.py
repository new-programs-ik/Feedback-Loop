"""Permanent test: the properties every formula must satisfy, run on the case fixture
(analysis/out/formula_cases.json - regenerated if missing) for the recommended settings, for
today's active version, and - as a control - for the manager's original, which must FAIL the
properties the study says it fails.

Run:  python -m unittest analysis.formula.test_properties      (from the repo root)
  or: python analysis/formula/test_properties.py
"""
from __future__ import annotations

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import OUT, read_json  # noqa: E402
from families import (FAMILIES, inputs_from_cases, score_any, score_points, verify_against_contract, TodayV7, Original)  # noqa: E402
from properties import run_properties, summarise, PROPERTIES  # noqa: E402
from cases import load_cases  # noqa: E402
from sentiment_score import CONFIGS  # noqa: E402

ORIGINAL_FAILS = {"P04", "P06", "P07", "P08", "P09", "P12", "P19", "P22"}   # what the study found for the manager's original


class PropertyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases, cls.fixture = load_cases(full_grid=False)
        cls.X = inputs_from_cases(cls.cases)
        cls.v7 = TodayV7().fit(None, None, None)
        path = os.path.join(OUT, "formula_recommended.json")
        cls.recommended = read_json(path)["recommended"]["settings"] if os.path.exists(path) else cls.v7
        cls.refinement = read_json(path).get("refinement", {}).get("settings") if os.path.exists(path) else None

    def test_fixture_is_complete(self):
        counts = self.fixture["counts"]
        self.assertGreaterEqual(counts["adversarial"], 50)
        self.assertEqual(counts["random"], 1000)
        self.assertEqual(counts["grid_sample"], 2000)
        self.assertEqual(len({c["id"] for c in self.cases}), len(self.cases))

    def test_recommended_passes_every_property(self):
        props = run_properties(self.recommended, self.cases, self.X)
        failed = summarise(props)["failed"]
        self.assertEqual(failed, [], "recommended settings fail: %s" % {p: props[p]["examples"][:1] for p in failed})

    def test_todays_v7_passes_every_property(self):
        props = run_properties(self.v7, self.cases, self.X)
        self.assertEqual(summarise(props)["failed"], [])

    def test_refinement_passes_every_property(self):
        if not self.refinement:
            self.skipTest("no refinement recorded")
        props = run_properties(self.refinement, self.cases, self.X)
        self.assertEqual(summarise(props)["failed"], [])

    def test_original_fails_exactly_what_the_study_says(self):
        props = run_properties(CONFIGS["C0"], self.cases, self.X)
        self.assertEqual(set(summarise(props)["failed"]), ORIGINAL_FAILS)

    def test_scorer_matches_the_contract(self):
        """The vectorised scorer must reproduce analysis/sentiment_score.py on contract-shaped configs."""
        for key in ("C0", "C5"):
            self.assertEqual(verify_against_contract(CONFIGS[key], self.X, limit=600), 0, key)
        self.assertEqual(verify_against_contract(self.v7, self.X, limit=600), 0, "v7")

    def test_property_catalogue(self):
        self.assertGreaterEqual(len(PROPERTIES), 22)
        for pid, p in PROPERTIES.items():
            self.assertTrue(p["name"])

    def test_named_cases_under_recommended(self):
        """A few named cases, as principles: no firm band from one voice; a webinar with five happy
        raters is not penalised; a big room saying no is flagged; a missing vote is scored on the rating."""
        by = {c["id"]: i for i, c in enumerate(self.cases)}
        r = score_any(self.X, self.recommended)
        self.assertIsNone(r["band"][by["A02"]])
        self.assertEqual(r["action"][by["A02"]], "watch")
        self.assertIn(r["band"][by["A04"]], ("excellent", "good"))
        self.assertIn(r["action"][by["A05"]], ("video", "transcript"))
        self.assertIsNotNone(r["band"][by["A10"]])
        self.assertEqual(r["action"][by["A30"]], "video")
        self.assertTrue(np.isnan(r["score"][by["A22"]]))


if __name__ == "__main__":
    unittest.main()
