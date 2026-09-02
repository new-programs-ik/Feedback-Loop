"""Data-quality check before the full-period (1 Jan - 31 Aug 2026) analysis."""
import datetime as dt
import os
import statistics as st
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ratings_data import load  # noqa: E402

LO, HI = dt.datetime(2026, 1, 1), dt.datetime(2026, 8, 31, 23, 59, 59)
rows = load(LO, HI)

print("rows loaded (deduped):", len(rows))
print("date range:", min(r["date"] for r in rows).date(), "to", max(r["date"] for r in rows).date())

print("\n--- data oddities ---")
over = [r for r in rows if r["pct"] > 100]
print("participation > 100%% (more ratings than attendees):", len(over))
for r in sorted(over, key=lambda r: -r["pct"])[:6]:
    print("   %.0f%%  %:.0f of %.0f  %.2f  %s" if False else
          "   %5.0f%%  %2.0f of %2.0f  rating %.2f  %s" % (r["pct"], r["responses"], r["attended"],
                                                           r["rating"], r["course"]))
print("rating out of 0-5:", sum(1 for r in rows if not (0 <= r["rating"] <= 5)))
print("attended = 1 or 2 (micro-classes):", sum(1 for r in rows if r["attended"] <= 2))
print("responses = 0:", sum(1 for r in rows if r["responses"] == 0))

print("\n--- how many reach key participation levels ---")
for t in (100, 90, 80, 70, 60, 50, 40):
    n = sum(1 for r in rows if r["pct"] >= t)
    print("   >= %3d%% : %4d  (%.1f%%)" % (t, n, n / len(rows) * 100))
hi80 = [r for r in rows if r["pct"] >= 80]
print("\nclasses at/above 80%% - their sizes:", Counter(int(r["attended"]) for r in hi80).most_common(8))
print("avg attendance of >=80%% classes: %.1f   vs all classes: %.1f"
      % (st.mean([r["attended"] for r in hi80]) if hi80 else 0,
         st.mean([r["attended"] for r in rows])))

print("\n--- course mapping over the full period ---")
for k, v in Counter(r["course"] for r in rows).most_common():
    print("   %4d  %s" % (v, k))
print("\n--- kinds ---")
for k, v in Counter(r["kind"] for r in rows).most_common():
    print("   %4d  %s" % (v, k))

print("\n--- monthly volumes ---")
for m in range(1, 9):
    g = [r for r in rows if r["date"].month == m]
    b = [r for r in g if r["rating"] < 4.55]
    print("   %s: %4d classes  %3d below 4.55 (%4.1f%%)  avg part %.1f%%"
          % (dt.date(2026, m, 1).strftime("%b"), len(g), len(b),
             len(b) / len(g) * 100 if g else 0, st.mean([r["pct"] for r in g]) if g else 0))

print("\n--- overall stats (full period) ---")
print("avg participation : %.1f%%   median %.1f%%" % (st.mean([r["pct"] for r in rows]),
                                                      st.median([r["pct"] for r in rows])))
print("avg rating        : %.2f" % st.mean([r["rating"] for r in rows]))
b = [r for r in rows if r["rating"] < 4.55]
g = [r for r in rows if r["rating"] >= 4.55]
print("below 4.55        : %d (%.1f%%)   avg part %.1f%%  median %.1f%%"
      % (len(b), len(b) / len(rows) * 100, st.mean([r["pct"] for r in b]),
         st.median([r["pct"] for r in b])))
print("4.55 and above    : %d (%.1f%%)   avg part %.1f%%  median %.1f%%"
      % (len(g), len(g) / len(rows) * 100, st.mean([r["pct"] for r in g]),
         st.median([r["pct"] for r in g])))
b45 = [r for r in rows if r["rating"] < 4.5]
g45 = [r for r in rows if r["rating"] >= 4.5]
print("below 4.50        : %d (%.1f%%)   avg part %.1f%%" % (len(b45), len(b45) / len(rows) * 100,
                                                             st.mean([r["pct"] for r in b45])))
print("4.50 and above    : %d (%.1f%%)   avg part %.1f%%" % (len(g45), len(g45) / len(rows) * 100,
                                                             st.mean([r["pct"] for r in g45])))
