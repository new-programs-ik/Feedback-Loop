"""Exploration: the instructor-approval vote (Yes/No) against the rating, Jan-Aug 2026.

Prints the raw numbers the approval study is built from. Local only.
"""
import datetime as dt
import os
import statistics as st
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ratings_data import load, GOOD  # noqa: E402

LO, HI = dt.datetime(2026, 1, 1), dt.datetime(2026, 8, 31, 23, 59, 59)
BAR = 80  # the VP's approval bar


def corr(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** .5
    return num / den if den else 0


rows = load(LO, HI)
print("rows", len(rows), "with approval", sum(1 for r in rows if r["approval"] is not None))
rows = [r for r in rows if r["approval"] is not None]
bad = lambda r: r["rating"] < GOOD           # noqa: E731
low = lambda r: r["approval"] < BAR          # noqa: E731

Y = sum(r["yes"] for r in rows)
N = sum(r["no"] for r in rows)
print("votes: yes %.0f no %.0f -> overall approval %.1f%%" % (Y, N, Y / (Y + N) * 100))
n_no = sum(1 for r in rows if r["no"] > 0)
print("classes with >=1 No: %d (%.1f%%)" % (n_no, n_no / len(rows) * 100))

print("\napproval band -> classes")
for lo, hi, l in [(100, 101, "100%"), (90, 100, "90-<100"), (80, 90, "80-<90"), (70, 80, "70-<80"),
                  (60, 70, "60-<70"), (50, 60, "50-<60"), (0, 50, "<50")]:
    g = [r for r in rows if lo <= r["approval"] < hi]
    if g:
        print("  %-8s n=%4d (%4.1f%%)  avg rating %.2f  below4.55 %3.0f%%  avg voices %.1f" % (
            l, len(g), len(g) / len(rows) * 100, st.mean(r["rating"] for r in g),
            sum(1 for r in g if bad(r)) / len(g) * 100, st.mean(r["responses"] for r in g)))

print("\nrating band -> approval")
for lo, hi, l in [(4.8, 5.01, "4.80-5.00"), (4.55, 4.8, "4.55-<4.80"), (4.4, 4.55, "4.40-<4.55"),
                  (4.2, 4.4, "4.20-<4.40"), (4.0, 4.2, "4.00-<4.20"), (3.5, 4.0, "3.50-<4.00"),
                  (0, 3.5, "<3.50")]:
    g = [r for r in rows if lo <= r["rating"] < hi]
    if g:
        ya = sum(r["yes"] for r in g)
        na = sum(r["no"] for r in g)
        print("  %-12s n=%4d mean approval %5.1f%%  pooled %5.1f%%  <80%%: %3.0f%%  ==100%%: %3.0f%%" % (
            l, len(g), st.mean(r["approval"] for r in g), ya / (ya + na) * 100,
            sum(1 for r in g if low(r)) / len(g) * 100,
            sum(1 for r in g if r["approval"] >= 100) / len(g) * 100))

print("\ncorr(rating, approval) = %.3f" % corr([r["rating"] for r in rows], [r["approval"] for r in rows]))
v5 = [r for r in rows if r["responses"] >= 5]
print("corr(rating, approval) voices>=5 = %.3f" % corr([r["rating"] for r in v5], [r["approval"] for r in v5]))
print("corr(approval, participation) = %.3f" % corr([r["pct"] for r in rows], [r["approval"] for r in rows]))

under = [r for r in rows if low(r)]
print("\n<80%% approval: %d classes (%.1f%%), with >=5 voices: %d" % (
    len(under), len(under) / len(rows) * 100, sum(1 for r in under if r["responses"] >= 5)))
m = Counter((bad(r), low(r)) for r in rows)
print("agreement: bad&low %d | bad&ok %d | fine&low %d | fine&ok %d" % (
    m[(True, True)], m[(True, False)], m[(False, True)], m[(False, False)]))
m5 = Counter((bad(r), low(r)) for r in v5)
print("  >=5 voices: bad&low %d | bad&ok %d | fine&low %d | fine&ok %d" % (
    m5[(True, True)], m5[(True, False)], m5[(False, True)], m5[(False, False)]))

print("\nvoices -> classes, <80%% share")
for v in range(1, 13):
    g = [r for r in rows if r["responses"] == v]
    if g:
        u = [r for r in g if low(r)]
        print("  %2d voices n=%4d  <80%%: %3d (%4.1f%%)  one-No approval=%.0f%%" % (
            v, len(g), len(u), len(u) / len(g) * 100, (v - 1) / v * 100))
g = [r for r in rows if r["responses"] >= 13]
u = [r for r in g if low(r)]
print("  13+ voices n=%d <80%%: %d (%.1f%%)" % (len(g), len(u), len(u) / len(g) * 100))

print("\nHIGH rating but LOW approval (>=5 voices):")
for r in sorted([r for r in rows if not bad(r) and low(r) and r["responses"] >= 5],
                key=lambda r: r["approval"])[:15]:
    print("  %s %-22s %-11s %-18s %-34s rating %.2f votes %.0fY/%.0fN = %.0f%%  resp %.0f/%.0f" % (
        r["date"].date(), r["course"][:22], r["kind"][:11], r["instructor"][:18], r["topic"][:34],
        r["rating"], r["yes"], r["no"], r["approval"], r["responses"], r["attended"]))
print("\nLOW rating but HIGH approval (>=5 voices, rating<4.3):")
for r in sorted([r for r in rows if bad(r) and not low(r) and r["responses"] >= 5 and r["rating"] < 4.3],
                key=lambda r: r["rating"])[:15]:
    print("  %s %-22s %-11s %-18s %-34s rating %.2f votes %.0fY/%.0fN = %.0f%%  resp %.0f/%.0f" % (
        r["date"].date(), r["course"][:22], r["kind"][:11], r["instructor"][:18], r["topic"][:34],
        r["rating"], r["yes"], r["no"], r["approval"], r["responses"], r["attended"]))

print("\nby course:")
byc = defaultdict(list)
for r in rows:
    byc[r["course"]].append(r)
for c in sorted(byc, key=lambda c: -len(byc[c])):
    g = byc[c]
    ya = sum(r["yes"] for r in g)
    na = sum(r["no"] for r in g)
    print("  %-34s n=%4d pooled %5.1f%%  <80%%: %3d (%4.1f%%)  below4.55: %3d  both: %3d  approval-only: %3d  rating-only: %3d" % (
        c[:34], len(g), ya / (ya + na) * 100, sum(1 for r in g if low(r)),
        sum(1 for r in g if low(r)) / len(g) * 100, sum(1 for r in g if bad(r)),
        sum(1 for r in g if bad(r) and low(r)), sum(1 for r in g if not bad(r) and low(r)),
        sum(1 for r in g if bad(r) and not low(r))))
for k in ("Live Class", "Test Review"):
    g = [r for r in rows if r["kind"] == k]
    ya = sum(r["yes"] for r in g)
    na = sum(r["no"] for r in g)
    print("  %s: n=%d pooled %.1f%%  <80%%: %d  approval-only: %d" % (
        k, len(g), ya / (ya + na) * 100, sum(1 for r in g if low(r)),
        sum(1 for r in g if not bad(r) and low(r))))

print("\nmonthly:")
for mth in range(1, 9):
    g = [r for r in rows if r["date"].month == mth]
    ya = sum(r["yes"] for r in g)
    na = sum(r["no"] for r in g)
    print("  %d: n=%d pooled %.1f%%  <80%%: %d (%.1f%%)  below4.55 %.1f%%  approval-only %d" % (
        mth, len(g), ya / (ya + na) * 100, sum(1 for r in g if low(r)),
        sum(1 for r in g if low(r)) / len(g) * 100, sum(1 for r in g if bad(r)) / len(g) * 100,
        sum(1 for r in g if not bad(r) and low(r))))

print("\napproval bar sensitivity: all / >=5 voices | extra beyond the rating rule: all / >=5")
for b in (60, 70, 75, 80, 85, 90, 95, 100.01):
    print("  <%3.0f%%: %4d / %4d | %4d / %4d" % (
        b, sum(1 for r in rows if r["approval"] < b),
        sum(1 for r in rows if r["approval"] < b and r["responses"] >= 5),
        sum(1 for r in rows if r["approval"] < b and not bad(r)),
        sum(1 for r in rows if r["approval"] < b and not bad(r) and r["responses"] >= 5)))

print("\ninstructors (>=10 classes): approval vs avg rating")
byi = defaultdict(list)
for r in rows:
    byi[r["instructor"]].append(r)
xs = []
for i, g in byi.items():
    if len(g) < 10:
        continue
    ya = sum(r["yes"] for r in g)
    na = sum(r["no"] for r in g)
    xs.append((ya / (ya + na) * 100, st.mean(r["rating"] for r in g), len(g), i, sum(1 for r in g if bad(r))))
xs.sort()
print("  corr(instructor approval, instructor avg rating) = %.3f" % corr([x[0] for x in xs], [x[1] for x in xs]))
for a, rt, n, i, b in xs[:12]:
    print("  %-24s classes %3d  approval %5.1f%%  avg rating %.2f  below4.55 %d" % (i[:24], n, a, rt, b))
print("  instructors pooled <80%%: %d of %d ; <90%%: %d" % (
    sum(1 for x in xs if x[0] < 80), len(xs), sum(1 for x in xs if x[0] < 90)))

# how often does a No appear in a class that is rated fine, and vice versa - vote-level view
print("\nwhere do the No votes live?")
for lo, hi, l in [(4.55, 5.01, ">=4.55"), (4.0, 4.55, "4.00-<4.55"), (0, 4.0, "<4.00")]:
    g = [r for r in rows if lo <= r["rating"] < hi]
    na = sum(r["no"] for r in g)
    print("  rating %-10s classes %4d  No votes %4.0f (%4.1f%% of all No)" % (l, len(g), na, na / N * 100))
