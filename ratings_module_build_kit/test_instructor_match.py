"""test_instructor_match.py - name normalisation and the duplicate-name suggester. Offline.
Run: python -m unittest test_instructor_match -v
"""
import datetime as dt
import unittest

import instructor_match as IM

D = dt.date

# The known groups from the plan (276 raw spellings ~ 180 people in the Jan-Aug sheet).
CANDIDATES = [("i-kalpesh", "Kalpesh Singh"), ("i-devdatt", "Devdatt Mahajan"), ("i-nikhil", "Nikhil Bhatnagar"),
              ("i-singhal", "Pranav Singhal"), ("i-singh", "Pranav Singh"), ("i-zoya", "Zoya Siddiqui"),
              ("i-jayant", "Jayant Jacob"), ("i-suresh", "Suresh Rao Shenoy"), ("i-ritwik", "Ritwik Singh"),
              ("i-ananya", "Ananya Singh")]


def best(raws, cands=CANDIDATES, context=None):
    """{raw: (candidate_name, score, method)} for the top suggestion of each raw name."""
    out = {}
    for s in IM.suggest(raws, cands, context):
        out.setdefault(s.raw_name, (s.candidate_name, s.score, s.method))
    return out


class TestNormalize(unittest.TestCase):
    def test_matches_the_sql_contract(self):
        self.assertEqual(IM.normalize("  Kalpesh   Singh "), "kalpesh singh")
        self.assertEqual(IM.normalize("Ándre-Marie  O'Neil"), "andremarie oneil")   # fold, keep [a-z0-9 ]
        self.assertEqual(IM.normalize("- Kalpesh"), "kalpesh")
        self.assertEqual(IM.normalize("Kalpesh -"), "kalpesh")
        self.assertEqual(IM.normalize("Dr. Devdatt"), "dr devdatt")                  # honorifics stay here
        self.assertEqual(IM.normalize(None), "")
        self.assertEqual(IM.normalize("Ravi 2"), "ravi 2")

    def test_match_form_drops_honorifics_and_doubled_tokens(self):
        self.assertEqual(IM.match_form("Dr. Devdatt Mahajan"), "devdatt mahajan")
        self.assertEqual(IM.match_form("Devdatt Devdatt"), "devdatt")
        self.assertEqual(IM.match_form("Prof Kalpesh Singh"), "kalpesh singh")


class TestDistances(unittest.TestCase):
    def test_damerau_levenshtein(self):
        self.assertEqual(IM.damerau_levenshtein("nikhil bhatnagar", "nikhil bhattnagar"), 1)
        self.assertEqual(IM.damerau_levenshtein("kalpesh", "kaplesh"), 1)      # transposition
        self.assertEqual(IM.damerau_levenshtein("zoya", "zoyan"), 1)
        self.assertEqual(IM.damerau_levenshtein("abc", "abc"), 0)

    def test_jaro_winkler(self):
        self.assertEqual(IM.jaro_winkler("abc", "abc"), 1.0)
        self.assertGreater(IM.jaro_winkler("nikhil bhatnagar", "nikhil bhattnagar"), 0.95)
        self.assertLess(IM.jaro_winkler("kalpesh singh", "ananya singh"), 0.8)


class TestKnownGroups(unittest.TestCase):
    def test_first_name_only_spellings_point_at_the_one_owner(self):
        b = best(["Kalpesh", "Devdatt", "Ritwik"])
        self.assertEqual(b["Kalpesh"], ("Kalpesh Singh", 0.80, "first_name"))
        self.assertEqual(b["Devdatt"], ("Devdatt Mahajan", 0.80, "first_name"))
        self.assertEqual(b["Ritwik"], ("Ritwik Singh", 0.80, "first_name"))

    def test_doubled_token_counts_as_first_name_only(self):
        self.assertEqual(best(["Devdatt Devdatt"])["Devdatt Devdatt"], ("Devdatt Mahajan", 0.80, "first_name"))

    def test_typo_in_the_surname(self):
        self.assertEqual(best(["Nikhil Bhattnagar"])["Nikhil Bhattnagar"], ("Nikhil Bhatnagar", 0.75, "typo"))

    def test_shared_first_name_is_weak(self):
        # two instructors called Pranav: a bare "Pranav" is 0.45 each -> under the keep line
        self.assertNotIn("Pranav", best(["Pranav"]))
        # ...unless the same-course evidence lifts it to exactly the keep line
        ctx = {IM.normalize("Pranav"): [IM.ClassRef("c1", D(2026, 3, 1), "RAG", "Live Class")],
               "i-singhal": [IM.ClassRef("c1", D(2026, 2, 1), "RAG", "Test Review")]}
        self.assertEqual(best(["Pranav"], context=ctx)["Pranav"], ("Pranav Singhal", 0.60, "first_name+course"))

    def test_singhal_vs_singh_is_never_a_confident_match(self):
        """Different people with near-identical names: suggested for a human at most, never >= 0.80."""
        for s in IM.suggest(["Pranav Singh", "Pranav Singhal"], CANDIDATES):
            if {s.raw_name, s.candidate_name} == {"Pranav Singh", "Pranav Singhal"}:
                self.assertLess(s.score, 0.80)
                self.assertEqual(s.method, "typo")

    def test_zoya_vs_zoyan_scores_low(self):
        out = IM.suggest(["Zoyan"], CANDIDATES)
        self.assertEqual(out, [])                                     # short names: no typo credit
        self.assertLess(IM.jaro_winkler("zoya", "zoyan"), 1.0)
        self.assertEqual(best(["Zoya"])["Zoya"], ("Zoya Siddiqui", 0.80, "first_name"))

    def test_exact_after_cleanup_is_a_strong_suggestion(self):
        self.assertEqual(best(["Dr. Kalpesh Singh"])["Dr. Kalpesh Singh"], ("Kalpesh Singh", 0.90, "cleanup_equal"))

    def test_prefix_and_initials(self):
        b = best(["Suresh Rao", "J Jacob", "JJ", "K Sharma"])
        self.assertEqual(b["Suresh Rao"], ("Suresh Rao Shenoy", 0.80, "prefix"))
        self.assertEqual(b["J Jacob"], ("Jayant Jacob", 0.70, "initials"))
        self.assertEqual(b["JJ"], ("Jayant Jacob", 0.70, "initials"))
        self.assertNotIn("K Sharma", b)                                # initials alone are not enough

    def test_surname_only_and_unrelated_names_get_nothing(self):
        self.assertEqual(IM.suggest(["Singh", "Zed Zed", ""], CANDIDATES), [])

    def test_exact_normalised_spelling_is_not_suggested(self):
        """The sync links exact spellings itself; the suggester must not echo them."""
        self.assertEqual(IM.suggest(["kalpesh singh", "Kalpesh  Singh"], CANDIDATES), [])


class TestContext(unittest.TestCase):
    def test_same_course_overlap_adds_and_same_day_clash_subtracts(self):
        ctx = {IM.normalize("Kalpesh"): [IM.ClassRef("c1", D(2026, 3, 1), "MCP Deep Dive", "Live Class")],
               "i-kalpesh": [IM.ClassRef("c1", D(2026, 2, 20), "MCP Deep Dive", "Test Review")]}
        self.assertEqual(best(["Kalpesh"], context=ctx)["Kalpesh"], ("Kalpesh Singh", 0.95, "first_name+course"))
        clash = {IM.normalize("Nikhil Bhattnagar"): [IM.ClassRef("c1", D(2026, 3, 5), "RAG", "Live Class")],
                 "i-nikhil": [IM.ClassRef("c1", D(2026, 3, 5), "Agents", "Live Class")]}
        self.assertNotIn("Nikhil Bhattnagar", best(["Nikhil Bhattnagar"], context=clash))   # 0.75 - 0.30

    def test_overlap_needs_the_same_topic_within_120_days(self):
        far = {IM.normalize("Kalpesh"): [IM.ClassRef("c1", D(2026, 8, 1), "MCP Deep Dive", "Live Class")],
               "i-kalpesh": [IM.ClassRef("c1", D(2026, 1, 1), "MCP Deep Dive", "Live Class")]}
        self.assertEqual(best(["Kalpesh"], context=far)["Kalpesh"][1], 0.80)
        other = {IM.normalize("Kalpesh"): [IM.ClassRef("c1", D(2026, 3, 1), "MCP Deep Dive", "Live Class")],
                 "i-kalpesh": [IM.ClassRef("c1", D(2026, 3, 8), "Something Else", "Live Class")]}
        self.assertEqual(best(["Kalpesh"], context=other)["Kalpesh"][1], 0.80)

    def test_same_class_twice_is_not_a_clash(self):
        same = {IM.normalize("Kalpesh"): [IM.ClassRef("c1", D(2026, 3, 5), "RAG", "Live Class")],
                "i-kalpesh": [IM.ClassRef("c1", D(2026, 3, 5), "RAG", "Live Class")]}
        self.assertEqual(best(["Kalpesh"], context=same)["Kalpesh"][1], 0.95)   # overlap, no penalty

    def test_candidate_aliases_count_as_spellings(self):
        cands = [IM.Candidate("i-kalpesh", "Kalpesh Singh", ("K. Singh",))]
        # "K Singh" normalises to the alias exactly -> the sync links it, nothing to suggest
        self.assertEqual(IM.suggest(["K Singh"], cands), [])
        # ...while an honorific in front of the alias is a cleanup_equal suggestion
        self.assertEqual(best(["Mr K Singh"], cands)["Mr K Singh"], ("Kalpesh Singh", 0.90, "cleanup_equal"))


class TestOutputShape(unittest.TestCase):
    def test_sorted_and_keyed_for_the_db(self):
        out = IM.suggest(["Kalpesh", "Nikhil Bhattnagar"], CANDIDATES)
        self.assertEqual([s.raw_name for s in out], ["Kalpesh", "Nikhil Bhattnagar"])
        s = out[0]
        self.assertEqual((s.raw_norm, s.candidate_id), ("kalpesh", "i-kalpesh"))
        self.assertIn("matched_spelling", s.evidence)
        self.assertTrue(all(x.score >= IM.KEEP for x in out))

    def test_accepts_dicts_and_dataclasses(self):
        out = IM.suggest(["Kalpesh"], [{"id": "x", "name": "Kalpesh Singh"}, IM.Candidate("y", "Ananya Singh")])
        self.assertEqual([(s.candidate_id, s.score) for s in out], [("x", 0.80)])


if __name__ == "__main__":
    unittest.main()
