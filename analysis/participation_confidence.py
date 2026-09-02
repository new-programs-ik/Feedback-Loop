"""Does participation work as a TRUST check on a bad rating?

Bishal's actual argument (which the first pass misread): when only 5 of 15 rate a class 3.20, the
score may be two annoyed learners - not worth a video analysis. When half the room rates it and it
is STILL bad, something is genuinely wrong - that earns the video.

So participation is not a severity measure, it is a CONFIDENCE measure. This script tests that idea
against the real data and finds the number the 80% guess should have been.
"""
import datetime as dt
import os
import statistics as st
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ratings_data import GOOD, load  # noqa: E402

LO, HI = dt.datetime(2026, 8, 16), dt.datetime(2026, 8, 30, 23, 59, 59)
rows = load(LO, HI)
bad = [r for r in rows if r["rating"] < GOOD]
good = [r for r in rows if r["rating"] >= GOOD]
AVG_PCT = st.mean([r["pct"] for r in rows])

print("=" * 78)
print("PARTICIPATION AS A CONFIDENCE CHECK  (%d classes, 16-30 Aug)" % len(rows))
print("=" * 78)
print("Average participation across every class : %.1f%%" % AVG_PCT)
print("Median                                   : %.1f%%" % st.median([r["pct"] for r in rows]))
print("Highest single class                     : %.1f%%   <- why 80%% could never fire"
      % max(r["pct"] for r in rows))

print("\n1. IS A LOW-PARTICIPATION RATING ACTUALLY LESS TRUSTWORTHY?")
print("-" * 78)
print("   If Bishal is right, ratings from thinly-rated classes should be more volatile -")
print("   a couple of unhappy voices can swing them.\n")
print("   %-26s%7s%12s%14s%16s" % ("group", "n", "avg rating", "spread (sd)", "share below 4.0"))
for lab, sel in (("participation < 48%", lambda r: r["pct"] < 48),
                 ("participation >= 48%", lambda r: r["pct"] >= 48)):
    g = [r for r in rows if sel(r)]
    ext = sum(1 for r in g if r["rating"] < 4.0)
    print("   %-26s%7d%12.2f%14.2f%15.1f%%"
          % (lab, len(g), st.mean([r["rating"] for r in g]),
             st.pstdev([r["rating"] for r in g]), ext / len(g) * 100))

print("\n   Among the %d LOW-RATED classes only:" % len(bad))
print("   %-26s%7s%14s%18s" % ("group", "n", "avg responses", "avg rating"))
for lab, sel in (("participation < 48%", lambda r: r["pct"] < 48),
                 ("participation >= 48%", lambda r: r["pct"] >= 48)):
    g = [r for r in bad if sel(r)]
    print("   %-26s%7d%14.1f%18.2f"
          % (lab, len(g), st.mean([r["responses"] for r in g]), st.mean([r["rating"] for r in g])))

print("\n2. WHERE TO PUT THE LINE  (bad classes only, n=%d)" % len(bad))
print("-" * 78)
print("   %-14s%10s%14s%28s" % ("threshold", "video", "transcript", "what video costs / 2 wks"))
for t in (40, 45, 48, 50, 55, 60, 80):
    v = [r for r in bad if r["pct"] >= t]
    tr = len(bad) - len(v)
    print("   >= %2d%%%15d%14d%22s"
          % (t, len(v), tr, "$%.2f" % (len(v) * 0.70 + tr * 0.51)))

print("\n3. THE RULE, WITH THE LINE AT THE AVERAGE (48%)")
print("-" * 78)
MIN_VOICES = 3
BAR = 48


def decide(r):
    if r["rating"] >= GOOD:
        return "NONE"
    if r["responses"] < MIN_VOICES:
        return "WATCH"
    return "VIDEO" if r["pct"] >= BAR else "TRANSCRIPT"


c = Counter(decide(r) for r in rows)
weeks = 15 / 7
print("   Rating >= 4.5                          -> no analysis        %3d  (%4.1f/wk)"
      % (c["NONE"], c["NONE"] / weeks))
print("   Below 4.5, fewer than %d ratings         -> watch only         %3d  (%4.1f/wk)"
      % (MIN_VOICES, c["WATCH"], c["WATCH"] / weeks))
print("   Below 4.5, participation below %d%%      -> TRANSCRIPT         %3d  (%4.1f/wk)"
      % (BAR, c["TRANSCRIPT"], c["TRANSCRIPT"] / weeks))
print("   Below 4.5, participation %d%% or above   -> VIDEO              %3d  (%4.1f/wk)"
      % (BAR, c["VIDEO"], c["VIDEO"] / weeks))
print("   Any escalation                         -> VIDEO, always")
print("\n   Cost: $%.2f per fortnight (~$%.0f/month)"
      % (c["VIDEO"] * 0.70 + c["TRANSCRIPT"] * 0.51,
         (c["VIDEO"] * 0.70 + c["TRANSCRIPT"] * 0.51) / 15 * 30))

print("\n4. WHAT LANDS WHERE")
print("-" * 78)
for want in ("VIDEO", "TRANSCRIPT", "WATCH"):
    g = sorted([r for r in rows if decide(r) == want], key=lambda r: r["rating"])
    print("\n   %s  (%d classes)" % (want, len(g)))
    print("     %7s%12s%9s  %-12s %s" % ("rating", "rated", "part.", "category", "course"))
    for r in g[:12]:
        print("     %7.2f%9.0f of %2.0f%8.0f%%  %-12s %s"
              % (r["rating"], r["responses"], r["attended"], r["pct"], r["kind"], r["course"]))
    if len(g) > 12:
        print("     ... and %d more" % (len(g) - 12))

print("\n5. THE TWO CASES YOU DESCRIBED")
print("-" * 78)
a = min(rows, key=lambda r: abs(r["rating"] - 3.20) + abs(r["responses"] - 5))
print("   a) thin sample, bad score : rating %.2f, %.0f of %.0f rated (%.0f%%)"
      % (a["rating"], a["responses"], a["attended"], a["pct"]))
print("      -> %s   (don't burn video on a score 5 people gave)" % decide(a))
b = [r for r in bad if r["pct"] >= BAR]
b = min(b, key=lambda r: r["rating"]) if b else None
if b:
    print("   b) half the room rated it and it is still bad: rating %.2f, %.0f of %.0f (%.0f%%)"
          % (b["rating"], b["responses"], b["attended"], b["pct"]))
    print("      -> %s   (representative and still bad = something real)" % decide(b))
