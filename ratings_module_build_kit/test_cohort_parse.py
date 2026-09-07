"""test_cohort_parse.py - the cohort-label parser against the sheet's real strings. Offline.

FIXTURES are the 100 most common cohort strings in the Jan-Aug 2026 workbook (1,825 of 2,784
rows), pulled read-only through analysis/ratings_data's loader constants and frozen here as
literals so the test never touches the workbook. Run: python -m unittest test_cohort_parse -v
"""
import datetime as dt
import unittest

import cohort_parse as CP
import course_rules as CR

FIXTURES = [  # (cohort text, dominant class type, rows Jan-Aug 2026): the 100 most common strings
    ('Advanced Machine Learning Program - Early-October 2025', 'ML Switchup Live Class', 52),
    ('Advanced Machine Learning Program - Early-February 2026', 'ML Switchup Live Class', 46),
    ('Advanced Machine Learning Program - End-November 2025', 'ML Switchup Live Class', 43),
    ('Machine Learning Program - Mid-February 2026', 'ML Switchup Live Class', 43),
    ('Machine Learning Program - Mid-November 2025', 'ML Switchup Live Class', 42),
    ('Machine Learning Flagship - IND Mid-February 2026', 'India ML Switchup Live Class', 42),
    ('Machine Learning Flagship - IND 2nd Mid-December 2025', 'India ML Switchup Live Class', 40),
    ('Machine Learning Program - Mid-March 2026', 'ML Switchup Live Class', 39),
    ('Advanced Machine Learning Program - End-August 2025, AI Data Science SwitchUp - End-August 2025', 'ML Switchup Live Class', 35),
    ('Machine Learning Program - Mid-October 2025', 'ML Switchup Live Class', 33),
    ('Machine Learning Program - 2nd Mid-April 2026', 'ML Switchup Live Class', 30),
    ('Machine Learning Flagship - IND Mid-October 2025', 'India ML Switchup Live Class', 28),
    ('Machine Learning Program - Mid-January 2026', 'ML Switchup Live Class', 27),
    ('Machine Learning Program - Mid-December 2025', 'ML Switchup Live Class', 26),
    ("India SWE's Placeholder, Transformative GenAI For SWEs - IND End-April 2026", 'India Transformative GenAI Live Class', 25),
    ("India Tech Professional's Placeholder, Transformative GenAI For Tech Professionals - IND End-April 2026", 'India Transformative GenAI Live Class', 25),
    ('Machine Learning Program - Mid-September 2025', 'ML Switchup Live Class', 24),
    ('Applied Agentic AI - 2nd Mid-March 2026, Applied Agentic AI For Tech Professionals 14 Week (Template)', 'Agentic AI Live Class', 24),
    ('Machine Learning Program - Mid-August 2025', 'ML Switchup Live Class', 22),
    ('AI Data Science SwitchUp - Early-April 2026', 'ML Switchup Live Class', 22),
    ('Applied Agentic AI - 2nd Mid-February 2026, Applied Agentic AI For Tech Professionals 14 Week (Template)', 'Agentic AI Live Class', 22),
    ("India Tech Professional's Placeholder, Transformative GenAI For Tech Professionals - IND End-March 2026 : Cohort 2", 'India Transformative GenAI Live Class', 22),
    ('Applied Agentic AI - Early-April 2026, Applied Agentic AI For Tech Professionals 14 Week (Template)', 'Agentic AI Live Class', 22),
    ('Advanced Machine Learning Program - End-May 2025', 'ML Switchup Live Class', 21),
    ('Advanced Machine Learning Program - End-May 2026', 'ML Switchup Live Class', 21),
    ('Agentic AI SWE Deprecated, Applied Agentic AI for SWEs - 2nd Mid-February 2026', 'Agentic AI Live Class', 21),
    ("India SWE's Placeholder, Transformative GenAI For SWEs - IND End-February 2026", 'India Transformative GenAI Live Class', 21),
    ("India Tech Professional's Placeholder, Transformative GenAI For Tech Professionals - IND End-February 2026", 'India Transformative GenAI Live Class', 21),
    ('Agentic AI SWE Deprecated, Applied Agentic AI for SWEs - 2nd Mid-March 2026', 'Agentic AI Live Class', 21),
    ("India SWE's Placeholder, Transformative GenAI For SWEs - IND End-March 2026", 'India Transformative GenAI Live Class', 21),
    ("India Tech Professional's Placeholder, Transformative GenAI For Tech Professionals - IND End-March 2026", 'India Transformative GenAI Live Class', 21),
    ('Advanced Machine Learning Program - 2nd End-March 2026', 'ML Switchup Live Class', 20),
    ('Machine Learning Program - Mid-December 2025, Machine Learning Program - Mid-January 2026', 'ML Switchup Live Class', 20),
    ('Agentic AI SWE Deprecated, Applied Agentic AI For SWEs - Early-February 2026', 'Agentic AI Live Class', 20),
    ('Agentic AI SWE Deprecated, Applied Agentic AI For SWEs - Mid-February 2026', 'Agentic AI Live Class', 20),
    ("India SWE's Placeholder, Transformative GenAI For SWEs - IND End-May 2026", 'India Transformative GenAI Live Class', 20),
    ('Machine Learning Program - 2nd End-May 2026', 'ML Switchup Live Class', 19),
    ('Advanced Machine Learning Program - Mid-July 2025', 'ML Switchup Live Class', 18),
    ('Agentic AI SWE Deprecated, Applied Agentic AI for SWEs - 2nd Mid-January 2026', 'Agentic AI Live Class', 18),
    ('Agentic AI SWE Deprecated, Applied Agentic AI for SWEs - Early-March 2026', 'Agentic AI Live Class', 18),
    ("India Tech Professional's Placeholder, Transformative GenAI For PM/TPM - IND End-May 2026", 'India Transformative GenAI Live Class', 18),
    ("Agentic Template (Deprecated), Applied Agentic AI for EM's - Early-June 2026", 'Agentic AI Live Class', 18),
    ('Advanced Machine Learning Program - Early-April 2025', 'ML Switchup Live Class', 17),
    ('Advanced Machine Learning Program - 2nd End-March 2026, AI Data Science SwitchUp - Early-April 2026', 'ML Switchup Live Class', 16),
    ('Agentic AI SWE Deprecated, Applied Agentic AI For SWEs - 2nd Mid-December 2025', 'Agentic AI Live Class', 16),
    ('Agentic AI SWE Deprecated, Applied Agentic AI For SWEs - Early-January 2026', 'Agentic AI Live Class', 16),
    ('Applied Agentic AI - Early-March 2026, Applied Agentic AI For Tech Professionals 14 Week (Template)', 'Agentic AI Live Class', 16),
    ("Applied Agentic AI for EM's - 2nd Mid-March 2026, Applied Agentic AI For Tech Professionals DNU", 'Agentic AI Live Class', 16),
    ('Machine Learning Flagship - IND End-July 2025', 'India ML Switchup Live Class', 15),
    ('Machine Learning Flagship - IND Early-July 2026', 'India ML Switchup Live Class', 15),
    ('Applied Agentic AI - 2nd Mid-April 2026, Applied Agentic AI - Early-May 2026', 'Agentic AI Live Class', 15),
    ("India SWE's Placeholder, Transformative GenAI For SWEs - IND 2nd Mid-June 2026", 'India Transformative GenAI Live Class', 15),
    ('AI Data Science SwitchUp - Early-April 2025', 'ML Switchup Live Class', 14),
    ('PwC x IK Agentic AI Accelerator - IND 2nd Mid-March 2026, PwC x IK Agentic AI Place Holder', 'India Agentic AI Live Class', 14),
    ('Agentic AI SWE Deprecated, Applied Agentic AI for SWEs - 2nd Mid-April 2026', 'Agentic AI Live Class', 14),
    ('Agentic AI SWE Deprecated, Applied Agentic AI for SWEs - Early-May 2026', 'Agentic AI Live Class', 14),
    ('Agentic AI SWE Deprecated, Applied Agentic AI for SWEs - Early-June 2026', 'Agentic AI Live Class', 14),
    ("India SWE's Placeholder, Transformative GenAI For SWEs - IND 2nd Mid-June 2026 : Cohort 2", 'India Transformative GenAI Live Class', 14),
    ('Applied Agentic AI - 2nd Mid-June 2026, Applied Agentic AI For Tech Professionals 14 Week (Template)', 'Agentic AI Live Class', 14),
    ('Applied Agentic AI - 2nd Mid-May 2026, Applied Agentic AI - Early-June 2026', 'Agentic AI Live Class', 14),
    ('Advanced Machine Learning Program - Mid-July 2025, AI Data Science SwitchUp - Early-July 2025', 'ML Switchup Live Class', 13),
    ('Advanced Machine Learning Program - End-August 2025', 'ML Switchup Live Class', 13),
    ('AI Data Science SwitchUp - Early-July 2025', 'ML Switchup Live Class', 13),
    ("India Tech Professional's Placeholder, Transformative GenAI For Tech Professionals - IND End-January 2026", 'India Transformative GenAI Review Class', 13),
    ('Agentic AI SWE Deprecated, Applied Agentic AI for SWEs - Early-April 2026', 'Agentic AI Live Class', 13),
    ('Applied Agentic AI - 2nd Mid-May 2026, Applied Agentic AI For Tech Professionals 14 Week (Template)', 'Agentic AI Live Class', 13),
    ('PwC x IK Agentic AI Accelerator - IND 2nd End-May 2026, PwC x IK Agentic AI Place Holder', 'India Agentic AI Live Class', 13),
    ('Applied Agentic AI - Early-July 2026, Applied Agentic AI For Tech Professionals 14 Week (Template)', 'Agentic AI Live Class', 13),
    ("Agentic Template (Deprecated), Applied Agentic AI for EM's - Early-July 2026", 'Agentic AI Live Class', 13),
    ('AI Data Science SwitchUp - IND End February 2025, Machine Learning SwitchUp - IND End February 2025', 'India ML Switchup Live Class', 12),
    ('AI Data Science SwitchUp - End-August 2025', 'ML Switchup Live Class', 12),
    ('Applied Agentic AI For Tech Professionals DNU, Transformative GenAI For Tech Professionals - IND Early-January 2026', 'India Transformative GenAI Live Class', 12),
    ("Applied Agentic AI for EM's - 2nd Mid-February 2026, Applied Agentic AI For Tech Professionals DNU", 'Agentic AI Live Class', 12),
    ("India SWE's Placeholder, Transformative GenAI For SWEs - IND End-January 2026", 'India Transformative GenAI Review Class', 12),
    ("Applied Agentic AI for EM's - Early-March 2026, Applied Agentic AI For Tech Professionals DNU", 'Agentic AI Live Class', 12),
    ('Applied Agentic AI - Early-May 2026, Applied Agentic AI For Tech Professionals 14 Week (Template)', 'Agentic AI Live Class', 12),
    ('Applied Agentic AI for SWEs - 2nd Mid-May 2026, Applied Agentic AI for SWEs - Mid-May 2026', 'Agentic AI Live Class', 12),
    ('Applied Agentic AI - 2nd mid-July 2026, Applied Agentic AI For Tech Professionals 14 Week (Template)', 'Agentic AI Live Class', 12),
    ('Applied Agentic AI for SWEs - 2nd Mid-June 2026, Applied Agentic AI for SWEs - Mid-June 2026, Forward Deployed Engineering - 2nd Mid-June 2026', 'Agentic AI Live Class', 12),
    ('Machine Learning Program - End-July 2026', 'ML Switchup Live Class', 11),
    ('Applied Agentic AI For Tech Professionals DNU, Transformative GenAI For Tech Professionals - IND End-November 2025', 'India Transformative GenAI Review Class', 11),
    ('Agentic AI SWE Deprecated, Applied Agentic AI for SWEs - 2nd End-March 2026', 'Agentic AI Review Class', 11),
    ('Agentic AI SWE Deprecated, Applied Agentic AI for SWEs - Mid-April 2026', 'Agentic AI Live Class', 11),
    ('Agentic AI SWE Deprecated, Applied Agentic AI for SWEs - Mid-May 2026', 'Agentic AI Live Class', 11),
    ("India Tech Professional's Placeholder, Transformative GenAI For PM/TPM - IND 2nd Mid-June 2026", 'India Transformative GenAI Review Class', 11),
    ('Agentic AI Pathway For SWEs - Early-December 2025, Applied Agentic AI For SWEs - Early-December 2025', 'Agentic AI Live Class', 10),
    ('Agentic AI SWE Deprecated, Applied Agentic AI for SWEs - 2nd Mid-October 2025', 'Agentic AI Live Class', 10),
    ('Applied Agentic AI For Tech Professionals DNU, Transformative GenAI For Tech Professionals - IND End-January 2026', 'India Transformative GenAI Live Class', 10),
    ('Applied Agentic AI for SWEs - Early-July 2026, Applied Agentic AI SWE Do Not Use', 'Agentic AI Live Class', 10),
    ('Applied Agentic AI for SWEs - Early-May 2026, Applied Agentic AI SWE Do Not Use', 'Agentic AI Live Class', 10),
    ('Applied Agentic AI for SWEs - 2nd End-March 2026, Applied Agentic AI for SWEs - 2nd Mid-April 2026, Applied Agentic AI for SWEs - Early-April 2026, Applied Agentic AI for SWEs - Mid-April 2026', 'Agentic AI Live Class', 10),
    ('Applied Agentic AI - Early-August 2026, Applied Agentic AI For Tech Professionals 14 Week (Template)', 'Agentic AI Live Class', 10),
    ("Applied Agentic AI - Early-February 2026, Applied Agentic AI for EM's - Early-February 2026", 'Agentic AI Live Class', 9),
    ("India Tech Professional's Placeholder, Transformative GenAI For Tech Professionals - IND Early-January 2026", 'India Transformative GenAI Live Class', 9),
    ("Applied Agentic AI for EM's - 2nd Mid-December 2025, Applied Agentic AI for EM's - Early-January 2026", 'Agentic AI Live Class', 9),
    ('PwC x IK Agentic AI Accelerator - IND 2nd Mid-February 2026, PwC x IK Agentic AI Place Holder', 'India Agentic AI Live Class', 9),
    ("Applied Agentic AI for EM's - Early-April 2026, Applied Agentic AI For Tech Professionals DNU", 'Agentic AI Live Class', 9),
    ("Applied Agentic AI for EM's - 2nd Mid-April 2026, Applied Agentic AI For Tech Professionals DNU", 'Agentic AI Review Class', 9),
    ('Applied Agentic AI for SWEs - 2nd Mid-April 2026, Applied Agentic AI for SWEs - Early-April 2026', 'Agentic AI Live Class', 9),
    ('Applied Agentic AI for SWEs - 2nd End-March 2026, Applied Agentic AI for SWEs - Mid-April 2026', 'Agentic AI Live Class', 9),
]


def parse(text, type_="Agentic AI Live Class", region=None):
    return CP.parse_cohorts_report(text, CR.course_of, region=region, type_=type_)


class TestRealStrings(unittest.TestCase):
    def test_at_least_99_percent_of_rows_yield_a_cohort(self):
        total = ok = 0
        unparsed = []
        for text, type_, n in FIXTURES:
            rep = parse(text, type_)
            total += n
            if rep.cohorts:
                ok += n
            unparsed.extend(rep.unparsed)
        self.assertGreaterEqual(ok / total, 0.99, f"unparsed: {unparsed[:10]}")

    def test_every_fixture_segment_is_parsed_or_junk(self):
        """Nothing in the top 100 is silently dropped: every segment is a cohort or known junk."""
        for text, type_, _ in FIXTURES:
            rep = parse(text, type_)
            self.assertEqual(rep.unparsed, (), f"{text!r} -> unparsed {rep.unparsed}")
            # two labels for the same intake collapse into one cohort, so cohorts + junk <= segments
            self.assertGreaterEqual(len(CP.split_segments(text)), len(rep.cohorts) + len(rep.junk), text)
            self.assertTrue(rep.cohorts, text)

    def test_no_junk_label_ever_becomes_a_cohort(self):
        for text, type_, _ in FIXTURES:
            for c in parse(text, type_).cohorts:
                self.assertFalse(CP.is_junk(c.raw_label), c.raw_label)
                self.assertNotIn("template", c.program.lower())
                self.assertNotIn("placeholder", c.program.lower())

    def test_keys_are_stable_and_names_unique_per_key(self):
        names = {}
        for text, type_, _ in FIXTURES:
            for c in parse(text, type_).cohorts:
                names.setdefault(c.cohort_key, set()).add(c.name)
        self.assertTrue(names)
        self.assertEqual([k for k, v in names.items() if len(v) > 1], [])


class TestSegments(unittest.TestCase):
    def test_plain_us_cohort(self):
        (c,) = parse("Advanced Machine Learning Program - Early-October 2025", "ML Switchup Live Class").cohorts
        self.assertEqual((c.course_label, c.region, c.year, c.month, c.part),
                         ("Advanced ML Program", "US", 2025, 10, "early"))
        self.assertEqual((c.intake_ordinal, c.cohort_no, c.audience), (1, None, None))
        self.assertEqual(c.start_month, dt.date(2025, 10, 1))
        self.assertEqual(c.cohort_key, "advanced-ml-program-US-2025-10-early-1-1")
        self.assertEqual(c.key_for("advanced-ml"), "advanced-ml-US-2025-10-early-1-1")
        self.assertEqual(c.name, "Advanced ML Program · Early-Oct 2025")

    def test_ind_second_intake_with_cohort_number(self):
        text = ("India Tech Professional's Placeholder, "
                "Transformative GenAI For Tech Professionals - IND 2nd End-March 2026 : Cohort 2")
        rep = parse(text, "India Transformative GenAI Live Class")
        self.assertEqual(len(rep.junk), 1)
        (c,) = rep.cohorts
        self.assertEqual((c.region, c.intake_ordinal, c.cohort_no, c.audience, c.part, c.month),
                         ("IND", 2, 2, "tech", "end", 3))
        self.assertEqual(c.key_suffix, "IND-2026-03-end-2-2-tech")
        self.assertEqual(c.name_for("Transformative GenAI"),
                         "Transformative GenAI for Tech Professionals · End-Mar 2026 (2nd) · Cohort 2 · IND")

    def test_region_comes_from_the_class_type_too(self):
        us = parse("Machine Learning Program - Mid-February 2026", "ML Switchup Live Class").cohorts[0]
        ind = parse("Machine Learning Program - Mid-February 2026", "India ML Switchup Live Class").cohorts[0]
        hint = parse("Machine Learning Program - Mid-February 2026", "", region="IND").cohorts[0]
        self.assertEqual((us.region, ind.region, hint.region), ("US", "IND", "IND"))
        self.assertNotEqual(us.cohort_key, ind.cohort_key)

    def test_two_courses_in_one_cell_each_get_their_own_course(self):
        rep = parse("Advanced Machine Learning Program - End-August 2025, AI Data Science SwitchUp - End-August 2025",
                    "ML Switchup Live Class")
        self.assertEqual([c.course_label for c in rep.cohorts], ["Advanced ML Program", "AI Data Science SwitchUp"])

    def test_semicolons_and_spaced_hyphen(self):
        rep = parse("Applied Agentic AI for SWEs - Mid-June 2026;Applied Agentic AI for SWEs - 2nd Mid-June 2026;"
                    "Forward Deployed Engineering - 2nd Mid-June 2026")
        self.assertEqual([(c.course_label, c.intake_ordinal) for c in rep.cohorts],
                         [("Applied Agentic AI", 1), ("Applied Agentic AI", 2),
                          ("FDE (Forward Deployed Engineering)", 2)])
        (c,) = parse("Applied Agentic AI for SWEs - Early- September 2026").cohorts
        self.assertEqual((c.month, c.part, c.audience), (9, "early", "swe"))

    def test_parenthesised_cohort_number(self):
        rep = parse("Applied Agentic AI for SWEs - Early-September 2025 (1);"
                    "Applied Agentic AI for SWEs - Early-September 2025 (2)")
        self.assertEqual([c.cohort_no for c in rep.cohorts], [1, 2])
        self.assertEqual(len({c.cohort_key for c in rep.cohorts}), 2)

    def test_audiences(self):
        cases = {"Applied Agentic AI for EM's - 2nd Mid-May 2026": "em",
                 "Transformative GenAI For PM/TPM - IND 2nd Mid-June 2026": "pm",
                 "Transformative GenAI For EM Pathway - IND End-March 2026": "em",
                 "Transformative GenAI For SWEs - IND End-April 2026": "swe",
                 "Applied Agentic AI - Early-April 2026": None}
        for text, want in cases.items():
            (c,) = parse(text).cohorts
            self.assertEqual(c.audience, want, text)

    def test_junk_markers_and_codes(self):
        junk = ["India SWE's Placeholder", "Applied Agentic AI For Tech Professionals 14 Week (Template)",
                "Agentic AI SWE Deprecated", "Applied Agentic AI SWE Do Not Use", "Test Cohort placeholder",
                "Agentic AI for Tech Proff PAthway TEmplate", "DNUtpm", "p2dnu", "DBUAB", "-",
                "Events and Session Requests", "Only for Ops"]
        for seg in junk:
            self.assertTrue(CP.is_junk(seg), seg)
        self.assertFalse(CP.is_junk("Applied Agentic AI for SWEs - Early-September 2026"))
        rep = parse("Agentic AI SWE Deprecated, Applied Agentic AI for SWEs - 2nd Mid-March 2026")
        self.assertEqual((len(rep.junk), len(rep.cohorts), rep.unparsed), (1, 1, ()))

    def test_unparseable_is_counted_never_fatal(self):
        rep = parse("Advanced ML Interview Prep Cohort April 2026", "Advanced Interview Prep")
        self.assertEqual((rep.cohorts, rep.unparsed), ((), ("Advanced ML Interview Prep Cohort April 2026",)))
        self.assertEqual(CP.parse_cohorts("", CR.course_of), [])
        self.assertEqual(CP.parse_cohorts(None, CR.course_of), [])

    def test_duplicate_labels_in_one_cell_collapse(self):
        rep = parse("Machine Learning Program - Mid-February 2026, Machine Learning Program - Mid-February 2026")
        self.assertEqual(len(rep.cohorts), 1)

    def test_fixed_course_label_and_month_forms(self):
        (c,) = CP.parse_cohorts("Whatever Program - Mid-Feb 2026", "My Course")
        self.assertEqual((c.course_label, c.month), ("My Course", 2))
        self.assertEqual(CP.month_number("Sept"), 9)
        self.assertIsNone(CP.month_number("Smarch"))
        self.assertIsNone(CP.parse_segment("Whatever Program - Mid-Smarch 2026", "x"))

    def test_week_number(self):
        start = dt.date(2026, 2, 15)
        self.assertEqual(CP.week_number(start, start), 1)
        self.assertEqual(CP.week_number(dt.date(2026, 2, 21), start), 1)
        self.assertEqual(CP.week_number(dt.date(2026, 2, 22), start), 2)
        self.assertEqual(CP.week_number(dt.date(2026, 2, 1), start), 1)     # never below 1


if __name__ == "__main__":
    unittest.main()
