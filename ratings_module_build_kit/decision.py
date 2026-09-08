"""decision.py - LEGACY: the team's which-analysis rules v1 and v2, as pure functions.

Status (Feedback Loop v3, Sep 2026): the queue decision now comes from the Class Sentiment Score,
computed inside the database by score_class_rating() with the active scoring_configs row
(analysis/sentiment_score.py is the reference). The sync still writes the v2 read-out below
(approval_pct, track_avg, health_score, health_band, flag_reasons) for ONE release so the two
rules can be compared side by side, and the web mirror still explains it - nothing else reads it.
Do not extend this file; retire it with those columns.

Rule v1 (validated against 8 months of ratings data, Sep 2026 - the Rating-Threshold study) - decide():
  - any escalation                          -> video, always
  - rating 4.55 or above                    -> none (no analysis unless a PM asks)
  - fewer than 5 ratings                    -> watch (one or two opinions is not a class problem)
  - >= 40% of attendees rated it            -> video (representative sample, still bad)
  - under 40%                               -> transcript (too thin to trust yet)

Rule v2 (Sep 2026 - the Instructor-Approval study; analysis/approval_rule.py is the spec) - decide_v2():
two bars decide IF, the weighted Class Health Score decides HOW URGENT and HOW DEEP.
  - any escalation                                  -> video, always (reason 'escalated')
  - rating < 4.55  or  approval < 80%               -> the class has a problem (reasons 'rating' / 'approval')
        neither bar fails                           -> none
        fewer than 5 ratings                        -> watch (either signal is too thin)
  - Health = 0.60*R + 0.25*A + 0.15*T, each 0-100   -> band: urgent (<70) / look (70 to <90) / borderline (>=90)
    (weights W below - 60/25/15 from analysis/approval_weights.py; older notes saying 60/30/10 are stale)
  - depth: urgent -> video whatever the reach; borderline -> transcript whatever the reach;
           in between, >= 40% of attendees rated -> video, else transcript.
  An unknown approval (no vote) or an unknown track record (fewer than 3 earlier classes) scores
  100 - a missing signal is never a penalty.

Contract - what a Verdict carries (the DB columns and the web mirror use the same names):
  decision      'none' | 'watch' | 'transcript' | 'video'
  health_score  0-100 to one decimal; None only when the rating is unknown
  health_band   'urgent' | 'look' | 'borderline' when the class is queued (video/transcript), else None
                (read from the UNROUNDED score, as the study does - see health_score)
  flag_reasons  tuple drawn from ('rating', 'approval', 'escalated'), always in that order

MIRROR: web/src/lib/decision.ts is the same rule for the web app. Edit both together, and keep
the constants identical - the tests on both sides pin the boundary values.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

RULE_VERSION = "v2"

GOOD = 4.55          # at or above this line a class is fine (LINE in the study)
MIN_VOICES = 5       # fewer ratings than this and the score is one or two opinions
PARTICIPATION_BAR = 40.0   # percent of attendees who rated (REACH_BAR in the study)
APPROVAL_BAR = 80.0  # percent of voters who would have the instructor back

# Where each Health component hits 0 - "as bad as it gets" (analysis/approval_weights.py).
R_FLOOR = 3.55       # rating a full point under the line
A_FLOOR = 40.0       # approval: only 4 in 10 would have the instructor back
T_FLOOR = 4.05       # instructor's average half a point under the line
T_MIN_CLASSES = 3    # earlier classes needed before a track record counts

W = (0.60, 0.25, 0.15)  # weights: rating / approval / track record
URGENT = 70.0        # health below this -> 'urgent'
BORDERLINE = 90.0    # health at or above this -> 'borderline'; between -> 'look'

# Depth by score: urgent -> video, borderline -> transcript, whatever the reach. Switched off
# (DEPTH_BY_SCORE=0), depth is reach-only as in v1 - the bars and bands are unchanged.
DEPTH_BY_SCORE = (os.environ.get("DEPTH_BY_SCORE") or "1").strip().lower() not in ("0", "false", "no", "off")

DECISIONS = ("none", "watch", "transcript", "video")
BANDS = ("urgent", "look", "borderline")
REASONS = ("rating", "approval", "escalated")


def decide(rating, num_ratings, attended, escalated: bool = False) -> str:
    """One class's verdict under rule v1. Missing data degrades to 'watch', never to a confident verdict."""
    if escalated:
        return "video"
    if rating is None:
        return "watch"
    if float(rating) >= GOOD:
        return "none"
    if num_ratings is None or int(num_ratings) < MIN_VOICES:
        return "watch"
    if not attended:
        return "watch"                      # can't compute participation
    pct = int(num_ratings) / int(attended) * 100.0
    return "video" if pct >= PARTICIPATION_BAR else "transcript"


# ── rule v2 ──────────────────────────────────────────────────────────────────

def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def score_rating(rating) -> float:
    """0 at R_FLOOR, 100 at the line."""
    return _clamp(100.0 * (float(rating) - R_FLOOR) / (GOOD - R_FLOOR))


def score_approval(approval_pct) -> float:
    """0 at A_FLOOR, 100 at the bar. No vote -> 100 (no penalty)."""
    if approval_pct is None:
        return 100.0
    return _clamp(100.0 * (float(approval_pct) - A_FLOOR) / (APPROVAL_BAR - A_FLOOR))


def score_track(track_avg) -> float:
    """0 at T_FLOOR, 100 at the line. No track record -> 100 (no penalty)."""
    if track_avg is None:
        return 100.0
    return _clamp(100.0 * (float(track_avg) - T_FLOOR) / (GOOD - T_FLOOR))


def health_score(rating, approval_pct=None, track_avg=None) -> float:
    """The Class Health Score, 0-100, unrounded. The band reads THIS value; the Verdict and the
    DB carry it rounded to one decimal - so a stored 90.0 can sit in 'look' (it was 89.99)."""
    return (W[0] * score_rating(rating) + W[1] * score_approval(approval_pct)
            + W[2] * score_track(track_avg))


def health_band(score) -> str:
    s = float(score)
    return "urgent" if s < URGENT else ("look" if s < BORDERLINE else "borderline")


def approval_pct(yes_votes, no_votes) -> Optional[float]:
    """yes/(yes+no) as a percent to two decimals; None when either count is unknown or no one voted."""
    if yes_votes is None or no_votes is None:
        return None
    yes, votes = int(yes_votes), int(yes_votes) + int(no_votes)
    return round(yes / votes * 100.0, 2) if votes > 0 else None


@dataclass(frozen=True)
class Verdict:
    decision: str
    health_score: Optional[float]
    health_band: Optional[str]
    flag_reasons: tuple = ()


def decide_v2(rating, num_ratings, attended, escalated: bool = False,
              approval_pct: Optional[float] = None, track_avg: Optional[float] = None) -> Verdict:
    """One class's verdict under rule v2. Missing data degrades to 'watch', never to a confident verdict."""
    if rating is None:
        return Verdict("video" if escalated else "watch", None, None,
                       ("escalated",) if escalated else ())
    reasons = []
    if float(rating) < GOOD:
        reasons.append("rating")
    if approval_pct is not None and float(approval_pct) < APPROVAL_BAR:
        reasons.append("approval")
    if escalated:
        reasons.append("escalated")
    raw = health_score(rating, approval_pct, track_avg)
    score, band = round(raw, 1), health_band(raw)
    if escalated:
        return Verdict("video", score, band, tuple(reasons))
    if not reasons:
        return Verdict("none", score, None, ())
    if num_ratings is None or int(num_ratings) < MIN_VOICES:
        return Verdict("watch", score, None, tuple(reasons))
    if DEPTH_BY_SCORE and band == "urgent":
        return Verdict("video", score, band, tuple(reasons))
    if DEPTH_BY_SCORE and band == "borderline":
        return Verdict("transcript", score, band, tuple(reasons))
    if not attended:
        return Verdict("watch", score, None, tuple(reasons))   # can't compute participation
    pct = int(num_ratings) / int(attended) * 100.0
    return Verdict("video" if pct >= PARTICIPATION_BAR else "transcript", score, band, tuple(reasons))
