"""Step 4a - the cases: simulate everything, not only what happened.

Three sources, one fixture file (analysis/out/formula_cases.json):

  grid         a full grid over the input space - rating x votes x approval x attended x track
               record x kind x cohort week (269,280 points). The properties run on the FULL grid
               (properties.py --full); the fixture keeps the axes plus a fixed-seed sample of 2,000
               points so the unit test stays quick.
  random       1,000 draws from wide distributions over every input at once (priors, attendance
               change, previous class, missing values included).
  adversarial  the named edge cases, every one kept in full: empty rooms, single voices, the
               200-person webinar, the big room saying no, rating and vote in disagreement, more
               raters than attendees, a missing vote column, a brand-new course, an instructor's
               first class, a bad record with a fine class, a tiny cohort, a review, an attendance
               collapse, a bimodal opinion behind a 3.8, the worst class of a 4.9 course, the
               guarded-line case, and the nonsense inputs.

Each case is a dict of the scorer's inputs (see families.INPUT_KEYS) plus 'kind', 'region',
'weekday' for the invariance checks. The EXPECTED behaviour is written as properties
(properties.py), not as numbers.

Run:  python analysis/formula/cases.py   -> analysis/out/formula_cases.json
"""
from __future__ import annotations

import itertools
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import OUT, write_json  # noqa: E402

CASES_JSON = os.path.join(OUT, "formula_cases.json")

GRID_AXES = {
    "rating": [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 3.8, 4.0, 4.2, 4.4, 4.5, 4.55, 4.6, 4.7, 4.8, 4.9, 5.0],
    "votes": [0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 30, 60],
    "approval": [0, 25, 50, 60, 70, 75, 79, 80, 85, 90, 100],
    "attended": [1, 3, 5, 10, 20, 50, 100, 300],
    "track": [None, 4.0, 4.7],
    "kind": ["live", "review"],
    "week": [1, 5, 15],
}
TYPICAL = {"prior_rating": 4.70, "prior_approval": 93.0, "module_prior_rating": 4.70, "module_prior_n": 10, "module_prior_approval": 93.0,
           "att_vs_prev": 1.0, "prev_rating": 4.70}


def _votes(votes, approval):
    yes = int(round(votes * approval / 100.0))
    return float(yes), float(votes - yes)


def grid_case(rating, votes, approval, attended, track, kind, week):
    yes, no = _votes(votes, approval)
    n = max(votes, 1) if votes else 0
    n = min(n, attended) if attended else n
    n = max(n, votes)
    return {"rating": rating, "num_ratings": float(n), "attended": float(attended), "yes_votes": yes, "no_votes": no, "escalated": 0,
            "track_avg": track, "track_ewma": track, "track_n": 0 if track is None else 6, **TYPICAL,
            "kind": kind, "region": "US", "weekday": 4, "week": week}


def grid_cases(sample=None, seed=7):
    axes = [GRID_AXES[k] for k in ("rating", "votes", "approval", "attended", "track", "kind", "week")]
    combos = list(itertools.product(*axes))
    if sample:
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(combos), size=min(sample, len(combos)), replace=False)
        combos = [combos[i] for i in sorted(idx)]
    return [{"id": "G%06d" % i, "source": "grid", "label": "rating %.2f, %d votes, %d%% yes, %d attended, track %s, %s, week %d" % (c[0], c[1], c[2], c[3], c[4], c[5], c[6]),
             "inputs": grid_case(*c)} for i, c in enumerate(combos)]


def random_cases(n=1000, seed=11):
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        # ratings: most classes 4.3-5.0, a real tail
        r = 5.0 - rng.gamma(1.6, 0.25) if rng.random() < 0.85 else rng.uniform(1.0, 4.3)
        r = float(np.clip(round(r, 2), 1.0, 5.0))
        att = int(np.clip(round(np.exp(rng.normal(2.9, 0.6))), 1, 300))
        votes = int(np.clip(round(att * rng.beta(2, 2.5)), 0, att)) if rng.random() < 0.97 else 0
        p = rng.beta(9, 1) if r >= 4.3 else rng.beta(3, 2)
        yes = int(round(votes * p))
        track = None if rng.random() < 0.25 else float(np.clip(round(rng.normal(4.62, 0.28), 2), 2.5, 5.0))
        track_n = 0 if track is None else int(rng.integers(3, 40))
        ewma = None if track is None else float(np.clip(round(track + rng.normal(0, 0.12), 2), 2.5, 5.0))
        mp = None if rng.random() < 0.2 else float(np.clip(round(rng.normal(4.68, 0.2), 2), 3.0, 5.0))
        mpn = 0 if mp is None else int(rng.integers(1, 30))
        mpa = None if mp is None else float(np.clip(rng.normal(93, 6), 40, 100))
        cp = None if rng.random() < 0.05 else float(np.clip(round(rng.normal(4.70, 0.12), 2), 3.5, 5.0))
        cpa = None if cp is None else float(np.clip(rng.normal(93, 4), 50, 100))
        avp = None if rng.random() < 0.15 else float(np.clip(round(np.exp(rng.normal(0, 0.3)), 2), 0.1, 5.0))
        prev = None if rng.random() < 0.1 else float(np.clip(round(rng.normal(4.7, 0.3), 2), 1.0, 5.0))
        missing_vote = rng.random() < 0.03
        out.append({"id": "R%04d" % i, "source": "random", "label": "random draw %d" % i,
                    "inputs": {"rating": r, "num_ratings": float(votes if votes else int(rng.integers(0, 3))), "attended": float(att),
                               "yes_votes": None if missing_vote else float(yes), "no_votes": None if missing_vote else float(votes - yes), "escalated": 0,
                               "track_avg": track, "track_ewma": ewma, "track_n": track_n,
                               "prior_rating": cp, "prior_approval": cpa, "module_prior_rating": mp, "module_prior_n": mpn, "module_prior_approval": mpa,
                               "att_vs_prev": avp, "prev_rating": prev,
                               "kind": "live" if rng.random() < 0.65 else "review", "region": "IND" if rng.random() < 0.3 else "US",
                               "weekday": int(rng.integers(0, 7)), "week": int(rng.integers(1, 30))}})
    return out


def adv(cid, label, **kw):
    inp = {"rating": None, "num_ratings": None, "attended": None, "yes_votes": None, "no_votes": None, "escalated": 0,
           "track_avg": None, "track_ewma": None, "track_n": 0, **TYPICAL, "kind": "live", "region": "US", "weekday": 4, "week": 5}
    inp.update(kw)
    return {"id": cid, "source": "adversarial", "label": label, "inputs": inp}


def adversarial_cases():
    return [
        adv("A01", "nobody attended", rating=4.5, num_ratings=0, attended=0, yes_votes=0, no_votes=0),
        adv("A02", "one rater, rated 5.0, said yes", rating=5.0, num_ratings=1, attended=1, yes_votes=1, no_votes=0),
        adv("A03", "one rater, rated 1.0, said no", rating=1.0, num_ratings=1, attended=1, yes_votes=0, no_votes=1),
        adv("A04", "200-person webinar, 5 happy raters", rating=4.9, num_ratings=5, attended=200, yes_votes=5, no_votes=0),
        adv("A05", "big room says no: 40 of 100 yes", rating=4.6, num_ratings=100, attended=200, yes_votes=40, no_votes=60),
        adv("A06", "rating high, vote low: 4.9 with 0 of 10", rating=4.9, num_ratings=10, attended=12, yes_votes=0, no_votes=10),
        adv("A07", "rating low, vote high: 1.0 with 10 of 10", rating=1.0, num_ratings=10, attended=12, yes_votes=10, no_votes=0),
        adv("A08", "more raters than attendees", rating=4.6, num_ratings=25, attended=20, yes_votes=25, no_votes=0),
        adv("A09", "missing vote column, low rating", rating=4.2, num_ratings=10, attended=20),
        adv("A10", "missing vote column, fine rating", rating=4.8, num_ratings=10, attended=20),
        adv("A11", "brand-new course: no priors at all", rating=4.87, num_ratings=3, attended=20, yes_votes=2, no_votes=1,
            prior_rating=None, prior_approval=None, module_prior_rating=None, module_prior_n=0, module_prior_approval=None, prev_rating=None, att_vs_prev=None),
        adv("A12", "an instructor's first class", rating=4.7, num_ratings=12, attended=20, yes_votes=11, no_votes=1, track_avg=None, track_ewma=None, track_n=0),
        adv("A13", "bad record, fine class", rating=4.8, num_ratings=15, attended=20, yes_votes=15, no_votes=0, track_avg=4.0, track_ewma=4.0, track_n=10),
        adv("A14", "great record, bad class", rating=4.0, num_ratings=15, attended=20, yes_votes=9, no_votes=6, track_avg=4.9, track_ewma=4.9, track_n=30),
        adv("A15", "tiny cohort of 5, all rated, one no", rating=4.8, num_ratings=5, attended=5, yes_votes=4, no_votes=1),
        adv("A16", "tiny cohort of 5, all said no", rating=3.5, num_ratings=5, attended=5, yes_votes=0, no_votes=5),
        adv("A17", "a test review (same numbers as A12)", rating=4.7, num_ratings=12, attended=20, yes_votes=11, no_votes=1, track_avg=None, track_ewma=None, track_n=0, kind="review"),
        adv("A18", "sudden attendance collapse on a fine class", rating=4.8, num_ratings=12, attended=6, yes_votes=12, no_votes=0, att_vs_prev=0.3),
        adv("A19a", "bimodal opinion behind a 3.8: 50% yes", rating=3.8, num_ratings=10, attended=15, yes_votes=5, no_votes=5),
        adv("A19b", "the same 3.8 with 95% yes", rating=3.8, num_ratings=20, attended=25, yes_votes=19, no_votes=1),
        adv("A20", "worst class of a 4.9 course: 4.6 with 12 of 12", rating=4.6, num_ratings=12, attended=15, yes_votes=12, no_votes=0,
            module_prior_rating=4.9, module_prior_n=20, module_prior_approval=98.0, prior_rating=4.9, prior_approval=98.0, prev_rating=4.9),
        adv("A22", "rating missing", num_ratings=5, attended=10, yes_votes=5, no_votes=0),
        adv("A23", "rating 0", rating=0, num_ratings=5, attended=5, yes_votes=5, no_votes=0),
        adv("A24", "rating above the scale (7)", rating=7, num_ratings=5, attended=5, yes_votes=5, no_votes=0),
        adv("A25", "negative responses", rating=4.6, num_ratings=-3, attended=20, yes_votes=0, no_votes=0),
        adv("A26a", "approval exactly 80.00: 4 of 5", rating=4.7, num_ratings=5, attended=10, yes_votes=4, no_votes=1),
        adv("A26b", "approval exactly 80.00: 8 of 10", rating=4.7, num_ratings=10, attended=10, yes_votes=8, no_votes=2),
        adv("A26c", "approval exactly 80.00: 12 of 15", rating=4.7, num_ratings=15, attended=15, yes_votes=12, no_votes=3),
        adv("A27", "approval 79.99 with a huge sample", rating=4.7, num_ratings=10000, attended=10000, yes_votes=7999, no_votes=2001),
        adv("A28", "exactly on both lines: 4.55, 8 of 10", rating=4.55, num_ratings=10, attended=20, yes_votes=8, no_votes=2, track_avg=4.6, track_ewma=4.6, track_n=5),
        adv("A29", "4.54 with 10 votes, everyone approves, course 4.70 (the guarded-line case)", rating=4.54, num_ratings=10, attended=20, yes_votes=10, no_votes=0, track_avg=4.6, track_ewma=4.6, track_n=5),
        adv("A30", "PM escalation on a fine class", rating=4.9, num_ratings=10, attended=10, yes_votes=10, no_votes=0, escalated=1),
        adv("A31a", "duplicate row (1 of 2)", rating=4.7, num_ratings=12, attended=20, yes_votes=11, no_votes=1),
        adv("A31b", "duplicate row (2 of 2)", rating=4.7, num_ratings=12, attended=20, yes_votes=11, no_votes=1),
        adv("A32", "votes do not add up to responses: 9 votes, 12 ratings", rating=4.7, num_ratings=12, attended=20, yes_votes=5, no_votes=4),
        adv("A33", "10,000 attended, nobody rated", num_ratings=0, attended=10000, yes_votes=0, no_votes=0),
        adv("A34", "a 3.0 class with an approved instructor (10 of 10)", rating=3.0, num_ratings=10, attended=15, yes_votes=10, no_votes=0),
        adv("A35", "new module (no module prior), course prior present", rating=4.4, num_ratings=8, attended=12, yes_votes=7, no_votes=1,
            module_prior_rating=None, module_prior_n=0, module_prior_approval=None),
        adv("A36", "attendance missing", rating=4.7, num_ratings=12, attended=None, yes_votes=12, no_votes=0),
        adv("A37a", "one vote out of 20 (before): 4.7, 18 of 20", rating=4.7, num_ratings=20, attended=25, yes_votes=18, no_votes=2),
        adv("A37b", "one vote out of 20 (after): 4.7, 17 of 20", rating=4.7, num_ratings=20, attended=25, yes_votes=17, no_votes=3),
        adv("A38a", "one vote out of 5 (before): 4.7, 5 of 5", rating=4.7, num_ratings=5, attended=8, yes_votes=5, no_votes=0),
        adv("A38b", "one vote out of 5 (after): 4.7, 4 of 5", rating=4.7, num_ratings=5, attended=8, yes_votes=4, no_votes=1),
        adv("A39", "few raters, high: 4.9 with 3 of 3", rating=4.9, num_ratings=3, attended=20, yes_votes=3, no_votes=0),
        adv("A40", "few raters, low: 3.9 with 0 of 3", rating=3.9, num_ratings=3, attended=20, yes_votes=0, no_votes=3),
        adv("A41a", "huge room, tiny reach: 300 attended, 3 rated 4.9", rating=4.9, num_ratings=3, attended=300, yes_votes=3, no_votes=0),
        adv("A41b", "small room, everyone rated: 3 attended, 3 rated 4.9", rating=4.9, num_ratings=3, attended=3, yes_votes=3, no_votes=0),
        adv("A42", "unusual for its module: 4.3 in a 4.95 module (15 votes)", rating=4.3, num_ratings=15, attended=20, yes_votes=13, no_votes=2,
            module_prior_rating=4.95, module_prior_n=25, module_prior_approval=99.0),
        adv("A43", "prior below the class: 4.6 with 4 votes in a 4.2 module", rating=4.6, num_ratings=4, attended=10, yes_votes=4, no_votes=0,
            module_prior_rating=4.2, module_prior_n=12, module_prior_approval=80.0, prior_rating=4.3, prior_approval=85.0),
        adv("A44", "reviews only: a review with a poor vote (4.4, 6 of 10)", rating=4.4, num_ratings=10, attended=14, yes_votes=6, no_votes=4, kind="review"),
        adv("A45", "IND cohort, same numbers as A12", rating=4.7, num_ratings=12, attended=20, yes_votes=11, no_votes=1, track_avg=None, track_ewma=None, track_n=0, region="IND"),
        adv("A46", "Monday class, same numbers as A12", rating=4.7, num_ratings=12, attended=20, yes_votes=11, no_votes=1, track_avg=None, track_ewma=None, track_n=0, weekday=0),
        adv("A47", "plainly fine: 4.9, 20 of 20, 40 attended", rating=4.9, num_ratings=20, attended=40, yes_votes=20, no_votes=0, track_avg=4.7, track_ewma=4.7, track_n=12),
        adv("A48", "plainly bad: 3.2, 2 of 20, 40 attended", rating=3.2, num_ratings=20, attended=40, yes_votes=2, no_votes=18, track_avg=4.7, track_ewma=4.7, track_n=12),
    ]


def build(grid_sample=2000):
    cases = adversarial_cases() + random_cases() + grid_cases(sample=grid_sample)
    return {"axes": GRID_AXES, "typical": TYPICAL, "grid_points": int(np.prod([len(v) for v in GRID_AXES.values()])),
            "counts": {"adversarial": sum(1 for c in cases if c["source"] == "adversarial"), "random": sum(1 for c in cases if c["source"] == "random"),
                       "grid_sample": sum(1 for c in cases if c["source"] == "grid")},
            "cases": cases}


def load_cases(full_grid=False):
    if not os.path.exists(CASES_JSON):
        write_json(CASES_JSON, build())
    from common import read_json
    fx = read_json(CASES_JSON)
    cases = [c for c in fx["cases"] if c["source"] != "grid"]
    cases += grid_cases() if full_grid else [c for c in fx["cases"] if c["source"] == "grid"]
    return cases, fx


if __name__ == "__main__":
    fx = build()
    write_json(CASES_JSON, fx)
    print("wrote %s: %d adversarial, %d random, %d of %s grid points sampled" % (
        CASES_JSON, fx["counts"]["adversarial"], fx["counts"]["random"], fx["counts"]["grid_sample"], "{:,}".format(fx["grid_points"])))
