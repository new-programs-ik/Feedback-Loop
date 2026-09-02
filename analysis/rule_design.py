"""Part 2 - design and test a replacement for the 80% participation gate.

Part 1 showed the 80% rule sends ZERO low-rated classes to video. This script works out what
participation actually measures, and tests candidate rules against the same 186 real classes.
"""
import json
import statistics as st
from collections import Counter

rows = json.load(open("analysis/window_rows.json", encoding="utf-8"))
bad = [r for r in rows if r["rating"] < 4.5]
good = [r for r in rows if r["rating"] >= 4.5]


def pctl(vals, p):
    vals = sorted(vals)
    if not vals:
        return 0.0
    k = (len(vals) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)


print("=" * 78)
print("PART 2 - WHAT SHOULD THE RULE BE?")
print("=" * 78)

print("\n1. WHAT IS A 'NORMAL' PARTICIPATION RATE? (all 186 classes)")
print("-" * 78)
allp = [r["pct"] for r in rows]
for p in (10, 25, 50, 75, 90, 95, 100):
    print("   p%-3d = %5.1f%%" % (p, pctl(allp, p)))
print("   mean = %5.1f%%    classes at or above 80%%: %d of %d (%.1f%%)"
      % (st.mean(allp), sum(1 for v in allp if v >= 80), len(allp),
         sum(1 for v in allp if v >= 80) / len(allp) * 100))
print("   -> 80%% is roughly the p%d line. It was never a normal number; it is an outlier."
      % round(sum(1 for v in allp if v < 80) / len(allp) * 100))

print("\n2. DOES PARTICIPATION MEASURE QUALITY, OR CLASS SIZE?")
print("-" * 78)
print("   %-18s%6s%14s%14s" % ("attendance", "n", "avg rated%", "avg rating"))
for lo, hi, label in ((1, 9, "1-9 students"), (10, 19, "10-19"), (20, 39, "20-39"), (40, 10 ** 6, "40+")):
    g = [r for r in rows if lo <= r["attended"] <= hi]
    if g:
        print("   %-18s%6d%13.1f%%%14.2f"
              % (label, len(g), st.mean([r["pct"] for r in g]), st.mean([r["rating"] for r in g])))
# correlation of participation with rating, and with class size
def corr(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    return num / den if den else 0.0

print("\n   correlation(participation, rating)     = %+.2f   <- what we assumed mattered"
      % corr([r["pct"] for r in rows], [r["rating"] for r in rows]))
print("   correlation(participation, class size) = %+.2f   <- what it actually tracks"
      % corr([r["pct"] for r in rows], [r["attended"] for r in rows]))
print("   -> participation mostly says how BIG the class was, not how GOOD it was.")

print("\n3. HOW BAD ARE THE BAD CLASSES? (the 37 below 4.5)")
print("-" * 78)
for lo, hi, label in ((0, 3.99, "below 4.0  (serious)"), (4.0, 4.24, "4.00-4.24"), (4.25, 4.49, "4.25-4.49")):
    g = [r for r in bad if lo <= r["rating"] <= hi]
    print("   %-22s n=%2d  (%4.1f%% of low-rated)  avg responses %4.1f  avg rated%% %.1f%%"
          % (label, len(g), len(g) / len(bad) * 100,
             st.mean([r["responses"] for r in g]) if g else 0,
             st.mean([r["pct"] for r in g]) if g else 0))

print("\n4. HOW MANY VOICES ARE BEHIND THE RATING? (this is the real confidence measure)")
print("-" * 78)
for n in (1, 2, 3, 5, 8, 10):
    g = [r for r in bad if r["responses"] >= n]
    print("   responses >= %2d : %2d of %d low-rated classes (%5.1f%%) qualify"
          % (n, len(g), len(bad), len(g) / len(bad) * 100))

print("\n5. CANDIDATE RULES, SCORED ON THE REAL 186 CLASSES")
print("-" * 78)


def simulate(name, decide):
    counts = Counter(decide(r) for r in rows)
    v, t, s = counts["video"], counts["transcript"], counts["skip"]
    # did we catch the classes that clearly deserve a look? (below 4.0 with >=5 voices)
    must = [r for r in rows if r["rating"] < 4.0 and r["responses"] >= 5]
    caught = sum(1 for r in must if decide(r) in ("video", "transcript"))
    on_video = sum(1 for r in must if decide(r) == "video")
    cost = v * 0.70 + t * 0.51
    print("   %-46s video %3d | transcript %3d | skip %3d" % (name, v, t, s))
    print("   %-46s must-see caught %d/%d (on video %d)  ~$%.0f / 2 weeks"
          % ("", caught, len(must), on_video, cost))


simulate("A. Current rule (>=80%% participation -> video)",
         lambda r: "skip" if r["rating"] >= 4.5
         else ("video" if r["pct"] >= 80 else "transcript"))

simulate("B. Same idea, threshold moved to 50%%",
         lambda r: "skip" if r["rating"] >= 4.5
         else ("video" if r["pct"] >= 50 else "transcript"))

simulate("C. Drop participation. Trust = number of responses",
         lambda r: "skip" if r["rating"] >= 4.5 or r["responses"] < 3
         else ("video" if (r["rating"] < 4.0 or r["responses"] >= 10) else "transcript"))

simulate("D. C, but video only for the serious ones (<4.25)",
         lambda r: "skip" if r["rating"] >= 4.5 or r["responses"] < 3
         else ("video" if r["rating"] < 4.25 else "transcript"))

simulate("E. C with a wider net (rating < 4.6)",
         lambda r: "skip" if r["rating"] >= 4.6 or r["responses"] < 3
         else ("video" if (r["rating"] < 4.0 or r["responses"] >= 10) else "transcript"))

print("\n6. RULE C APPLIED - what a PM would actually see in a week")
print("-" * 78)


def rule_c(r):
    if r["rating"] >= 4.5:
        return "skip"
    if r["responses"] < 3:
        return "skip (too few voices)"
    if r["rating"] < 4.0 or r["responses"] >= 10:
        return "video"
    return "transcript"


picked = [(r, rule_c(r)) for r in rows]
for label in ("video", "transcript", "skip (too few voices)"):
    g = [r for r, d in picked if d == label]
    if not g:
        continue
    print("\n   %s -> %d classes in 2 weeks (%.0f/week)" % (label.upper(), len(g), len(g) / 2))
    for r in sorted(g, key=lambda r: r["rating"])[:14]:
        print("     %.2f  resp %2.0f/%2.0f (%4.1f%%)  %-12s %-34s %s"
              % (r["rating"], r["responses"], r["attended"], r["pct"], r["kind"],
                 r["course"], r["topic"][:34]))
    if len(g) > 14:
        print("     ... and %d more" % (len(g) - 14))

print("\n7. THE CLASS YOU NAMED, UNDER EACH RULE")
print("-" * 78)
target = min(bad, key=lambda r: abs(r["rating"] - 3.75) + abs(r["responses"] - 7))
print("   %s - %s (%s)" % (target["course"], target["topic"][:40], target["kind"]))
print("   rating %.2f, %.0f of %.0f rated (%.1f%%)"
      % (target["rating"], target["responses"], target["attended"], target["pct"]))
print("   old rule (>=80%%) : %s" % ("video" if target["pct"] >= 80 else "TRANSCRIPT ONLY - the miss you spotted"))
print("   rule C           : %s" % rule_c(target).upper())
