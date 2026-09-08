"""Step 4b - the properties: the expected behaviour of a formula on every case, written as
principles, not numbers. A family that violates a property is out - unless the property is wrong,
and then the study says so (see P12's note on head-count).

Each property is a function over (scorer, cases) returning {passed, violations, examples, note}.
The scorer is any callable X -> result (families.score_any with a config bound).

Run:  python analysis/formula/properties.py [--full]   -> analysis/out/formula_properties.json
      python -m unittest analysis.formula.test_properties
"""
from __future__ import annotations

import copy
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import OUT, BANDS, BAND_RANK, LINE, BAR, write_json, read_json, spearman  # noqa: E402
from families import inputs_from_cases, score_any, perturb, FAMILIES, describe, _prior_arrays  # noqa: E402
from cases import load_cases  # noqa: E402

NAN = float("nan")
ONE_VOTE_MAX_POINTS = 8.0          # one vote out of 20 may move the score by at most this
MISSING_VOTE_TOLERANCE = 5.0       # a missing vote may cost at most this against a vote exactly at the bar


def _rank(b):
    return -1 if b is None else BAND_RANK[b]


def _examples(cases, idx, res, res2=None, limit=3):
    out = []
    for i in list(idx)[:limit]:
        e = {"id": cases[i]["id"], "label": cases[i]["label"], "score": None if np.isnan(res["score"][i]) else float(res["score"][i]),
             "band": res["band"][i], "action": res["action"][i]}
        if res2 is not None:
            e["after"] = {"score": None if np.isnan(res2["score"][i]) else float(res2["score"][i]), "band": res2["band"][i], "action": res2["action"][i]}
        out.append(e)
    return out


def _with(X, **changes):
    P = {k: v.copy() for k, v in X.items()}
    for k, v in changes.items():
        P[k] = v if isinstance(v, np.ndarray) else np.full(len(P["rating"]), NAN if v is None else float(v))
    return P


PROPERTIES = {}


def prop(pid, name, families="all"):
    def deco(fn):
        PROPERTIES[pid] = {"id": pid, "name": name, "fn": fn}
        return fn
    return deco


@prop("P01", "Bounded: every score is between 0 and 100 (or there is no score), every band is one of the four (or none)")
def p01(scorer, X, cases, cfg):
    r = scorer(X)
    sc = r["score"]
    bad = np.flatnonzero((~np.isnan(sc)) & ((sc < 0) | (sc > 100)))
    bad_b = [i for i, b in enumerate(r["band"]) if b is not None and b not in BANDS]
    idx = sorted(set(bad.tolist()) | set(bad_b))
    return {"violations": len(idx), "examples": _examples(cases, idx, r)}


@prop("P02", "A higher rating never lowers the score (everything else equal)")
def p02(scorer, X, cases, cfg):
    r = scorer(X)
    up = _with(X, rating=np.minimum(5.0, X["rating"] + 0.1))
    r2 = scorer(up)
    ok = ~np.isnan(r["score"]) & ~np.isnan(r2["score"])
    idx = np.flatnonzero(ok & (r2["score"] < r["score"] - 1e-9))
    return {"violations": int(len(idx)), "examples": _examples(cases, idx, r, r2)}


@prop("P03", "One yes turned into a no never raises the score; a no turned into a yes never lowers it")
def p03(scorer, X, cases, cfg):
    r = scorer(X)
    r2 = scorer(perturb(X, "yes_to_no"))
    ok = ~np.isnan(r["score"]) & ~np.isnan(r2["score"])
    idx = np.flatnonzero(ok & (r2["score"] > r["score"] + 1e-9))
    P = {k: v.copy() for k, v in X.items()}
    m = P["no_votes"] >= 1
    P["no_votes"][m] -= 1
    P["yes_votes"][m] += 1
    r3 = scorer(P)
    ok3 = ~np.isnan(r["score"]) & ~np.isnan(r3["score"])
    idx3 = np.flatnonzero(ok3 & (r3["score"] < r["score"] - 1e-9))
    idx_all = sorted(set(idx.tolist()) | set(idx3.tolist()))
    return {"violations": len(idx_all), "examples": _examples(cases, idx_all, r, r2)}


@prop("P04", "Irrelevant inputs change nothing: the kind of session, the region, the weekday, and the size of the room when there is no history to compare it with")
def p04(scorer, X, cases, cfg):
    r = scorer(X)
    # attended matters only through reach (a points input the study rejects) or attendance change (history); with att_vs_prev missing it must not matter
    P = _with(X, att_vs_prev=None)
    base = scorer(P)
    big = _with(P, attended=np.where(np.isnan(X["attended"]), NAN, np.maximum(X["attended"] * 10, X["num_ratings"])))
    r2 = scorer(big)
    ok = ~np.isnan(base["score"]) & ~np.isnan(r2["score"])
    idx = np.flatnonzero(ok & (np.abs(r2["score"] - base["score"]) > 1e-9))
    # kind/region/weekday are not scorer inputs at all: assert by construction (the scorer never reads them)
    return {"violations": int(len(idx)), "examples": _examples(cases, idx, base, r2),
            "note": "kind, region and weekday are not inputs of any family; the room size is tested with the attendance history removed"}


@prop("P05", "Under both human lines with 10+ votes can never be Good or Excellent")
def p05(scorer, X, cases, cfg):
    r = scorer(X)
    votes = X["yes_votes"] + X["no_votes"]
    appr = X["yes_votes"] / np.where(votes > 0, votes, 1) * 100
    m = (votes >= 10) & (X["rating"] < LINE) & (appr < BAR)
    idx = [i for i in np.flatnonzero(m) if r["band"][i] in ("good", "excellent")]
    return {"violations": len(idx), "examples": _examples(cases, idx, r)}


@prop("P06", "Under one human line with 10+ votes can never be Excellent")
def p06(scorer, X, cases, cfg):
    r = scorer(X)
    votes = X["yes_votes"] + X["no_votes"]
    appr = X["yes_votes"] / np.where(votes > 0, votes, 1) * 100
    m = (votes >= 10) & ((X["rating"] < LINE) | (appr < BAR))
    idx = [i for i in np.flatnonzero(m) if r["band"][i] == "excellent"]
    return {"violations": len(idx), "examples": _examples(cases, idx, r)}


@prop("P07", "One vote out of 20 (or more) moves the score by at most 8 points, and the band by at most one step unless a hard line is crossed")
def p07(scorer, X, cases, cfg):
    r = scorer(X)
    votes = X["yes_votes"] + X["no_votes"]
    m = votes >= 20
    idx, crossings, tested = [], 0, 0
    for how in ("yes_to_no", "one_point_less"):
        r2 = scorer(perturb(X, how))
        ok = m & ~np.isnan(r["score"]) & ~np.isnan(r2["score"])
        d = np.abs(r2["score"] - r["score"])
        bad = np.flatnonzero(ok & (d > ONE_VOTE_MAX_POINTS))
        idx += bad.tolist()
        for i in np.flatnonzero(ok):
            tested += 1
            if r["band"][i] is None or r2["band"][i] is None:
                continue
            crossed = any(f in r2["flags"][i] and f not in r["flags"][i] for f in ("under_rating_line", "under_approval_bar"))
            if abs(_rank(r["band"][i]) - _rank(r2["band"][i])) > 1:
                if crossed:
                    crossings += 1
                else:
                    idx.append(int(i))
    idx = sorted(set(idx))
    return {"violations": len(idx), "examples": _examples(cases, idx, r),
            "note": "%d of %d one-vote moves at 20+ votes jumped two bands across a hard line (the line, not the score, decided) - reported, not a violation" % (crossings, tested)}


@prop("P08", "A missing vote is not a failed vote: with no vote the class never lands in a worse band than with everyone saying no, scores no higher than with everyone saying yes, and a class rated 4.55+ with no vote is never Bad")
def p08(scorer, X, cases, cfg):
    n = np.where(np.isnan(X["num_ratings"]), 10.0, np.maximum(X["num_ratings"], 5.0))
    r_nv = scorer(_with(X, yes_votes=None, no_votes=None, num_ratings=n))
    r_no = scorer(_with(X, yes_votes=0.0, no_votes=n, num_ratings=n))
    r_yes = scorer(_with(X, yes_votes=n, no_votes=0.0, num_ratings=n))
    ok = ~np.isnan(r_nv["score"]) & ~np.isnan(r_no["score"]) & ~np.isnan(r_yes["score"]) & (r_yes["score"] > r_no["score"] + 1e-9)
    worse_band = np.array([_rank(r_nv["band"][i]) > _rank(r_no["band"][i]) and r_nv["band"][i] is not None for i in range(len(cases))])
    treated_as_failed = ((r_nv["score"] <= r_no["score"] + 1e-9) & (r_nv["score"] > 0) & worse_band) | (r_nv["score"] < r_no["score"] - 1e-9) & worse_band
    idx = np.flatnonzero(ok & (treated_as_failed | (r_nv["score"] > r_yes["score"] + 1.0))).tolist()
    idx += [i for i in range(len(cases)) if X["rating"][i] >= LINE and r_nv["band"][i] == "bad" and not (X["escalated"][i] > 0.5)]
    idx = sorted(set(idx))
    return {"violations": len(idx), "examples": _examples(cases, idx, r_nv, r_no)}


@prop("P09", "Vote floors: under 3 voices no firm band; under the analysis floor never an analysis; nobody attended or nobody rated is a watch")
def p09(scorer, X, cases, cfg):
    r = scorer(X)
    votes = np.where(np.isnan(X["yes_votes"]) | np.isnan(X["no_votes"]), 0, X["yes_votes"] + X["no_votes"])
    voices = np.where(votes > 0, votes, np.where(np.isnan(X["num_ratings"]), 0, X["num_ratings"]))
    idx = []
    for i in range(len(cases)):
        if X["escalated"][i] > 0.5:
            continue
        if voices[i] < 3 and r["band"][i] is not None and not r["provisional"][i]:
            idx.append(i)
        if voices[i] < 5 and r["action"][i] in ("video", "transcript"):
            idx.append(i)
        if (voices[i] == 0 or (not np.isnan(X["attended"][i]) and X["attended"][i] == 0)) and r["action"][i] != "watch":
            idx.append(i)
    idx = sorted(set(idx))
    return {"violations": len(idx), "examples": _examples(cases, idx, r)}


@prop("P10", "Nonsense is rejected: a negative count, a rating over 5, a rating of 0 or a missing rating gives no score and a watch")
def p10(scorer, X, cases, cfg):
    r = scorer(X)
    bad = np.zeros(len(cases), bool)
    for k in ("num_ratings", "attended", "yes_votes", "no_votes"):
        bad |= (~np.isnan(X[k])) & (X[k] < 0)
    bad |= np.isnan(X["rating"]) | (X["rating"] <= 0) | (X["rating"] > 5)
    idx = [i for i in np.flatnonzero(bad) if not np.isnan(r["score"][i]) or r["band"][i] is not None or (r["action"][i] != "watch" and X["escalated"][i] < 0.5)]
    return {"violations": len(idx), "examples": _examples(cases, idx, r)}


@prop("P11", "An escalated class is always a video analysis")
def p11(scorer, X, cases, cfg):
    P = _with(X, escalated=1.0)
    r = scorer(P)
    idx = [i for i in range(len(cases)) if r["action"][i] != "video"]
    return {"violations": len(idx), "examples": _examples(cases, idx, r)}


@prop("P12", "Head-count is trust, not points: at the same rating and vote, more raters only move the score toward the class's own numbers (up when the class sits above its prior, down when below), never the other way")
def p12(scorer, X, cases, cfg):
    votes = X["yes_votes"] + X["no_votes"]
    r_lo = scorer(_with(X, num_ratings=votes, attended=np.maximum(X["attended"], votes)))
    r_hi = scorer(_with(X, num_ratings=votes * 5, yes_votes=X["yes_votes"] * 5, no_votes=X["no_votes"] * 5, attended=np.maximum(X["attended"], votes * 5)))
    prior, pa = _prior_arrays(X, cfg)
    ap = _appr(X) * 100
    has_prior = ~np.isnan(prior) & ~np.isnan(pa)
    above = has_prior & (X["rating"] > prior) & (ap > pa)
    below = has_prior & (X["rating"] < prior) & (ap < pa)
    ok = ~np.isnan(r_lo["score"]) & ~np.isnan(r_hi["score"]) & ~np.isnan(ap) & (votes >= 1)
    idx = np.flatnonzero(ok & ((above & (r_hi["score"] < r_lo["score"] - 0.05)) | (below & (r_hi["score"] > r_lo["score"] + 0.05))))
    return {"violations": int(len(idx)), "examples": _examples(cases, idx, r_lo, r_hi),
            "note": "The manager's 'responses' points (6 at 10+ raters) fail this by design: they reward head-count itself. "
                    "The literal reading 'more raters never lower the score' is wrong for a class below its prior - more raters "
                    "are more evidence that the class really was low. A Wilson lower bound fails it too: it treats a thin vote as a bad vote."}


def _appr(X):
    votes = X["yes_votes"] + X["no_votes"]
    return np.where(votes > 0, X["yes_votes"] / np.where(votes > 0, votes, 1), NAN)


@prop("P13", "No false alarm on a plainly fine class: rated 4.7+ with 90%+ approval and 10+ votes is never Bad; rated 4.9 with 100% is never below Good")
def p13(scorer, X, cases, cfg):
    r = scorer(X)
    votes = X["yes_votes"] + X["no_votes"]
    appr = _appr(X) * 100
    m1 = (votes >= 10) & (X["rating"] >= 4.7) & (appr >= 90) & (X["escalated"] < 0.5)
    idx = [i for i in np.flatnonzero(m1) if r["band"][i] == "bad"]
    m2 = (votes >= 10) & (X["rating"] >= 4.9) & (appr >= 100)
    idx += [i for i in np.flatnonzero(m2) if r["band"][i] in ("bad", "average")]
    idx = sorted(set(idx))
    return {"violations": len(idx), "examples": _examples(cases, idx, r)}


@prop("P14", "Grade inflation (+0.2 on every rating, priors included) keeps the order of classes")
def p14(scorer, X, cases, cfg):
    r = scorer(X)
    P = {k: v.copy() for k, v in X.items()}
    for k in ("rating", "track_avg", "track_ewma", "prior_rating", "module_prior_rating", "prev_rating"):
        P[k] = np.minimum(5.0, P[k] + 0.2)
    r2 = scorer(P)
    ok = ~np.isnan(r["score"]) & ~np.isnan(r2["score"])
    rho = spearman(r["score"][ok], r2["score"][ok])
    flagged = np.mean([a in ("video", "transcript") for a in r["action"][ok]]) if ok.any() else 0
    flagged2 = np.mean([a in ("video", "transcript") for a in r2["action"][ok]]) if ok.any() else 0
    # order violations: pairs where the inflated order reverses; approximate by counting classes whose rank moves > 5% of n
    from scipy.stats import rankdata
    ra, rb = rankdata(r["score"][ok]), rankdata(r2["score"][ok])
    moved = np.flatnonzero(np.abs(ra - rb) > 0.05 * ok.sum())
    return {"violations": int(len(moved)) if rho < 0.98 else 0, "examples": _examples(cases, np.flatnonzero(ok)[moved], r, r2),
            "note": "rank correlation %.4f; share flagged for analysis %.1f%% -> %.1f%% after inflation (an alarm to watch, not a violation)" % (rho, flagged * 100, flagged2 * 100)}


@prop("P15", "No history is never worse than the worst history: a first class (no record) never lands in a worse band than the same class with a record at the floor; a brand-new course (no prior) is still scored")
def p15(scorer, X, cases, cfg):
    r_none = scorer(_with(X, track_avg=None, track_ewma=None, track_n=0.0))
    r_floor = scorer(_with(X, track_avg=4.05, track_ewma=4.05, track_n=6.0))
    ok = ~np.isnan(r_none["score"]) & ~np.isnan(r_floor["score"])
    worse_band = np.array([_rank(r_none["band"][i]) > _rank(r_floor["band"][i]) and r_none["band"][i] is not None for i in range(len(cases))])
    idx = np.flatnonzero(ok & (r_none["score"] < r_floor["score"] - 1e-9) & worse_band).tolist()
    r_np = scorer(_with(X, prior_rating=None, prior_approval=None, module_prior_rating=None, module_prior_n=0.0, module_prior_approval=None))
    r0 = scorer(X)
    idx += [i for i in range(len(cases)) if np.isnan(r_np["score"][i]) and not np.isnan(r0["score"][i])]
    idx = sorted(set(idx))
    return {"violations": len(idx), "examples": _examples(cases, idx, r_none, r_floor)}


TYPICAL_PRIORS = dict(prior_rating=4.70, prior_approval=93.0, module_prior_rating=4.70, module_prior_n=10.0, module_prior_approval=93.0, att_vs_prev=None, prev_rating=None)


@prop("P16", "A bad record alone cannot sink a plainly fine class (4.8, 15 of 15, a typical module) below Good")
def p16(scorer, X, cases, cfg):
    P = _with(X, rating=4.8, num_ratings=15.0, yes_votes=15.0, no_votes=0.0, attended=np.maximum(np.where(np.isnan(X["attended"]), 20, X["attended"]), 15),
              track_avg=4.0, track_ewma=4.0, track_n=10.0, escalated=0.0, **TYPICAL_PRIORS)
    r = scorer(P)
    idx = [i for i in range(len(cases)) if r["band"][i] in ("average", "bad")]
    return {"violations": len(idx), "examples": _examples(cases, idx, r)}


@prop("P23", "A low prior alone cannot sink a plainly fine class (4.8, 15 of 15, no record) below Good, even in a module usually rated 4.0")
def p23(scorer, X, cases, cfg):
    P = _with(X, rating=4.8, num_ratings=15.0, yes_votes=15.0, no_votes=0.0, attended=np.maximum(np.where(np.isnan(X["attended"]), 20, X["attended"]), 15),
              track_avg=None, track_ewma=None, track_n=0.0, escalated=0.0, prior_rating=4.0, prior_approval=80.0, module_prior_rating=4.0, module_prior_n=20.0,
              module_prior_approval=80.0, att_vs_prev=None, prev_rating=None)
    r = scorer(P)
    idx = [i for i in range(len(cases)) if r["band"][i] in ("average", "bad")]
    return {"violations": len(idx), "examples": _examples(cases, idx, r),
            "note": "two bad histories together (a 4.0 module AND a 4.0 record) may put such a class in Average - a transcript read - and the study accepts that"}


@prop("P17", "A tiny cohort of 5 with one no (4.8, 4 of 5) is never Bad and never a video")
def p17(scorer, X, cases, cfg):
    P = _with(X, rating=4.8, num_ratings=5.0, attended=5.0, yes_votes=4.0, no_votes=1.0, escalated=0.0)
    r = scorer(P)
    idx = [i for i in range(len(cases)) if r["band"][i] == "bad" or r["action"][i] == "video"]
    return {"violations": len(idx), "examples": _examples(cases, idx, r)}


@prop("P18", "An attendance collapse on a fine class (4.8, 12 of 12, a third of the previous room) is never Bad")
def p18(scorer, X, cases, cfg):
    P = _with(X, rating=4.8, num_ratings=12.0, attended=6.0, yes_votes=12.0, no_votes=0.0, att_vs_prev=0.3, escalated=0.0)
    r = scorer(P)
    idx = [i for i in range(len(cases)) if r["band"][i] == "bad"]
    return {"violations": len(idx), "examples": _examples(cases, idx, r)}


@prop("P19", "A 3.8 with half the room saying no scores lower than a 3.8 with 95% yes, and neither is Good or Excellent")
def p19(scorer, X, cases, cfg):
    A = _with(X, rating=3.8, num_ratings=10.0, attended=15.0, yes_votes=5.0, no_votes=5.0, escalated=0.0)
    B = _with(X, rating=3.8, num_ratings=20.0, attended=25.0, yes_votes=19.0, no_votes=1.0, escalated=0.0)
    ra, rb = scorer(A), scorer(B)
    idx = [i for i in range(len(cases)) if (ra["score"][i] >= rb["score"][i]) or ra["band"][i] in ("good", "excellent") or rb["band"][i] in ("good", "excellent")]
    return {"violations": len(idx), "examples": _examples(cases, idx, ra, rb)}


@prop("P20", "The worst class of a 4.9 course (4.6 with 12 of 12) clears both lines and is never Bad")
def p20(scorer, X, cases, cfg):
    P = _with(X, rating=4.6, num_ratings=12.0, attended=15.0, yes_votes=12.0, no_votes=0.0, escalated=0.0,
              module_prior_rating=4.9, module_prior_n=20.0, module_prior_approval=98.0, prior_rating=4.9, prior_approval=98.0, prev_rating=4.9)
    r = scorer(P)
    idx = [i for i in range(len(cases)) if r["band"][i] == "bad"]
    return {"violations": len(idx), "examples": _examples(cases, idx, r)}


@prop("P21", "Deterministic: the same inputs always give the same score")
def p21(scorer, X, cases, cfg):
    r1, r2 = scorer(X), scorer({k: v.copy() for k, v in X.items()})
    ok = ~(np.isnan(r1["score"]) & np.isnan(r2["score"]))
    idx = [i for i in np.flatnonzero(ok) if r1["score"][i] != r2["score"][i] or r1["band"][i] != r2["band"][i]]
    return {"violations": len(idx), "examples": _examples(cases, idx, r1, r2)}


@prop("P22", "The two lines are literal: a class under 4.55 (or under 80%) with 5+ votes is never Good or Excellent, whatever prior it is blended with")
def p22(scorer, X, cases, cfg):
    r = scorer(X)
    votes = X["yes_votes"] + X["no_votes"]
    appr = _appr(X) * 100
    m = (votes >= 5) & ((X["rating"] < LINE) | (appr < BAR))
    idx = [i for i in np.flatnonzero(m) if r["band"][i] in ("good", "excellent") and not r["provisional"][i]]
    return {"violations": len(idx), "examples": _examples(cases, idx, r)}


# ------------------------------------------------------------------ running
def run_properties(cfg, cases, X=None):
    X = inputs_from_cases(cases) if X is None else X
    scorer = lambda XX: score_any(XX, cfg)  # noqa: E731
    out = {}
    for pid, p in PROPERTIES.items():
        res = p["fn"](scorer, X, cases, cfg)
        res["passed"] = res["violations"] == 0
        out[pid] = {"name": p["name"], **res}
    return out


def summarise(props):
    return {"passed": sum(1 for p in props.values() if p["passed"]), "failed": [pid for pid, p in props.items() if not p["passed"]], "total": len(props)}


def main(full=False):
    t0 = time.time()
    cases, fx = load_cases(full_grid=full)
    X = inputs_from_cases(cases)
    from features import load_features
    df = load_features()
    from families import inputs_from_df
    Xdf = inputs_from_df(df[df["split"] == "fit"])
    trust = read_json(os.path.join(OUT, "formula_trust.json"))
    out = {"meta": {"cases": len(cases), "full_grid": full, "generated": time.strftime("%Y-%m-%d %H:%M")}, "properties": {pid: p["name"] for pid, p in PROPERTIES.items()}, "families": {}}
    for key, fam in FAMILIES.items():
        cfg = fam.fit(df[df["split"] == "fit"], Xdf, trust)
        props = run_properties(cfg, cases, X)
        s = summarise(props)
        out["families"][key] = {"name": fam.name, "config": cfg, "summary": s, "properties": props}
        print("%-4s %-70s %d/%d passed; failed: %s (%.0fs)" % (key, fam.name[:70], s["passed"], s["total"], ", ".join(s["failed"]) or "-", time.time() - t0))
        if "--examples" in sys.argv:
            for pid in s["failed"]:
                pr = props[pid]
                print("      %s x%d %s" % (pid, pr["violations"], pr.get("note", "")))
                for e in pr["examples"][:2]:
                    print("         ", e)
    write_json(os.path.join(OUT, "formula_properties.json"), out)


if __name__ == "__main__":
    main(full="--full" in sys.argv)
