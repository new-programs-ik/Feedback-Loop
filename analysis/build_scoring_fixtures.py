"""Generates supabase/fixtures/scoring_cases.json and scoring_configs.json from the reference scorer.

The manager's 36 worked examples (24 combinations + 12 scenarios) are asserted against the
document's own numbers before anything is written, so the fixture can never drift from the
methodology it claims to implement.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sentiment_score import CONFIGS, score, reason  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "supabase", "fixtures")

# --- the document's examples: (label, rating, approved?, reach %, adequate?, expected score, band)
DOC_SCENARIOS = [
    ("Ideal class", 5.0, True, 100, True, 100.0, "excellent"),
    ("High rating, small class, full reach", 4.9, True, 100, False, 92.8, "excellent"),
    ("High rating, full volume + reach", 4.9, True, 100, True, 98.8, "excellent"),
    ("Boundary at 4.7", 4.7, True, 100, True, 96.4, "excellent"),
    ("Boundary at 4.5", 4.5, True, 100, True, 94.0, "excellent"),
    ("High rating, low instructor approval", 4.8, False, 100, True, 67.6, "average"),
    ("Solid mid-range class", 4.0, False, 50, False, 50.0, "bad"),
    ("Tiny class, everyone responded", 5.0, True, 100, False, 94.0, "excellent"),
    ("Larger class, weak turnout", 4.8, True, 17, False, 88.3, "good"),
    ("Approval collapse", 4.0, False, 100, True, 58.0, "bad"),
    ("Very low rating", 1.5, True, 100, True, 58.0, "bad"),
    ("Worst case", 2.5, False, 10, False, 30.4, "bad"),
]
DOC_COMBOS = [  # rating, approved, reach, adequate, expected, band
    (4.8, True, 100, True, 97.6, "excellent"), (4.8, True, 100, False, 91.6, "excellent"),
    (4.8, True, 40, True, 95.2, "excellent"), (4.8, True, 20, False, 88.4, "good"),
    (4.8, False, 100, True, 67.6, "average"), (4.8, False, 100, False, 61.6, "average"),
    (4.8, False, 40, True, 65.2, "average"), (4.8, False, 20, False, 58.4, "bad"),
    (4.0, True, 100, True, 88.0, "good"), (4.0, True, 100, False, 82.0, "good"),
    (4.0, True, 40, True, 85.6, "good"), (4.0, True, 20, False, 78.8, "good"),
    (4.0, False, 100, True, 58.0, "bad"), (4.0, False, 100, False, 52.0, "bad"),
    (4.0, False, 40, True, 55.6, "bad"), (4.0, False, 20, False, 48.8, "bad"),
    (2.5, True, 100, True, 70.0, "average"), (2.5, True, 100, False, 64.0, "average"),
    (2.5, True, 40, True, 67.6, "average"), (2.5, True, 20, False, 60.8, "average"),
    (2.5, False, 100, True, 40.0, "bad"), (2.5, False, 100, False, 34.0, "bad"),
    (2.5, False, 40, True, 37.6, "bad"), (2.5, False, 20, False, 30.8, "bad"),
]


def doc_inputs(rating, approved, reach_pct, adequate):
    """Concrete counts that reproduce the document's abstract yes/no inputs exactly."""
    n = 10 if adequate else 5                       # >= 10 responses passes the target
    attended = round(n / (reach_pct / 100.0))       # reach = n / attended
    yes = n if approved else round(n * 0.2)          # 100% or 20% approval as in the document
    return {"rating": rating, "num_ratings": n, "attended": attended, "yes_votes": yes, "no_votes": n - yes,
            "escalated": False, "track_avg": None, "prior_rating": 4.7, "prior_approval": 93}


def add_case(cases, cfg_key, label, inputs, expect=None, note="", decimals=2):
    res = score(inputs, CONFIGS[cfg_key])
    if expect is not None:
        exp_score, exp_band = expect
        got = None if res["score"] is None else round(res["score"], decimals)
        assert got == exp_score and res["band"] == exp_band, (label, res["score"], res["band"], expect)
    cases.append({"id": f"{cfg_key}-{len(cases) + 1:03d}", "config": cfg_key, "label": label, "note": note,
                  "inputs": inputs, "expected": {"score": res["score"], "band": res["band"], "action": res["action"],
                                                 "provisional": res["provisional"], "flags": res["flags"]},
                  "reason": reason(inputs, res, CONFIGS[cfg_key])})


def main():
    cases = []
    # 1. the document, under C0 - asserted against its own numbers
    # the document prints one decimal; we store two, so the document's numbers are checked at one
    for label, rating, approved, reach_pct, adequate, exp, band in DOC_SCENARIOS:
        add_case(cases, "C0", "doc: " + label, doc_inputs(rating, approved, reach_pct, adequate), (exp, band), decimals=1)
    for rating, approved, reach_pct, adequate, exp, band in DOC_COMBOS:
        add_case(cases, "C0", f"doc combo {rating} {'yes' if approved else 'no'} {reach_pct}% {'adequate' if adequate else 'thin'}",
                 doc_inputs(rating, approved, reach_pct, adequate), (exp, band), decimals=1)
    # 2. band edges (C0): construct scores on both sides of every edge
    add_case(cases, "C0", "edge 90.00 -> excellent", {"rating": 4.5, "num_ratings": 10, "attended": 10, "yes_votes": 10, "no_votes": 0}, (94.0, "excellent"))
    add_case(cases, "C0", "edge just under 90 -> good", {"rating": 4.5, "num_ratings": 10, "attended": 25, "yes_votes": 10, "no_votes": 0}, (91.6, "excellent"))
    add_case(cases, "C0", "edge 89.99 area: 4.16 full -> good", {"rating": 4.16, "num_ratings": 10, "attended": 10, "yes_votes": 10, "no_votes": 0}, (89.92, "good"))
    add_case(cases, "C0", "edge 90 exactly: 4.1667 full", {"rating": 4.1667, "num_ratings": 10, "attended": 10, "yes_votes": 10, "no_votes": 0}, (90.0, "excellent"))
    add_case(cases, "C0", "edge 75 exactly", {"rating": 3.75, "num_ratings": 5, "attended": 5, "yes_votes": 5, "no_votes": 0}, (79.0, "good"))
    add_case(cases, "C0", "edge 60 exactly: 4.1667 no approval full reach adequate", {"rating": 4.1667, "num_ratings": 10, "attended": 10, "yes_votes": 2, "no_votes": 8}, (60.0, "average"))
    add_case(cases, "C0", "edge 59.99: 4.166 no approval", {"rating": 4.166, "num_ratings": 10, "attended": 10, "yes_votes": 2, "no_votes": 8}, (59.99, "bad"))
    # 3. approval bar inclusivity (C0)
    add_case(cases, "C0", "approval exactly 80: 4 of 5", {"rating": 4.5, "num_ratings": 5, "attended": 10, "yes_votes": 4, "no_votes": 1}, (86.0, "good"))
    add_case(cases, "C0", "approval exactly 80: 8 of 10", {"rating": 4.5, "num_ratings": 10, "attended": 10, "yes_votes": 8, "no_votes": 2}, (94.0, "excellent"))
    add_case(cases, "C0", "approval exactly 80: 12 of 15", {"rating": 4.5, "num_ratings": 15, "attended": 15, "yes_votes": 12, "no_votes": 3}, (94.0, "excellent"))
    add_case(cases, "C0", "approval 79.99 fails: 3 of 4 = 75", {"rating": 4.5, "num_ratings": 4, "attended": 10, "yes_votes": 3, "no_votes": 1}, (55.6, "bad"))
    add_case(cases, "C0", "approval 7 of 9 = 77.8 fails", {"rating": 4.5, "num_ratings": 9, "attended": 9, "yes_votes": 7, "no_votes": 2}, (58.0, "bad"))
    add_case(cases, "C0", "the famous 4.87 with 2 of 3", {"rating": 4.87, "num_ratings": 3, "attended": 20, "yes_votes": 2, "no_votes": 1}, (59.04, "bad"))
    # 4. null and nonsense (C0 policies: missing approval/reach = zero)
    add_case(cases, "C0", "no rating", {"rating": None, "num_ratings": 5, "attended": 10, "yes_votes": 5, "no_votes": 0}, (None, None))
    add_case(cases, "C0", "escalated without rating -> video", {"rating": None, "num_ratings": 5, "attended": 10, "yes_votes": 5, "no_votes": 0, "escalated": True}, (None, None))
    add_case(cases, "C0", "no vote at all (zero policy)", {"rating": 4.2, "num_ratings": 10, "attended": 20, "yes_votes": None, "no_votes": None}, (58.4, "bad"))
    add_case(cases, "C0", "attendance missing (zero policy)", {"rating": 4.7, "num_ratings": 12, "attended": None, "yes_votes": 12, "no_votes": 0}, (92.4, "excellent"))
    add_case(cases, "C0", "responses > attended -> reach clamped", {"rating": 4.6, "num_ratings": 25, "attended": 20, "yes_votes": 25, "no_votes": 0}, (95.2, "excellent"))
    add_case(cases, "C0", "negative responses rejected", {"rating": 4.6, "num_ratings": -3, "attended": 20, "yes_votes": 0, "no_votes": 0}, (None, None))
    add_case(cases, "C0", "rating above the scale rejected", {"rating": 7, "num_ratings": 5, "attended": 5, "yes_votes": 5, "no_votes": 0}, (None, None))
    add_case(cases, "C0", "rating zero rejected", {"rating": 0, "num_ratings": 5, "attended": 5, "yes_votes": 5, "no_votes": 0}, (None, None))
    add_case(cases, "C0", "nobody attended", {"rating": 4.5, "num_ratings": 0, "attended": 0, "yes_votes": 0, "no_votes": 0}, (54.0, "bad"))
    add_case(cases, "C0", "rated 1.0 but loved", {"rating": 1.0, "num_ratings": 10, "attended": 10, "yes_votes": 10, "no_votes": 0}, (52.0, "bad"))
    add_case(cases, "C0", "rated 5.0 but rejected", {"rating": 5.0, "num_ratings": 10, "attended": 10, "yes_votes": 0, "no_votes": 10}, (70.0, "average"))
    add_case(cases, "C0", "escalated fine class -> video", {"rating": 4.9, "num_ratings": 10, "attended": 10, "yes_votes": 10, "no_votes": 0, "escalated": True}, (98.8, "excellent"))
    # 5. C5 - the recommended candidate, worked cases from the plan
    C5 = {"prior_rating": 4.7, "prior_approval": 93}
    add_case(cases, "C5", "famous 4.87 with 2 of 3 -> guarded, provisional", {"rating": 4.87, "num_ratings": 3, "attended": 20, "yes_votes": 2, "no_votes": 1, **C5})
    add_case(cases, "C5", "4.30 with 60% approval, 20 votes -> both lines missed -> bad", {"rating": 4.30, "num_ratings": 20, "attended": 30, "yes_votes": 12, "no_votes": 8, **C5})
    add_case(cases, "C5", "4.80 polite rating, 6 of 10 -> average", {"rating": 4.80, "num_ratings": 10, "attended": 20, "yes_votes": 6, "no_votes": 4, **C5})
    add_case(cases, "C5", "4.30 everyone approves -> rating line -> average", {"rating": 4.30, "num_ratings": 20, "attended": 30, "yes_votes": 20, "no_votes": 0, **C5})
    add_case(cases, "C5", "3.60 everyone approves -> bad", {"rating": 3.60, "num_ratings": 10, "attended": 15, "yes_votes": 10, "no_votes": 0, **C5})
    add_case(cases, "C5", "4.70 with 15 of 20 -> guard keeps a big sample's signal -> average", {"rating": 4.70, "num_ratings": 20, "attended": 25, "yes_votes": 15, "no_votes": 5, **C5})
    add_case(cases, "C5", "3 of 4 yes -> guard passes", {"rating": 4.7, "num_ratings": 4, "attended": 10, "yes_votes": 3, "no_votes": 1, **C5})
    add_case(cases, "C5", "7 of 9 yes -> guard passes", {"rating": 4.7, "num_ratings": 9, "attended": 12, "yes_votes": 7, "no_votes": 2, **C5})
    add_case(cases, "C5", "cohort of 3, all yes -> provisional, watch", {"rating": 4.9, "num_ratings": 3, "attended": 3, "yes_votes": 3, "no_votes": 0, **C5})
    add_case(cases, "C5", "two voters -> no band", {"rating": 5.0, "num_ratings": 2, "attended": 2, "yes_votes": 2, "no_votes": 0, **C5})
    add_case(cases, "C5", "webinar 200 attended, 5 happy raters -> provisional, never bad", {"rating": 4.9, "num_ratings": 5, "attended": 200, "yes_votes": 5, "no_votes": 0, **C5})
    add_case(cases, "C5", "big room says no: 40 of 100 -> bad", {"rating": 4.6, "num_ratings": 100, "attended": 200, "yes_votes": 40, "no_votes": 60, **C5})
    add_case(cases, "C5", "no vote recorded, rating under the line -> average", {"rating": 4.2, "num_ratings": 10, "attended": 20, "yes_votes": None, "no_votes": None, **C5})
    add_case(cases, "C5", "bad track record, fine class -> good not excellent", {"rating": 4.7, "num_ratings": 12, "attended": 20, "yes_votes": 11, "no_votes": 1, "track_avg": 4.0, **C5})
    add_case(cases, "C5", "first class, no track -> neutral", {"rating": 4.7, "num_ratings": 12, "attended": 20, "yes_votes": 11, "no_votes": 1, **C5})
    add_case(cases, "C5", "exactly on both lines -> good", {"rating": 4.55, "num_ratings": 10, "attended": 20, "yes_votes": 8, "no_votes": 2, "track_avg": 4.6, **C5})
    add_case(cases, "C5", "just under the line, everyone approves -> average", {"rating": 4.54, "num_ratings": 10, "attended": 20, "yes_votes": 10, "no_votes": 0, "track_avg": 4.6, **C5})
    add_case(cases, "C5", "everyone says no, high rating -> flagged, one line missed -> average", {"rating": 4.9, "num_ratings": 10, "attended": 10, "yes_votes": 0, "no_votes": 10, **C5})
    add_case(cases, "C5", "escalated -> video whatever the band", {"rating": 4.9, "num_ratings": 10, "attended": 10, "yes_votes": 10, "no_votes": 0, "escalated": True, **C5})
    add_case(cases, "C5", "test review 8 of 15 rated, all yes -> not penalised", {"rating": 4.8, "num_ratings": 8, "attended": 15, "yes_votes": 8, "no_votes": 0, **C5})
    add_case(cases, "C5", "hard class great teacher big sample: 3.0, 40 of 40 -> bad", {"rating": 3.0, "num_ratings": 40, "attended": 45, "yes_votes": 40, "no_votes": 0, **C5})
    # 6. the graded variants on the same edge inputs
    for key in ("C1", "C2", "C3", "C4"):
        add_case(cases, key, "famous 4.87 with 2 of 3", {"rating": 4.87, "num_ratings": 3, "attended": 20, "yes_votes": 2, "no_votes": 1, **C5})
        add_case(cases, key, "responses 9 vs 10 at the target", {"rating": 4.5, "num_ratings": 9, "attended": 12, "yes_votes": 9, "no_votes": 0, **C5})
        add_case(cases, key, "approval 79.99 area: 4 of 5", {"rating": 4.6, "num_ratings": 5, "attended": 10, "yes_votes": 4, "no_votes": 1, **C5})

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "scoring_cases.json"), "w", encoding="utf-8") as f:
        json.dump({"contract": "analysis/sentiment_score.py", "cases": cases}, f, indent=1)
    with open(os.path.join(OUT_DIR, "scoring_configs.json"), "w", encoding="utf-8") as f:
        json.dump(CONFIGS, f, indent=1)
    print("wrote %d cases, %d configs -> %s" % (len(cases), len(CONFIGS), OUT_DIR))
    for c in cases:
        if c["config"] == "C5":
            e = c["expected"]
            print("  C5 %-62s score %-6s band %-9s action %-10s %s" % (c["label"][:62], e["score"], e["band"], e["action"], "prov" if e["provisional"] else ""))


if __name__ == "__main__":
    main()
