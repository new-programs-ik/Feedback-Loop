"""Step 3 - the formula families, each a small JSON of settings a PM could read on a Scoring page.

Two scorers:

  score_points(X, cfg)    weighted points - a strict superset of the scoring contract
                          (analysis/sentiment_score.py). A config without the new keys is scored
                          exactly as the contract scores it (verify_against_contract checks that).
                          New keys, all optional:
                            guard.k_approval      separate prior strength for the vote (phantom votes)
                            guard.prior           "course" (contract) | "module" | "instructor" | "hierarchical"
                            guard.k_low/k_high    asymmetric trust: k for a rating below / above its prior
                            approval.mode         + "wilson" (lower bound of the vote's interval)
                            track.mode            + "ewma" (recency-weighted record)
                            caps.basis            "guarded" (contract) | "raw" (the lines read the raw values)
                            extras                optional components: module_delta, attendance, momentum
                            weights               may carry the extras' weights
  score_logistic(X, cfg)  a monotone logistic model mapped to 0-100 (100 minus the chance the
                          next class goes wrong), with sign constraints so more no-votes never
                          raise the score and a higher rating never lowers it.

Every family: key, name, one-sentence explanation, fit(df_fit) -> settings, and the inputs it
reads. Fitting only ever sees the fit months; the loop (loop.py) decides what to keep.

X is a dict of numpy arrays (see inputs_from_df / inputs_from_cases): rating, num_ratings,
attended, yes_votes, no_votes, escalated, track_avg, track_ewma, track_n, prior_rating,
prior_approval, module_prior_rating, module_prior_n, module_prior_approval, att_vs_prev,
prev_rating. NaN means missing.
"""
from __future__ import annotations

import copy
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (OUT, LINE, BAR, BANDS, BAND_RANK, ACTIONS, auc, read_json)  # noqa: E402
from sentiment_score import CONFIGS, MANAGER_ORIGINAL, score as contract_score, round2  # noqa: E402

INPUT_KEYS = ["rating", "num_ratings", "attended", "yes_votes", "no_votes", "escalated", "track_avg", "track_ewma", "track_n",
              "prior_rating", "prior_approval", "module_prior_rating", "module_prior_n", "module_prior_approval", "att_vs_prev", "prev_rating"]
NAN = float("nan")


# ------------------------------------------------------------------ inputs
def inputs_from_df(df):
    def col(name, default=NAN):
        return df[name].astype(float).values if name in df else np.full(len(df), default)
    return {
        "rating": col("rating"), "num_ratings": col("responses"), "attended": col("attended"),
        "yes_votes": col("yes"), "no_votes": col("no"), "escalated": col("escalated", 0.0),
        "track_avg": col("track_mean"), "track_ewma": col("track_ewma"), "track_n": col("track_n", 0.0),
        "prior_rating": col("course_prior_rating"), "prior_approval": col("course_prior_approval"),
        "module_prior_rating": col("module_prior_rating"), "module_prior_n": col("module_prior_n", 0.0),
        "module_prior_approval": col("module_prior_approval"),
        "att_vs_prev": col("att_vs_prev"), "prev_rating": col("prev_rating"),
    }


def inputs_from_cases(cases):
    X = {k: np.full(len(cases), NAN) for k in INPUT_KEYS}
    X["escalated"][:] = 0.0
    X["track_n"][:] = 0.0
    X["module_prior_n"][:] = 0.0
    for i, c in enumerate(cases):
        for k in INPUT_KEYS:
            v = c["inputs"].get(k)
            if v is not None and v == v:
                X[k][i] = float(v)
    return X


def perturb(X, how):
    """The one-vote perturbations: 'yes_to_no' (one yes becomes a no) and 'one_point_less' (one
    rater gives one point less: the average drops by 1/n)."""
    P = {k: v.copy() for k, v in X.items()}
    if how == "yes_to_no":
        m = P["yes_votes"] >= 1
        P["yes_votes"][m] -= 1
        P["no_votes"][m] += 1
    elif how == "one_point_less":
        n = P["num_ratings"]
        m = (n >= 1) & ~np.isnan(P["rating"])
        P["rating"][m] = np.maximum(1.0, P["rating"][m] - 1.0 / n[m])
    return P


# ------------------------------------------------------------------ the points scorer
def _shape_up(v, floor, top, top_value=100.0):
    """0 at floor, top_value at top, clamped to [0, top_value]."""
    return np.clip((v - floor) / (top - floor) * top_value, 0.0, top_value)


def _rating_component(adj, r):
    scale = float(r["scale"])
    if r["mode"] == "knee":
        floor, line, lv = float(r["floor"]), float(r["line"]), float(r["line_value"])
        below = _shape_up(adj, floor, line, lv)
        above = lv + np.clip((adj - line) / (scale - line), 0.0, 1.0) * (100.0 - lv)
        out = np.where(adj <= floor, 0.0, np.where(adj <= line, below, above))
    else:
        out = adj / scale * 100.0
    return np.clip(out, 0.0, 100.0)


def _prior_arrays(X, cfg):
    """The prior the guard shrinks toward, per row, by the config's guard.prior rule."""
    src = cfg.get("guard", {}).get("prior", "course")
    pr, pa = X["prior_rating"], X["prior_approval"]
    if src == "module":
        pr = np.where(np.isnan(X["module_prior_rating"]), pr, X["module_prior_rating"])
        pa = np.where(np.isnan(X["module_prior_approval"]), pa, X["module_prior_approval"])
    elif src == "instructor":
        t = np.where(np.isnan(X["track_ewma"]), X["track_avg"], X["track_ewma"])
        pr = np.where(np.isnan(t), pr, t)
    elif src == "hierarchical":
        min_n = float(cfg["guard"].get("prior_min_n", 3))
        use_m = (~np.isnan(X["module_prior_rating"])) & (X["module_prior_n"] >= min_n)
        pr = np.where(use_m, X["module_prior_rating"], pr)
        pa = np.where(use_m & ~np.isnan(X["module_prior_approval"]), X["module_prior_approval"], pa)
    return pr, pa


def score_points(X, cfg):
    """Vectorised weighted-points score. Returns dict of arrays: score (nan when no score), band
    (object array: 'excellent'.. or None), action, provisional (bool), flags (list of lists)."""
    n_rows = len(X["rating"])
    rating, n, att = X["rating"], X["num_ratings"], X["attended"]
    yes, no = X["yes_votes"], X["no_votes"]
    esc = X["escalated"] > 0.5
    scale = float(cfg["rating"]["scale"])
    flags = [[] for _ in range(n_rows)]

    invalid = np.zeros(n_rows, bool)
    for key in ("num_ratings", "attended", "yes_votes", "no_votes"):
        bad = (~np.isnan(X[key])) & (X[key] < 0)
        invalid |= bad
        for i in np.flatnonzero(bad):
            flags[i].append("invalid_" + key)
    bad_r = (~np.isnan(rating)) & ((rating < 0) | (rating > scale))
    invalid |= bad_r
    for i in np.flatnonzero(bad_r):
        flags[i].append("invalid_rating")
    no_rating = np.isnan(rating) & ~invalid
    zero_rating = (rating == 0) & ~invalid
    for i in np.flatnonzero(no_rating):
        flags[i].append("no_rating")
    for i in np.flatnonzero(zero_rating):
        flags[i].append("rating_zero")
    rejected = invalid | no_rating | zero_rating

    votes = np.where(np.isnan(yes) | np.isnan(no), NAN, yes + no)
    votes = np.where(votes <= 0, NAN, votes)
    approval = np.where(np.isnan(votes), NAN, yes / np.where(np.isnan(votes), 1.0, votes) * 100.0)
    for i in np.flatnonzero(np.isnan(approval) & ~rejected):
        flags[i].append("no_vote")
    for i in np.flatnonzero((~np.isnan(votes)) & (~np.isnan(n)) & (np.abs(votes - n) > 0.5) & ~rejected):
        flags[i].append("votes_ne_responses")
    for i in np.flatnonzero(np.isnan(n) & ~rejected):
        flags[i].append("no_responses")
    for i in np.flatnonzero((n == 0) & ~rejected):
        flags[i].append("zero_responses")
    for i in np.flatnonzero((np.isnan(att) | (att == 0)) & ~rejected):
        flags[i].append("no_attendance")
    reach = np.where((~np.isnan(n)) & (~np.isnan(att)) & (att > 0), n / np.where(att > 0, att, 1.0) * 100.0, NAN)
    for i in np.flatnonzero((reach > 100.0) & ~rejected):
        flags[i].append("reach_clamped")
    reach = np.minimum(reach, 100.0)
    for i in np.flatnonzero((~np.isnan(approval)) & (rating >= 4.5) & (approval < 50) & ~rejected):
        flags[i].append("rating_vote_disagree")

    # ---- the guard: shrink toward the prior with k phantom raters / votes -----------------
    g = cfg.get("guard", {})
    k = float(g.get("k") or 0)
    k_a = float(g.get("k_approval", k) if g.get("k_approval") is not None else k)
    pr, pa = _prior_arrays(X, cfg)
    adj_rating, adj_approval = rating.copy(), approval.copy()
    kr = np.full(n_rows, k)
    if g.get("k_low") is not None or g.get("k_high") is not None:
        kr = np.where(rating < pr, float(g.get("k_low", k)), float(g.get("k_high", k)))
    can_r = (kr > 0) & ~np.isnan(pr) & ~np.isnan(n)
    with np.errstate(invalid="ignore", divide="ignore"):
        adj_rating = np.where(can_r, (n * rating + kr * pr) / (n + kr), rating)
        can_a = (k_a > 0) & ~np.isnan(approval) & ~np.isnan(pa) & ~np.isnan(votes)
        adj_approval = np.where(can_a, (yes + k_a * pa / 100.0) / (np.where(np.isnan(votes), 1.0, votes) + k_a) * 100.0, approval)
    guarded = (can_r & (adj_rating != rating)) | (can_a & (adj_approval != approval))
    for i in np.flatnonzero(guarded & ~rejected):
        flags[i].append("guarded")

    # ---- components ------------------------------------------------------------------------
    comps, weights = {}, cfg["weights"]
    comps["rating"] = _rating_component(adj_rating, cfg["rating"])
    a = cfg["approval"]
    if a["mode"] == "wilson":
        z = float(a.get("z", 1.0))
        vv = np.where(np.isnan(votes), 1.0, votes)
        p = yes / vv
        d = 1 + z * z / vv
        c = p + z * z / (2 * vv)
        m = z * np.sqrt(p * (1 - p) / vv + z * z / (4 * vv * vv))
        adj_approval = np.where(np.isnan(votes), NAN, (c - m) / d * 100.0)
    if a["mode"] == "cliff":
        comp_a = np.where(adj_approval >= float(a["bar"]), 100.0, 0.0)
    else:
        comp_a = _shape_up(adj_approval, float(a["floor"]), float(a["bar"]))
    comp_a = np.where(np.isnan(adj_approval), 0.0 if cfg["missing"]["approval"] == "zero" else NAN, comp_a)
    comps["approval"] = comp_a
    s = cfg["sample"]
    if s["mode"] == "off":
        comps["sample"] = np.full(n_rows, NAN)
    else:
        t = float(s["target"])
        comps["sample"] = np.where(np.isnan(n), 0.0, np.clip(n / t * 100.0, 0, 100) if s["mode"] == "graded" else np.where(n >= t, 100.0, 0.0))
    if cfg["reach"]["mode"] == "off":
        comps["reach"] = np.full(n_rows, NAN)
    else:
        comps["reach"] = np.where(np.isnan(reach), 0.0 if cfg["missing"]["reach"] == "zero" else NAN, reach)
    t = cfg["track"]
    if t["mode"] == "off":
        comps["track"] = np.full(n_rows, NAN)
    else:
        tv = X["track_ewma"] if t["mode"] == "ewma" else X["track_avg"]
        tv = np.where(np.isnan(tv) & (t["mode"] == "ewma"), X["track_avg"], tv)
        comps["track"] = np.where(np.isnan(tv), NAN, _shape_up(tv, float(t["floor"]), float(t["line"])))
        for i in np.flatnonzero(np.isnan(tv) & ~rejected):
            flags[i].append("no_track")
    for name, spec in (cfg.get("extras") or {}).items():
        if name == "module_delta":
            v = rating - X["module_prior_rating"]
            v = np.where(X["module_prior_n"] >= float(spec.get("min_n", 3)), v, NAN)
        elif name == "attendance":
            v = X["att_vs_prev"]
        elif name == "momentum":
            v = X["prev_rating"]
        else:
            continue
        comps[name] = np.where(np.isnan(v), NAN, _shape_up(v, float(spec["floor"]), float(spec["ceiling"])))

    num = np.zeros(n_rows)
    den = np.zeros(n_rows)
    for key, comp in comps.items():
        w = float(weights.get(key, 0) or 0)
        if w <= 0:
            continue
        ok = ~np.isnan(comp)
        num += np.where(ok, comp * w, 0.0)
        den += np.where(ok, w, 0.0)
    raw = np.where(den > 0, num / np.where(den > 0, den, 1.0), 0.0)
    sc = np.array([round2(v) for v in raw])

    # ---- band, caps, vote floors -----------------------------------------------------------
    b = cfg["bands"]
    band_idx = np.where(sc >= float(b["excellent"]), 0, np.where(sc >= float(b["good"]), 1, np.where(sc >= float(b["average"]), 2, 3)))
    mv = cfg["min_votes"]
    voices = np.where(np.isnan(votes), np.where(np.isnan(n), 0.0, n), votes)
    act_floor = float(mv.get("action", 0) or 0)
    enough = voices >= act_floor
    caps = cfg["caps"]
    basis = caps.get("basis", "guarded")
    cr = rating if basis in ("raw", "raw_rating") else adj_rating
    ca = approval if basis == "raw" else adj_approval
    missed = np.zeros(n_rows, int)
    if caps.get("rating_line") is not None:
        m = enough & (cr < float(caps["rating_line"]))
        missed += m
        for i in np.flatnonzero(m & ~rejected):
            flags[i].append("under_rating_line")
    if caps.get("approval_bar") is not None:
        m = enough & (~np.isnan(ca)) & (ca < float(caps["approval_bar"]))
        missed += m
        for i in np.flatnonzero(m & ~rejected):
            flags[i].append("under_approval_bar")
    band_idx = np.where(missed == 1, np.maximum(band_idx, 2), band_idx)
    band_idx = np.where(missed >= 2, 3, band_idx)
    band_floor = float(mv.get("band", 0) or 0)
    thin = voices < band_floor
    provisional = (~thin) & (~enough) & (act_floor > 0)
    for i in np.flatnonzero(thin & ~rejected):
        flags[i].append("thin_no_band")
    for i in np.flatnonzero(provisional & ~rejected):
        flags[i].append("thin_provisional")
    band = np.array([None if (thin[i] or rejected[i]) else BANDS[band_idx[i]] for i in range(n_rows)], dtype=object)
    actions = cfg["actions"]
    action = np.array([("video" if esc[i] else actions["no_data"] if (band[i] is None or provisional[i]) else actions[band[i]]) for i in range(n_rows)], dtype=object)
    for i in np.flatnonzero(esc):
        flags[i].append("escalated")
    sc = np.where(rejected, NAN, sc)
    provisional = np.where(rejected, False, provisional)
    return {"score": sc, "band": band, "action": action, "provisional": provisional.astype(bool), "flags": flags,
            "adj_rating": np.where(rejected, NAN, adj_rating), "adj_approval": np.where(rejected, NAN, adj_approval), "components": comps}


def verify_against_contract(cfg, X, limit=None):
    """Score every row with the contract and compare (score, band, action, provisional).
    Only for configs the contract understands; returns the number of disagreements."""
    n = len(X["rating"]) if limit is None else min(limit, len(X["rating"]))
    fast = score_points({k: v[:n] for k, v in X.items()}, cfg)
    bad = 0
    for i in range(n):
        inp = {k: (None if np.isnan(X[k][i]) else float(X[k][i])) for k in ("rating", "num_ratings", "attended", "yes_votes", "no_votes", "track_avg", "prior_rating", "prior_approval")}
        inp["escalated"] = bool(X["escalated"][i] > 0.5)
        c = contract_score(inp, cfg)
        f_sc = None if np.isnan(fast["score"][i]) else float(fast["score"][i])
        if (f_sc, fast["band"][i], fast["action"][i], bool(fast["provisional"][i])) != (c["score"], c["band"], c["action"], c["provisional"]):
            bad += 1
            if bad <= 3:
                print("  contract mismatch row %d: fast %s / %s / %s / %s vs contract %s / %s / %s / %s" % (
                    i, f_sc, fast["band"][i], fast["action"][i], fast["provisional"][i], c["score"], c["band"], c["action"], c["provisional"]))
    return bad


# ------------------------------------------------------------------ the logistic scorer
LOGIT_INPUTS = {
    # name: (how it is read from X, sign constraint: +1 means "more of this = safer", transform)
    "rating": ("adj_rating", +1), "approval": ("adj_approval", +1), "track": ("track", +1),
    "module_delta": ("module_delta", +1), "attendance": ("att_vs_prev", +1), "momentum": ("prev_rating", +1),
}


def _logit_raw(X, cfg):
    """The raw (unstandardised) monotone inputs of the logistic family, plus the base result."""
    g = cfg.get("guard", {})
    pts_cfg = {**MANAGER_ORIGINAL, "guard": g, "approval": {"mode": "graded", "bar": 80, "floor": 40},
               "missing": {"approval": "neutral", "reach": "neutral", "track": "neutral"}, "caps": {"rating_line": None, "approval_bar": None},
               "min_votes": {"band": 0, "action": 0}}
    base = score_points(X, pts_cfg)
    _, pa = _prior_arrays(X, pts_cfg)
    approval = np.where(np.isnan(base["adj_approval"]), pa, base["adj_approval"])      # no vote: the prior's approval (neutral)
    raw = {"rating": np.minimum(base["adj_rating"], 5.0), "approval": approval,
           "track": np.where(np.isnan(X["track_ewma"]), X["track_avg"], X["track_ewma"]),
           "module_delta": np.where(X["module_prior_n"] >= 3, X["rating"] - X["module_prior_rating"], NAN),
           "attendance": X["att_vs_prev"], "momentum": X["prev_rating"]}
    return raw, base


def _logit_features(X, cfg):
    """Standardised, monotone features with missing values set to the centre (neutral)."""
    raw, base = _logit_raw(X, cfg)
    F = {}
    for name in cfg["inputs"]:
        v = raw[name].astype(float)
        z = (v - cfg["centre"][name]) / cfg["spread"][name]
        z = np.where(np.isnan(z), 0.0, z)          # missing = neutral
        F[name] = np.clip(z, -4, 4)
    return F, base


def score_logistic(X, cfg):
    F, base = _logit_features(X, cfg)
    n_rows = len(X["rating"])
    eta = np.full(n_rows, float(cfg["intercept"]))
    for name, z in F.items():
        eta += float(cfg["coef"][name]) * z
    p = 1.0 / (1.0 + np.exp(-eta))                # chance the next class goes wrong
    sc = np.array([round2(v) for v in np.clip(100.0 * (1.0 - p), 0, 100)])
    rejected = np.isnan(base["score"])
    # bands, caps and vote floors as in the points scorer
    tmp = {**MANAGER_ORIGINAL, "bands": cfg["bands"], "min_votes": cfg["min_votes"], "caps": cfg["caps"], "actions": cfg.get("actions", ACTIONS),
           "guard": cfg.get("guard", {"k": 0}), "weights": {"rating": 100, "approval": 0, "sample": 0, "reach": 0, "track": 0},
           "approval": {"mode": "graded", "bar": 80, "floor": 40}, "sample": {"mode": "off", "target": 10}, "reach": {"mode": "off"},
           "track": {"mode": "off", "floor": 4.05, "line": 4.55, "min_classes": 3}, "missing": {"approval": "neutral", "reach": "neutral", "track": "neutral"}}
    shell = score_points(X, tmp)
    b = cfg["bands"]
    band_idx = np.where(sc >= float(b["excellent"]), 0, np.where(sc >= float(b["good"]), 1, np.where(sc >= float(b["average"]), 2, 3)))
    votes = np.where(np.isnan(X["yes_votes"]) | np.isnan(X["no_votes"]), NAN, X["yes_votes"] + X["no_votes"])
    votes = np.where(votes <= 0, NAN, votes)
    voices = np.where(np.isnan(votes), np.where(np.isnan(X["num_ratings"]), 0.0, X["num_ratings"]), votes)
    act_floor = float(cfg["min_votes"].get("action", 0) or 0)
    enough = voices >= act_floor
    missed = np.zeros(n_rows, int)
    caps = cfg["caps"]
    approval = np.where(np.isnan(votes), NAN, X["yes_votes"] / np.where(np.isnan(votes), 1.0, votes) * 100.0)
    if caps.get("rating_line") is not None:
        missed += enough & (X["rating"] < float(caps["rating_line"]))
    if caps.get("approval_bar") is not None:
        missed += enough & (~np.isnan(approval)) & (approval < float(caps["approval_bar"]))
    band_idx = np.where(missed == 1, np.maximum(band_idx, 2), band_idx)
    band_idx = np.where(missed >= 2, 3, band_idx)
    thin = voices < float(cfg["min_votes"].get("band", 0) or 0)
    provisional = (~thin) & (~enough) & (act_floor > 0)
    band = np.array([None if (thin[i] or rejected[i]) else BANDS[band_idx[i]] for i in range(n_rows)], dtype=object)
    actions = cfg.get("actions", ACTIONS)
    esc = X["escalated"] > 0.5
    action = np.array([("video" if esc[i] else actions["no_data"] if (band[i] is None or provisional[i]) else actions[band[i]]) for i in range(n_rows)], dtype=object)
    return {"score": np.where(rejected, NAN, sc), "band": band, "action": action, "provisional": (provisional & ~rejected).astype(bool),
            "flags": shell["flags"], "adj_rating": base["adj_rating"], "adj_approval": base["adj_approval"], "components": F, "p": p}


def score_any(X, cfg):
    return score_logistic(X, cfg) if cfg.get("model") == "logistic" else score_points(X, cfg)


# ------------------------------------------------------------------ fitting helpers
def base_config(name):
    cfg = copy.deepcopy(MANAGER_ORIGINAL)
    cfg["name"] = name
    cfg["rating"].update({"mode": "knee", "floor": 3.55, "line": LINE, "line_value": 75})
    cfg["approval"].update({"mode": "graded", "floor": 40, "bar": BAR})
    cfg["sample"]["mode"] = "off"
    cfg["reach"]["mode"] = "off"
    cfg["track"].update({"mode": "on", "floor": 4.05, "line": LINE, "min_classes": 3})
    cfg["weights"] = {"rating": 60, "approval": 25, "sample": 0, "reach": 0, "track": 15}
    cfg["guard"] = {"k": 0, "prior": "course"}
    cfg["min_votes"] = {"band": 3, "action": 5}
    cfg["caps"] = {"rating_line": LINE, "approval_bar": BAR}
    cfg["missing"] = {"approval": "neutral", "reach": "neutral", "track": "neutral"}
    return cfg


def objective(res, df, targets=("t_a", "t_c")):
    """The pre-registered fitting objective: the mean AUC of (100 - score) for the two
    'next class goes wrong' targets, on rows where each target exists. NaN scores rank lowest."""
    sc = res["score"]
    vals = []
    for t in targets:
        m = df[t].notna().values
        if m.sum() < 30:
            continue
        s = np.where(np.isnan(sc[m]), 101.0, sc[m])
        vals.append(auc(-s, df[t].values[m]))
    return float(np.mean(vals)) if vals else float("nan")


WEIGHT_LIMITS = {"rating": (60, 75), "approval": (25, 40), "track": (0, 15), "module_delta": (0, 15), "attendance": (0, 15), "momentum": (0, 15)}


def fit_weights(df, X, cfg, keys, step=5, min_w=0, limits=WEIGHT_LIMITS):
    """Coordinate search over integer weights (step points) summing to 100 across `keys`,
    maximising the objective on the fit months. Starts from the config's weights. The limits
    are design rules a PM can state, the manager's own neighbourhood: the rating is 60-75 of the
    100 points, the vote 25-40, the instructor's record and any history input at most 15 each.
    The properties pin them: under 60 for the rating, a class on the 4.55 line with a bad record
    and no vote falls to Bad (P08); under 25 for the vote, the guard's pull on a thin rating can
    outweigh a 45-point vote gap (P19); over 15 for the record, a bad record sinks a plainly fine
    class (P16)."""
    cfg = copy.deepcopy(cfg)
    w = {k: float(cfg["weights"].get(k, 0)) for k in keys}
    tot = sum(w.values()) or 100.0
    w = {k: round(v / tot * 100 / step) * step for k, v in w.items()}
    diff = 100 - sum(w.values())
    w[keys[0]] += diff
    for k in keys:                                   # pull the start inside the limits
        lo_, hi_ = limits.get(k, (0, 100))
        if w[k] > hi_:
            w["rating"] += w[k] - hi_
            w[k] = hi_
        elif w[k] < lo_:
            w["rating"] -= lo_ - w[k]
            w[k] = lo_

    def val(wd):
        c = copy.deepcopy(cfg)
        c["weights"].update(wd)
        return objective(score_any(X, c), df)
    best = val(w)
    improved = True
    while improved:
        improved = False
        for src in keys:
            for dst in keys:
                if src == dst or w[src] - step < min_w:
                    continue
                cand = dict(w)
                cand[src] -= step
                cand[dst] += step
                if any(not (limits.get(k, (0, 100))[0] <= cand[k] <= limits.get(k, (0, 100))[1]) for k in keys):
                    continue
                v = val(cand)
                if v > best + 1e-6:
                    best, w, improved = v, cand, True
    cfg["weights"].update(w)
    return cfg, best


def fit_bands_for_workload(df, X, cfg, weeks, capacity=12.0, videos=5.0):
    """Lower the Average and Bad edges on the fit months if that is what it takes for the queue
    to fit the capacity: at most `videos` a week in Bad and `capacity` analyses a week in all.
    The capacity is a ceiling, never a target: an edge only ever moves DOWN from the round
    number (an edge is never raised to fill spare capacity). The Excellent edge is untouched -
    it changes no work. Classes forced by the hard lines are counted first; if they alone exceed
    the capacity no edge can fix it and the config is returned unchanged."""
    cfg = copy.deepcopy(cfg)
    res = score_any(X, cfg)
    sc = res["score"]
    firm = np.array([b is not None for b in res["band"]]) & (~res["provisional"]) & ~np.isnan(sc)
    lines = np.array([("under_rating_line" in f) or ("under_approval_bar" in f) for f in res["flags"]]) & firm
    forced_video = np.array([("under_rating_line" in f) and ("under_approval_bar" in f) for f in res["flags"]]) & firm
    free = firm & ~lines
    order = np.sort(sc[free])
    b = cfg["bands"]

    def edge_for(budget_per_week, base_count, round_edge):
        room = int(max(0, budget_per_week * weeks - base_count))
        if len(order) == 0:
            return round_edge
        if room >= len(order):
            return round_edge
        # the score at which `room` free classes sit below: the largest edge that respects the budget
        return float(min(round_edge, np.floor(order[room])))
    e_bad = edge_for(videos, int(forced_video.sum()), float(b["average"]))
    e_avg = edge_for(capacity, int(lines.sum()), float(b["good"]))
    b["average"] = float(max(0.0, min(e_bad, e_avg - 5.0)))
    b["good"] = float(max(b["average"] + 5.0, min(e_avg, float(b["excellent"]) - 5.0)))
    return cfg


# ------------------------------------------------------------------ the families
class Family:
    key = ""
    name = ""
    inputs = ()

    def sentence(self, cfg):
        return ""

    def fit(self, df, X, trust):
        raise NotImplementedError

    def contract_shape(self, cfg):
        """(fits the contract as-is, list of new keys the contract would need)."""
        needs = []
        if cfg.get("model") == "logistic":
            return False, ["a logistic model (new shape)"]
        g = cfg.get("guard", {})
        if g.get("prior", "course") != "course":
            needs.append("guard.prior = %s" % g["prior"])
        if g.get("k_approval") is not None and float(g["k_approval"]) != float(g.get("k") or 0):
            needs.append("guard.k_approval")
        if g.get("k_low") is not None or g.get("k_high") is not None:
            needs.append("guard.k_low / k_high")
        if cfg["approval"]["mode"] == "wilson":
            needs.append("approval.mode = wilson")
        if cfg["track"]["mode"] == "ewma":
            needs.append("track.mode = ewma")
        if cfg["caps"].get("basis", "guarded") != "guarded":
            needs.append("caps.basis = raw")
        for k, w in cfg["weights"].items():
            if k in ("module_delta", "attendance", "momentum") and w:
                needs.append("component %s" % k)
        return (not needs), needs


class Original(Family):
    key, name = "C0", "Manager's original (60/30/6/4, pass/fail)"
    inputs = ("rating", "approval", "responses", "reach")

    def sentence(self, cfg):
        return "Rating out of 60, 30 points if 80% would have the instructor back, 6 if ten or more rated, up to 4 for the share of the room that rated."

    def fit(self, df, X, trust):
        return copy.deepcopy(CONFIGS["C0"])


class TodayV7(Family):
    key, name = "v7", "Today's active version (two lines + graded score, guard off)"
    inputs = ("rating", "approval", "track record")

    def sentence(self, cfg):
        return "Rating out of 60 (steeper below 4.55), approval out of 25 (gradual from 40% to 80%), the instructor's record out of 15; under 4.55 or under 80% caps the band at Average, both at Bad; a band needs 3 votes, an analysis 6."

    def fit(self, df, X, trust):
        path = os.path.join(OUT, "recommended_config.json")
        cfg = read_json(path) if os.path.exists(path) else copy.deepcopy(CONFIGS["C5"])
        cfg.pop("note", None)
        return cfg


class C5Guarded(Family):
    key, name = "C5", "C5 as studied (guard k=5 on the course prior, lines read on the guarded values)"
    inputs = ("rating", "approval", "track record", "course prior")

    def sentence(self, cfg):
        return "As today's version, but thin votes are blended with five typical votes for the course before the lines are read."

    def fit(self, df, X, trust):
        return copy.deepcopy(CONFIGS["C5"])


class Points(Family):
    """Weighted points with the trust machinery: shrinkage toward a prior with the data-derived
    k, vote floors, the lines read on the raw values; weights refitted; optional extras."""
    key, name = "P", "Weighted points + trust"
    inputs = ("rating", "approval", "track record", "prior (module, else course)")

    def __init__(self, prior="hierarchical", extras=(), k_mode="data", caps=True, caps_basis="raw", track_mode="on",
                 approval_mode="graded", asym=False, rating_mode="knee", refit_weights=True, key=None, name=None, weights=None,
                 min_action=5, workload_bands=False):
        self.prior, self.extras, self.k_mode, self.caps, self.caps_basis = prior, tuple(extras), k_mode, caps, caps_basis
        self.track_mode, self.approval_mode, self.asym, self.rating_mode = track_mode, approval_mode, asym, rating_mode
        self.refit_weights, self.weights0, self.min_action, self.workload_bands = refit_weights, weights, min_action, workload_bands
        if key:
            self.key = key
        if name:
            self.name = name
        self.inputs = tuple(["rating", "approval"] + (["track record"] if track_mode != "off" else []) + list(extras))

    def sentence(self, cfg):
        w = cfg["weights"]
        parts = ["rating out of %d" % w["rating"], "approval out of %d" % w["approval"]]
        if w.get("track"):
            parts.append("the instructor's %s out of %d" % ("recent record" if cfg["track"]["mode"] == "ewma" else "record", w["track"]))
        for k, label in (("module_delta", "how the class compares with its module"), ("attendance", "attendance against the previous class"), ("momentum", "the cohort's previous class")):
            if w.get(k):
                parts.append("%s out of %d" % (label, w[k]))
        g = cfg["guard"]
        trust = ""
        if g.get("k"):
            trust = "; with few raters the numbers are blended with about %g typical classes of the %s first" % (round(float(g["k"]), 1), {"hierarchical": "module (or course)", "course": "course", "module": "module", "instructor": "instructor"}[g.get("prior", "course")])
        caps = "; under 4.55 or under 80% caps the band at Average, both at Bad" if cfg["caps"].get("rating_line") is not None else ""
        return "%s%s%s; a band needs %d votes, an analysis %d." % (", ".join(parts).capitalize(), trust, caps, cfg["min_votes"]["band"], cfg["min_votes"]["action"])

    def fit(self, df, X, trust):
        cfg = base_config(self.name)
        cfg["rating"]["mode"] = self.rating_mode
        cfg["approval"]["mode"] = self.approval_mode
        cfg["track"]["mode"] = self.track_mode
        cfg["min_votes"] = {"band": 3, "action": self.min_action}
        k_src = {"hierarchical": "module_prior_rating", "module": "module_prior_rating", "course": "course_prior_rating", "instructor": "track_mean"}[self.prior]
        k = float(trust["variance"][k_src]["fit"]["k"]) if self.k_mode == "data" else float(self.k_mode)
        cfg["guard"] = {"k": round(k, 1), "prior": self.prior, "k_approval": round(float(trust["approval_prior"]["fit"]["a_plus_b"]), 1)}
        if self.prior == "hierarchical":
            cfg["guard"]["prior_min_n"] = 3
        if self.asym:
            cfg["guard"]["k_low"] = round(k * 2, 1)
            cfg["guard"]["k_high"] = round(k / 2, 1)
        if not self.caps:
            cfg["caps"] = {"rating_line": None, "approval_bar": None}
        elif self.caps_basis != "guarded":
            cfg["caps"]["basis"] = self.caps_basis
        cfg["extras"] = {}
        for e in self.extras:
            cfg["extras"][e] = {"module_delta": {"floor": -0.4, "ceiling": 0.1, "min_n": 3}, "attendance": {"floor": 0.5, "ceiling": 1.0},
                                "momentum": {"floor": 4.05, "ceiling": LINE}}[e]
            cfg["weights"][e] = 10
        if self.weights0:
            cfg["weights"].update(self.weights0)
        keys = ["rating", "approval"] + (["track"] if self.track_mode != "off" else []) + list(self.extras)
        if self.refit_weights:
            cfg, _ = fit_weights(df, X, cfg, keys)
        if self.workload_bands:
            from common import weeks_in
            cfg = fit_bands_for_workload(df, X, cfg, weeks_in(sorted(set(int(m) for m in df["month"]))))
        return cfg


class Logistic(Family):
    key, name = "L", "Monotone logistic (100 minus the chance the next class goes wrong)"

    def __init__(self, inputs=("rating", "approval", "track"), key=None, name=None, guard=True, workload_bands=True):
        self.use = tuple(inputs)
        self.inputs = tuple(inputs)
        self.guard = guard
        self.workload_bands = workload_bands
        if key:
            self.key = key
        if name:
            self.name = name

    def sentence(self, cfg):
        return ("The score is 100 minus the chance (in %%) that the next class goes wrong, estimated from %s; the two lines and the vote floors apply as today. "
                "A PM can read the weights but cannot work the number out by hand." % ", ".join(cfg["inputs"]))

    def fit(self, df, X, trust):
        from scipy.optimize import minimize
        cfg = {"model": "logistic", "name": self.name, "inputs": list(self.use),
               "guard": {"k": round(float(trust["variance"]["module_prior_rating"]["fit"]["k"]), 1), "prior": "hierarchical", "prior_min_n": 3,
                         "k_approval": round(float(trust["approval_prior"]["fit"]["a_plus_b"]), 1)} if self.guard else {"k": 0, "prior": "course"},
               "centre": {}, "spread": {}, "coef": {}, "intercept": 0.0,
               "min_votes": {"band": 3, "action": 5}, "caps": {"rating_line": LINE, "approval_bar": BAR, "basis": "raw"},
               "bands": {"excellent": 90, "good": 75, "average": 60}, "actions": dict(ACTIONS)}
        # centres and spreads from the fit months (raw values)
        raw, _ = _logit_raw(X, cfg)
        for k in self.use:
            v = raw[k].astype(float)
            v = v[~np.isnan(v)]
            cfg["centre"][k] = float(np.median(v)) if len(v) else 0.0
            cfg["spread"][k] = float(max(np.std(v), 1e-3)) if len(v) else 1.0
        F, _ = _logit_features(X, cfg)
        y = np.where(df["t_a"].notna().values, df["t_a"].values, np.nan).astype(float)
        yc = df["t_c"].values.astype(float)
        y = np.where(np.isnan(y), yc, np.fmax(y, np.where(np.isnan(yc), 0, yc)))
        m = ~np.isnan(y)
        Z = np.column_stack([F[k][m] for k in self.use])
        yy = y[m]

        def nll(theta):
            b0, b = theta[0], theta[1:]
            eta = b0 + Z @ b
            ll = yy * eta - np.logaddexp(0, eta)
            return -ll.sum() / len(yy) + 0.01 * float(b @ b)
        bounds = [(None, None)] + [(None, 0.0) for _ in self.use]     # safer inputs lower the chance of trouble
        r = minimize(nll, np.zeros(len(self.use) + 1), bounds=bounds, method="L-BFGS-B")
        cfg["intercept"] = float(r.x[0])
        cfg["coef"] = {k: float(v) for k, v in zip(self.use, r.x[1:])}
        if self.workload_bands:
            from common import weeks_in
            cfg = fit_bands_for_workload(df, X, cfg, weeks_in(sorted(set(int(m) for m in df["month"]))))
        return cfg


class Sequential(Points):
    """The instructor's series: recency-weighted record (EWMA) and shrinkage toward it."""
    key, name = "S", "Sequential: recent record + shrinkage toward the instructor's own record"

    def __init__(self, **kw):
        kw.setdefault("prior", "instructor")
        kw.setdefault("track_mode", "ewma")
        super().__init__(**kw)


FAMILIES = {
    "C0": Original(), "v7": TodayV7(), "C5": C5Guarded(),
    "P": Points(key="P", name="Weighted points + trust (module prior, data k, raw lines)"),
    "B": Points(key="B", name="Bayesian: shrunk rating + beta-posterior vote + points", prior="hierarchical", approval_mode="graded"),
    "L": Logistic(),
    "S": Sequential(key="S"),
}


def describe(cfg):
    if cfg.get("model") == "logistic":
        return "logistic on %s; coef %s; bands %g/%g/%g" % (", ".join(cfg["inputs"]), {k: round(v, 2) for k, v in cfg["coef"].items()},
                                                            cfg["bands"]["excellent"], cfg["bands"]["good"], cfg["bands"]["average"])
    w = cfg["weights"]
    g = cfg["guard"]
    bits = ["rating %s" % ("knee" if cfg["rating"]["mode"] == "knee" else "linear"), "approval %s" % cfg["approval"]["mode"],
            "track %s" % cfg["track"]["mode"], "weights " + "/".join("%s %g" % (k, v) for k, v in w.items() if v),
            "guard k=%g%s prior=%s%s" % (g.get("k") or 0, (" k_a=%g" % g["k_approval"]) if g.get("k_approval") is not None else "", g.get("prior", "course"),
                                         (" asym %g/%g" % (g["k_low"], g["k_high"])) if g.get("k_low") is not None else ""),
            "lines %s" % ("off" if cfg["caps"].get("rating_line") is None else cfg["caps"].get("basis", "guarded")),
            "votes %d/%d" % (cfg["min_votes"]["band"], cfg["min_votes"]["action"]),
            "bands %g/%g/%g" % (cfg["bands"]["excellent"], cfg["bands"]["good"], cfg["bands"]["average"])]
    return "; ".join(bits)


if __name__ == "__main__":
    from features import load_features
    df = load_features()
    X = inputs_from_df(df)
    for key in ("C0", "C5"):
        print(key, "contract mismatches:", verify_against_contract(CONFIGS[key], X))
    v7 = TodayV7().fit(df, X, None)
    print("v7 contract mismatches:", verify_against_contract(v7, X))
    res = score_points(X, v7)
    agree = np.mean([(a == b) for a, b in zip(res["band"], df["v7_band"].where(df["v7_band"].notna(), None))])
    print("v7 band agreement with the database's stored bands: %.3f" % agree)
