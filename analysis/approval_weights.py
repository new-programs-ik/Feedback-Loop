"""Deriving the weights for the Class Health Score - rating, approval, track record.

Three lenses, all on the same Jan-Aug 2026 rows:
  1. Redundancy      - how much of each signal is already carried by the others (correlations).
  2. Predictive power - which signal today predicts the instructor's NEXT class going wrong
                        (logistic regression, standardised, pure Python - no numpy here).
  3. Calibration      - grid over weight sets x thresholds: what each catches, what it misses,
                        how many analyses per week it costs, how stable it is to one vote.
Prints everything; the report script picks the numbers up from `compute()`.
"""
import datetime as dt
import math
import os
import statistics as st
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ratings_data import load, GOOD  # noqa: E402

LO, HI = dt.datetime(2026, 1, 1), dt.datetime(2026, 8, 31, 23, 59, 59)
LINE = GOOD          # 4.55 rating line
APPROVAL_BAR = 80    # the VP's instructor-approval bar
REACH_BAR = 40       # participation bar (depth: video vs transcript)
VOICES = 5           # voice floor
# Where each component hits 0 (its "as bad as it gets") - derived below from the data, but these
# are the rounded values the rule ships with, so that a human can hold them in their head.
R_FLOOR = 3.55       # rating a full point under the line -> 0
A_FLOOR = 40         # approval: only 4 in 10 would have the instructor back -> 0
T_FLOOR = 4.05       # instructor's average half a point under the line -> 0
T_MIN_CLASSES = 3    # need this many earlier classes before a track record counts
# The recommended weights (rating / approval / track record). Derived in compute(): the joint
# model's predictive shares for the two kinds of trouble - a low rating next class, a failed vote
# next class - averaged, because the rule has to catch both, then rounded to the nearest five.
RECOMMENDED = (0.60, 0.25, 0.15)


def clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def score_rating(rating):
    return clamp(100.0 * (rating - R_FLOOR) / (LINE - R_FLOOR))


def score_approval(approval):
    return clamp(100.0 * (approval - A_FLOOR) / (APPROVAL_BAR - A_FLOOR))


def score_track(avg):
    if avg is None:
        return 100.0          # no history -> no penalty
    return clamp(100.0 * (avg - T_FLOOR) / (LINE - T_FLOOR))


def corr(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** .5
    return num / den if den else 0.0


def zs(xs):
    m, s = st.mean(xs), st.pstdev(xs)
    return [(x - m) / s if s else 0.0 for x in xs]


def solve(A, b):
    """Gauss-Jordan for a small dense system."""
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        pv = M[c][c]
        M[c] = [v / pv for v in M[c]]
        for r in range(n):
            if r != c and M[r][c]:
                f = M[r][c]
                M[r] = [a - f * b_ for a, b_ in zip(M[r], M[c])]
    return [M[i][n] for i in range(n)]


def logistic(X, y, iters=25):
    """Newton-Raphson logistic regression. X rows already carry a leading 1."""
    k = len(X[0])
    w = [0.0] * k
    for _ in range(iters):
        g = [0.0] * k
        H = [[0.0] * k for _ in range(k)]
        for xi, yi in zip(X, y):
            z = sum(a * b for a, b in zip(w, xi))
            p = 1 / (1 + math.exp(-max(-30, min(30, z))))
            for a in range(k):
                g[a] += (p - yi) * xi[a]
                for b in range(k):
                    H[a][b] += p * (1 - p) * xi[a] * xi[b]
        for a in range(k):
            H[a][a] += 1e-6
        step = solve(H, g)
        w = [wi - si for wi, si in zip(w, step)]
        if max(abs(s) for s in step) < 1e-8:
            break
    return w


def ols(X, y):
    k = len(X[0])
    XtX = [[sum(r[a] * r[b] for r in X) for b in range(k)] for a in range(k)]
    Xty = [sum(r[a] * yi for r, yi in zip(X, y)) for a in range(k)]
    return solve(XtX, Xty)


def compute(verbose=True):
    rows = [r for r in load(LO, HI) if r["approval"] is not None]
    rows.sort(key=lambda r: (r["date"], r["instructor"], r["topic"]))
    P = print if verbose else (lambda *a, **k: None)

    # ---- track record: the instructor's average over their EARLIER classes this year ----------
    hist = defaultdict(list)
    for r in rows:
        prev = hist[r["instructor"]]
        r["track"] = st.mean(prev) if len(prev) >= T_MIN_CLASSES else None
        r["track_n"] = len(prev)
        prev.append(r["rating"])
    # the instructor's NEXT class (the outcome for lens 2)
    nxt = {}
    for r in reversed(rows):
        r["next"] = nxt.get(r["instructor"])
        nxt[r["instructor"]] = r
    for r in rows:
        r["R"] = score_rating(r["rating"])
        r["A"] = score_approval(r["approval"])
        r["T"] = score_track(r["track"])

    bad = lambda r: r["rating"] < LINE                 # noqa: E731
    low = lambda r: r["approval"] < APPROVAL_BAR       # noqa: E731
    voiced = [r for r in rows if r["responses"] >= VOICES]
    with_track = [r for r in rows if r["track"] is not None]
    P("rows %d | with >=5 voices %d | with a track record %d (%.0f%%)" % (
        len(rows), len(voiced), len(with_track), len(with_track) / len(rows) * 100))

    # ---- where the component floors come from ------------------------------------------------
    def q(xs, p):
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(p * len(xs)))]
    rd = [LINE - r["rating"] for r in rows if bad(r)]
    ad = [APPROVAL_BAR - r["approval"] for r in rows if low(r)]
    td = [LINE - r["track"] for r in with_track if r["track"] < LINE]
    P("\nDEFICIT QUANTILES among failures (50/75/90/max):")
    P("  rating   %.2f %.2f %.2f %.2f  -> floor %.2f under the line" % (q(rd, .5), q(rd, .75), q(rd, .9), max(rd), LINE - R_FLOOR))
    P("  approval %.0f %.0f %.0f %.0f  -> floor %d under the bar" % (q(ad, .5), q(ad, .75), q(ad, .9), max(ad), APPROVAL_BAR - A_FLOOR))
    P("  track    %.2f %.2f %.2f %.2f  -> floor %.2f under the line" % (q(td, .5), q(td, .75), q(td, .9), max(td), LINE - T_FLOOR))

    # ---- lens 1: redundancy --------------------------------------------------------------------
    P("\nLENS 1 - redundancy (>=5 voices, with track record):")
    sub = [r for r in voiced if r["track"] is not None]
    cRA = corr([r["R"] for r in sub], [r["A"] for r in sub])
    cRT = corr([r["R"] for r in sub], [r["T"] for r in sub])
    cAT = corr([r["A"] for r in sub], [r["T"] for r in sub])
    P("  corr R-A %.2f | R-T %.2f | A-T %.2f" % (cRA, cRT, cAT))
    # unique variance of each = 1 - R^2 when regressed on the other two
    def unique(target, others):
        X = [[1.0] + [r[o] for o in others] for r in sub]
        y = [r[target] for r in sub]
        b = ols(X, y)
        pred = [sum(a * c for a, c in zip(b, x)) for x in X]
        ssr = sum((p - yi) ** 2 for p, yi in zip(pred, y))
        sst = sum((yi - st.mean(y)) ** 2 for yi in y)
        return 1 - (1 - ssr / sst)
    uR, uA, uT = unique("R", ["A", "T"]), unique("A", ["R", "T"]), unique("T", ["R", "A"])
    P("  unique information: R %.0f%% | A %.0f%% | T %.0f%%" % (uR * 100, uA * 100, uT * 100))

    # ---- lens 2: predictive power ------------------------------------------------------------
    P("\nLENS 2 - what predicts the instructor's NEXT class (>=5 voices both sides):")
    fit = [r for r in voiced if r["next"] is not None and r["next"]["responses"] >= VOICES]
    P("  pairs: %d" % len(fit))
    feats = {"R": [r["R"] for r in fit], "A": [r["A"] for r in fit], "T": [r["T"] for r in fit]}
    Z = {k: zs(v) for k, v in feats.items()}
    X = [[1.0, Z["R"][i], Z["A"][i], Z["T"][i]] for i in range(len(fit))]
    lens2 = {}
    for name, y in (("next rated below %.2f" % LINE, [1.0 if r["next"]["rating"] < LINE else 0.0 for r in fit]),
                    ("next approval below %d%%" % APPROVAL_BAR, [1.0 if r["next"]["approval"] < APPROVAL_BAR else 0.0 for r in fit]),
                    ("next fails either", [1.0 if (r["next"]["rating"] < LINE or r["next"]["approval"] < APPROVAL_BAR) else 0.0 for r in fit])):
        w = logistic(X, y)
        # single-signal fits, for "how much does each carry alone"
        singles = {}
        for j, k in enumerate(("R", "A", "T")):
            ws = logistic([[1.0, x[j + 1]] for x in X], y)
            singles[k] = ws[1]
        tot = sum(abs(v) for v in w[1:])
        share = {k: abs(w[j + 1]) / tot * 100 for j, k in enumerate(("R", "A", "T"))}
        lens2[name] = dict(beta={k: w[j + 1] for j, k in enumerate(("R", "A", "T"))}, share=share, singles=singles,
                           base=sum(y) / len(y) * 100)
        P("  outcome '%s' (base rate %.0f%%): std betas R %+.2f A %+.2f T %+.2f  -> shares R %.0f%% A %.0f%% T %.0f%%   (alone: R %+.2f A %+.2f T %+.2f)" % (
            name, sum(y) / len(y) * 100, w[1], w[2], w[3], share["R"], share["A"], share["T"],
            singles["R"], singles["A"], singles["T"]))
    # the derived weights: average the joint shares over the two kinds of trouble, round to 5
    kr, ka = "next rated below %.2f" % LINE, "next approval below %d%%" % APPROVAL_BAR
    avg_share = {k: (lens2[kr]["share"][k] + lens2[ka]["share"][k]) / 2 for k in ("R", "A", "T")}
    derived = tuple(round(avg_share[k] / 5) * 5 / 100 for k in ("R", "A", "T"))
    P("  derived weights: average shares R %.1f A %.1f T %.1f -> rounded %.2f / %.2f / %.2f (RECOMMENDED = %s)" % (
        avg_share["R"], avg_share["A"], avg_share["T"], derived[0], derived[1], derived[2], RECOMMENDED))
    # plain-English version: next-class failure rate by this class's verdicts
    P("  next class below the line, given THIS class:")
    grp = {
        "rated fine, approval fine": [r for r in fit if not bad(r) and not low(r)],
        "rated low, approval fine": [r for r in fit if bad(r) and not low(r)],
        "rated fine, approval low": [r for r in fit if not bad(r) and low(r)],
        "rated low, approval low": [r for r in fit if bad(r) and low(r)],
    }
    lens2_groups = {}
    for k, g in grp.items():
        if g:
            nb = sum(1 for r in g if r["next"]["rating"] < LINE) / len(g) * 100
            na = sum(1 for r in g if r["next"]["approval"] < APPROVAL_BAR) / len(g) * 100
            lens2_groups[k] = (len(g), nb, na)
            P("    %-28s n=%4d  next rated low %4.0f%%  next approval low %4.0f%%" % (k, len(g), nb, na))
    grp_t = {
        "track record >= line": [r for r in fit if r["track"] is not None and r["track"] >= LINE],
        "track record < line": [r for r in fit if r["track"] is not None and r["track"] < LINE],
    }
    for k, g in grp_t.items():
        if g:
            nb = sum(1 for r in g if r["next"]["rating"] < LINE) / len(g) * 100
            lens2_groups[k] = (len(g), nb, None)
            P("    %-28s n=%4d  next rated low %4.0f%%" % (k, len(g), nb))

    # ---- lens 3: calibration grid ---------------------------------------------------------------
    P("\nLENS 3 - calibration (classes with >=5 voices; fewer voices stay 'watch')")
    weeks = ((HI - LO).days + 1) / 7.0
    consensus = [r for r in voiced if bad(r) and low(r)]                 # both signals agree
    clear = [r for r in voiced if r["rating"] < 4.40]                    # clearly under the line
    appr = [r for r in voiced if low(r)]                                 # the VP's rule
    cur = [r for r in voiced if bad(r)]                                  # today's rule
    P("  today's rule flags %d (%.1f/wk); approval rule alone %d; consensus %d; clearly-low %d" % (
        len(cur), len(cur) / weeks, len(appr), len(consensus), len(clear)))

    def health(r, w):
        return w[0] * r["R"] + w[1] * r["A"] + w[2] * r["T"]

    def flip_rate(w, thr):
        """Share of flagged classes whose verdict flips if ONE vote changes (No->Yes or a
        single 5->4 rating). Stability of the rule to a single opinion."""
        flips = 0
        n = 0
        for r in voiced:
            h = health(r, w)
            flagged = h < thr
            if not flagged:
                continue
            n += 1
            v = r["responses"]
            # one No becomes a Yes; one rating point rises by 1/v (a single 4->5)
            appr2 = min(100.0, (r["yes"] + 1) / v * 100) if r["no"] > 0 else r["approval"]
            rat2 = min(5.0, r["rating"] + 1.0 / v)
            h2 = w[0] * score_rating(rat2) + w[1] * score_approval(appr2) + w[2] * r["T"]
            if h2 >= thr:
                flips += 1
        return flips / n * 100 if n else 0

    results = []
    grid = []
    for wr in range(30, 85, 5):
        for wa in range(10, 60, 5):
            wt = 100 - wr - wa
            if 0 <= wt <= 30:
                grid.append((wr / 100, wa / 100, wt / 100))
    thresholds = [80, 82.5, 85, 87.5, 90, 92.5, 95]
    for w in grid:
        for thr in thresholds:
            flagged = [r for r in voiced if health(r, w) < thr]
            fs = set(id(r) for r in flagged)
            res = dict(
                w=w, thr=thr, n=len(flagged), perweek=len(flagged) / weeks,
                miss_consensus=sum(1 for r in consensus if id(r) not in fs),
                miss_clear=sum(1 for r in clear if id(r) not in fs),
                miss_appr=sum(1 for r in appr if id(r) not in fs),
                miss_cur=sum(1 for r in cur if id(r) not in fs),
                added=sum(1 for r in flagged if not bad(r)),
                flip=None,
            )
            results.append(res)
    # feasible = misses nothing the two signals agree on, nothing clearly low
    feasible = [x for x in results if x["miss_consensus"] == 0 and x["miss_clear"] == 0]
    P("  grid: %d settings, %d feasible (miss no consensus-bad and no clearly-low class)" % (len(results), len(feasible)))
    feasible.sort(key=lambda x: (x["n"], x["miss_appr"]))
    P("  leanest feasible settings (fewest analyses while catching every consensus/clear case):")
    for x in feasible[:12]:
        x["flip"] = flip_rate(x["w"], x["thr"])
        P("    R %.0f A %.0f T %.0f thr %.1f -> flags %4d (%.1f/wk)  misses: approval-rule %3d  today's-rule %3d | added beyond today %3d | one-vote flips %.0f%%" % (
            x["w"][0] * 100, x["w"][1] * 100, x["w"][2] * 100, x["thr"], x["n"], x["perweek"],
            x["miss_appr"], x["miss_cur"], x["added"], x["flip"]))

    # a fixed threshold, what each weight family does (for the report's table)
    P("\n  at threshold 90 - how the weight mix changes the outcome:")
    table90 = []
    for w in [(0.8, 0.1, 0.1), (0.7, 0.2, 0.1), (0.6, 0.3, 0.1), RECOMMENDED, (0.5, 0.4, 0.1), (0.5, 0.3, 0.2), (0.6, 0.2, 0.2), (0.4, 0.4, 0.2)]:
        x = next(y for y in results if y["w"] == w and y["thr"] == 90)
        x["flip"] = flip_rate(w, 90)
        table90.append(x)
        P("    R %.0f A %.0f T %.0f -> flags %4d (%.1f/wk)  misses: consensus %2d clear %2d approval-rule %3d today's %3d | added %3d | flips %.0f%%" % (
            w[0] * 100, w[1] * 100, w[2] * 100, x["n"], x["perweek"], x["miss_consensus"], x["miss_clear"],
            x["miss_appr"], x["miss_cur"], x["added"], x["flip"]))
    P("\n  the recommended mix across thresholds:")
    table_thr = []
    for thr in thresholds:
        x = next(y for y in results if y["w"] == RECOMMENDED and y["thr"] == thr)
        x["flip"] = flip_rate(x["w"], thr)
        table_thr.append(x)
        P("    thr %.1f -> flags %4d (%.1f/wk)  misses: consensus %2d clear %2d approval-rule %3d today's %3d | added %3d | flips %.0f%%" % (
            thr, x["n"], x["perweek"], x["miss_consensus"], x["miss_clear"], x["miss_appr"], x["miss_cur"], x["added"], x["flip"]))

    return dict(rows=rows, voiced=voiced, results=results, feasible=feasible, table90=table90, table_thr=table_thr,
                lens1=dict(cRA=cRA, cRT=cRT, cAT=cAT, uR=uR, uA=uA, uT=uT), lens2=lens2, lens2_groups=lens2_groups,
                avg_share=avg_share, derived=derived,
                weeks=weeks, health=health, deficits=dict(r=rd, a=ad, t=td))


if __name__ == "__main__":
    compute()
