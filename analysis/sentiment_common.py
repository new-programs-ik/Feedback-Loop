"""Shared machinery for the Class Sentiment Score validation (Feedback Loop v3).

One place for: the eight months of classes with everything the scorer needs attached (course
priors for the guard, the instructor's track record, the instructor's next class), the two
one-vote perturbations, the six yardsticks, the scorecard, the config builder used by the sweep,
and a fast scorer that reproduces analysis/sentiment_score.py exactly (verified, never trusted).

The contract (sentiment_score.py) is never modified here. Where the study needs speed, the fast
scorer precomputes the per-class components and is checked against the contract on every setting
that matters (see FastScorer.verify).
"""
from __future__ import annotations

import copy
import csv
import datetime as dt
import json
import math
import os
import statistics as st
import sys
from bisect import bisect_left
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ratings_data import load  # noqa: E402
from sentiment_score import CONFIGS, MANAGER_ORIGINAL, BANDS, BAND_RANK, score, round2  # noqa: E402
from instructor_names import propose_aliases  # noqa: E402

OUT = os.path.join(HERE, "out")
LO, HI = dt.datetime(2026, 1, 1), dt.datetime(2026, 8, 31, 23, 59, 59)
WEEKS = ((HI - LO).days + 1) / 7.0                      # 34.7 weeks
LINE, BAR, VOICES = 4.55, 80.0, 5                       # the two agreed lines and the voice floor
PRIOR_DAYS, PRIOR_MIN = 180, 10                         # the guard's course prior window
TRACK_MIN = 3                                           # earlier classes before a track record counts
CEILING = {"per_week": 12.0, "videos": 5.0}             # the team's capacity
COST = {"video": 0.70, "transcript": 0.51, "none": 0.0, "watch": 0.0}
BUCKETS = (("1-2", 1, 2), ("3-4", 3, 4), ("5-9", 5, 9), ("10-19", 10, 19), ("20+", 20, 10 ** 9))
SIZE_BUCKETS = (("<10", 0, 9), ("10-19", 10, 19), ("20-29", 20, 29), ("30+", 30, 10 ** 9))
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug")
BAND_LABEL = {"excellent": "Excellent", "good": "Good", "average": "Average", "bad": "Bad", None: "no band"}
# scorecard weights (plan 4f); each yardstick has two sub-marks worth the weight each -> 200 max
WEIGHTS = {"Y1": 25, "Y2": 20, "Y3": 20, "Y4": 15, "Y5": 15, "Y6": 5}


def bucket(v, table=BUCKETS):
    for name, lo, hi in table:
        if lo <= v <= hi:
            return name
    return table[0][0]


# ------------------------------------------------------------------ data with context
def load_rows(lo=LO, hi=HI):
    rows = load(lo, hi, strict=False)
    for i, r in enumerate(rows):
        r["id"] = i
        r["votes"] = (r["yes"] or 0) + (r["no"] or 0)
        r["month"] = r["date"].month
        r["weekday"] = WEEKDAYS[r["date"].weekday()]
        r["vote_bucket"] = bucket(r["votes"])
        r["size_bucket"] = bucket(r["attended"], SIZE_BUCKETS)
        r["instructor_raw"] = r["instructor"]
    return rows


def resolve_names(rows, alias=None, write=True):
    """Attach the resolved instructor name (aliases from instructor_names)."""
    if alias is None:
        alias = propose_aliases(rows, write=write)
    for r in rows:
        r["instructor_resolved"] = alias.get(r["instructor_raw"], r["instructor_raw"])
    return alias


def attach_priors(rows):
    """Course prior for the guard: the course's average rating and POOLED approval over the
    previous PRIOR_DAYS days (at least PRIOR_MIN classes), else the course over the whole window,
    else every class over the whole window."""
    by_course = defaultdict(list)
    for r in sorted(rows, key=lambda r: r["date"]):
        by_course[r["course"]].append(r)
    prefix = {}
    for c, lst in by_course.items():
        dates = [r["date"] for r in lst]
        cr, cy, cv = [0.0], [0.0], [0.0]
        for r in lst:
            cr.append(cr[-1] + r["rating"])
            cy.append(cy[-1] + r["yes"])
            cv.append(cv[-1] + r["votes"])
        prefix[c] = (dates, cr, cy, cv)
    all_r = st.mean(r["rating"] for r in rows)
    all_a = sum(r["yes"] for r in rows) / sum(r["votes"] for r in rows) * 100
    course_all = {}
    for c, lst in by_course.items():
        if len(lst) >= PRIOR_MIN:
            course_all[c] = (st.mean(r["rating"] for r in lst), sum(r["yes"] for r in lst) / sum(r["votes"] for r in lst) * 100)
    for r in rows:
        dates, cr, cy, cv = prefix[r["course"]]
        hi_i = bisect_left(dates, r["date"])
        lo_i = bisect_left(dates, r["date"] - dt.timedelta(days=PRIOR_DAYS))
        n = hi_i - lo_i
        if n >= PRIOR_MIN and (cv[hi_i] - cv[lo_i]) > 0:
            r["prior_rating"] = (cr[hi_i] - cr[lo_i]) / n
            r["prior_approval"] = (cy[hi_i] - cy[lo_i]) / (cv[hi_i] - cv[lo_i]) * 100
            r["prior_source"] = "course-180d"
        elif r["course"] in course_all:
            r["prior_rating"], r["prior_approval"] = course_all[r["course"]]
            r["prior_source"] = "course-all"
        else:
            r["prior_rating"], r["prior_approval"], r["prior_source"] = all_r, all_a, "all"
    return rows


def attach_track_and_next(rows, key="instructor_resolved"):
    """The instructor's average over >= TRACK_MIN EARLIER classes, and their next class."""
    ordered = sorted(rows, key=lambda r: (r["date"], r[key], r["topic"]))
    hist = defaultdict(list)
    for r in ordered:
        k = r[key]
        prev = hist[k] if k else []
        r["track_" + key] = st.mean(prev) if len(prev) >= TRACK_MIN else None
        r["track_n_" + key] = len(prev)
        if k:
            hist[k].append(r["rating"])
    nxt = {}
    for r in reversed(ordered):
        k = r[key]
        r["next_" + key] = nxt.get(k) if k else None
        if k:
            nxt[k] = r
    return rows


def pairs_for(rows, key="instructor_resolved", voices=VOICES):
    """(class, next class) pairs with >= voices votes on both sides - the Y3 population."""
    out = []
    for r in rows:
        n = r.get("next_" + key)
        if n is not None and r["votes"] >= voices and n["votes"] >= voices:
            out.append((r["id"], n["id"]))
    return out


def low_next(r):
    return r["rating"] < LINE or (r["approval"] is not None and r["approval"] < BAR)


def inputs_of(r, key="instructor_resolved"):
    return {"rating": r["rating"], "num_ratings": r["responses"], "attended": r["attended"],
            "yes_votes": r["yes"], "no_votes": r["no"], "escalated": False,
            "track_avg": r.get("track_" + key), "prior_rating": r["prior_rating"], "prior_approval": r["prior_approval"]}


def perturb_yes_to_no(inp):
    """One learner who said yes says no instead (only when someone said yes)."""
    if not inp["yes_votes"]:
        return inp
    p = dict(inp)
    p["yes_votes"], p["no_votes"] = inp["yes_votes"] - 1, inp["no_votes"] + 1
    return p


def perturb_rating(inp):
    """One rater gives one point less: the average drops by 1 / number of ratings."""
    n = inp["num_ratings"] or 0
    if n <= 0 or inp["rating"] is None:
        return inp
    p = dict(inp)
    p["rating"] = max(1.0, inp["rating"] - 1.0 / n)
    return p


class Study:
    """Everything loaded once: rows with context, aliases, next-class pairs, input variants."""

    def __init__(self, lo=LO, hi=HI, write_aliases=True):
        self.lo, self.hi = lo, hi
        self.weeks = ((hi - lo).days + 1) / 7.0
        self.rows = load_rows(lo, hi)
        self.alias = resolve_names(self.rows, write=write_aliases)
        attach_priors(self.rows)
        attach_track_and_next(self.rows, "instructor_resolved")
        attach_track_and_next(self.rows, "instructor_raw")
        self.pairs = {"resolved": pairs_for(self.rows, "instructor_resolved"), "raw": pairs_for(self.rows, "instructor_raw")}
        self.inputs = [inputs_of(r) for r in self.rows]
        self.inputs_yes = [perturb_yes_to_no(i) for i in self.inputs]
        self.inputs_rat = [perturb_rating(i) for i in self.inputs]

    def run_contract(self, cfg, variant="base"):
        src = {"base": self.inputs, "yes": self.inputs_yes, "rating": self.inputs_rat}[variant]
        return [score(i, cfg) for i in src]


# ------------------------------------------------------------------ the yardsticks
def _share(a, b):
    return a / b * 100 if b else 0.0


def standardised_share(rows, res, group_fn, band_set=("excellent",), width=0.1):
    """Excellent share (or any band set) per group at EQUAL rating: within 0.1-rating buckets,
    weighted by the pooled bucket mix (direct standardisation). Returns {group: share}."""
    banded = [(r, x) for r, x in zip(rows, res) if x["band"] is not None]
    buckets = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    total = Counter()
    for r, x in banded:
        b = math.floor(r["rating"] / width + 1e-9)
        g = group_fn(r)
        buckets[b][g][0] += 1
        buckets[b][g][1] += 1 if x["band"] in band_set else 0
        total[b] += 1
    N = sum(total.values())
    groups = {g for b in buckets for g in buckets[b]}
    out = {}
    for g in groups:
        acc, wsum = 0.0, 0.0
        for b, gm in buckets.items():
            if g in gm and gm[g][0] > 0:
                acc += gm[g][1] / gm[g][0] * total[b]
                wsum += total[b]
        out[g] = acc / wsum * 100 if wsum else 0.0
    return out


def evaluate(rows, res, res_yes, res_rat, pairs, weeks=WEEKS):
    """All measurable yardsticks for one configuration. res* are lists aligned with rows."""
    n_all = len(rows)
    # ---- Y1: one vote --------------------------------------------------------------------------
    flips = Counter()
    by_bucket = defaultdict(lambda: [0, 0, 0])
    transitions = Counter()
    flip_firm = firm = 0
    for r, a, b, c in zip(rows, res, res_yes, res_rat):
        fy = a["band"] != b["band"]
        fr = a["band"] != c["band"]
        fe = fy or fr
        fv = a["action"] != b["action"] or a["action"] != c["action"]      # the verdict (action) changes
        flips["yes"] += fy
        flips["rating"] += fr
        flips["either"] += fe
        flips["verdict"] += fv
        if fy:
            transitions["%s>%s" % (BAND_LABEL[a["band"]], BAND_LABEL[b["band"]])] += 1
        if fr:
            transitions["%s>%s" % (BAND_LABEL[a["band"]], BAND_LABEL[c["band"]])] += 1
        by_bucket[r["vote_bucket"]][0] += 1
        by_bucket[r["vote_bucket"]][1] += fe
        by_bucket[r["vote_bucket"]][2] += fv
        if a["band"] is not None and not a["provisional"]:
            firm += 1
            flip_firm += fe
        if r["votes"] >= 10:
            flips["n10"] += 1
            flips["flip10"] += fe
            flips["verdict10"] += fv
    y1 = {"flip_all": _share(flips["either"], n_all), "flip_10plus": _share(flips["flip10"], flips["n10"]),
          "flip_yes": _share(flips["yes"], n_all), "flip_rating": _share(flips["rating"], n_all),
          "flip_firm": _share(flip_firm, firm), "flips": flips["either"], "n": n_all,
          "verdict_all": _share(flips["verdict"], n_all), "verdict_10plus": _share(flips["verdict10"], flips["n10"]),
          "verdict_flips": flips["verdict"],
          "transitions": dict(transitions.most_common()),
          "by_bucket": {k: {"n": v[0], "flips": v[1], "share": _share(v[1], v[0]), "verdict_share": _share(v[2], v[0])}
                        for k, v in by_bucket.items()}}
    # ---- Y2: the two human signals -------------------------------------------------------------
    voiced = [(r, x) for r, x in zip(rows, res) if r["votes"] >= VOICES]
    fc = [r for r, x in voiced if x["band"] in ("good", "excellent") and (r["rating"] < LINE or r["approval"] < BAR)]
    fc_rating = [r for r in fc if r["rating"] < LINE]
    fa = [r for r, x in voiced if x["band"] == "bad" and r["rating"] >= LINE and r["approval"] >= BAR]
    bad_all = [r for r, x in zip(rows, res) if x["band"] == "bad"]
    bad_high = [r for r in bad_all if r["rating"] >= LINE]
    y2 = {"n_voiced": len(voiced), "false_comfort": len(fc), "false_comfort_share": _share(len(fc), len(voiced)),
          "false_comfort_rating": len(fc_rating), "false_comfort_approval": len(fc) - len(fc_rating),
          "false_alarm": len(fa), "false_alarm_share": _share(len(fa), len(voiced)),
          "bad_total": len(bad_all), "bad_rated_fine": len(bad_high), "bad_rated_fine_share": _share(len(bad_high), len(bad_all))}
    # ---- Y3: the next class --------------------------------------------------------------------
    per_band = {b: [0, 0] for b in BANDS}
    for i, j in pairs:
        b = res[i]["band"]
        if b is None or res[i]["provisional"]:
            continue
        per_band[b][0] += 1
        per_band[b][1] += 1 if low_next(rows[j]) else 0
    y3 = {b: {"n": v[0], "low": v[1], "share": _share(v[1], v[0])} for b, v in per_band.items()}
    shares = [y3[b]["share"] for b in BANDS]
    y3["order_ok"] = sum(1 for k in range(3) if shares[3 - k] > shares[2 - k])   # bad > average > good > excellent
    y3["ratio_bad_excellent"] = (y3["bad"]["share"] / y3["excellent"]["share"]) if y3["excellent"]["share"] else float("inf")
    y3["min_band_n"] = min(y3[b]["n"] for b in BANDS)
    y3["base_rate"] = _share(sum(1 for i, j in pairs if low_next(rows[j])), len(pairs))
    y3["pairs"] = len(pairs)
    # ---- Y4: band sizes and workload -----------------------------------------------------------
    bands = Counter(x["band"] for x in res)
    banded = sum(v for k, v in bands.items() if k is not None)
    actions = Counter(x["action"] for x in res)
    y4 = {"band_counts": {BAND_LABEL[k]: v for k, v in bands.items()},
          "band_shares": {b: _share(bands[b], banded) for b in BANDS}, "no_band_share": _share(bands[None], n_all),
          "provisional": sum(1 for x in res if x["provisional"]),
          "actions": dict(actions), "per_week": (actions["video"] + actions["transcript"]) / weeks,
          "videos_per_week": actions["video"] / weeks, "transcripts_per_week": actions["transcript"] / weeks,
          "cost_per_week": (actions["video"] * COST["video"] + actions["transcript"] * COST["transcript"]) / weeks}
    y4["min_share"], y4["max_share"] = min(y4["band_shares"].values()), max(y4["band_shares"].values())
    # ---- Y5: fairness --------------------------------------------------------------------------
    size = standardised_share(rows, res, lambda r: "<10" if r["responses"] < 10 else "10+")
    kind = standardised_share(rows, res, lambda r: r["kind"], )
    thin = [(r, x) for r, x in zip(rows, res) if r["votes"] <= 3 and x["band"] in ("bad", "excellent") and not x["provisional"]]
    y5 = {"excellent_lt10": size.get("<10", 0.0), "excellent_10plus": size.get("10+", 0.0),
          "size_gap": abs(size.get("<10", 0.0) - size.get("10+", 0.0)),
          "excellent_live": kind.get("Live Class", 0.0), "excellent_review": kind.get("Test Review", 0.0),
          "kind_gap": abs(kind.get("Live Class", 0.0) - kind.get("Test Review", 0.0)),
          "thin_firm": len(thin), "thin_firm_bad": sum(1 for r, x in thin if x["band"] == "bad"),
          "thin_firm_excellent": sum(1 for r, x in thin if x["band"] == "excellent")}
    return {"Y1": y1, "Y2": y2, "Y3": y3, "Y4": y4, "Y5": y5}


def moving_parts(cfg):
    """How many ideas a PM must hold: active components + guard + caps + floors + knee."""
    parts = sum(1 for k, w in cfg["weights"].items() if w and not (k == "track" and cfg["track"]["mode"] != "on")
                and not (k == "sample" and cfg["sample"]["mode"] == "off") and not (k == "reach" and cfg["reach"]["mode"] == "off"))
    parts += 1 if (cfg["guard"]["k"] or 0) > 0 else 0
    parts += 1 if cfg["caps"].get("rating_line") is not None or cfg["caps"].get("approval_bar") is not None else 0
    parts += 1 if (cfg["min_votes"].get("band") or cfg["min_votes"].get("action")) else 0
    parts += 1 if cfg["rating"]["mode"] == "knee" else 0
    parts += 1 if cfg["approval"]["mode"] == "graded" else 0
    return parts


def y6_proxy(cfg):
    """Explainability, as a proxy until the PM test is run: the manager's formula (4 parts) scores
    10 of 10; every extra idea costs a point; the two hard lines give one back because they let a
    PM read Bad / Average straight off the reason sentence."""
    caps = cfg["caps"].get("rating_line") is not None or cfg["caps"].get("approval_bar") is not None
    return max(4, min(10, 10 - (moving_parts(cfg) - 4) + (1 if caps else 0)))


def _under(value, mark, weight):
    """Full credit at or under the mark, linear to zero at twice the mark."""
    if value <= mark:
        return weight
    return weight * max(0.0, 1.0 - (value - mark) / mark)


def _atleast(value, mark, weight):
    if value >= mark:
        return weight
    return weight * max(0.0, value / mark)


def scorecard(m, y6):
    """The plan's scorecard: Y1 25 · Y2 20 · Y3 20 · Y4 15 · Y5 15 · Y6 5, two sub-marks each
    (max 200), plus the two vetoes."""
    W = WEIGHTS
    pts = {
        "Y1": _under(m["Y1"]["flip_all"], 10.0, W["Y1"]) + _under(m["Y1"]["flip_10plus"], 5.0, W["Y1"]),
        "Y2": _under(m["Y2"]["false_comfort_share"], 2.0, W["Y2"]) + _under(m["Y2"]["false_alarm_share"], 5.0, W["Y2"]),
        "Y3": (W["Y3"] * m["Y3"]["order_ok"] / 3.0
               + _atleast(min(m["Y3"]["ratio_bad_excellent"], 2.0), 2.0, W["Y3"] / 2.0)
               + _atleast(m["Y3"]["min_band_n"], 100, W["Y3"] / 2.0)),
        "Y4": (W["Y4"] * sum(1 for b in BANDS if 5.0 <= m["Y4"]["band_shares"][b] <= 75.0) / 4.0
               + (_under(m["Y4"]["per_week"], CEILING["per_week"], W["Y4"] / 2.0)
                  + _under(m["Y4"]["videos_per_week"], CEILING["videos"], W["Y4"] / 2.0))),
        "Y5": (_under(m["Y5"]["size_gap"], 10.0, W["Y5"] / 2.0) + _under(m["Y5"]["kind_gap"], 10.0, W["Y5"] / 2.0)
               + (W["Y5"] if m["Y5"]["thin_firm"] == 0 else W["Y5"] * max(0.0, 1.0 - m["Y5"]["thin_firm"] / 100.0))),
        "Y6": y6,
    }
    vetoes = []
    if m["Y2"]["false_comfort_share"] > 5.0:
        vetoes.append("false comfort above 5%%: %.1f%%" % m["Y2"]["false_comfort_share"])
    if m["Y4"]["per_week"] > CEILING["per_week"]:
        vetoes.append("workload above the ceiling: %.1f analyses a week" % m["Y4"]["per_week"])
    if m["Y4"]["videos_per_week"] > CEILING["videos"]:
        vetoes.append("more than 5 videos a week: %.1f" % m["Y4"]["videos_per_week"])
    passes = {
        "Y1a": m["Y1"]["flip_all"] < 10.0, "Y1b": m["Y1"]["flip_10plus"] < 5.0,
        "Y2a": m["Y2"]["false_comfort_share"] < 2.0, "Y2b": m["Y2"]["false_alarm_share"] < 5.0,
        "Y3a": m["Y3"]["order_ok"] == 3 and m["Y3"]["ratio_bad_excellent"] >= 2.0, "Y3b": m["Y3"]["min_band_n"] >= 100,
        "Y4a": 5.0 <= m["Y4"]["min_share"] and m["Y4"]["max_share"] <= 75.0,
        "Y4b": m["Y4"]["per_week"] <= CEILING["per_week"] and m["Y4"]["videos_per_week"] <= CEILING["videos"],
        "Y5a": m["Y5"]["size_gap"] < 10.0 and m["Y5"]["kind_gap"] < 10.0, "Y5b": m["Y5"]["thin_firm"] == 0,
    }
    return {"points": {k: round(v, 1) for k, v in pts.items()}, "total": round(sum(pts.values()), 1),
            "max": 2 * sum(W.values()), "vetoes": vetoes, "passes": passes}


# ------------------------------------------------------------------ config builder (sweep space)
def make_cfg(name="setting", rating_mode="knee", rating_floor=3.55, approval_mode="graded", approval_floor=40,
             approval_bar=80, sample_mode="off", sample_target=10, reach_mode="off", track_mode="on",
             guard_k=5, min_band=3, min_action=5, caps=True, caps_basis="guarded", weights=None, bands=None, missing="neutral"):
    cfg = copy.deepcopy(MANAGER_ORIGINAL)
    cfg["name"] = name
    cfg["rating"].update({"mode": rating_mode, "floor": rating_floor})
    cfg["approval"].update({"mode": approval_mode, "floor": approval_floor, "bar": approval_bar})
    cfg["sample"].update({"mode": sample_mode, "target": sample_target})
    cfg["reach"]["mode"] = reach_mode
    cfg["track"]["mode"] = track_mode
    cfg["guard"]["k"] = guard_k
    cfg["min_votes"] = {"band": min_band, "action": min_action}
    cfg["caps"] = {"rating_line": LINE if caps else None, "approval_bar": float(approval_bar) if caps else None}
    if caps and caps_basis != "guarded":
        cfg["caps"]["basis"] = caps_basis          # proposed contract change, see FastScorer._missed
    cfg["weights"] = dict(weights or {"rating": 60, "approval": 25, "sample": 0, "reach": 0, "track": 15})
    if bands:
        cfg["bands"] = dict(bands)
    cfg["missing"] = {"approval": missing, "reach": missing, "track": "neutral"}
    return cfg


def needs_contract_change(cfg):
    return cfg["caps"].get("basis", "guarded") != "guarded"


def cfg_signature(cfg):
    w = cfg["weights"]
    return ("%s%.2f/%s%d-%d/%s%d/%s/%s/k%d/f%d-%d/caps%s/w%d-%d-%d-%d-%d/b%.1f-%.1f-%.1f" % (
        cfg["rating"]["mode"][:1], cfg["rating"]["floor"], cfg["approval"]["mode"][:1], cfg["approval"]["floor"], cfg["approval"]["bar"],
        cfg["sample"]["mode"][:1], cfg["sample"]["target"], cfg["reach"]["mode"][:2], cfg["track"]["mode"][:2], cfg["guard"]["k"],
        cfg["min_votes"]["band"], cfg["min_votes"]["action"],
        ("off" if cfg["caps"]["rating_line"] is None else cfg["caps"].get("basis", "guarded")[:3]),
        w["rating"], w["approval"], w["sample"], w["reach"], w["track"], cfg["bands"]["excellent"], cfg["bands"]["good"], cfg["bands"]["average"]))


def describe_cfg(cfg):
    w = cfg["weights"]
    bits = ["rating %s" % ("steeper below %.2f" % cfg["rating"]["line"] if cfg["rating"]["mode"] == "knee" else "straight / 5"),
            "approval %s" % ("slope %d-%d" % (cfg["approval"]["floor"], cfg["approval"]["bar"]) if cfg["approval"]["mode"] == "graded"
                             else "cliff at %d" % cfg["approval"]["bar"]),
            "responses %s" % ("off" if cfg["sample"]["mode"] == "off" else "%s at %d" % (cfg["sample"]["mode"], cfg["sample"]["target"])),
            "reach %s" % ("on" if cfg["reach"]["mode"] != "off" else "off"),
            "track record %s" % cfg["track"]["mode"],
            "guard k=%d" % (cfg["guard"]["k"] or 0),
            "min votes %d/%d" % (cfg["min_votes"]["band"], cfg["min_votes"]["action"]),
            "hard lines %s" % ("off" if cfg["caps"]["rating_line"] is None else
                               ("on (raw values - needs the contract change)" if needs_contract_change(cfg) else "on")),
            "weights %d/%d/%d/%d/%d" % (w["rating"], w["approval"], w["sample"], w["reach"], w["track"]),
            "bands %g/%g/%g" % (cfg["bands"]["excellent"], cfg["bands"]["good"], cfg["bands"]["average"])]
    return "; ".join(bits)


# ------------------------------------------------------------------ the fast scorer
def _round2_fast(v):
    x = v * 100.0
    f = math.floor(x)
    d = x - f
    if abs(d - 0.5) < 1e-7:
        return round2(v)
    return (f + (1 if d > 0.5 else 0)) / 100.0


class FastScorer:
    """Reproduces sentiment_score.score() for the study's rows, many configurations quickly.

    Only the paths real rows take are vectorised (a rating, votes, attendance on every row); any
    row the contract would reject or that lacks a vote is scored by the contract itself.
    """

    def __init__(self, inputs):
        self.inputs = inputs
        self.n = len(inputs)
        self.cache = {}
        self.rating = [i["rating"] for i in inputs]
        self.num = [i["num_ratings"] for i in inputs]
        self.att = [i["attended"] for i in inputs]
        self.yes = [i["yes_votes"] for i in inputs]
        self.no = [i["no_votes"] for i in inputs]
        self.votes = [(y + n) if (y is not None and n is not None and (y + n) > 0) else None for y, n in zip(self.yes, self.no)]
        self.approval = [(y / v * 100.0) if v else None for y, v in zip(self.yes, self.votes)]
        self.reach = [min(100.0, n / a * 100.0) if (n is not None and a) else None for n, a in zip(self.num, self.att)]
        self.track = [i.get("track_avg") for i in inputs]
        self.pr = [i.get("prior_rating") for i in inputs]
        self.pa = [i.get("prior_approval") for i in inputs]
        self.voices = [v if v is not None else (n or 0) for v, n in zip(self.votes, self.num)]
        # rows the fast path must not touch
        self.slow = [k for k in range(self.n) if self.rating[k] is None or self.rating[k] <= 0 or self.rating[k] > 5
                     or any(v is not None and v < 0 for v in (self.num[k], self.att[k], self.yes[k], self.no[k]))
                     or inputs[k].get("escalated")]

    def _adj(self, k):
        key = ("adj", k)
        if key not in self.cache:
            if k > 0:
                ar = [((n * r + k * p) / (n + k)) if (p is not None and n is not None) else r for r, n, p in zip(self.rating, self.num, self.pr)]
                aa = [((y + k * p / 100.0) / (v + k) * 100.0) if (a is not None and p is not None and v) else a
                      for a, y, v, p in zip(self.approval, self.yes, self.votes, self.pa)]
            else:
                ar, aa = list(self.rating), list(self.approval)
            self.cache[key] = (ar, aa)
        return self.cache[key]

    def _comp_rating(self, cfg):
        r = cfg["rating"]
        k = float(cfg["guard"]["k"] or 0)
        key = ("rating", r["mode"], float(r["floor"]), float(r["line"]), float(r["line_value"]), float(r["scale"]), k)
        if key not in self.cache:
            ar, _ = self._adj(k)
            scale = float(r["scale"])
            if r["mode"] == "knee":
                floor, line, lv = float(r["floor"]), float(r["line"]), float(r["line_value"])
                out = []
                for a in ar:
                    if a is None:
                        out.append(None)
                    elif a <= floor:
                        out.append(0.0)
                    elif a <= line:
                        out.append(max(0.0, min(100.0, (a - floor) / (line - floor) * lv)))
                    else:
                        out.append(max(0.0, min(100.0, lv + (a - line) / (scale - line) * (100.0 - lv))))
            else:
                out = [max(0.0, min(100.0, a / scale * 100.0)) if a is not None else None for a in ar]
            self.cache[key] = out
        return self.cache[key]

    def _comp_approval(self, cfg):
        a = cfg["approval"]
        k = float(cfg["guard"]["k"] or 0)
        zero = cfg["missing"]["approval"] == "zero"
        key = ("approval", a["mode"], float(a["floor"]), float(a["bar"]), k, zero)
        if key not in self.cache:
            _, aa = self._adj(k)
            floor, bar = float(a["floor"]), float(a["bar"])
            out = []
            for v in aa:
                if v is None:
                    out.append(0.0 if zero else None)
                elif a["mode"] == "graded":
                    out.append(max(0.0, min(100.0, (v - floor) / (bar - floor) * 100.0)))
                else:
                    out.append(100.0 if v >= bar else 0.0)
            self.cache[key] = out
        return self.cache[key]

    def _comp_sample(self, cfg):
        s = cfg["sample"]
        key = ("sample", s["mode"], float(s["target"]))
        if key not in self.cache:
            if s["mode"] == "off":
                out = [None] * self.n
            else:
                t = float(s["target"])
                out = [0.0 if n is None else (max(0.0, min(100.0, n / t * 100.0)) if s["mode"] == "graded" else (100.0 if n >= t else 0.0))
                       for n in self.num]
            self.cache[key] = out
        return self.cache[key]

    def _comp_reach(self, cfg):
        zero = cfg["missing"]["reach"] == "zero"
        key = ("reach", cfg["reach"]["mode"], zero)
        if key not in self.cache:
            if cfg["reach"]["mode"] == "off":
                out = [None] * self.n
            else:
                out = [(0.0 if zero else None) if v is None else v for v in self.reach]
            self.cache[key] = out
        return self.cache[key]

    def _comp_track(self, cfg):
        t = cfg["track"]
        key = ("track", t["mode"], float(t["floor"]), float(t["line"]))
        if key not in self.cache:
            if t["mode"] != "on":
                out = [None] * self.n
            else:
                fl, ln = float(t["floor"]), float(t["line"])
                out = [None if v is None else max(0.0, min(100.0, (v - fl) / (ln - fl) * 100.0)) for v in self.track]
            self.cache[key] = out
        return self.cache[key]

    def _missed(self, cfg):
        caps = cfg["caps"]
        k = float(cfg["guard"]["k"] or 0)
        act = float(cfg["min_votes"].get("action", 0) or 0)
        rl = caps.get("rating_line")
        ab = caps.get("approval_bar")
        # "basis" is NOT part of the contract (which always uses the guarded values). "raw" and
        # "raw_rating" are the proposed contract change the study measures; any config carrying
        # them is labelled as needing that change and is never verified against the contract.
        basis = caps.get("basis", "guarded")
        key = ("missed", k, act, rl, ab, basis)
        if key not in self.cache:
            ar, aa = self._adj(k)
            if basis == "raw":
                ar, aa = self.rating, self.approval
            elif basis == "raw_rating":
                ar = self.rating
            out = []
            for i in range(self.n):
                enough = self.voices[i] >= act
                m = 0
                if rl is not None and enough and ar[i] < float(rl):
                    m += 1
                if ab is not None and enough and aa[i] is not None and aa[i] < float(ab):
                    m += 1
                out.append(m)
            self.cache[key] = out
        return self.cache[key]

    def run(self, cfg):
        """Per class: dict(score, band, action, provisional) - same values as the contract."""
        comps = {"rating": self._comp_rating(cfg), "approval": self._comp_approval(cfg), "sample": self._comp_sample(cfg),
                 "reach": self._comp_reach(cfg), "track": self._comp_track(cfg)}
        w = {key: float(cfg["weights"].get(key, 0)) for key in comps}
        active = [key for key in comps if w[key] > 0]
        missed = self._missed(cfg)
        b = cfg["bands"]
        ex, gd, av = float(b["excellent"]), float(b["good"]), float(b["average"])
        band_floor = float(cfg["min_votes"].get("band", 0) or 0)
        act_floor = float(cfg["min_votes"].get("action", 0) or 0)
        actions = cfg["actions"]
        out = []
        slow = set(self.slow)
        for i in range(self.n):
            if i in slow:
                out.append(score(self.inputs[i], cfg))
                continue
            num = den = 0.0
            for key in active:
                c = comps[key][i]
                if c is not None:
                    num += c * w[key]
                    den += w[key]
            sc = _round2_fast(num / den) if den else 0.0
            band = "excellent" if sc >= ex else "good" if sc >= gd else "average" if sc >= av else "bad"
            m = missed[i]
            if m == 1:
                band = BANDS[max(BAND_RANK[band], BAND_RANK["average"])]
            elif m >= 2:
                band = "bad"
            voices = self.voices[i]
            provisional = False
            if voices < band_floor:
                band_out = None
            else:
                band_out = band
                if voices < act_floor and act_floor:
                    provisional = True
            action = actions["no_data"] if (band_out is None or provisional) else actions[band_out]
            out.append({"score": sc, "band": band_out, "action": action, "provisional": provisional})
        return out

    def verify(self, cfg):
        """Compare with the contract on every row; return the number of disagreements
        (-1 when the config carries the proposed 'caps basis' change the contract lacks)."""
        if cfg["caps"].get("basis", "guarded") != "guarded":
            return -1
        fast = self.run(cfg)
        bad = 0
        for i, f in enumerate(fast):
            c = score(self.inputs[i], cfg)
            if (f["score"], f["band"], f["action"], f["provisional"]) != (c["score"], c["band"], c["action"], c["provisional"]):
                bad += 1
                if bad <= 3:
                    print("  fast/contract mismatch row %d: %s vs %s" % (i, f, {k: c[k] for k in ("score", "band", "action", "provisional")}))
        return bad


class Engine:
    """Three fast scorers (base, yes->no, one point less) plus evaluate() for a config."""

    def __init__(self, study: Study):
        self.study = study
        self.base = FastScorer(study.inputs)
        self.yes = FastScorer(study.inputs_yes)
        self.rat = FastScorer(study.inputs_rat)

    def run(self, cfg):
        return self.base.run(cfg), self.yes.run(cfg), self.rat.run(cfg)

    def metrics(self, cfg, naming="resolved"):
        a, b, c = self.run(cfg)
        m = evaluate(self.study.rows, a, b, c, self.study.pairs[naming], self.study.weeks)
        m["Y6"] = y6_proxy(cfg)
        m["scorecard"] = scorecard(m, m["Y6"])
        m["parts"] = moving_parts(cfg)
        return m

    def verify(self, cfg):
        if needs_contract_change(cfg):
            return -1
        return self.base.verify(cfg) + self.yes.verify(cfg) + self.rat.verify(cfg)


# ------------------------------------------------------------------ output helpers
def write_csv(path, header, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, default=_json_default)


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _json_default(o):
    if isinstance(o, (dt.datetime, dt.date)):
        return o.isoformat()
    if isinstance(o, float) and (o != o or o in (float("inf"), float("-inf"))):
        return None
    if isinstance(o, set):
        return sorted(o)
    raise TypeError(str(type(o)))


def fmt_pct(v, d=1):
    return ("%%.%df%%%%" % d) % v


if __name__ == "__main__":
    import time
    t0 = time.time()
    S = Study()
    print("rows %d | weeks %.1f | aliases %d | pairs resolved %d raw %d | load %.1fs" % (
        len(S.rows), S.weeks, len(S.alias), len(S.pairs["resolved"]), len(S.pairs["raw"]), time.time() - t0))
    print("prior sources:", Counter(r["prior_source"] for r in S.rows))
    print("track coverage resolved %d raw %d" % (sum(1 for r in S.rows if r["track_instructor_resolved"] is not None),
                                                sum(1 for r in S.rows if r["track_instructor_raw"] is not None)))
    E = Engine(S)
    for key, cfg in CONFIGS.items():
        t1 = time.time()
        bad = E.verify(cfg)
        m = E.metrics(cfg)
        print("%s verify mismatches %d (%.1fs) | bands %s | flip %.1f%% | fc %.1f%% fa %.1f%% | /wk %.1f | total %s" % (
            key, bad, time.time() - t1, m["Y4"]["band_counts"], m["Y1"]["flip_all"], m["Y2"]["false_comfort_share"],
            m["Y2"]["false_alarm_share"], m["Y4"]["per_week"], m["scorecard"]["total"]))
    import random
    random.seed(7)
    bad = 0
    t1 = time.time()
    for _ in range(40):
        cfg = make_cfg(rating_mode=random.choice(["linear", "knee"]), rating_floor=random.choice([3.3, 3.55, 3.8]),
                       approval_mode=random.choice(["cliff", "graded"]), approval_floor=random.choice([30, 40, 50]),
                       approval_bar=random.choice([70, 75, 80, 85, 90]), sample_mode=random.choice(["off", "cliff", "graded"]),
                       sample_target=random.choice([5, 8, 10, 12, 15]), reach_mode=random.choice(["off", "graded"]),
                       track_mode=random.choice(["off", "on"]), guard_k=random.choice([0, 3, 5, 10]),
                       min_band=random.choice([0, 3, 5]), min_action=random.choice([0, 3, 5]), caps=random.choice([True, False]),
                       weights={"rating": random.choice([40, 60, 80]), "approval": random.choice([10, 25, 45]),
                                "sample": random.choice([0, 6]), "reach": random.choice([0, 4]), "track": random.choice([0, 15])},
                       bands={"excellent": random.choice([85, 90, 95]), "good": random.choice([70, 75, 80]), "average": random.choice([55, 60, 65])})
        bad += E.verify(cfg)
    print("random sweep configs: 40 verified, mismatches %d (%.1fs)" % (bad, time.time() - t1))
