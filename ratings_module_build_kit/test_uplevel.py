"""test_uplevel.py — the parsing and matching that map a class to its UpLevel recording.

These are pure functions; no network, no session. The two real classes below are the ones checked
by hand against UpLevel on 22 September 2026 (the links are public Vimeo ids, not secrets)."""
import datetime as dt
import unittest

import uplevel as UP

# The two rows verified by hand: name string, clean topic, the known Vimeo link.
ML_ARCH = {
    "name": "ML Architectures Live Class with Sarfaraz, ML Architectures, Sunday, September 13, 2026 09:00 AM PDT",
    "topic__name": "ML Architectures", "vimeo_link": "https://vimeo.com/1226433411", "duration_in_sec": 17508,
}
MLOPS = {
    "name": "MLOPs - Model Training Live Class Lakshaya, Lakshaya, Sunday, September 13, 2026, 09:00 AM US/Pacific",
    "topic__name": "MLOPs - Model Training 1", "vimeo_link": "https://vimeo.com/1226939172", "duration_in_sec": 10311,
}
ARS = {
    "name": "Computer Vision - 1 Assignment Review Class with Evgeny Saveliev, Computer Vision, Friday, September 12, 2026, 09:00 AM US/Pacific",
    "topic__name": "Computer Vision - 1", "vimeo_link": "https://vimeo.com/1220000001", "duration_in_sec": 3600,
}


class TestParsing(unittest.TestCase):
    def test_the_date_is_read_from_the_name(self):
        self.assertEqual(UP.parse_date(ML_ARCH["name"]), dt.date(2026, 9, 13))
        self.assertEqual(UP.parse_date(ARS["name"]), dt.date(2026, 9, 12))
        self.assertIsNone(UP.parse_date("no date here"))

    def test_the_category_is_read_from_the_name(self):
        self.assertEqual(UP.parse_category(ML_ARCH["name"]), "live_class")
        self.assertEqual(UP.parse_category(ARS["name"]), "ars")
        self.assertEqual(UP.parse_category("Office Hours with X, Monday, January 1, 2026"), "coaching")
        self.assertIsNone(UP.parse_category("Something Else, Monday, January 1, 2026"))

    def test_a_row_without_a_vimeo_link_is_skipped(self):
        self.assertIsNone(UP.video_from_row({"name": "x", "vimeo_link": None, "link": None}))

    def test_a_row_becomes_a_video(self):
        v = UP.video_from_row(ML_ARCH)
        self.assertEqual(v.vimeo_id, "1226433411")
        self.assertEqual(v.vimeo_link, "https://vimeo.com/1226433411")
        self.assertEqual(v.topic, "ML Architectures")
        self.assertEqual(v.category, "live_class")
        self.assertEqual(v.class_date, dt.date(2026, 9, 13))

    def test_topic_similarity_is_lenient_but_honest(self):
        self.assertGreaterEqual(UP.topic_similarity("MLOps - Model Training", "MLOPs - Model Training 1"), 0.6)
        self.assertGreaterEqual(UP.topic_similarity("RAG Powered Knowledge Agents", "RAG Knowledge Agents"), 0.6)
        self.assertLess(UP.topic_similarity("Calculus Primer", "Computer Vision"), 0.35)

    def test_instructor_is_found_by_a_real_name_part(self):
        self.assertTrue(UP.instructor_in(ML_ARCH["name"], "Sarfaraz"))
        self.assertTrue(UP.instructor_in(ARS["name"], "Evgeny Saveliev"))
        self.assertFalse(UP.instructor_in(ML_ARCH["name"], "Lakshaya"))


class TestMatching(unittest.TestCase):
    def test_the_known_class_is_a_perfect_match(self):
        m = UP.score_match(UP.video_from_row(ML_ARCH), topic="ML Architectures", instructor="Sarfaraz",
                           class_date=dt.date(2026, 9, 13), kind="live_class")
        self.assertGreaterEqual(m.score, 0.95)
        self.assertIn("same date", m.reasons)

    def test_a_different_day_is_ruled_out(self):
        m = UP.score_match(UP.video_from_row(ML_ARCH), topic="ML Architectures", instructor="Sarfaraz",
                           class_date=dt.date(2026, 9, 20), kind="live_class")
        self.assertIsNone(m)   # a recording on another day is a different class

    def test_the_wrong_category_is_penalised(self):
        # our live class must not match an assignment-review recording of a near topic on the same day
        m = UP.score_match(UP.video_from_row(ARS), topic="Computer Vision - 1", instructor="Evgeny Saveliev",
                           class_date=dt.date(2026, 9, 12), kind="live_class")
        self.assertLess(m.score, 0.8)
        self.assertTrue(any("category" in r for r in m.reasons))

    def test_another_instructors_class_on_the_same_day_is_not_offered(self):
        # Seen in production on 23 Sep: "Product Sense with Apoorv" scored 0.65 against
        # "AI Product Architecture with Yadhu" because it shared the date. It cannot be the class.
        other = {"name": "Product Sense Live Class with Apoorv Gupta, Apoorv, Saturday, September 19, 2026, 08:30 PM",
                 "topic__name": "Product Sense", "vimeo_link": "https://vimeo.com/1228707645"}
        self.assertIsNone(UP.score_match(UP.video_from_row(other), topic="AI Product Architecture",
                                         instructor="Yadhu", class_date=dt.date(2026, 9, 19), kind="live_class"))

    def test_a_different_spelling_of_the_instructor_still_matches_on_the_class_name(self):
        m = UP.score_match(UP.video_from_row(ML_ARCH), topic="ML Architectures", instructor="Sarfaraz Ahmed Khan",
                           class_date=dt.date(2026, 9, 13), kind="live_class")
        self.assertIsNotNone(m)                              # "Sarfaraz" is in the name
        m = UP.score_match(UP.video_from_row(ML_ARCH), topic="ML Architectures", instructor="S. Khan",
                           class_date=dt.date(2026, 9, 13), kind="live_class")
        self.assertIsNotNone(m)                              # no name part matches, but the class name does
        self.assertIn("instructor not found in the recording name", m.reasons)

    def test_ranking_prefers_the_stronger_match_and_drops_wrong_days(self):
        other_day = dict(ML_ARCH); other_day["vimeo_link"] = "https://vimeo.com/999"
        other_day["name"] = other_day["name"].replace("September 13", "September 6")
        matches = UP.rank_matches([other_day, ML_ARCH], topic="ML Architectures",
                                  instructor="Sarfaraz", class_date=dt.date(2026, 9, 13), kind="live_class")
        self.assertEqual(len(matches), 1)                      # the Sep 6 one is a different class
        self.assertEqual(matches[0].video.vimeo_id, "1226433411")

    def test_search_terms_prefer_the_instructor(self):
        terms = UP._search_terms("Sarfaraz", "ML Architectures")
        self.assertEqual(terms[0], "sarfaraz")


class TestSessionSeam(unittest.TestCase):
    def test_a_missing_session_is_not_connected_not_a_silent_empty(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"UPLEVEL_COOKIE": ""}, clear=False), \
             patch.object(UP, "_stored_secret", return_value=""), \
             patch.object(UP, "COOKIE_FILE", "/does/not/exist"):
            with self.assertRaises(UP.UplevelNotConnected):
                UP._read_cookie_header()

    def test_the_cookie_is_pulled_from_a_copy_as_curl(self):
        import os
        from unittest.mock import patch
        curl = "curl 'https://uplevel.interviewkickstart.com/videos/' -b 'sessionid=abc; csrftoken=def'"
        with patch.dict(os.environ, {"UPLEVEL_COOKIE": curl}, clear=False), \
             patch.object(UP, "_stored_secret", return_value=""):
            self.assertEqual(UP._read_cookie_header(), "sessionid=abc; csrftoken=def")

    def test_what_an_admin_saved_in_the_app_wins_over_the_environment(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"UPLEVEL_COOKIE": "sessionid=from-env"}, clear=False), \
             patch.object(UP, "_stored_secret", return_value="sessionid=from-app; csrftoken=x"):
            self.assertEqual(UP._read_cookie_header(), "sessionid=from-app; csrftoken=x")

    def test_a_database_that_cannot_be_asked_falls_back_to_the_environment(self):
        import os
        from unittest.mock import patch
        import store as ST
        with patch.dict(os.environ, {"UPLEVEL_COOKIE": "sessionid=from-env"}, clear=False), \
             patch.object(ST, "get_integration_secret", side_effect=ST.StoreUnavailable("down")):
            self.assertEqual(UP._read_cookie_header(), "sessionid=from-env")

    def test_only_the_two_session_cookies_are_kept(self):
        import requests
        s = requests.Session()
        for k, v in (("sessionid", "abc"), ("csrftoken", "def"), ("refresh_token", "secret"), ("_ga", "x")):
            s.cookies.set(k, v, domain="uplevel.interviewkickstart.com")
        self.assertEqual(UP.cookie_header_of(s), "sessionid=abc; csrftoken=def")


if __name__ == "__main__":
    unittest.main()
