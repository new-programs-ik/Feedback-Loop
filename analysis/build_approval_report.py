"""Builds the local HTML report for the instructor-approval study (Jan-Aug 2026).

"Does the room want the instructor back?" - the Yes/No vote against the rating, the VP's 80% bar,
and the weights for the combined Class Health Score. Local only: the workbook is confidential, so
nothing here is committed or published. Charts are inline SVG so the PDF renders offline.
"""
import os
import statistics as st
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from approval_weights import (compute, LINE, APPROVAL_BAR, REACH_BAR, VOICES,  # noqa: E402
                              R_FLOOR, A_FLOOR, T_FLOOR, T_MIN_CLASSES)
from approval_rule import (W, URGENT, BORDERLINE, health, band, verdict_v1, verdict_v2,  # noqa: E402
                           flip_rate)

BLUE, ORANGE = "#2a78d6", "#eb6834"
GREEN = "#2f9e6e"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"]

C = compute(verbose=False)
rows, weeks = C["rows"], C["weeks"]
bad = lambda r: r["rating"] < LINE              # noqa: E731
low = lambda r: r["approval"] < APPROVAL_BAR    # noqa: E731
voiced = [r for r in rows if r["responses"] >= VOICES]


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def corr(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** .5
    return num / den if den else 0.0


# ------------------------------------------------------------------ headline numbers
Y = sum(r["yes"] for r in rows)
N = sum(r["no"] for r in rows)
n = len(rows)
approval_all = Y / (Y + N) * 100
under = [r for r in rows if low(r)]
under5 = [r for r in under if r["responses"] >= VOICES]
badrows = [r for r in rows if bad(r)]
bad_ok = [r for r in badrows if not low(r)]
fine_low = [r for r in rows if not bad(r) and low(r)]
fine_low5 = [r for r in fine_low if r["responses"] >= VOICES]
both = [r for r in rows if bad(r) and low(r)]
c_ra = corr([r["rating"] for r in rows], [r["approval"] for r in rows])
c_ra5 = corr([r["rating"] for r in voiced], [r["approval"] for r in voiced])
c_ap = corr([r["pct"] for r in rows], [r["approval"] for r in rows])
no_in_fine = sum(r["no"] for r in rows if not bad(r))
n100 = sum(1 for r in rows if r["approval"] >= 100)


# ------------------------------------------------------------------ chart: scatter rating x approval
def scatter():
    W_, H_ = 720, 430
    ml, mr, mt, mb = 54, 18, 30, 44
    pw, ph = W_ - ml - mr, H_ - mt - mb
    x = lambda r: ml + (r - 3.0) / 2.0 * pw       # noqa: E731
    y = lambda a: mt + (100 - a) / 100 * ph        # noqa: E731
    p = ['<svg viewBox="0 0 %d %d" role="img" aria-label="Every class plotted by rating against '
         'the share who would have the instructor back. The %.2f rating line and the %d percent '
         'approval bar split the cloud into four: most classes sit top-right, fine on both; a '
         'bottom-left corner fails both; and two thin strips disagree.">' % (W_, H_, LINE, APPROVAL_BAR)]
    for a in (0, 20, 40, 60, 80, 100):
        p.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="var(--grid)"/>' % (ml, y(a), W_ - mr, y(a)))
        p.append('<text x="%d" y="%.1f" text-anchor="end" class="tick">%d%%</text>' % (ml - 8, y(a) + 4, a))
    for rt in (3.0, 3.5, 4.0, 4.5, 5.0):
        p.append('<text x="%.1f" y="%d" text-anchor="middle" class="tick">%.1f</text>' % (x(rt), H_ - mb + 20, rt))
    # quadrant shading: fails both
    p.append('<rect x="%d" y="%.1f" width="%.1f" height="%.1f" fill="%s" fill-opacity=".08"/>'
             % (ml, y(APPROVAL_BAR), x(LINE) - ml, mt + ph - y(APPROVAL_BAR), ORANGE))
    # jitter deterministic by index so identical (rating, approval) pairs don't hide each other
    for i, r in enumerate(rows):
        jx = ((i * 7919) % 11 - 5) * 0.35
        jy = ((i * 104729) % 11 - 5) * 0.35
        col = ORANGE if (bad(r) and low(r)) else (BLUE if (not bad(r) and not low(r)) else "var(--ink3)")
        p.append('<circle cx="%.1f" cy="%.1f" r="2.2" fill="%s" fill-opacity=".55"/>'
                 % (x(max(3.0, r["rating"])) + jx, y(r["approval"]) + jy, col))
    p.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s" stroke-width="1.5" stroke-dasharray="5 4"/>'
             % (x(LINE), mt, x(LINE), mt + ph, ORANGE))
    p.append('<text x="%.1f" y="%d" class="gate" text-anchor="start">%.2f line</text>' % (x(LINE) + 6, mt + 12, LINE))
    p.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s" stroke-width="1.5" stroke-dasharray="5 4"/>'
             % (ml, y(APPROVAL_BAR), W_ - mr, y(APPROVAL_BAR), ORANGE))
    p.append('<text x="%d" y="%.1f" class="gate" text-anchor="end">%d%% bar</text>' % (W_ - mr - 4, y(APPROVAL_BAR) - 6, APPROVAL_BAR))
    p.append('<text x="%.1f" y="%.1f" class="note">fails both (%d)</text>' % (ml + 8, mt + ph - 10, len(both)))
    p.append('<text x="%.1f" y="%.1f" class="note">hard class, good teacher (%d)</text>'
             % (ml + 8, y(93), len(bad_ok)))
    p.append('<text x="%.1f" y="%.1f" class="note" text-anchor="end">polite rating, would not have them back (%d)</text>'
             % (W_ - mr - 4, y(14), len(fine_low)))
    p.append('<text x="%d" y="%d" class="axis" transform="rotate(-90 14 %d)" text-anchor="middle">would have the instructor back</text>'
             % (14, mt + ph / 2, mt + ph / 2))
    p.append('<text x="%.1f" y="%d" class="axis" text-anchor="middle">class rating</text>' % (ml + pw / 2, H_ - 6))
    p.append('</svg>')
    return "".join(p)


# ------------------------------------------------------------------ chart: approval by rating band
BANDS = [(4.8, 5.01, "4.80&ndash;5.00"), (4.55, 4.8, "4.55&ndash;4.79"), (4.4, 4.55, "4.40&ndash;4.54"),
         (4.2, 4.4, "4.20&ndash;4.39"), (4.0, 4.2, "4.00&ndash;4.19"), (3.5, 4.0, "3.50&ndash;3.99"), (0, 3.5, "under 3.50")]


def band_chart():
    W_, H_ = 720, 260
    ml, mr, mt, mb = 54, 18, 26, 46
    pw, ph = W_ - ml - mr, H_ - mt - mb
    groups = [(l, [r for r in rows if lo <= r["rating"] < hi]) for lo, hi, l in BANDS]
    p = ['<svg viewBox="0 0 %d %d" role="img" aria-label="Share of classes under the %d percent '
         'approval bar, by rating band. Almost none above %.2f, then it climbs steeply: about a '
         'quarter of classes rated 4.40 to 4.54, and more than four in five under 4.0.">' % (W_, H_, APPROVAL_BAR, LINE)]
    for v in (0, 25, 50, 75, 100):
        yy = mt + ph - v / 100 * ph
        p.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="var(--grid)"/>' % (ml, yy, W_ - mr, yy))
        p.append('<text x="%d" y="%.1f" text-anchor="end" class="tick">%d%%</text>' % (ml - 8, yy + 4, v))
    w = pw / len(groups) - 12
    for i, (l, g) in enumerate(groups):
        share = sum(1 for r in g if low(r)) / len(g) * 100 if g else 0
        bx = ml + i * (pw / len(groups)) + 6
        bh = share / 100 * ph
        p.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="3" fill="%s"/>'
                 % (bx, mt + ph - bh, w, bh, ORANGE if share >= 50 else BLUE))
        p.append('<text x="%.1f" y="%.1f" text-anchor="middle" class="pctlab" style="fill:var(--ink)">%.0f%%</text>'
                 % (bx + w / 2, mt + ph - bh - 6, share))
        p.append('<text x="%.1f" y="%d" text-anchor="middle" class="tick">%s</text>' % (bx + w / 2, H_ - mb + 16, l))
        p.append('<text x="%.1f" y="%d" text-anchor="middle" class="tick">%d classes</text>' % (bx + w / 2, H_ - mb + 30, len(g)))
    p.append('</svg>')
    return "".join(p)


# ------------------------------------------------------------------ chart: small-room trap
def voices_chart():
    W_, H_ = 720, 240
    ml, mr, mt, mb = 54, 18, 26, 40
    pw, ph = W_ - ml - mr, H_ - mt - mb
    groups = []
    for v in range(1, 13):
        groups.append((str(v), [r for r in rows if r["responses"] == v]))
    groups.append(("13+", [r for r in rows if r["responses"] >= 13]))
    p = ['<svg viewBox="0 0 %d %d" role="img" aria-label="Share of classes under the approval bar by '
         'number of people who voted. With two to four voters a single No fails the bar, so the '
         'share spikes to 8 to 16 percent; from five voters it settles around 8 percent.">' % (W_, H_)]
    for v in (0, 5, 10, 15, 20):
        yy = mt + ph - v / 20 * ph
        p.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="var(--grid)"/>' % (ml, yy, W_ - mr, yy))
        p.append('<text x="%d" y="%.1f" text-anchor="end" class="tick">%d%%</text>' % (ml - 8, yy + 4, v))
    w = pw / len(groups) - 8
    for i, (l, g) in enumerate(groups):
        share = sum(1 for r in g if low(r)) / len(g) * 100 if g else 0
        bx = ml + i * (pw / len(groups)) + 4
        bh = min(share, 20) / 20 * ph
        p.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="3" fill="%s"/>'
                 % (bx, mt + ph - bh, w, bh, ORANGE if i in (1, 2, 3) else BLUE))
        p.append('<text x="%.1f" y="%.1f" text-anchor="middle" class="tick" style="fill:var(--ink)">%.0f%%</text>'
                 % (bx + w / 2, mt + ph - bh - 5, share))
        p.append('<text x="%.1f" y="%d" text-anchor="middle" class="tick">%s</text>' % (bx + w / 2, H_ - mb + 16, l))
    p.append('<text x="%.1f" y="%d" class="axis" text-anchor="middle">people who voted</text>' % (ml + pw / 2, H_ - 4))
    p.append('</svg>')
    return "".join(p)


# ------------------------------------------------------------------ chart: monthly two lines
def monthly_chart():
    W_, H_ = 720, 250
    ml, mr, mt, mb = 54, 18, 24, 36
    pw, ph = W_ - ml - mr, H_ - mt - mb
    pts_bar, pts_line = [], []
    for m in range(1, 9):
        g = [r for r in rows if r["date"].month == m]
        pts_bar.append(sum(1 for r in g if low(r)) / len(g) * 100)
        pts_line.append(sum(1 for r in g if bad(r)) / len(g) * 100)
    x = lambda i: ml + i / 7 * pw               # noqa: E731
    y = lambda v: mt + ph - v / 30 * ph          # noqa: E731
    p = ['<svg viewBox="0 0 %d %d" role="img" aria-label="Monthly share of classes under the '
         '%.2f rating line and under the %d percent approval bar. Both climb across the year: '
         'rating from %.0f to %.0f percent, approval from %.0f to %.0f percent.">'
         % (W_, H_, LINE, APPROVAL_BAR, pts_line[0], pts_line[-1], pts_bar[0], pts_bar[-1])]
    for v in (0, 10, 20, 30):
        p.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="var(--grid)"/>' % (ml, y(v), W_ - mr, y(v)))
        p.append('<text x="%d" y="%.1f" text-anchor="end" class="tick">%d%%</text>' % (ml - 8, y(v) + 4, v))
    for i in range(8):
        p.append('<text x="%.1f" y="%d" text-anchor="middle" class="tick">%s</text>' % (x(i), H_ - mb + 18, MONTHS[i]))
    for pts, col, lab in ((pts_line, ORANGE, "under %.2f" % LINE), (pts_bar, BLUE, "under %d%% approval" % APPROVAL_BAR)):
        d = " ".join("%s%.1f,%.1f" % ("M" if i == 0 else "L", x(i), y(v)) for i, v in enumerate(pts))
        p.append('<path d="%s" fill="none" stroke="%s" stroke-width="2.5"/>' % (d, col))
        for i, v in enumerate(pts):
            p.append('<circle cx="%.1f" cy="%.1f" r="3.5" fill="%s"/>' % (x(i), y(v), col))
        p.append('<text x="%.1f" y="%.1f" class="barlab" style="fill:%s" text-anchor="end">%s %.0f%%</text>'
                 % (x(7) - 8, y(pts[-1]) - 8, col, lab, pts[-1]))
    p.append('</svg>')
    return "".join(p)


# ------------------------------------------------------------------ chart: health score bands
def health_chart():
    queued = [r for r in rows if verdict_v2(r) in ("video", "transcript")]
    W_, H_ = 720, 230
    ml, mr, mt, mb = 54, 18, 24, 40
    pw, ph = W_ - ml - mr, H_ - mt - mb
    bins = list(range(0, 101, 5))
    counts = [0] * (len(bins) - 1)
    for r in queued:
        h = min(99.99, health(r))
        counts[int(h // 5)] += 1
    mx = max(counts)
    p = ['<svg viewBox="0 0 %d %d" role="img" aria-label="Health score of the %d classes in the queue, '
         'in bands of five points. Most sit between 85 and 100, the borderline band; a long tail '
         'runs down to near zero, the urgent band.">' % (W_, H_, len(queued))]
    w = pw / len(counts) - 3
    for i, c in enumerate(counts):
        lo = bins[i]
        col = ORANGE if lo < URGENT else (BLUE if lo >= BORDERLINE else "var(--ink3)")
        bx = ml + i * (pw / len(counts)) + 1.5
        bh = c / mx * ph if mx else 0
        p.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="2" fill="%s"/>' % (bx, mt + ph - bh, w, bh, col))
        if c:
            p.append('<text x="%.1f" y="%.1f" text-anchor="middle" class="tick">%d</text>' % (bx + w / 2, mt + ph - bh - 4, c))
    for v in (0, 20, 40, 60, 80, 100):
        p.append('<text x="%.1f" y="%d" text-anchor="middle" class="tick">%d</text>' % (ml + v / 100 * pw, H_ - mb + 16, v))
    for v, lab in ((URGENT, "urgent below %d" % URGENT), (BORDERLINE, "borderline from %d" % BORDERLINE)):
        xx = ml + v / 100 * pw
        p.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s" stroke-dasharray="5 4"/>' % (xx, mt, xx, mt + ph, ORANGE))
        p.append('<text x="%.1f" y="%d" class="gate" text-anchor="end">%s</text>' % (xx - 6, mt + 12, lab))
    p.append('<text x="%.1f" y="%d" class="axis" text-anchor="middle">Class Health Score (100 = at or above every bar)</text>' % (ml + pw / 2, H_ - 4))
    p.append('</svg>')
    return "".join(p)


# ------------------------------------------------------------------ tables
def approval_band_rows():
    out = ""
    for lo, hi, l in [(100, 101, "100% &mdash; nobody said no"), (90, 100, "90&ndash;99%"), (80, 90, "80&ndash;89%"),
                      (70, 80, "70&ndash;79%"), (60, 70, "60&ndash;69%"), (50, 60, "50&ndash;59%"), (0, 50, "under 50%")]:
        g = [r for r in rows if lo <= r["approval"] < hi]
        if not g:
            continue
        cls = " class='warnrow'" if lo < APPROVAL_BAR else ""
        out += ("<tr%s><td>%s</td><td class='n'>%d</td><td class='n'>%.1f%%</td><td class='n'>%.2f</td>"
                "<td class='n'>%.0f%%</td><td class='n'>%.1f</td></tr>"
                % (cls, l, len(g), len(g) / n * 100, st.mean(r["rating"] for r in g),
                   sum(1 for r in g if bad(r)) / len(g) * 100, st.mean(r["responses"] for r in g)))
    return out


def rating_band_rows():
    out = ""
    for lo, hi, l in BANDS:
        g = [r for r in rows if lo <= r["rating"] < hi]
        if not g:
            continue
        ya = sum(r["yes"] for r in g)
        na = sum(r["no"] for r in g)
        out += ("<tr><td>%s</td><td class='n'>%d</td><td class='n'>%.1f%%</td><td class='n'>%.0f%%</td>"
                "<td class='n'>%.0f%%</td></tr>"
                % (l, len(g), ya / (ya + na) * 100, sum(1 for r in g if r["approval"] >= 100) / len(g) * 100,
                   sum(1 for r in g if low(r)) / len(g) * 100))
    return out


def bar_rows():
    out = ""
    for b in (70, 75, 80, 85, 90):
        cls = " class='pickrow'" if b == APPROVAL_BAR else ""
        a = [r for r in voiced if r["approval"] < b]
        extra = [r for r in a if not bad(r)]
        out += ("<tr%s><td>under %d%%</td><td class='n'>%d</td><td class='n'>%.1f%%</td><td class='n'>%d</td>"
                "<td class='n'>%.1f / week</td></tr>"
                % (cls, b, len(a), len(a) / len(voiced) * 100, len(extra), len(extra) / weeks))
    return out


def listing(group, limit=8):
    out = ""
    for r in group[:limit]:
        out += ("<tr><td>%s</td><td>%s</td><td>%s</td><td class='n'>%.2f</td><td class='n'>%.0f yes / %.0f no</td>"
                "<td class='n'>%.0f%%</td><td class='n'>%.0f of %.0f</td></tr>"
                % (r["date"].strftime("%d %b"), esc(r["course"]), esc(r["instructor"]), r["rating"],
                   r["yes"], r["no"], r["approval"], r["responses"], r["attended"]))
    return out


def course_rows():
    byc = defaultdict(list)
    for r in rows:
        byc[r["course"]].append(r)
    out = ""
    for c in sorted(byc, key=lambda c: -len([r for r in byc[c] if verdict_v2(r) in ("video", "transcript")])):
        g = byc[c]
        if len(g) < 20:
            continue
        ya = sum(r["yes"] for r in g)
        na = sum(r["no"] for r in g)
        q = [r for r in g if verdict_v2(r) in ("video", "transcript")]
        out += ("<tr><td>%s</td><td class='n'>%d</td><td class='n'>%.1f%%</td><td class='n'>%d</td>"
                "<td class='n'>%d</td><td class='n'>%d</td><td class='n'><b style='color:%s'>%d</b></td>"
                "<td class='n'>%d</td><td class='n'>%d</td><td class='n'>%d</td></tr>"
                % (esc(c), len(g), ya / (ya + na) * 100, sum(1 for r in g if low(r)),
                   sum(1 for r in q if bad(r) and not low(r)), sum(1 for r in q if not bad(r) and low(r)),
                   ORANGE, sum(1 for r in q if bad(r) and low(r)),
                   sum(1 for r in q if band(health(r)) == "Urgent"),
                   sum(1 for r in q if verdict_v2(r) == "video"), sum(1 for r in q if verdict_v2(r) == "transcript")))
    return out


def monthly_rows():
    out = ""
    for m in range(1, 9):
        g = [r for r in rows if r["date"].month == m]
        ya = sum(r["yes"] for r in g)
        na = sum(r["no"] for r in g)
        q = [r for r in g if verdict_v2(r) in ("video", "transcript")]
        out += ("<tr><td>%s</td><td class='n'>%d</td><td class='n'>%.1f%%</td><td class='n'>%d (%.0f%%)</td>"
                "<td class='n'>%d (%.0f%%)</td><td class='n'>%d</td><td class='n'>%d</td><td class='n'>%d</td></tr>"
                % (MONTHS[m - 1], len(g), ya / (ya + na) * 100,
                   sum(1 for r in g if bad(r)), sum(1 for r in g if bad(r)) / len(g) * 100,
                   sum(1 for r in g if low(r)), sum(1 for r in g if low(r)) / len(g) * 100,
                   sum(1 for r in g if not bad(r) and low(r) and r["responses"] >= VOICES),
                   sum(1 for r in q if band(health(r)) == "Urgent"), len(q)))
    return out


def instructor_rows():
    byi = defaultdict(list)
    for r in rows:
        byi[r["instructor"]].append(r)
    xs = []
    for i, g in byi.items():
        if len(g) < 10:
            continue
        ya = sum(r["yes"] for r in g)
        na = sum(r["no"] for r in g)
        xs.append((ya / (ya + na) * 100, i, g, na))
    xs.sort()
    out = ""
    for a, i, g, na in xs:
        if a >= 90:
            break
        cls = " class='warnrow'" if a < APPROVAL_BAR else ""
        out += ("<tr%s><td>%s</td><td class='n'>%d</td><td class='n'>%.0f</td><td class='n'>%.1f%%</td>"
                "<td class='n'>%.2f</td><td class='n'>%d</td><td class='n'>%d</td></tr>"
                % (cls, esc(i), len(g), na, a, st.mean(r["rating"] for r in g),
                   sum(1 for r in g if bad(r)), sum(1 for r in g if low(r))))
    return out, len(xs), sum(1 for x in xs if x[0] < APPROVAL_BAR), sum(1 for x in xs if x[0] < 90)


def lens2_rows():
    G = C["lens2_groups"]
    out = ""
    for k, label in (("rated fine, approval fine", "Rated %.2f+ and %d%%+ approval" % (LINE, APPROVAL_BAR)),
                     ("rated low, approval fine", "Rated under %.2f, approval fine" % LINE),
                     ("rated fine, approval low", "Rated fine, approval under %d%%" % APPROVAL_BAR),
                     ("rated low, approval low", "Fails both")):
        nn, nb, na = G[k]
        cls = " class='warnrow'" if k == "rated low, approval low" else ""
        out += "<tr%s><td>%s</td><td class='n'>%d</td><td class='n'>%.0f%%</td><td class='n'>%.0f%%</td></tr>" % (cls, label, nn, nb, na)
    return out


def track_rows():
    G = C["lens2_groups"]
    a, b = G["track record >= line"], G["track record < line"]
    return ("<tr><td>Instructor's earlier classes average %.2f or above</td><td class='n'>%d</td><td class='n'>%.0f%%</td></tr>"
            "<tr class='warnrow'><td>Instructor's earlier classes average under %.2f</td><td class='n'>%d</td><td class='n'>%.0f%%</td></tr>"
            % (LINE, a[0], a[1], LINE, b[0], b[1]))


def pure_score_rows():
    out = ""
    for x in C["table_thr"]:
        if x["thr"] not in (85, 90, 95):
            continue
        w = x["w"]
        out += ("<tr><td>score under %.0f</td><td class='n'>%d (%.1f / wk)</td><td class='n'>%d</td>"
                "<td class='n'>%d</td><td class='n'>%d</td></tr>"
                % (x["thr"], x["n"], x["perweek"], x["miss_cur"], x["miss_appr"], x["miss_consensus"]))
    return out


def weights_rows():
    queued = [r for r in rows if verdict_v2(r) in ("video", "transcript")]
    out = ""
    for w in [(0.8, 0.1, 0.1), (0.7, 0.2, 0.1), (0.6, 0.3, 0.1), (0.5, 0.4, 0.1), (0.5, 0.3, 0.2)]:
        bc = Counter(band(health(r, w)) for r in queued)
        vid = sum(1 for r in queued if verdict_v2(r, w) == "video")
        cls = " class='pickrow'" if w == W else ""
        out += ("<tr%s><td>%.0f / %.0f / %.0f</td><td class='n'>%d</td><td class='n'>%d</td><td class='n'>%d</td>"
                "<td class='n'>%d</td><td class='n'>%d</td></tr>"
                % (cls, w[0] * 100, w[1] * 100, w[2] * 100, bc["Urgent"], bc["Needs a look"], bc["Borderline"],
                   vid, len(queued) - vid))
    return out


def outcome_rows():
    v1 = Counter(verdict_v1(r) for r in rows)
    v2 = Counter(verdict_v2(r) for r in rows)
    v2b = Counter(verdict_v2(r, urgent_to_video=False, borderline_to_transcript=False) for r in rows)
    out = ""
    for label, c, cls in (("Today's rule (rating + reach)", v1, ""),
                          ("Rule v2 &mdash; recommended", v2, " class='pickrow'"),
                          ("Rule v2, depth by reach only", v2b, " class='dim'")):
        work = c["video"] + c["transcript"]
        cost = (c["video"] * 0.70 + c["transcript"] * 0.51) / 8
        out += ("<tr%s><td>%s</td><td class='n'>%d</td><td class='n'>%d</td><td class='n'>%d</td>"
                "<td class='n'>%d</td><td class='n'>%.1f</td><td class='n'>$%.0f</td></tr>"
                % (cls, label, c["watch"], c["video"], c["transcript"], work, work / weeks, cost))
    return out, v1, v2


def example_card(r, title, verdict_text):
    return ("<div class='card'><p style='margin:0 0 4px'><b>%s.</b> %s &mdash; %s, %s. Rating <b>%.2f</b>, "
            "vote <b>%.0f yes / %.0f no (%.0f%%)</b>, %.0f of %.0f rated it (%.0f%%)%s.</p>"
            "<p style='margin:0' class='sub'>Rating score %.0f &middot; approval score %.0f &middot; track record %.0f "
            "&rarr; <b>Health %.0f &mdash; %s</b>. &rarr; <b>%s</b></p></div>"
            % (title, esc(r["course"]), esc(r["instructor"]), r["date"].strftime("%d %b"), r["rating"], r["yes"], r["no"],
               r["approval"], r["responses"], r["attended"], r["pct"],
               (", earlier classes average %.2f" % r["track"]) if r["track"] else "",
               r["R"], r["A"], r["T"], health(r), band(health(r)), verdict_text))


ex13 = min(voiced, key=lambda r: abs(r["yes"] - 13) + abs(r["no"] - 2) + abs(r["rating"] - 4.5))
ex_polite = min([r for r in voiced if not bad(r) and low(r)], key=lambda r: r["approval"])
ex_hard = min([r for r in voiced if bad(r) and not low(r)], key=lambda r: r["rating"])
ex_urgent = min([r for r in voiced if bad(r) and low(r) and r["pct"] < REACH_BAR], key=lambda r: health(r))
ex_repeat = min([r for r in voiced if bad(r) and not low(r) and r["track"] and r["track"] < LINE], key=lambda r: r["track"])


def vtext(r):
    v = verdict_v2(r)
    if v == "video":
        return "Video analysis" + (" (urgent, whatever the reach)" if health(r) < URGENT and r["pct"] < REACH_BAR else "")
    if v == "transcript":
        return "Transcript analysis first" + (" (borderline, even though reach is fine)" if health(r) >= BORDERLINE and r["pct"] >= REACH_BAR else "")
    return v


outcomes, V1, V2 = outcome_rows()
ins_rows, ins_n, ins_lt80, ins_lt90 = instructor_rows()
queued = [r for r in rows if verdict_v2(r) in ("video", "transcript")]
bands_c = Counter(band(health(r)) for r in queued)
urgent_lowreach = [r for r in queued if health(r) < URGENT and r["pct"] < REACH_BAR]
borderline_highreach = [r for r in queued if health(r) >= BORDERLINE and r["pct"] >= REACH_BAR]
L1, L2 = C["lens1"], C["lens2"]
l2r = L2["next rated below %.2f" % LINE]
l2a = L2["next approval below %d%%" % APPROVAL_BAR]
flip1, flip2 = flip_rate(rows, verdict_v1), flip_rate(rows, verdict_v2)
jan, aug = [r for r in rows if r["date"].month == 1], [r for r in rows if r["date"].month == 8]
tr_cov = sum(1 for r in rows if r["track"] is not None) / n * 100
v4 = [r for r in rows if r["responses"] == 4]
v5 = [r for r in rows if r["responses"] == 5]

HTML = """<title>Instructor Approval Study</title>
<style>
:root{--bg:#f7f7f5;--surface:#fff;--surface2:#f2f2ef;--ink:#16161a;--ink2:#4b4b53;
  --ink3:#7a7a85;--grid:#e2e2dd;--line:#dededa;--brand:%(BLUE)s;--warn:%(ORANGE)s;--radius:12px}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#131315;--surface:#1b1b1e;
  --surface2:#232326;--ink:#f3f3f5;--ink2:#bdbdc4;--ink3:#8c8c95;--grid:#33333a;--line:#33333a;
  --brand:#3987e5;--warn:#d95926}}
:root[data-theme="dark"]{--bg:#131315;--surface:#1b1b1e;--surface2:#232326;--ink:#f3f3f5;
  --ink2:#bdbdc4;--ink3:#8c8c95;--grid:#33333a;--line:#33333a;--brand:#3987e5;--warn:#d95926}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 ui-sans-serif,system-ui,
  "Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:860px;margin:0 auto;padding:44px 28px 72px}
h1{font-size:33px;line-height:1.12;letter-spacing:-.02em;margin:0 0 6px}
h2{font-size:21px;letter-spacing:-.01em;margin:40px 0 10px;padding-top:14px;border-top:1px solid var(--line)}
h3{font-size:16px;margin:24px 0 6px}
.kicker{font-size:11.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;
  color:var(--brand);margin-bottom:10px}
.sub{color:var(--ink2);font-size:12.5px;font-weight:400}
p{margin:10px 0}
.lede{font-size:17.5px;color:var(--ink2)}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);
  padding:18px 20px;margin:16px 0}
.finding{border-left:4px solid var(--warn)}
.ok{border-left:4px solid %(BLUE)s}
.figure{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);
  padding:16px 14px 8px;margin:18px 0}
.figure svg{display:block;width:100%%;height:auto}
.cap{color:var(--ink2);font-size:13px;padding:6px 4px 4px}
.legend{display:flex;gap:18px;padding:2px 4px 10px;font-size:13px;color:var(--ink2);flex-wrap:wrap}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%%;margin-right:6px;vertical-align:-1px}
.tick{font-size:11px;fill:var(--ink3)}
.axis{font-size:12px;fill:var(--ink2)}
.note{font-size:11.5px;fill:var(--ink3)}
.gate{font-size:12px;font-weight:700;fill:%(ORANGE)s}
.barlab{font-size:12px;font-weight:700;fill:%(BLUE)s}
.pctlab{font-size:11.5px;font-weight:700;fill:%(ORANGE)s}
table{width:100%%;border-collapse:collapse;margin:10px 0;font-size:14px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--ink2);
  background:var(--surface2)}
td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tr.pickrow td{background:color-mix(in srgb,%(BLUE)s 10%%,transparent);font-weight:650}
tr.warnrow td{background:color-mix(in srgb,%(ORANGE)s 9%%,transparent)}
tr.dim td{color:var(--ink2)}
.formula{background:var(--surface2);border-radius:var(--radius);padding:16px 20px;margin:14px 0;
  font-size:15px}
.formula b{font-size:15.5px}
.big{display:flex;gap:14px;flex-wrap:wrap;margin:14px 0}
.stat{flex:1 1 150px;background:var(--surface);border:1px solid var(--line);
  border-radius:var(--radius);padding:14px 16px}
.stat .v{font-size:27px;font-weight:750;letter-spacing:-.02em}
.stat .l{font-size:12.5px;color:var(--ink2);margin-top:2px}
.rule{background:var(--surface2);border-radius:var(--radius);padding:4px 20px;margin:14px 0}
.rule ol{padding-left:20px}
.rule li{margin:9px 0}
footer{margin-top:44px;padding-top:16px;border-top:1px solid var(--line);
  color:var(--ink3);font-size:12.5px}
@media print{body{background:#fff}.wrap{max-width:none;padding:0}
  h2{break-after:avoid}.figure,.card,table,.formula{break-inside:avoid}}
</style>
<div class="wrap">
<div class="kicker">Interview Kickstart &middot; New Programs</div>
<h1>Does the room want the instructor back?</h1>
<p class="lede">Every rating form asks a second question: <i>would you want this instructor to take the
class again?</i> This study reads that <b>yes/no vote</b> for all <b>%(n)s classes</b> from 1 January
to 31 August 2026 &mdash; <b>%(votes)s votes</b> &mdash; sets it beside the rating, tests the
<b>%(abar)d%% approval bar</b>, and works out how much weight the vote should carry next to the
rating rule we already run.</p>

<div class="card ok">
<h3 style="margin-top:4px">What we are proposing</h3>
<p style="margin:0">Two bars decide <b>whether</b> a class needs a look: rated <b>below %(line).2f</b>,
or fewer than <b>%(abar)d%%</b> of the room would have the instructor back (either one, with at least
%(voices)d people voting). A weighted <b>Class Health Score</b> &mdash; rating <b>%(wr).0f%%</b>,
approval vote <b>%(wa).0f%%</b>, instructor's track record <b>%(wt).0f%%</b> &mdash; then decides
<b>how urgent</b> it is and <b>how deep</b> the analysis goes.</p>
<p class="sub" style="margin:10px 0 0">The %(abar)d%% bar is the bar set for us; the %(line).2f line and the
%(reach)d%% participation bar are the settings from the participation study. The weights are what
this study is for &mdash; section 2 shows where they come from, and section 3 what they change.</p>
</div>

<div class="big">
  <div class="stat"><div class="v">%(approval).1f%%</div><div class="l">of all votes say <i>yes, have them back</i></div></div>
  <div class="stat"><div class="v">%(n100pct).0f%%</div><div class="l">of classes had nobody say no</div></div>
  <div class="stat"><div class="v" style="color:var(--warn)">%(underpct).1f%%</div><div class="l">of classes fall under the %(abar)d%% bar (%(nunder)d)</div></div>
  <div class="stat"><div class="v" style="color:var(--warn)">%(badokpct).0f%%</div><div class="l">of low-rated classes still approve the instructor</div></div>
</div>

<h2>1. What the vote says</h2>

<h3>a) The vote is not the rating</h3>
<p>They move together &mdash; the correlation is <b>%(cra).2f</b> (%(cra5).2f once five or more people
voted) &mdash; but that leaves about half of what the vote says <b>unexplained by the rating</b>. Put the
two bars over the whole eight months and the disagreement is not a rounding error:</p>
<div class="figure">
%(scatter)s
<div class="legend">
  <span><span class="dot" style="background:%(BLUE)s"></span>fine on both (%(nfine)d)</span>
  <span><span class="dot" style="background:%(ORANGE)s"></span>fails both (%(nboth)d)</span>
  <span><span class="dot" style="background:#7a7a85"></span>the two disagree (%(ndisagree)d)</span>
</div>
<div class="cap">All %(n)s classes by rating and by the share who would have the instructor back. The
%(line).2f line and the %(abar)d%% bar cut the cloud into four. Most classes sit top-right; the shaded
corner fails both; the two thin strips are where the signals disagree &mdash; and they are the reason
the vote earns a place in the rule.</div>
</div>
<div class="card finding">
<p style="margin:0"><b>The rating flags the class; the vote flags the instructor.</b> Of the
<b>%(nbad)d</b> classes rated under %(line).2f, <b>%(nbadok)d (%(badokpct).0f%%)</b> still cleared the
%(abar)d%% approval bar &mdash; the room found the class hard or the session poor but did not blame the
teacher. And <b>%(noinfine).0f%% of every &ldquo;no&rdquo; vote</b> was cast in a class rated %(line).2f or
better &mdash; a good class where one or two people would still rather have someone else. Two different
questions, two different answers.</p>
</div>

<h3>b) Where they disagree &mdash; two kinds of class we were missing or mis-reading</h3>
<p><b>Polite rating, would not have them back.</b> %(nfinelow)d classes were rated %(line).2f or better yet
fell under the %(abar)d%% bar (%(nfinelow5)d of them with five or more votes). Today's rule never sees
these. Every one of them is an instructor question, which is exactly what the vote is for:</p>
<table>
<tr><th>Date</th><th>Course</th><th>Instructor</th><th>Rating</th><th>Vote</th><th>Approval</th><th>Rated</th></tr>
%(polite_rows)s
</table>
<p><b>Hard class, good teacher.</b> The far larger group runs the other way &mdash; rated low, instructor
approved. These are still analysed (the rating says something went wrong), but the vote tells the
analyst where <i>not</i> to look first: the room is not asking for a different instructor.</p>
<table>
<tr><th>Date</th><th>Course</th><th>Instructor</th><th>Rating</th><th>Vote</th><th>Approval</th><th>Rated</th></tr>
%(hard_rows)s
</table>

<h3>c) How approval tracks the rating</h3>
<div class="figure">
%(band_chart)s
<div class="cap">Share of classes under the %(abar)d%% bar, by rating band. Almost nothing above %(line).2f,
then a steep climb: about <b>one in four</b> of the 4.40&ndash;4.54 classes, and <b>more than four in
five</b> of anything under 4.0. The vote agrees with the rating when the rating is clearly bad, and
adds its own opinion in the borderline band.</div>
</div>
<table>
<tr><th>Rating band</th><th>Classes</th><th>Pooled approval</th><th>Nobody said no</th><th>Under %(abar)d%%</th></tr>
%(rating_band_rows)s
</table>

<h3>d) The %(abar)d%% bar in practice</h3>
<p>Set at %(abar)d%% and applied only where five or more people voted, the bar catches <b>%(nunder5)d classes</b>
over the eight months &mdash; and <b>%(nfinelow5)d of them (%(extraperweek).1f a week)</b> are new: classes
today's rule lets through. That is a small, affordable addition, and the table shows why %(abar)d%% is the
right place for it: at 85%% the list of new classes quadruples, mostly one-&ldquo;no&rdquo; classes rated
4.6+; at 75%% it barely catches anything the rating had not already caught.</p>
<table>
<tr><th>Approval bar</th><th>Classes caught (5+ votes)</th><th>Share of classes</th><th>New &mdash; not caught by the rating</th><th>Extra work</th></tr>
%(bar_rows)s
</table>
<table>
<tr><th>Approval</th><th>Classes</th><th>Share</th><th>Avg rating</th><th>Rated under %(line).2f</th><th>Avg voices</th></tr>
%(approval_band_rows)s
</table>

<h3>e) The small-room trap &mdash; why the five-voice floor matters even more here</h3>
<div class="figure">
%(voices_chart)s
<div class="cap">Share of classes under the %(abar)d%% bar, by how many people voted. With two, three or four
voters a <b>single &ldquo;no&rdquo; fails the bar</b> (50%%, 67%%, 75%%), so the share spikes to
%(v2pct).0f&ndash;%(v4pct).0f%%; at exactly five voters one &ldquo;no&rdquo; is exactly 80%% and passes,
so it drops to %(v5pct).0f%%. From six voters on it settles around 8&ndash;12%%.</div>
</div>
<p>A percentage hides the size of the room here just as it did for participation. One unhappy person in
a class of four is a 75%% approval &mdash; a fail &mdash; on the strength of one opinion. So the vote
gets the same protection the rating has: <b>fewer than %(voices)d votes &rarr; watch, do not act.</b>
With that floor, %(nunder)d classes under the bar become %(nunder5)d actionable ones.</p>

<h3>f) The trend, by month and by course</h3>
<div class="figure">
%(monthly_chart)s
<div class="cap">The share of classes under the approval bar has doubled across the year &mdash;
<b>%(janlow).0f%% in January to %(auglow).0f%% in August</b> &mdash; on the same slope as the rating
(%(janbad).0f%% to %(augbad).0f%% under %(line).2f). The room is not just rating lower; it is more often
asking for a different instructor.</div>
</div>
<table>
<tr><th>Month</th><th>Classes</th><th>Pooled approval</th><th>Under %(line).2f</th><th>Under %(abar)d%%</th>
  <th>New (vote only, 5+ votes)</th><th>Urgent</th><th>Queue (rule v2)</th></tr>
%(monthly_rows)s
</table>
<p>By course, the approval bar reads differently from the rating line. <b>Transformative GenAI</b> has both the
lowest pooled approval among the big courses and the most classes failing both bars; <b>Applied Agentic
AI</b> produces the most &ldquo;hard class, good teacher&rdquo; cases &mdash; low ratings the room does not
pin on the instructor, which points at content and difficulty rather than delivery. Section 4 has the full table.</p>

<h3>g) Instructors &mdash; the vote as a track record</h3>
<p>Pooled over the year for the %(insn)d instructors with ten or more classes, approval and average rating
agree strongly (correlation %(cins).2f) &mdash; but not perfectly. <b>%(inslt80)d</b> instructor sits under
the %(abar)d%% bar for the whole year and <b>%(inslt90)d</b> sit under 90%%; the first row is the clearest
example of a rating that stays polite while the room quietly votes the other way.</p>
<table>
<tr><th>Instructor</th><th>Classes</th><th>&ldquo;No&rdquo; votes</th><th>Approval</th><th>Avg rating</th>
  <th>Classes under %(line).2f</th><th>Classes under %(abar)d%%</th></tr>
%(ins_rows)s
</table>

<h2>2. Finding the weights</h2>
<p>The question is how much each of three things should count: the <b>rating</b> (with its voice checks),
the <b>approval vote</b>, and the instructor's <b>track record</b> &mdash; their average over their earlier
classes this year (%(trcov).0f%% of classes have one, after %(trmin)d earlier classes). Three independent
lenses, all on the same %(n)s classes.</p>

<h3>Lens 1 &mdash; how much of each signal is new information</h3>
<p>Regress each signal on the other two and see what is left. The rating and the vote each carry about
<b>half</b> their information uniquely (rating %(uR).0f%%, vote %(uA).0f%%) &mdash; they overlap, but
neither is a copy of the other. The track record is <b>almost entirely new</b> (%(uT).0f%%): it is about
the instructor across classes, not this class, and correlates with neither (%(cRT).2f with the rating,
%(cAT).2f with the vote).</p>

<h3>Lens 2 &mdash; which signal today predicts trouble next time</h3>
<p>If a signal only describes today, it is worth acting on once. If it predicts the <i>next</i> class
by the same instructor, it is worth weighting. For every class with five or more votes we looked at that
instructor's next class (%(pairs)d pairs):</p>
<table>
<tr><th>This class</th><th>Pairs</th><th>Next class rated under %(line).2f</th><th>Next class under %(abar)d%% approval</th></tr>
%(lens2_rows)s
</table>
<table>
<tr><th>Track record</th><th>Pairs</th><th>Next class rated under %(line).2f</th></tr>
%(track_rows)s
</table>
<p>Three things follow. A low rating roughly doubles the chance the next class is low too
(%(base).0f%% &rarr; %(rlow).0f%%); adding a failed vote raises it again to <b>%(both_next).0f%%</b> &mdash;
the vote adds real predictive weight on top of the rating. A failed vote on a well-rated class is a
weaker but real warning (%(flow).0f%%). And a poor track record more than doubles the risk on its own
(%(tr_ok).0f%% &rarr; %(tr_bad).0f%%). Put in one model with everything standardised, the rating carries
<b>%(sR).0f%%</b> of the predictive weight for the next rating and the track record <b>%(sT).0f%%</b>; for
predicting the next <i>approval</i> failure the vote is as strong as the rating (%(saA).0f%% vs
%(saR).0f%%). The vote is the only signal that predicts its own kind of trouble.</p>

<h3>What the lenses agree on &mdash; and the weights we recommend</h3>
<div class="formula">
<b>Rating (with the voice checks) &nbsp;%(wr).0f%%</b> &nbsp;&middot;&nbsp; <b>Approval vote &nbsp;%(wa).0f%%</b>
&nbsp;&middot;&nbsp; <b>Track record &nbsp;%(wt).0f%%</b><br>
<span class="sub">Data-supported range: rating 55&ndash;65, vote 25&ndash;35, track record 10&ndash;15. The
%(wr).0f / %(wa).0f / %(wt).0f split first proposed internally sits inside it, and is the simplest
version to explain.</span>
</div>
<p>The rating is the strongest single signal on every lens, so it leads. The vote is half new information
and the only predictor of approval trouble, so it takes a real share rather than a token one. The track
record is independent of both and doubles the risk when it is poor, but it describes the instructor, not
the class, so it nudges the score rather than driving it.</p>

<h3>Lens 3 &mdash; why the score cannot replace the bars</h3>
<p>The natural next idea is to let the weighted score decide on its own: one number, one threshold. We
tested every mix from 30/10 to 80/50 across seven thresholds (%(ngrid)d settings). <b>None of them</b>
keeps every class that fails both bars <i>and</i> every class rated under 4.40 &mdash; because a weighted
average lets a perfect vote buy back a bad rating. With the recommended mix:</p>
<table>
<tr><th>Score alone decides</th><th>Classes flagged</th><th>Today's flags it drops</th><th>Vote failures it drops</th><th>Fails-both it drops</th></tr>
%(pure_rows)s
</table>
<p>Read the middle column: at a threshold of 90 the score drops <b>%(drop90)d</b> classes today's rule
analyses &mdash; in effect it moves the %(line).2f line to about 4.38 for any instructor the room likes, and
the %(abar)d%% bar to 67%%. Nobody agreed to that. So the bars stay hard, and the score does the two jobs
a weighted average is actually good at: <b>ordering the queue</b> and <b>choosing the depth</b>.</p>

<h2>3. The rule</h2>
<div class="rule"><ol>
<li>Fewer than <b>%(voices)d people</b> voted &rarr; <b>watch only</b>. Too thin for either signal.</li>
<li>Rated <b>%(line).2f or above</b> and <b>%(abar)d%% or more</b> would have the instructor back &rarr;
<b>no analysis</b> (unless a PM asks for one).</li>
<li>Rated <b>below %(line).2f</b>, <i>or</i> approval <b>under %(abar)d%%</b> &rarr; <b>enters the queue</b>.
Either bar alone is enough.</li>
<li>In the queue, the <b>Class Health Score</b> sets the priority: <b>Urgent</b> under %(urgent)d,
<b>Needs a look</b> %(urgent)d&ndash;%(borderline)d, <b>Borderline</b> %(borderline)d and above.</li>
<li>Depth: <b>Urgent &rarr; video</b>, whatever the participation. <b>Borderline &rarr; transcript first</b>,
even when participation is fine. In between, the participation check decides as today: <b>%(reach)d%%
or more of the room rated it &rarr; video</b>, otherwise transcript.</li>
<li>Any <b>escalation</b> or reported issue &rarr; video, always.</li>
</ol></div>

<div class="formula">
<b>Class Health Score</b> = %(wr).0f%% &times; Rating score &nbsp;+&nbsp; %(wa).0f%% &times; Approval score &nbsp;+&nbsp; %(wt).0f%% &times; Track-record score<br><br>
<span class="sub">Each part is 100 at or above its bar and falls in a straight line to 0 at &ldquo;as bad as it
gets&rdquo;: rating %(line).2f &rarr; %(rfloor).2f (a full point under the line); approval %(abar)d%% &rarr;
%(afloor)d%% (fewer than four in ten would have them back); track record %(line).2f &rarr; %(tfloor).2f
(their average half a point under the line). No track record yet &rarr; no penalty. The floors sit at the
worst 5&ndash;10%% of each signal's failures in this data, so the three parts fall at comparable speed.</span>
</div>

<div class="figure">
%(health_chart)s
<div class="cap">Health score of the %(nqueue)d classes that enter the queue over the eight months.
<b>%(nurgent)d urgent</b> (average rating %(urg_r).2f, approval %(urg_a).0f%%), <b>%(nlook)d need a look</b>,
<b>%(nborder)d borderline</b> (average %(bor_r).2f, approval %(bor_a).0f%%). The borderline band is the
majority &mdash; which is the case for starting them with a transcript.</div>
</div>

<h3>What it produces over the eight months</h3>
<table>
<tr><th>Rule</th><th>Watch</th><th>Video</th><th>Transcript</th><th>Analyses</th><th>Per week</th><th>AI cost / month</th></tr>
%(outcomes)s
</table>
<p>Against today's rule, v2 <b>drops nothing</b> &mdash; every class today's rule analyses is still analysed
&mdash; and adds the <b>%(nfinelow5)d vote-only classes</b>. The score then moves the depth in both
directions: <b>%(nurgentlow)d urgent classes</b> that the participation check alone would have held at
transcript go straight to video, and <b>%(nborderhigh)d borderline classes</b> that would have earned a
video on participation alone start with a transcript instead. Net: fewer videos, more first-pass
transcripts, and the videos concentrated where both signals say something is wrong. One learner's vote
flips the verdict on %(flip2).0f%% of flagged classes &mdash; the same order as today's rule (%(flip1).0f%%),
because the rooms are small; the five-voice floor is what keeps it there.</p>

<h3>How much the weights actually move</h3>
<table>
<tr><th>Rating / vote / track record</th><th>Urgent</th><th>Needs a look</th><th>Borderline</th><th>&rarr; video</th><th>&rarr; transcript</th></tr>
%(weights_rows)s
</table>
<p>Across sensible mixes the weights shift about twenty classes between bands over eight months
&mdash; two or three a month. That is the honest finding: <b>the bars do the heavy lifting; the weights
fine-tune urgency and depth.</b> It also means the weights are safe to adjust later without anyone's
class silently dropping out of the queue.</p>

<h3>Five worked cases</h3>
%(ex13)s
%(ex_polite)s
%(ex_hard)s
%(ex_urgent)s
%(ex_repeat)s

<h2>4. What lands where, by course</h2>
<table>
<tr><th>Course</th><th>Classes</th><th>Approval</th><th>Under %(abar)d%%</th><th>Queue: rating only</th>
  <th>Vote only</th><th>Fails both</th><th>Urgent</th><th>&rarr; video</th><th>&rarr; transcript</th></tr>
%(course_rows)s
</table>
<p>Two courses carry most of the work, as they did in the participation study. But the vote splits them:
Transformative GenAI's problem is concentrated in classes that fail <i>both</i> bars &mdash; the room is
unhappy with the class and the teacher &mdash; while Applied Agentic AI's is mostly rating-only. The
same queue size, two different conversations to have.</p>

<h2>5. What changes in the product</h2>
<p>Nothing here needs new data: the sheet already carries the Yes and No counts on every row, so the
hourly sync reads two more columns and stores the vote beside the rating. From there:</p>
<ul>
<li>Every class in the <b>Needs analysis</b> queue shows the vote (&ldquo;13 of 15 would have them back&rdquo;),
the Health Score and its band, and is sorted urgent-first. The Slack note to the course handler says the
same in one line.</li>
<li>The <b>decision rule</b> in the worker and the web app moves to v2 &mdash; the two bars, the score, the
depth rule &mdash; with the weights and floors kept as settings, so the numbers above can be tuned without
touching code.</li>
<li><b>Instructor Analytics</b> gains the approval rate per SME and per topic: the &ldquo;polite rating&rdquo;
pattern in section 1g becomes visible on the instructor's own page, not just in this report.</li>
<li><b>Reports</b> and <b>Insights</b> carry the approval bar beside the rating line, per course.</li>
</ul>

<footer>Source: the class-ratings workbook, tabs MLSU_Live_Class_Poll and Agentic_AI_Live_Class_Poll,
sessions dated 1 January&ndash;31 August 2026; %(n)s classes after removing duplicates and rows where
responses exceed attendance. &ldquo;Approval&rdquo; = yes &divide; (yes + no); on every row yes + no equals
the number of ratings. Track record = the instructor's average rating over their earlier classes in the
period, after at least %(trmin)d. Lens 2 uses logistic regression on standardised scores; lens 3 a grid of
%(ngrid)d weight&ndash;threshold settings. Scripts: analysis/approval_explore.py, approval_weights.py,
approval_rule.py. Confidential &mdash; internal use.</footer>
</div>
""" % dict(
    BLUE=BLUE, ORANGE=ORANGE, n="{:,}".format(n), votes="{:,}".format(int(Y + N)),
    line=LINE, abar=APPROVAL_BAR, voices=VOICES, reach=REACH_BAR,
    wr=W[0] * 100, wa=W[1] * 100, wt=W[2] * 100,
    approval=approval_all, n100pct=n100 / n * 100, underpct=len(under) / n * 100, nunder=len(under),
    nunder5=len(under5), badokpct=len(bad_ok) / len(badrows) * 100,
    cra=c_ra, cra5=c_ra5, scatter=scatter(), nfine=sum(1 for r in rows if not bad(r) and not low(r)),
    nboth=len(both), ndisagree=len(bad_ok) + len(fine_low), nbad=len(badrows), nbadok=len(bad_ok),
    noinfine=no_in_fine / N * 100, nfinelow=len(fine_low), nfinelow5=len(fine_low5),
    polite_rows=listing(sorted(fine_low5, key=lambda r: r["approval"])),
    hard_rows=listing(sorted([r for r in bad_ok if r["responses"] >= VOICES], key=lambda r: r["rating"])),
    band_chart=band_chart(), rating_band_rows=rating_band_rows(),
    extraperweek=len(fine_low5) / weeks, bar_rows=bar_rows(), approval_band_rows=approval_band_rows(),
    voices_chart=voices_chart(),
    v2pct=sum(1 for r in rows if r["responses"] == 2 and low(r)) / max(1, sum(1 for r in rows if r["responses"] == 2)) * 100,
    v4pct=sum(1 for r in v4 if low(r)) / len(v4) * 100, v5pct=sum(1 for r in v5 if low(r)) / len(v5) * 100,
    monthly_chart=monthly_chart(),
    janlow=sum(1 for r in jan if low(r)) / len(jan) * 100, auglow=sum(1 for r in aug if low(r)) / len(aug) * 100,
    janbad=sum(1 for r in jan if bad(r)) / len(jan) * 100, augbad=sum(1 for r in aug if bad(r)) / len(aug) * 100,
    monthly_rows=monthly_rows(), insn=ins_n, inslt80=ins_lt80, inslt90=ins_lt90, ins_rows=ins_rows,
    cins=0.73, trcov=tr_cov, trmin=T_MIN_CLASSES,
    uR=L1["uR"] * 100, uA=L1["uA"] * 100, uT=L1["uT"] * 100, cRT=L1["cRT"], cAT=L1["cAT"],
    pairs=sum(v[0] for k, v in C["lens2_groups"].items() if "record" not in k),
    lens2_rows=lens2_rows(), track_rows=track_rows(),
    base=C["lens2_groups"]["rated fine, approval fine"][1], rlow=C["lens2_groups"]["rated low, approval fine"][1],
    both_next=C["lens2_groups"]["rated low, approval low"][1], flow=C["lens2_groups"]["rated fine, approval low"][1],
    tr_ok=C["lens2_groups"]["track record >= line"][1], tr_bad=C["lens2_groups"]["track record < line"][1],
    sR=l2r["share"]["R"], sT=l2r["share"]["T"], saA=l2a["share"]["A"], saR=l2a["share"]["R"],
    ngrid=len(C["results"]), pure_rows=pure_score_rows(),
    drop90=next(x for x in C["table_thr"] if x["thr"] == 90)["miss_cur"],
    urgent=URGENT, borderline=BORDERLINE, rfloor=R_FLOOR, afloor=A_FLOOR, tfloor=T_FLOOR,
    health_chart=health_chart(), nqueue=len(queued), nurgent=bands_c["Urgent"], nlook=bands_c["Needs a look"],
    nborder=bands_c["Borderline"],
    urg_r=st.mean(r["rating"] for r in queued if band(health(r)) == "Urgent"),
    urg_a=st.mean(r["approval"] for r in queued if band(health(r)) == "Urgent"),
    bor_r=st.mean(r["rating"] for r in queued if band(health(r)) == "Borderline"),
    bor_a=st.mean(r["approval"] for r in queued if band(health(r)) == "Borderline"),
    outcomes=outcomes, nurgentlow=len(urgent_lowreach), nborderhigh=len(borderline_highreach),
    flip1=flip1, flip2=flip2, weights_rows=weights_rows(),
    ex13=example_card(ex13, "Thirteen yes, two no", vtext(ex13)),
    ex_polite=example_card(ex_polite, "Polite rating, would not have them back", vtext(ex_polite)),
    ex_hard=example_card(ex_hard, "Hard class, good teacher", vtext(ex_hard)),
    ex_urgent=example_card(ex_urgent, "Fails both, thin reach", vtext(ex_urgent)),
    ex_repeat=example_card(ex_repeat, "Repeat pattern", vtext(ex_repeat)),
    course_rows=course_rows(),
)

out = os.path.join(HERE, "instructor-approval-report.html")
open(out, "w", encoding="utf-8").write(HTML)
print("wrote %s  (%.0f KB)" % (out, len(HTML) / 1024))
print("queue %d | urgent %d | look %d | borderline %d | v2 video %d transcript %d | v1 video %d transcript %d"
      % (len(queued), bands_c["Urgent"], bands_c["Needs a look"], bands_c["Borderline"],
         V2["video"], V2["transcript"], V1["video"], V1["transcript"]))
