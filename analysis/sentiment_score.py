"""The Class Sentiment Score - reference implementation and the scoring contract.

Every implementation (the Postgres function in migration 0015, the TypeScript preview mirror in
web/src/lib/sentiment.ts, and the validation scripts here) must produce exactly what this module
produces for the cases in supabase/fixtures/scoring_cases.json. Change the contract here first,
regenerate the fixtures, then bring the others in line.

A configuration is a plain dict (stored as JSON in scoring_configs.config):

  rating    mode "linear" (rating / scale) or "knee" (0 at floor, line_value at line, 100 at scale)
  approval  mode "cliff" (100 at/above bar, else 0) or "graded" (0 at floor -> 100 at bar)
  sample    mode "cliff" (100 when num_ratings >= target), "graded" (num_ratings / target) or "off"
  reach     mode "graded" (num_ratings / attended) or "off"
  track     mode "on" (0 at floor -> 100 at line, needs min_classes earlier classes) or "off"
  weights   points per component; only INCLUDED components count, the rest are re-scaled
  guard     k > 0 blends few votes toward the course's typical vote/rating (shrinkage)
  min_votes band: fewer votes -> no band ("no_data"); action: fewer votes -> never an analysis
  caps      hard lines: under rating_line or approval_bar (with >= min_votes.action votes) caps
            the band at Average; both missed caps it at Bad
  bands     lower edges of Excellent / Good / Average; the band reads the ROUNDED score
  missing   what a missing input does: "neutral" (excluded, weights re-scaled) or "zero"
  actions   band -> analysis depth; "no_data" -> what happens under the vote floor
  thin      fewer than min_answers approval answers: a passing approval does not count, and the
            rating must clear rating_line on its own or the band is capped at Average. Either
            value null switches that half off.
"""
from __future__ import annotations

import copy
import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

BANDS = ("excellent", "good", "average", "bad")
BAND_RANK = {b: i for i, b in enumerate(BANDS)}          # lower = better

MANAGER_ORIGINAL = {
    "name": "Manager's original (60/30/6/4, pass/fail)",
    "rating": {"mode": "linear", "scale": 5, "floor": 3.55, "line": 4.55, "line_value": 75},
    "approval": {"mode": "cliff", "bar": 80, "floor": 40},
    "sample": {"mode": "cliff", "target": 10},
    "reach": {"mode": "graded"},
    "track": {"mode": "off", "floor": 4.05, "line": 4.55, "min_classes": 3},
    "weights": {"rating": 60, "approval": 30, "sample": 6, "reach": 4, "track": 0},
    "guard": {"k": 0, "prior": "course"},
    "min_votes": {"band": 0, "action": 0},
    "caps": {"rating_line": None, "approval_bar": None},
    "bands": {"excellent": 90, "good": 75, "average": 60},
    "missing": {"approval": "zero", "reach": "zero", "track": "neutral"},
    "actions": {"bad": "video", "average": "transcript", "good": "none", "excellent": "none",
                "no_data": "watch"},
    "thin": {"min_answers": None, "rating_line": None},
}


def _variant(base: dict, name: str, **changes: dict) -> dict:
    cfg = copy.deepcopy(base)
    cfg["name"] = name
    for key, patch in changes.items():
        cfg[key].update(patch)
    return cfg


CONFIGS = {
    "C0": MANAGER_ORIGINAL,
    "C1": _variant(MANAGER_ORIGINAL, "Original + minimum votes", min_votes={"band": 5, "action": 5}),
    "C2": _variant(MANAGER_ORIGINAL, "Graded approval", approval={"mode": "graded"},
                   missing={"approval": "neutral", "reach": "neutral"}),
    "C3": _variant(MANAGER_ORIGINAL, "Graded + small-sample guard", approval={"mode": "graded"},
                   sample={"mode": "graded"}, guard={"k": 5}, min_votes={"band": 3, "action": 5},
                   missing={"approval": "neutral", "reach": "neutral"}),
    "C4": _variant(MANAGER_ORIGINAL, "Data-derived weights", rating={"mode": "knee"},
                   approval={"mode": "graded"}, sample={"mode": "off"}, reach={"mode": "off"},
                   track={"mode": "on"}, weights={"rating": 60, "approval": 25, "sample": 0, "reach": 0, "track": 15},
                   guard={"k": 5}, min_votes={"band": 3, "action": 5},
                   missing={"approval": "neutral", "reach": "neutral"}),
    # The live settings: the manager's original with one safety net added. A class rated below the
    # floor is forced down to Average, which means somebody reads the transcript, however good the
    # approval looks. Asked for by Sreejit on 10 Sep 2026 because the classification was leaning
    # entirely on approval when the raw rating was very low.
    "C0F": _variant(MANAGER_ORIGINAL, "Original + the 4.3 rating floor",
                    caps={"rating_line": 4.3}),
    # The live settings: the 4.3 floor, plus the rule that approval from fewer than six learners may
    # warn but never vouch, and that such a class must clear 4.6 on its rating alone.
    "C0T": _variant(MANAGER_ORIGINAL, "Original + 4.3 floor + trust approval from 6 answers",
                    caps={"rating_line": 4.3}, thin={"min_answers": 6, "rating_line": 4.6}),
    "C5": _variant(MANAGER_ORIGINAL, "Two lines + graded score", rating={"mode": "knee"},
                   approval={"mode": "graded"}, sample={"mode": "off"}, reach={"mode": "off"},
                   track={"mode": "on"}, weights={"rating": 60, "approval": 25, "sample": 0, "reach": 0, "track": 15},
                   guard={"k": 5}, min_votes={"band": 3, "action": 5},
                   caps={"rating_line": 4.55, "approval_bar": 80},
                   missing={"approval": "neutral", "reach": "neutral"}),
}


def _num(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def round2(v: float) -> float:
    """Round half up to two decimals - the same rule in SQL (round(numeric, 2)) and TS."""
    return float(Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def score(inputs: dict, cfg: dict) -> dict:
    """Score one class.

    inputs: rating, num_ratings, attended, yes_votes, no_votes, escalated, track_avg,
            prior_rating, prior_approval (the course's typical rating / approval %, for the guard).
    Returns: score, band, action, components, flags, adjusted (the guarded rating/approval).
    """
    flags: list[str] = []
    rating = _num(inputs.get("rating"))
    n = _num(inputs.get("num_ratings"))
    attended = _num(inputs.get("attended"))
    yes = _num(inputs.get("yes_votes"))
    no = _num(inputs.get("no_votes"))
    escalated = bool(inputs.get("escalated"))
    track = _num(inputs.get("track_avg"))
    prior_rating = _num(inputs.get("prior_rating"))
    prior_approval = _num(inputs.get("prior_approval"))
    scale = float(cfg["rating"]["scale"])

    # ---- reject nonsense outright ------------------------------------------------------------
    for key, val in (("num_ratings", n), ("attended", attended), ("yes_votes", yes), ("no_votes", no)):
        if val is not None and val < 0:
            flags.append("invalid_" + key)
    if rating is not None and (rating < 0 or rating > scale):
        flags.append("invalid_rating")
    if any(f.startswith("invalid_") for f in flags):
        return _no_score(flags, escalated, cfg)
    if rating is None:
        flags.append("no_rating")
        return _no_score(flags, escalated, cfg)
    if rating == 0:
        flags.append("rating_zero")
        return _no_score(flags, escalated, cfg)

    # ---- derived inputs ----------------------------------------------------------------------
    votes = (yes + no) if (yes is not None and no is not None) else None
    if votes is not None and votes <= 0:
        votes = None
    approval = (yes / votes * 100.0) if votes else None
    if approval is None:
        flags.append("no_vote")
    if votes is not None and n is not None and abs(votes - n) > 0.5:
        flags.append("votes_ne_responses")
    if n is None:
        flags.append("no_responses")
    elif n == 0:
        flags.append("zero_responses")
    if attended is None or attended == 0:
        flags.append("no_attendance")
    reach = None
    if n is not None and attended:
        reach = n / attended * 100.0
        if reach > 100.0:
            reach = 100.0
            flags.append("reach_clamped")
    if approval is not None and rating >= 4.5 and approval < 50:
        flags.append("rating_vote_disagree")

    # ---- small-sample guard (shrinkage toward the course's typical values) -------------------
    k = float(cfg["guard"]["k"] or 0)
    adj_rating, adj_approval = rating, approval
    if k > 0:
        if prior_rating is not None and n is not None:
            adj_rating = (n * rating + k * prior_rating) / (n + k)
        if approval is not None and prior_approval is not None and votes:
            adj_approval = (yes + k * prior_approval / 100.0) / (votes + k) * 100.0
        if adj_rating != rating or adj_approval != approval:
            flags.append("guarded")

    # ---- components ---------------------------------------------------------------------------
    comps: dict[str, Optional[float]] = {}
    r = cfg["rating"]
    if r["mode"] == "knee":
        floor, line, lv = float(r["floor"]), float(r["line"]), float(r["line_value"])
        if adj_rating <= floor:
            comps["rating"] = 0.0
        elif adj_rating <= line:
            comps["rating"] = (adj_rating - floor) / (line - floor) * lv
        else:
            comps["rating"] = lv + (adj_rating - line) / (scale - line) * (100.0 - lv)
    else:
        comps["rating"] = adj_rating / scale * 100.0
    comps["rating"] = _clamp(comps["rating"])

    a = cfg["approval"]
    if adj_approval is None:
        comps["approval"] = 0.0 if cfg["missing"]["approval"] == "zero" else None
    elif a["mode"] == "graded":
        comps["approval"] = _clamp((adj_approval - float(a["floor"])) / (float(a["bar"]) - float(a["floor"])) * 100.0)
    else:
        comps["approval"] = 100.0 if adj_approval >= float(a["bar"]) else 0.0

    # ---- too few approval answers: approval may warn, never vouch -----------------------------
    # A percentage of three people is not evidence that a class went well. A failing approval from
    # a small group still counts, because when those classes were checked against their recordings
    # most had a real content problem. A passing one from the same small group no longer lifts the
    # score; the class is scored on its other inputs instead.
    thin = cfg.get("thin") or {}
    thin_min = _num(thin.get("min_answers"))
    is_thin = thin_min is not None and votes is not None and votes < thin_min
    if is_thin and adj_approval is not None and adj_approval >= float(a["bar"]):
        comps["approval"] = None
        flags.append("thin_approval_not_counted")

    s = cfg["sample"]
    if s["mode"] == "off":
        comps["sample"] = None
    elif n is None:
        comps["sample"] = 0.0
    elif s["mode"] == "graded":
        comps["sample"] = _clamp(n / float(s["target"]) * 100.0)
    else:
        comps["sample"] = 100.0 if n >= float(s["target"]) else 0.0

    if cfg["reach"]["mode"] == "off":
        comps["reach"] = None
    elif reach is None:
        comps["reach"] = 0.0 if cfg["missing"]["reach"] == "zero" else None
    else:
        comps["reach"] = reach

    t = cfg["track"]
    if t["mode"] != "on" or track is None:
        comps["track"] = None
        if t["mode"] == "on" and track is None:
            flags.append("no_track")
    else:
        comps["track"] = _clamp((track - float(t["floor"])) / (float(t["line"]) - float(t["floor"])) * 100.0)

    weights = cfg["weights"]
    used = {key: float(weights.get(key, 0)) for key, val in comps.items() if val is not None and float(weights.get(key, 0)) > 0}
    denom = sum(used.values())
    raw = sum(comps[key] * w for key, w in used.items()) / denom if denom else 0.0
    sc = round2(raw)

    # ---- band, caps, vote floor --------------------------------------------------------------
    b = cfg["bands"]
    band = "excellent" if sc >= float(b["excellent"]) else "good" if sc >= float(b["good"]) \
        else "average" if sc >= float(b["average"]) else "bad"

    mv = cfg["min_votes"]
    enough_for_action = (votes if votes is not None else (n or 0)) >= float(mv.get("action", 0) or 0)
    caps = cfg["caps"]
    missed = 0
    if caps.get("rating_line") is not None and enough_for_action and adj_rating < float(caps["rating_line"]):
        missed += 1
        flags.append("under_rating_line")
    if caps.get("approval_bar") is not None and enough_for_action and adj_approval is not None \
            and adj_approval < float(caps["approval_bar"]):
        missed += 1
        flags.append("under_approval_bar")
    if missed == 1:
        band = BANDS[max(BAND_RANK[band], BAND_RANK["average"])]
    elif missed >= 2:
        band = "bad"

    # With approval untrustworthy, the rating has to carry the decision alone. Below the line the
    # class is read. This caps at Average and never pushes a class to Bad, so video does not grow.
    if is_thin and thin.get("rating_line") is not None and adj_rating < float(thin["rating_line"]):
        if BAND_RANK[band] < BAND_RANK["average"]:
            band = "average"
        flags.append("thin_under_rating_line")

    voices = votes if votes is not None else (n or 0)
    provisional = False
    if voices < float(mv.get("band", 0) or 0):
        band_out: Optional[str] = None
        flags.append("thin_no_band")
    else:
        band_out = band
        if not enough_for_action and mv.get("action", 0):
            provisional = True
            flags.append("thin_provisional")

    actions = cfg["actions"]
    if escalated:
        action = "video"
        flags.append("escalated")
    elif band_out is None or provisional:
        action = actions["no_data"]
    else:
        action = actions[band_out]

    return {
        "score": sc, "band": band_out, "action": action, "provisional": provisional,
        "components": {k_: (round2(v) if v is not None else None) for k_, v in comps.items()},
        "weights_used": used, "flags": flags,
        "adjusted": {"rating": round2(adj_rating), "approval": (round2(adj_approval) if adj_approval is not None else None)},
    }


def _no_score(flags: list[str], escalated: bool, cfg: dict) -> dict:
    action = "video" if escalated else cfg["actions"]["no_data"]
    if escalated:
        flags.append("escalated")
    return {"score": None, "band": None, "action": action, "provisional": False,
            "components": {}, "weights_used": {}, "flags": flags, "adjusted": {"rating": None, "approval": None}}


def reason(inputs: dict, result: dict, cfg: dict) -> str:
    """One plain-English sentence a PM can read out."""
    rating = _num(inputs.get("rating"))
    yes, no = _num(inputs.get("yes_votes")), _num(inputs.get("no_votes"))
    if result["band"] is None:
        if "no_rating" in result["flags"]:
            return "No rating recorded yet."
        return "Not enough voices yet to judge this class."
    parts = []
    if rating is not None:
        parts.append(f"Rated {rating:.2f}")
    if yes is not None and no is not None and yes + no > 0:
        pct = yes / (yes + no) * 100
        parts.append(f"{int(yes)} of {int(yes + no)} would have the instructor back ({pct:.0f}%)")
    band = result["band"].capitalize()
    tail = {"video": "video analysis", "transcript": "transcript analysis", "none": "no analysis", "watch": "watch"}[result["action"]]
    prov = " (provisional — few votes)" if result["provisional"] else ""
    return " · ".join(parts) + f" → {band}{prov} → {tail}."


if __name__ == "__main__":
    print(json.dumps(score({"rating": 4.9, "num_ratings": 5, "attended": 5, "yes_votes": 5, "no_votes": 0}, CONFIGS["C0"]), indent=1))
