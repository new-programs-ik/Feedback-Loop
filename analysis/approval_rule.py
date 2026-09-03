"""Rule v2 - two bars decide IF, the weighted Health Score decides HOW URGENT and HOW DEEP.

  1. fewer than VOICES ratings                       -> watch (both signals too thin)
  2. rating < LINE  or  approval < APPROVAL_BAR       -> enters the queue
  3. Health = wR*R + wA*A + wT*T (0-100)              -> Urgent (<70) / Needs a look (70-<90) / Borderline (>=90)
  4. depth: reach >= REACH_BAR -> video, else transcript; Urgent goes to video whatever the reach.

Prints the Jan-Aug outcomes so the report can quote them. Local only.
"""
import datetime as dt
import os
import statistics as st
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from approval_weights import (compute, score_rating, score_approval, LINE, APPROVAL_BAR, REACH_BAR,  # noqa: E402
                              VOICES)

W = (0.6, 0.3, 0.1)      # rating / approval / track record
URGENT, BORDERLINE = 70, 90


def health(r, w=W):
    return w[0] * r["R"] + w[1] * r["A"] + w[2] * r["T"]


def band(h):
    return "Urgent" if h < URGENT else ("Needs a look" if h < BORDERLINE else "Borderline")


def verdict_v1(r):
    if r["rating"] >= LINE:
        return "none"
    if r["responses"] < VOICES:
        return "watch"
    return "video" if r["pct"] >= REACH_BAR else "transcript"


def verdict_v2(r, w=W, urgent_to_video=True, borderline_to_transcript=True):
    if r["responses"] < VOICES:
        return "watch" if (r["rating"] < LINE or r["approval"] < APPROVAL_BAR) else "none"
    if r["rating"] >= LINE and r["approval"] >= APPROVAL_BAR:
        return "none"
    h = health(r, w)
    if urgent_to_video and h < URGENT:
        return "video"
    if borderline_to_transcript and h >= BORDERLINE:
        return "transcript"
    return "video" if r["pct"] >= REACH_BAR else "transcript"


def flip_rate(rows, verdict):
    """Share of flagged classes whose verdict changes if one learner votes differently."""
    flips = n = 0
    for r in rows:
        v = verdict(r)
        if v in ("none", "watch"):
            continue
        n += 1
        k = r["responses"]
        r2 = dict(r)
        r2["rating"] = min(5.0, r["rating"] + 1.0 / k)
        if r["no"] > 0:
            r2["approval"] = (r["yes"] + 1) / k * 100
        r2["R"], r2["A"] = score_rating(r2["rating"]), score_approval(r2["approval"])
        if verdict(r2) in ("none", "watch"):
            flips += 1
    return flips / n * 100 if n else 0.0


def main():
    C = compute(verbose=False)
    rows, weeks = C["rows"], C["weeks"]
    bad = lambda r: r["rating"] < LINE              # noqa: E731
    low = lambda r: r["approval"] < APPROVAL_BAR    # noqa: E731

    v1 = Counter(verdict_v1(r) for r in rows)
    v2 = Counter(verdict_v2(r) for r in rows)
    v2b = Counter(verdict_v2(r, urgent_to_video=False, borderline_to_transcript=False) for r in rows)
    print("today's rule   :", dict(v1), " analyses/wk %.1f" % ((v1["video"] + v1["transcript"]) / weeks))
    print("rule v2        :", dict(v2), " analyses/wk %.1f" % ((v2["video"] + v2["transcript"]) / weeks))
    print("rule v2 reach  :", dict(v2b), " analyses/wk %.1f" % ((v2b["video"] + v2b["transcript"]) / weeks))
    print("flip rate: today %.0f%%  v2 %.0f%%" % (flip_rate(rows, verdict_v1), flip_rate(rows, verdict_v2)))

    queued = [r for r in rows if verdict_v2(r) in ("video", "transcript")]
    print("\nqueue %d: entered by rating only %d | approval only %d | both %d" % (
        len(queued), sum(1 for r in queued if bad(r) and not low(r)), sum(1 for r in queued if not bad(r) and low(r)),
        sum(1 for r in queued if bad(r) and low(r))))
    bands = Counter(band(health(r)) for r in queued)
    print("bands:", dict(bands))
    for b in ("Urgent", "Needs a look", "Borderline"):
        g = [r for r in queued if band(health(r)) == b]
        if g:
            print("  %-13s n=%3d  avg rating %.2f  avg approval %.0f%%  video %d transcript %d" % (
                b, len(g), st.mean(r["rating"] for r in g), st.mean(r["approval"] for r in g),
                sum(1 for r in g if verdict_v2(r) == "video"), sum(1 for r in g if verdict_v2(r) == "transcript")))
    urg_lowreach = [r for r in queued if health(r) < URGENT and r["pct"] < REACH_BAR]
    print("urgent but low reach (video by the urgency route): %d (%.1f/wk)" % (len(urg_lowreach), len(urg_lowreach) / weeks))

    # change vs today's rule
    moved_out = [r for r in rows if verdict_v1(r) in ("video", "transcript") and verdict_v2(r) not in ("video", "transcript")]
    moved_in = [r for r in rows if verdict_v1(r) not in ("video", "transcript") and verdict_v2(r) in ("video", "transcript")]
    deeper = [r for r in rows if verdict_v1(r) == "transcript" and verdict_v2(r) == "video"]
    print("vs today: moved out %d, moved in %d (all approval-only), transcript->video %d" % (len(moved_out), len(moved_in), len(deeper)))

    # weight sensitivity: how does the ORDER/BANDS change between mixes
    print("\nweight sensitivity (queue bands):")
    for w in [(0.8, 0.1, 0.1), (0.7, 0.2, 0.1), (0.6, 0.3, 0.1), (0.5, 0.4, 0.1), (0.5, 0.3, 0.2)]:
        bc = Counter(band(health(r, w)) for r in queued)
        urg = sum(1 for r in queued if health(r, w) < URGENT and r["pct"] < REACH_BAR)
        print("  R %.0f A %.0f T %.0f -> urgent %3d  look %3d  borderline %3d | urgent-route videos %d" % (
            w[0] * 100, w[1] * 100, w[2] * 100, bc["Urgent"], bc["Needs a look"], bc["Borderline"], urg))

    # by course
    print("\nby course (rule v2):")
    byc = defaultdict(list)
    for r in rows:
        byc[r["course"]].append(r)
    for c in sorted(byc, key=lambda c: -len(byc[c])):
        g = byc[c]
        if len(g) < 20:
            continue
        q = [r for r in g if verdict_v2(r) in ("video", "transcript")]
        ya = sum(r["yes"] for r in g)
        na = sum(r["no"] for r in g)
        print("  %-34s n=%4d approval %5.1f%%  queue %3d (%4.1f%%): rating-only %3d approval-only %2d both %3d | urgent %2d  video %3d transcript %3d" % (
            c[:34], len(g), ya / (ya + na) * 100, len(q), len(q) / len(g) * 100,
            sum(1 for r in q if bad(r) and not low(r)), sum(1 for r in q if not bad(r) and low(r)),
            sum(1 for r in q if bad(r) and low(r)), sum(1 for r in q if band(health(r)) == "Urgent"),
            sum(1 for r in q if verdict_v2(r) == "video"), sum(1 for r in q if verdict_v2(r) == "transcript")))

    # examples
    print("\nworked examples:")
    def show(r, label):
        print("  %s: %s %s | %s | rating %.2f  votes %.0fY/%.0fN=%.0f%%  reach %.0f/%.0f=%.0f%%  track %s | R %.0f A %.0f T %.0f -> health %.0f (%s) -> %s" % (
            label, r["date"].date(), r["course"][:20], r["instructor"][:18], r["rating"], r["yes"], r["no"], r["approval"],
            r["responses"], r["attended"], r["pct"], ("%.2f" % r["track"]) if r["track"] else "n/a", r["R"], r["A"], r["T"],
            health(r), band(health(r)), verdict_v2(r)))
    ex = [r for r in rows if r["responses"] >= VOICES]
    show(min(ex, key=lambda r: abs(r["yes"] - 13) + abs(r["no"] - 2) + abs(r["rating"] - 4.5)), "13 yes / 2 no")
    show(min([r for r in ex if not bad(r) and low(r)], key=lambda r: r["approval"]), "polite rating, no")
    show(min([r for r in ex if bad(r) and not low(r)], key=lambda r: r["rating"]), "low rating, yes")
    show(min([r for r in ex if bad(r) and low(r) and r["pct"] < REACH_BAR], key=lambda r: health(r)), "urgent, low reach")
    show(min([r for r in ex if bad(r) and not low(r) and r["track"] and r["track"] < LINE], key=lambda r: r["track"]), "repeat offender")


if __name__ == "__main__":
    main()
