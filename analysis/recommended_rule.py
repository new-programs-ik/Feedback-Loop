"""Part 3 - the recommended replacement rule, costed on the real 16-30 Aug data."""
import json
import statistics as st
from collections import Counter, defaultdict

rows = json.load(open("analysis/window_rows.json", encoding="utf-8"))
WEEKS = 15 / 7.0

MIN_VOICES = 3          # below this the "rating" is one or two people
SERIOUS = 4.25          # clearly bad -> look with video
NEEDS_LOOK = 4.5        # the existing line, kept


def decide(r, escalation=False):
    if escalation:
        return "VIDEO"
    if r["responses"] < MIN_VOICES:
        return "WATCH"                       # too few voices to act on
    if r["rating"] >= NEEDS_LOOK:
        return "NONE"
    return "VIDEO" if r["rating"] < SERIOUS else "TRANSCRIPT"


print("=" * 78)
print("RECOMMENDED RULE - scored on 186 real classes (16-30 Aug 2026)")
print("=" * 78)
print("  1. Fewer than %d ratings          -> WATCH (rating is 1-2 opinions; no analysis)" % MIN_VOICES)
print("  2. Rating >= %.1f                  -> NO ANALYSIS (unless a PM asks)" % NEEDS_LOOK)
print("  3. Rating < %.2f                  -> VIDEO ANALYSIS" % SERIOUS)
print("  4. Rating %.2f - %.2f            -> TRANSCRIPT ANALYSIS" % (SERIOUS, NEEDS_LOOK - 0.01))
print("  5. Any escalation                -> VIDEO ANALYSIS, always")
print("  (participation %% is not used as a gate at all - see why in the report)")

counts = Counter(decide(r) for r in rows)
print("\n  OUTCOME OVER 15 DAYS")
print("  " + "-" * 74)
for k in ("VIDEO", "TRANSCRIPT", "WATCH", "NONE"):
    n = counts[k]
    print("    %-11s %3d classes   %4.1f per week   %4.1f%% of all classes"
          % (k, n, n / WEEKS, n / len(rows) * 100))
work = counts["VIDEO"] + counts["TRANSCRIPT"]
cost = counts["VIDEO"] * 0.70 + counts["TRANSCRIPT"] * 0.51
print("\n    PM workload : %.1f analyses/week   AI cost: $%.2f / 15 days (~$%.0f per month)"
      % (work / WEEKS, cost, cost / 15 * 30))

print("\n  WHAT IT CATCHES vs THE OLD 80%% RULE")
print("  " + "-" * 74)
old_video = sum(1 for r in rows if r["rating"] < 4.5 and r["pct"] >= 80)
serious = [r for r in rows if r["rating"] < 4.0 and r["responses"] >= MIN_VOICES]
print("    Classes the old rule would have put on video : %d  (out of %d low-rated)"
      % (old_video, sum(1 for r in rows if r["rating"] < 4.5)))
print("    Serious classes (< 4.0, %d+ voices)          : %d - all on VIDEO under the new rule: %s"
      % (MIN_VOICES, len(serious),
         all(decide(r) == "VIDEO" for r in serious)))

print("\n  BY COURSE - what a PM in each programme would get per week")
print("  " + "-" * 74)
by = defaultdict(Counter)
for r in rows:
    by[r["course"]][decide(r)] += 1
print("    %-36s%8s%12s%8s%8s" % ("Course", "video", "transcript", "watch", "none"))
for c in sorted(by, key=lambda c: -(by[c]["VIDEO"] + by[c]["TRANSCRIPT"])):
    k = by[c]
    print("    %-36s%8.1f%12.1f%8.1f%8.1f"
          % (c, k["VIDEO"] / WEEKS, k["TRANSCRIPT"] / WEEKS, k["WATCH"] / WEEKS, k["NONE"] / WEEKS))

print("\n  BY CATEGORY")
print("  " + "-" * 74)
for kind in ("Live Class", "Test Review"):
    g = [r for r in rows if r["kind"] == kind]
    k = Counter(decide(r) for r in g)
    print("    %-13s n=%3d   video %.1f/wk   transcript %.1f/wk   watch %.1f/wk"
          % (kind, len(g), k["VIDEO"] / WEEKS, k["TRANSCRIPT"] / WEEKS, k["WATCH"] / WEEKS))

print("\n  SENSITIVITY - if you want fewer or more analyses")
print("  " + "-" * 74)
for serious_line, look_line in ((4.0, 4.5), (4.25, 4.5), (4.5, 4.5), (4.25, 4.6)):
    v = sum(1 for r in rows if r["responses"] >= MIN_VOICES and r["rating"] < serious_line)
    t = sum(1 for r in rows if r["responses"] >= MIN_VOICES and serious_line <= r["rating"] < look_line)
    print("    video below %.2f, transcript %.2f-%.2f : %4.1f video + %4.1f transcript per week (%.1f total)"
          % (serious_line, serious_line, look_line, v / WEEKS, t / WEEKS, (v + t) / WEEKS))
