"""Step 5a - the evaluation of one formula (a family's settings) on one set of months.

Everything the loop and the report need, on whatever rows are passed in (the selection folds,
the held-out months, a fairness slice):

  signal      AUC of (100 - score) for the targets a, b, c, c_below, d, with a cluster bootstrap
              (instructors for a, cohorts for b/c) - and the pre-registered objective: the mean
              of a and c, with its standard error
  bands       next-class risk per band (the Y3 view), band mix, no-band share, provisional count
  stability   one-vote flips (label and verdict), for every class and for 10+ votes; the largest
              and typical score move from one vote among classes with 20+ votes
  lines       false comfort (firm Good/Excellent under a line with 5+ votes), false alarm (Bad
              though fine on both lines), Bad classes rated 4.55+, hidden lows
  workload    analyses a week (video + transcript), videos a week, cost
  fairness    at equal rating: the share flagged for analysis and the Excellent share, by
              live/review, India/US, small/big room, weekday group - and the gaps

evaluate(df, cfg, weeks) scores and measures; metrics(df, res, res_y, res_r, weeks) measures
already-scored rows, so the loop can pool folds scored with their own settings.
"""
from __future__ import annotations

import math
import os
import sys
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (LINE, BAR, VOICES, BANDS, BAND_LABEL, COST, auc, cluster_bootstrap)  # noqa: E402
from families import inputs_from_df, score_any, perturb  # noqa: E402

TARGET_CLUSTER = {"t_a": "instructor", "t_b": "cohort", "t_c": "cohort", "t_c_below": "cohort", "t_d": None}


def _share(a, b):
    return a / b * 100.0 if b else 0.0


def standardised(df, res, group_fn, pick, width=0.1):
    """Share of `pick(result, i)` per group at EQUAL rating (0.1 buckets, weighted by the pooled mix)."""
    buckets = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    total = Counter()
    ratings = df["rating"].values
    groups = [group_fn(r) for r in df.to_dict("records")]
    for i in range(len(df)):
        if res["band"][i] is None:
            continue
        b = math.floor(ratings[i] / width + 1e-9)
        g = groups[i]
        buckets[b][g][0] += 1
        buckets[b][g][1] += 1 if pick(res, i) else 0
        total[b] += 1
    out = {}
    for g in set(groups):
        acc = wsum = 0.0
        for b, gm in buckets.items():
            if g in gm and gm[g][0] > 0:
                acc += gm[g][1] / gm[g][0] * total[b]
                wsum += total[b]
        out[g] = acc / wsum * 100 if wsum else 0.0
    return out


def score_three(df, cfg, X=None):
    X = inputs_from_df(df) if X is None else X
    return score_any(X, cfg), score_any(perturb(X, "yes_to_no"), cfg), score_any(perturb(X, "one_point_less"), cfg)


def concat_results(parts):
    out = {}
    for k in ("score", "band", "action", "provisional"):
        out[k] = np.concatenate([p[k] for p in parts])
    out["flags"] = sum((p["flags"] for p in parts), [])
    return out


def evaluate(df, cfg, weeks, bootstrap=100, X=None):
    df = df.reset_index(drop=True)
    res, res_y, res_r = score_three(df, cfg, X)
    return metrics(df, res, res_y, res_r, weeks, bootstrap)


def metrics(df, res, res_y, res_r, weeks, bootstrap=100):
    df = df.reset_index(drop=True)
    sc = res["score"]
    worst = np.where(np.isnan(sc), 101.0, sc)
    n = len(df)
    votes = df["votes"].values
    approval = df["approval"].values
    rating = df["rating"].values

    # ---- signal -------------------------------------------------------------------------------
    signal = {}
    for t, cl in TARGET_CLUSTER.items():
        m = df[t].notna().values
        if m.sum() < 30 or df[t][m].nunique() < 2:
            signal[t] = None
            continue
        y = df[t].values[m].astype(float)
        s = -worst[m]
        clusters = df[cl].fillna("none").values[m] if cl else np.arange(m.sum())
        if bootstrap:
            est, se, lo, hi = cluster_bootstrap(lambda idx: auc(s[idx], y[idx]), clusters, reps=bootstrap)
        else:
            est, se, lo, hi = auc(s, y), float("nan"), float("nan"), float("nan")
        signal[t] = {"auc": est, "se": se, "lo": lo, "hi": hi, "n": int(m.sum()), "positives": int(y.sum())}
    obj = [signal[t]["auc"] for t in ("t_a", "t_c") if signal.get(t)]
    ses = [signal[t]["se"] for t in ("t_a", "t_c") if signal.get(t) and signal[t]["se"] == signal[t]["se"]]
    objective = {"value": float(np.mean(obj)) if obj else float("nan"), "se": (math.sqrt(sum(v * v for v in ses)) / len(ses)) if ses else float("nan")}

    # ---- bands ----------------------------------------------------------------------------------
    per_band = {b: {"n": 0, "a_n": 0, "a_low": 0, "c_n": 0, "c_low": 0} for b in BANDS}
    ta, tc = df["t_a"].values, df["t_c"].values
    for i in range(n):
        b = res["band"][i]
        if b is None or res["provisional"][i]:
            continue
        pb = per_band[b]
        pb["n"] += 1
        if ta[i] == ta[i]:
            pb["a_n"] += 1
            pb["a_low"] += int(ta[i])
        if tc[i] == tc[i]:
            pb["c_n"] += 1
            pb["c_low"] += int(tc[i])
    for b, pb in per_band.items():
        pb["a_share"] = _share(pb["a_low"], pb["a_n"])
        pb["c_share"] = _share(pb["c_low"], pb["c_n"])
    a_shares = [per_band[b]["a_share"] for b in BANDS]
    order_ok = sum(1 for k in range(3) if a_shares[3 - k] > a_shares[2 - k])
    counts = Counter(res["band"])
    banded = sum(v for k, v in counts.items() if k is not None)
    bands = {"per_band": per_band, "order_ok_a": order_ok,
             "ratio_bad_excellent_a": (per_band["bad"]["a_share"] / per_band["excellent"]["a_share"]) if per_band["excellent"]["a_share"] else None,
             "counts": {BAND_LABEL[k]: v for k, v in counts.items()}, "shares": {b: _share(counts[b], banded) for b in BANDS},
             "no_band_share": _share(counts[None], n), "provisional": int(res["provisional"].sum()),
             "no_score": int(np.isnan(sc).sum())}

    # ---- stability ------------------------------------------------------------------------------
    flips = Counter()
    moves = {"yes": [], "rating": []}
    for i in range(n):
        fy = res["band"][i] != res_y["band"][i]
        fr = res["band"][i] != res_r["band"][i]
        fv = res["action"][i] != res_y["action"][i] or res["action"][i] != res_r["action"][i]
        flips["label"] += fy or fr
        flips["verdict"] += fv
        if votes[i] >= 10:
            flips["n10"] += 1
            flips["label10"] += fy or fr
            flips["verdict10"] += fv
        if votes[i] >= 20 and not np.isnan(sc[i]):
            if not np.isnan(res_y["score"][i]):
                moves["yes"].append(abs(res_y["score"][i] - sc[i]))
            if not np.isnan(res_r["score"][i]):
                moves["rating"].append(abs(res_r["score"][i] - sc[i]))
    stability = {"flip_label": _share(flips["label"], n), "flip_verdict": _share(flips["verdict"], n),
                 "flip_label_10plus": _share(flips["label10"], flips["n10"]), "flip_verdict_10plus": _share(flips["verdict10"], flips["n10"]),
                 "max_move_20plus": max(moves["yes"] + moves["rating"]) if (moves["yes"] or moves["rating"]) else 0.0,
                 "median_move_yes_20plus": float(np.median(moves["yes"])) if moves["yes"] else 0.0,
                 "median_move_rating_20plus": float(np.median(moves["rating"])) if moves["rating"] else 0.0}

    # ---- the two lines --------------------------------------------------------------------------
    voiced = votes >= VOICES
    under = (rating < LINE) | (np.where(np.isnan(approval), 100.0, approval) < BAR)
    fine = ~under
    fc = [i for i in np.flatnonzero(voiced & under) if res["band"][i] in ("good", "excellent") and not res["provisional"][i]]
    fc_prov = [i for i in np.flatnonzero(voiced & under) if res["band"][i] in ("good", "excellent") and res["provisional"][i]]
    fa = [i for i in np.flatnonzero(voiced & fine) if res["band"][i] == "bad"]
    bad_all = [i for i in range(n) if res["band"][i] == "bad"]
    lines = {"n_voiced": int(voiced.sum()), "false_comfort": len(fc), "false_comfort_share": _share(len(fc), voiced.sum()),
             "false_comfort_provisional": len(fc_prov), "false_alarm": len(fa), "false_alarm_share": _share(len(fa), voiced.sum()),
             "bad_total": len(bad_all), "bad_rated_fine": sum(1 for i in bad_all if rating[i] >= LINE),
             "hidden_lows": sum(1 for i in np.flatnonzero(voiced & (rating < LINE)) if res["action"][i] == "none")}

    # ---- workload ---------------------------------------------------------------------------------
    actions = Counter(res["action"])
    workload = {"actions": dict(actions), "per_week": (actions["video"] + actions["transcript"]) / weeks, "videos_per_week": actions["video"] / weeks,
                "transcripts_per_week": actions["transcript"] / weeks, "cost_per_week": (actions["video"] * COST["video"] + actions["transcript"] * COST["transcript"]) / weeks,
                "weeks": weeks}

    # ---- fairness ---------------------------------------------------------------------------------
    flagged = lambda r, i: r["action"][i] in ("video", "transcript")  # noqa: E731
    excellent = lambda r, i: r["band"][i] == "excellent"  # noqa: E731
    slices = {"kind": lambda r: "review" if r["kind"] == "review" else "live", "region": lambda r: r["region"],
              "room": lambda r: "<10 responses" if r["responses"] < 10 else "10+ responses",
              "weekday": lambda r: "Thu-Sun" if r["weekday"] >= 3 else "Mon-Wed"}
    fairness = {}
    for name, fn in slices.items():
        fl = standardised(df, res, fn, flagged)
        ex = standardised(df, res, fn, excellent)
        fairness[name] = {"flagged": fl, "excellent": ex, "flagged_gap": (max(fl.values()) - min(fl.values())) if fl else 0.0,
                          "excellent_gap": (max(ex.values()) - min(ex.values())) if ex else 0.0}
    fairness["max_flagged_gap"] = max(v["flagged_gap"] for v in fairness.values() if isinstance(v, dict))
    fairness["max_excellent_gap"] = max(v["excellent_gap"] for v in fairness.values() if isinstance(v, dict))

    return {"n": n, "signal": signal, "objective": objective, "bands": bands, "stability": stability, "lines": lines, "workload": workload, "fairness": fairness}


def constraints(ev, capacity=12.0, videos=5.0):
    """The hard lines a candidate must clear on the selection months before its signal counts."""
    fails = []
    if ev["lines"]["false_comfort_share"] > 2.0:
        fails.append("false comfort %.1f%% > 2%%" % ev["lines"]["false_comfort_share"])
    if ev["lines"]["false_alarm_share"] > 5.0:
        fails.append("false alarm %.1f%% > 5%%" % ev["lines"]["false_alarm_share"])
    if ev["workload"]["per_week"] > capacity:
        fails.append("workload %.1f a week > %g" % (ev["workload"]["per_week"], capacity))
    if ev["workload"]["videos_per_week"] > videos:
        fails.append("videos %.1f a week > %g" % (ev["workload"]["videos_per_week"], videos))
    return fails


def soft_marks(ev):
    """Yardsticks that are reported and used as tie-breakers, never as vetoes."""
    return {"verdict_flips_10plus": ev["stability"]["flip_verdict_10plus"], "label_flips": ev["stability"]["flip_label"],
            "band_order": ev["bands"]["order_ok_a"], "fairness_gap": ev["fairness"]["max_flagged_gap"]}
