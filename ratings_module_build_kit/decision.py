"""decision.py - the team's which-analysis rule, as one pure function.

The rule (validated against 8 months of ratings data, Sep 2026 - see the Rating-Threshold study):
  - any escalation                          -> video, always
  - rating 4.55 or above                    -> none (no analysis unless a PM asks)
  - fewer than 5 ratings                    -> watch (one or two opinions is not a class problem)
  - >= 40% of attendees rated it            -> video (representative sample, still bad)
  - under 40%                               -> transcript (too thin to trust yet)

MIRROR: web/src/lib/decision.ts is the same rule for the web app. Edit both together, and keep
the constants identical - the tests on both sides pin the boundary values.
"""

GOOD = 4.55          # at or above this line a class is fine
MIN_VOICES = 5       # fewer ratings than this and the score is one or two opinions
PARTICIPATION_BAR = 40.0   # percent of attendees who rated

DECISIONS = ("none", "watch", "transcript", "video")


def decide(rating, num_ratings, attended, escalated: bool = False) -> str:
    """One class's verdict. Missing data degrades to 'watch', never to a confident verdict."""
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
