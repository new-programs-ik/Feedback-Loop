"""Numbers for the agreed operating settings: rating line 4.55, participation bar 40%,
plus a 'voice factor' that stops a percentage from lying about a small class.
"""
import datetime as dt
import os
import statistics as st
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ratings_data import load  # noqa: E402

LO, HI = dt.datetime(2026, 8, 16), dt.datetime(2026, 8, 30, 23, 59, 59)
rows = load(LO, HI)
LINE = 4.55          # at or above this, the class is fine
BAR = 40             # participation bar
VOICES = 5           # minimum number of ratings for the score to mean anything

bad = [r for r in rows if r["rating"] < LINE]
good = [r for r in rows if r["rating"] >= LINE]

print("=" * 78)
print("OPERATING SETTINGS: rating line %.2f, participation bar %d%%, voices >= %d"
      % (LINE, BAR, VOICES))
print("=" * 78)
print("Classes                       : %d" % len(rows))
print("At or above %.2f               : %d (%.1f%%)" % (LINE, len(good), len(good) / len(rows) * 100))
print("Below %.2f                     : %d (%.1f%%)" % (LINE, len(bad), len(bad) / len(rows) * 100))
print("  (at the old 4.50 line it was  37)")

print("\nPARTICIPATION AVERAGES AT THE NEW LINE")
for lab, g in (("at or above %.2f" % LINE, good), ("below %.2f" % LINE, bad)):
    print("  %-22s n=%3d  avg %.1f%%  median %.1f%%  avg ratings %.1f"
          % (lab, len(g), st.mean([r["pct"] for r in g]), st.median([r["pct"] for r in g]),
             st.mean([r["responses"] for r in g])))

print("\n1. WHY A PERCENTAGE ALONE LIES - what 40%% is worth at different class sizes")
print("-" * 78)
print("  %-16s%8s%14s%18s" % ("class size", "n", "avg part.", "40% would mean"))
for lo, hi, lab in ((1, 9, "1-9 learners"), (10, 19, "10-19"), (20, 39, "20-39"), (40, 999, "40+")):
    g = [r for r in rows if lo <= r["attended"] <= hi]
    if not g:
        continue
    mid = st.median([r["attended"] for r in g])
    print("  %-16s%8d%13.1f%%%14.0f voices" % (lab, len(g), st.mean([r["pct"] for r in g]), mid * 0.4))
print("\n  -> 40%% of a 10-person class is 4 voices. 40%% of a 100-person class is 40.")
print("     Same percentage, completely different confidence. Hence the voice floor.")

print("\n2. THE VOICE FLOOR - how many classes does it actually catch?")
print("-" * 78)
reach = [r for r in bad if r["pct"] >= BAR]
both = [r for r in reach if r["responses"] >= VOICES]
caught = [r for r in reach if r["responses"] < VOICES]
print("  Below %.2f                                  : %d" % (LINE, len(bad)))
print("  ... of those, participation >= %d%%          : %d" % (BAR, len(reach)))
print("  ... of those, ALSO %d+ voices (-> video)     : %d" % (VOICES, len(both)))
print("  ... reached %d%% but on fewer than %d voices  : %d  <- the voice floor stops these"
      % (BAR, VOICES, len(caught)))
for r in caught:
    print("        %.2f  %.0f of %.0f (%.0f%%)  %s" % (r["rating"], r["responses"], r["attended"],
                                                       r["pct"], r["course"]))

print("\n3. THE FULL RULE, SCORED")
print("-" * 78)


def decide(r):
    if r["rating"] >= LINE:
        return "NONE"
    if r["responses"] < VOICES:
        return "WATCH"
    return "VIDEO" if r["pct"] >= BAR else "TRANSCRIPT"


c = Counter(decide(r) for r in rows)
weeks = 15 / 7
for k, lab in (("VIDEO", "Video analysis"), ("TRANSCRIPT", "Transcript analysis"),
               ("WATCH", "Watch only"), ("NONE", "No analysis")):
    print("  %-22s %3d classes   %4.1f / week" % (lab, c[k], c[k] / weeks))
cost = c["VIDEO"] * 0.70 + c["TRANSCRIPT"] * 0.51
print("  workload %.1f analyses/week   cost $%.2f per fortnight (~$%.0f/month)"
      % ((c["VIDEO"] + c["TRANSCRIPT"]) / weeks, cost, cost / 15 * 30))

print("\n4. HOW THE SETTINGS COMPARE  (video / transcript / watch)")
print("-" * 78)
print("  %-34s%9s%12s%8s%10s" % ("setting", "video", "transcript", "watch", "per week"))
for line_, bar_, voices_, lab in (
        (4.50, 80, 3, "original guess (4.50 / 80%)"),
        (4.50, 48, 3, "data average (4.50 / 48%)"),
        (4.55, 40, 5, "AGREED (4.55 / 40% / 5 voices)"),
        (4.55, 40, 3, "4.55 / 40% / 3 voices"),
        (4.55, 45, 5, "4.55 / 45% / 5 voices"),
        (4.55, 50, 5, "4.55 / 50% / 5 voices")):
    def d(r):
        if r["rating"] >= line_:
            return "NONE"
        if r["responses"] < voices_:
            return "WATCH"
        return "VIDEO" if r["pct"] >= bar_ else "TRANSCRIPT"
    k = Counter(d(r) for r in rows)
    print("  %-34s%9d%12d%8d%10.1f"
          % (lab, k["VIDEO"], k["TRANSCRIPT"], k["WATCH"],
             (k["VIDEO"] + k["TRANSCRIPT"]) / weeks))

print("\n5. THE SYMMETRIC CASE - good ratings that are also thinly evidenced")
print("-" * 78)
thin_good = [r for r in good if r["responses"] < VOICES]
print("  Rated %.2f+ but on fewer than %d voices : %d classes (%.1f%% of the good ones)"
      % (LINE, VOICES, len(thin_good), len(thin_good) / len(good) * 100))
print("  Rated %.2f+ with %d+ voices AND >=%d%%    : %d  <- genuinely confirmed good"
      % (LINE, VOICES, BAR, sum(1 for r in good if r["responses"] >= VOICES and r["pct"] >= BAR)))

print("\n6. YOUR EXAMPLES")
print("-" * 78)
for want, r in (("thin sample, bad score",
                 min(rows, key=lambda r: abs(r["rating"] - 3.20) + abs(r["responses"] - 5))),
                ("100-learner class, 40% rated (illustration)", None)):
    if r:
        print("  %s: %.2f, %.0f of %.0f (%.0f%%) -> %s"
              % (want, r["rating"], r["responses"], r["attended"], r["pct"], decide(r)))
print("  100 learners, 40 rated (40%%) -> reach OK, voices 40 >> %d -> fully trusted score" % VOICES)
print("  10 learners,   4 rated (40%%) -> reach OK, voices 4 < %d  -> WATCH, not video" % VOICES)
