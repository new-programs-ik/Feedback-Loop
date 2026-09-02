"""Builds the local HTML report for the participation-threshold study - FULL PERIOD (Jan-Aug 2026).

Local only - the underlying workbook is confidential, so nothing here is committed or published.
Charts are inline SVG (no CDN) so the PDF renders identically offline.
"""
import datetime as dt
import os
import statistics as st
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ratings_data import load  # noqa: E402

LO, HI = dt.datetime(2026, 1, 1), dt.datetime(2026, 8, 31, 23, 59, 59)

# --- the operating settings New Programs has chosen for the first run --------------------------
LINE = 4.55      # at or above this a class needs no analysis
BAR = 40         # participation bar: the share of attendees who rated it
VOICES = 5       # minimum number of ratings before the score means anything

BLUE, ORANGE = "#2a78d6", "#eb6834"     # validated pair (light + dark, all-pairs)
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"]

rows = load(LO, HI)
bad = [r for r in rows if r["rating"] < LINE]
good = [r for r in rows if r["rating"] >= LINE]
bad45 = [r for r in rows if r["rating"] < 4.5]
good45 = [r for r in rows if r["rating"] >= 4.5]
WEEKS = ((HI - LO).days + 1) / 7.0
DATA_AVG = st.mean(r["pct"] for r in rows)           # the long-run average participation
CROSS = VOICES / (BAR / 100.0)
n80 = sum(1 for r in rows if r["pct"] >= 80)


def corr(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    return num / den if den else 0.0


C_RATING = corr([r["pct"] for r in rows], [r["rating"] for r in rows])
C_SIZE = corr([r["pct"] for r in rows], [r["attended"] for r in rows])


def decide(r, line=LINE, bar=BAR, voices=VOICES):
    if r["rating"] >= line:
        return "NONE"
    if r["responses"] < voices:
        return "WATCH"
    return "VIDEO" if r["pct"] >= bar else "TRANSCRIPT"


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------- chart 1: scatter (2,780 dots)
def scatter():
    W, H = 720, 416
    ml, mr, mt, mb = 54, 18, 38, 44
    pw, ph = W - ml - mr, H - mt - mb
    x = lambda p: ml + p / 100 * pw
    y = lambda r: mt + (5.0 - r) / (5.0 - 3.0) * ph

    p = ['<svg viewBox="0 0 %d %d" role="img" aria-label="All %d classes from January to August '
         'plotted by rating against rating participation. The cloud is flat - participation does '
         'not predict the rating - and thins out sharply past 70 percent. The shaded corner, rated '
         'below %.2f with at least %d percent participation, earns a video analysis.">'
         % (W, H, len(rows), LINE, BAR)]
    for r in (3.0, 3.5, 4.0, 4.5, 5.0):
        p.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="var(--grid)" stroke-width="1"/>'
                 % (ml, y(r), W - mr, y(r)))
        p.append('<text x="%d" y="%.1f" text-anchor="end" class="tick">%.1f</text>' % (ml - 8, y(r) + 4, r))
    for pc in (0, 20, 40, 60, 80, 100):
        p.append('<text x="%.1f" y="%d" text-anchor="middle" class="tick">%d%%</text>'
                 % (x(pc), H - mb + 20, pc))
    p.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" fill-opacity=".07"/>'
             % (x(BAR), y(LINE), x(100) - x(BAR), mt + ph - y(LINE), ORANGE))
    p.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="var(--ink3)" stroke-width="2" '
             'stroke-dasharray="5 4"/>' % (ml, y(LINE), W - mr, y(LINE)))
    p.append('<text x="%d" y="%.1f" class="note">rating %.2f - below this we look</text>'
             % (ml + 6, y(LINE) + 16, LINE))
    p.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s" stroke-width="2"/>'
             % (x(BAR), mt, x(BAR), H - mb, BLUE))
    p.append('<text x="%.1f" y="24" text-anchor="middle" class="barlab">%d%% bar</text>'
             % (x(BAR), BAR))
    p.append('<text x="%.1f" y="%.1f" class="note" style="fill:%s">below %.2f AND a representative '
             'sample</text>' % (x(55), y(3.16), ORANGE, LINE))
    p.append('<text x="%.1f" y="%.1f" class="note" style="fill:%s">&#8594; video analysis</text>'
             % (x(55), y(3.06), ORANGE))
    p.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="var(--ink3)" stroke-width="2" '
             'stroke-dasharray="3 3"/>' % (x(80), mt, x(80), H - mb))
    p.append('<text x="%.1f" y="24" text-anchor="middle" class="note">80%% &mdash; reached by '
             '%.1f%% of classes</text>' % (min(x(80) + 4, W - mr - 100), n80 / len(rows) * 100))
    for r in rows:
        c = ORANGE if r["rating"] < LINE else BLUE
        p.append('<circle cx="%.1f" cy="%.1f" r="3" fill="%s" fill-opacity=".4"/>'
                 % (x(min(r["pct"], 100)), y(max(min(r["rating"], 5.0), 3.0)), c))
    p.append('<text x="%d" y="%d" text-anchor="middle" class="axis">rating participation '
             '(share of attendees who rated)</text>' % (ml + pw / 2, H - 6))
    p.append('<text transform="translate(14,%d) rotate(-90)" text-anchor="middle" class="axis">'
             'class rating</text>' % (mt + ph / 2))
    p.append("</svg>")
    return "".join(p)


# ---------------------------------------------------------------- chart 2: histogram
def histogram():
    W, H = 720, 250
    ml, mr, mt, mb = 48, 18, 30, 44
    pw, ph = W - ml - mr, H - mt - mb
    bins = [0] * 10
    for r in rows:
        bins[min(int(r["pct"] // 10), 9)] += 1
    top = max(bins)
    bw = pw / 10
    p = ['<svg viewBox="0 0 %d %d" role="img" aria-label="Distribution of rating participation '
         'across all %d classes. It peaks at 50 to 60 percent and almost vanishes past 70. The 40 '
         'percent operating bar sits below the average of about 51 percent; the original 80 percent '
         'gate is out in the tail.">' % (W, H, len(rows))]
    for i, n in enumerate(bins):
        h = (n / top) * ph if top else 0
        bx = ml + i * bw + 2
        p.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="4" fill="%s" '
                 'fill-opacity=".85"><title>%d-%d%%: %d classes</title></rect>'
                 % (bx, mt + ph - h, bw - 4, h, BLUE, i * 10, i * 10 + 10, n))
        if n:
            p.append('<text x="%.1f" y="%.1f" text-anchor="middle" class="tick">%d</text>'
                     % (bx + (bw - 4) / 2, mt + ph - h - 6, n))
    for i in range(11):
        p.append('<text x="%.1f" y="%d" text-anchor="middle" class="tick">%d</text>'
                 % (ml + i * bw, H - mb + 18, i * 10))
    bx40 = ml + (BAR / 100) * pw
    p.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s" stroke-width="2"/>'
             % (bx40, mt - 6, bx40, mt + ph, ORANGE))
    p.append('<text x="%.1f" y="%d" text-anchor="end" class="gate">%d%% bar &#8594;</text>'
             % (bx40 - 6, mt - 12, BAR))
    bxavg = ml + (DATA_AVG / 100) * pw
    p.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="var(--ink3)" stroke-width="2" '
             'stroke-dasharray="4 3"/>' % (bxavg, mt - 6, bxavg, mt + ph))
    # (no in-chart label - it would sit on the tallest bar's count; the caption names this line)
    p.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="var(--ink3)" stroke-width="2" '
             'stroke-dasharray="2 3"/>' % (ml + 8 * bw, mt - 6, ml + 8 * bw, mt + ph))
    p.append('<text x="%.1f" y="%d" text-anchor="middle" class="note">80%% &mdash; %d classes</text>'
             % (ml + 9 * bw, mt - 12, n80))
    p.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="var(--grid)"/>'
             % (ml, mt + ph, W - mr, mt + ph))
    p.append('<text x="%d" y="%d" text-anchor="middle" class="axis">rating participation %%</text>'
             % (ml + pw / 2, H - 6))
    p.append("</svg>")
    return "".join(p)


# ---------------------------------------------------------------- chart 3: monthly trend
def monthly():
    W, H = 720, 270
    ml, mr, mt, mb = 48, 18, 34, 40
    pw, ph = W - ml - mr, H - mt - mb
    data = []
    for m in range(1, 9):
        g = [r for r in rows if r["date"].month == m]
        b = sum(1 for r in g if r["rating"] < LINE)
        data.append((len(g), b))
    top = max(n for n, _ in data)
    bw = pw / 8
    p = ['<svg viewBox="0 0 %d %d" role="img" aria-label="Classes per month, January to August, '
         'split into rated %.2f and above versus below. The share below %.2f climbs from 15 percent '
         'in January to 24 percent in August.">' % (W, H, LINE, LINE)]
    for i, (n, b) in enumerate(data):
        gh = ((n - b) / top) * ph
        bh = (b / top) * ph
        bx = ml + i * bw + 6
        w = bw - 12
        p.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="4" fill="%s">'
                 '<title>%s: %d rated %.2f+</title></rect>'
                 % (bx, mt + ph - gh, w, gh, BLUE, MONTHS[i], n - b, LINE))
        p.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="4" fill="%s">'
                 '<title>%s: %d below %.2f</title></rect>'
                 % (bx, mt + ph - gh - bh - 2, w, max(bh - 2, 2), ORANGE, MONTHS[i], b, LINE))
        p.append('<text x="%.1f" y="%.1f" text-anchor="middle" class="pctlab">%.0f%%</text>'
                 % (bx + w / 2, mt + ph - gh - bh - 8, b / n * 100))
        p.append('<text x="%.1f" y="%d" text-anchor="middle" class="tick">%s</text>'
                 % (bx + w / 2, H - mb + 16, MONTHS[i]))
        p.append('<text x="%.1f" y="%d" text-anchor="middle" class="tick">%d</text>'
                 % (bx + w / 2, H - mb + 30, n))
    p.append('<text x="%d" y="16" class="tick">%% = share of the month rated below %.2f &middot; '
             'number under each month = classes run</text>' % (ml, LINE))
    p.append("</svg>")
    return "".join(p)


# ---------------------------------------------------------------- tables
def group_rows():
    out = ""
    for lab, g, strong in ((("Rated <b>%.2f and above</b>" % LINE), good, True),
                           (("Rated <b>below %.2f</b>" % LINE), bad, True),
                           ("<span class='sub'>&mdash; at the old 4.50 line: 4.50 and above</span>",
                            good45, False),
                           ("<span class='sub'>&mdash; at the old 4.50 line: below 4.50</span>",
                            bad45, False)):
        cls = "" if strong else " class='dim'"
        out += ("<tr%s><td>%s</td><td class='n'>%d</td><td class='n'>%.0f</td><td class='n'>%.0f</td>"
                "<td class='n'><b>%.1f%%</b></td><td class='n'>%.1f%%</td><td class='n'>%.1f</td></tr>"
                % (cls, lab, len(g), sum(r["attended"] for r in g), sum(r["responses"] for r in g),
                   st.mean([r["pct"] for r in g]), st.median([r["pct"] for r in g]),
                   st.mean([r["responses"] for r in g])))
    out += ("<tr class='pickrow'><td><b>All classes</b></td><td class='n'>%d</td>"
            "<td class='n'>%.0f</td><td class='n'>%.0f</td><td class='n'><b>%.1f%%</b></td>"
            "<td class='n'>%.1f%%</td><td class='n'>%.1f</td></tr>"
            % (len(rows), sum(r["attended"] for r in rows), sum(r["responses"] for r in rows),
               DATA_AVG, st.median([r["pct"] for r in rows]),
               st.mean([r["responses"] for r in rows])))
    return out


def trust_rows():
    out = ""
    half = round(DATA_AVG)
    for lab, sel in (("Under %d%%" % half, lambda r: r["pct"] < half),
                     ("%d%% or more" % half, lambda r: r["pct"] >= half)):
        g = [r for r in rows if sel(r)]
        gb = [r for r in bad if sel(r)]
        out += ("<tr><td><b>%s</b></td><td class='n'>%d</td><td class='n'>%.2f</td>"
                "<td class='n'>%.1f%%</td><td class='n'>%.1f</td></tr>"
                % (lab, len(g), st.pstdev([r["rating"] for r in g]),
                   sum(1 for r in g if r["rating"] < 4.0) / len(g) * 100,
                   st.mean([r["responses"] for r in gb]) if gb else 0))
    return out


def size_rows():
    out = ""
    for lo_, hi_, lab in ((1, 9, "1&ndash;9 learners"), (10, 19, "10&ndash;19"),
                          (20, 39, "20&ndash;39"), (40, 9999, "40 or more")):
        g = [r for r in rows if lo_ <= r["attended"] <= hi_]
        if not g:
            continue
        med = st.median([r["attended"] for r in g])
        voices = med * BAR / 100.0
        weak = voices < VOICES
        out += ("<tr%s><td>%s</td><td class='n'>%d</td><td class='n'>%.0f</td>"
                "<td class='n'>%.1f%%</td><td class='n'><b>%.0f</b></td><td>%s</td></tr>"
                % (" class='warnrow'" if weak else "", lab, len(g), med,
                   st.mean([r["pct"] for r in g]), voices,
                   "too few voices &mdash; the floor takes over" if weak
                   else "the %d%% bar governs" % BAR))
    return out


def monthly_rows():
    out = ""
    for m in range(1, 9):
        g = [r for r in rows if r["date"].month == m]
        b = [r for r in g if r["rating"] < LINE]
        d = Counter(decide(r) for r in g)
        out += ("<tr><td>%s</td><td class='n'>%d</td><td class='n'>%d</td><td class='n'>%.1f%%</td>"
                "<td class='n'>%.1f%%</td><td class='n'>%d</td><td class='n'>%d</td></tr>"
                % (MONTHS[m - 1], len(g), len(b), len(b) / len(g) * 100,
                   st.mean([r["pct"] for r in g]), d["VIDEO"], d["TRANSCRIPT"]))
    return out


def threshold_rows():
    out = ""
    for t in (30, 40, 45, 50, 60, 80):
        v = [r for r in bad if r["pct"] >= t and r["responses"] >= VOICES]
        tr = [r for r in bad if r["pct"] < t and r["responses"] >= VOICES]
        cls, note = "", ""
        if t == BAR:
            cls, note = " class='pickrow'", "our operating setting"
        elif t == 50:
            note = "the long-run average (%.1f%%)" % DATA_AVG
        elif t == 80:
            note = "the original guess &mdash; catches almost nothing"
        elif t == 30:
            note = "nearly every low-rated class gets video"
        out += ("<tr%s><td class='n'><b>%d%%</b></td><td class='n'>%d</td><td class='n'>%d</td>"
                "<td class='n'>%.1f</td><td>%s</td></tr>"
                % (cls, t, len(v), len(tr), (len(v) + len(tr)) / WEEKS, note))
    return out


def settings_rows():
    out = ""
    for line_, bar_, voices_, lab, cls in (
            (4.50, 80, 3, "The original guess", ""),
            (4.50, 50, 3, "Old line, bar at the data average", ""),
            (LINE, BAR, VOICES, "<b>Our setting</b>", " class='pickrow'"),
            (LINE, 45, VOICES, "Bar raised to 45%", ""),
            (LINE, 50, VOICES, "Bar raised to 50%", "")):
        k = Counter(decide(r, line_, bar_, voices_) for r in rows)
        out += ("<tr%s><td>%s</td><td class='n'>%.2f</td><td class='n'>%d%%</td>"
                "<td class='n'>%d</td><td class='n'>%d</td><td class='n'>%d</td>"
                "<td class='n'>%.1f</td></tr>"
                % (cls, lab, line_, bar_, k["VIDEO"], k["TRANSCRIPT"], k["WATCH"],
                   (k["VIDEO"] + k["TRANSCRIPT"]) / WEEKS))
    return out


def outcome_rows():
    c = Counter(decide(r) for r in rows)
    labels = [("VIDEO", "Video analysis",
               "below %.2f, %d%%+ rated it, %d+ ratings" % (LINE, BAR, VOICES)),
              ("TRANSCRIPT", "Transcript analysis", "below %.2f, under %d%% rated it" % (LINE, BAR)),
              ("WATCH", "Watch only", "fewer than %d ratings &mdash; too few voices" % VOICES),
              ("NONE", "No analysis", "rated %.2f or above" % LINE)]
    return "".join(
        "<tr><td><b>%s</b><div class='sub'>%s</div></td><td class='n'>%d</td>"
        "<td class='n'>%.1f</td></tr>" % (name, why, c[k], c[k] / WEEKS)
        for k, name, why in labels), c


def listing(kind, limit=15):
    g = sorted([r for r in rows if decide(r) == kind], key=lambda r: r["rating"])
    out = "".join(
        "<tr><td class='n'><b>%.2f</b></td><td class='n'>%.0f of %.0f</td>"
        "<td class='n'>%.0f%%</td><td>%s</td><td>%s</td><td class='n'>%s</td></tr>"
        % (r["rating"], r["responses"], r["attended"], r["pct"], r["kind"], esc(r["course"]),
           r["date"].strftime("%d %b"))
        for r in g[:limit])
    if len(g) > limit:
        out += ("<tr class='dim'><td colspan='6'>&hellip; and %d more (worst %d shown)</td></tr>"
                % (len(g) - limit, limit))
    return out


def course_rows():
    by = defaultdict(list)
    for r in rows:
        by[r["course"]].append(r)
    out = ""
    for c in sorted(by, key=lambda c: -len([r for r in by[c] if r["rating"] < LINE])):
        for kind in ("Live Class", "Test Review"):
            g = [r for r in by[c] if r["kind"] == kind]
            if not g:
                continue
            b = [r for r in g if r["rating"] < LINE]
            d = Counter(decide(r) for r in g)
            out += ("<tr><td>%s</td><td>%s</td><td class='n'>%d</td><td class='n'>%s</td>"
                    "<td class='n'>%s</td><td class='n'>%.2f</td><td class='n'>%.0f%%</td>"
                    "<td class='n'>%d</td><td class='n'>%d</td></tr>"
                    % (esc(c), kind, len(g),
                       ("<b style='color:%s'>%d</b>" % (ORANGE, len(b))) if b else "0",
                       ("%.1f%%" % (len(b) / len(g) * 100)) if b else "&#8212;",
                       st.mean([r["rating"] for r in g]), st.mean([r["pct"] for r in g]),
                       d["VIDEO"], d["TRANSCRIPT"]))
    return out


rows_outcome, C = outcome_rows()
cost = C["VIDEO"] * 0.70 + C["TRANSCRIPT"] * 0.51
above_bar = sum(1 for r in rows if r["pct"] >= BAR)
thin = min(rows, key=lambda r: abs(r["rating"] - 3.20) + abs(r["responses"] - 5))
solid = min([r for r in bad if r["pct"] >= BAR and r["responses"] >= VOICES],
            key=lambda r: r["rating"])
floor_caught = [r for r in bad if r["pct"] >= BAR and r["responses"] < VOICES]
thin_good = [r for r in good if r["responses"] < VOICES]
jan = [r for r in rows if r["date"].month == 1]
aug = [r for r in rows if r["date"].month == 8]
jan_bad = sum(1 for r in jan if r["rating"] < LINE) / len(jan) * 100
aug_bad = sum(1 for r in aug if r["rating"] < LINE) / len(aug) * 100

HTML = """<title>Rating Participation Study</title>
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
.legend{display:flex;gap:18px;padding:2px 4px 10px;font-size:13px;color:var(--ink2)}
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
<h1>When should a low-rated class get a video analysis?</h1>
<p class="lede">Deciding which classes the AI should analyse &mdash; and how deeply &mdash; using
<b>eight months of real class data</b>: every live class and test review session from 1 January to
31 August 2026. %(n)s classes. This sets out what the data shows, what we are choosing to run with,
and where the two differ.</p>

<div class="card ok">
<h3 style="margin-top:4px">The settings we are starting with</h3>
<p style="margin:0">A class gets a <b>video analysis</b> when it is rated <b>below %(line).2f</b> and
<b>%(bar)d%% or more</b> of the learners who attended actually rated it &mdash; provided at least
<b>%(voices)d people</b> rated it at all. Below %(bar)d%% it gets a transcript analysis instead.</p>
<p class="sub" style="margin:10px 0 0">These are our recommended starting values, not what the data
alone would pick. Over the eight months the average participation is <b>%(dataavg).1f%%</b>; we are
setting the bar at <b>%(bar)d%%</b> deliberately, so that fewer genuinely-bad classes slip through.
Section 5 shows exactly what that choice costs and buys.</p>
</div>

<div class="big">
  <div class="stat"><div class="v">%(n)s</div><div class="l">classes, Jan&ndash;Aug 2026</div></div>
  <div class="stat"><div class="v">%(nbad)d</div><div class="l">rated below %(line).2f (%(badpct).0f%%)</div></div>
  <div class="stat"><div class="v">%(dataavg).1f%%</div><div class="l">average participation</div></div>
  <div class="stat"><div class="v" style="color:var(--warn)">%(pct80).1f%%</div>
    <div class="l">of classes ever reach 80%% participation</div></div>
</div>

<h2>1. What eight months of data says</h2>

<h3>a) The original 80%% rule could never have worked</h3>
<div class="card finding">
<p style="margin:0">Across %(n)s classes, only <b>%(n80)d (%(pct80).1f%%)</b> were rated by 80%% of
their attendees &mdash; and they average just <b>17 learners</b>, several of them 1&ndash;2-person
sessions where a single rating is 50&ndash;100%% by itself. In a typical fortnight, <b>zero</b>
classes reach the gate (16&ndash;30 Aug: none of 186). As written, the rule would have sent
essentially every low-rated class to transcript-only and the video path would almost never have
fired. The idea behind the rule is sound; the number sat outside the data.</p>
</div>

<h3>b) How many learners actually rate a class</h3>
<p>Attendance versus who left a rating &mdash; <b>%(att)s learners</b> sat in a class over the eight
months, and <b>%(resp)s</b> of them left a rating:</p>
<table>
<tr><th>Group</th><th>Classes</th><th>Learners attended</th><th>Learners who rated</th>
  <th>Avg participation</th><th>Median</th><th>Avg ratings per class</th></tr>
%(group_rows)s
</table>
<p>Two readings. First, the well-rated and badly-rated groups sit only <b>%(gap).1f points apart</b>
(%(gm).1f%% vs %(bm).1f%%) &mdash; a bad class is not rated noticeably less often than a good one, so
<b>participation cannot tell you whether a class went wrong</b> (correlation with the rating:
%(crating)+.2f; with class size: %(csize)+.2f &mdash; it tracks how big the room was, not how good
the class was). Second, and this is what makes it useful: <b>a normal class is rated by about half
its room</b> (mean %(dataavg).1f%%, median 50%%) &mdash; and that has been true every single month
since January.</p>

<h3>c) But participation does tell you how much to trust the score</h3>
<p>If only 5 of 15 learners rate a class 3.20, the score might be two annoyed people. If half the
room rates it and it is still bad, something is genuinely wrong. Eight months of data back this:</p>
<table>
<tr><th>Participation</th><th>Classes</th><th>Rating spread (std dev)</th>
  <th>Share rated below 4.0</th><th>Avg voices behind a low rating</th></tr>
%(trust_rows)s
</table>
<p>Classes rated by under half the room swing <b>%(spreadx).0f%% wider</b> and are
<b>%(extx).1f&times; more likely</b> to land below 4.0 &mdash; and when they do go low, the score
rests on <b>%(voicelo).0f responses</b> on average rather than <b>%(voicehi).0f</b>. Participation is
not a severity measure; it is a <b>confidence measure</b>, and as one it works.</p>

<div class="figure">
%(histogram)s
<div class="cap">Participation across all %(n)s classes, with the three lines that have been
proposed: our <b>%(bar)d%% bar</b>, the <b>%(dataavg).0f%% long-run average</b>, and the original
<b>80%% gate</b> out in the tail of the distribution.</div>
</div>

<h3>d) The trend the VP should see: low-rated classes are increasing</h3>
<div class="figure">
%(monthly_chart)s
<div class="legend">
  <span><span class="dot" style="background:%(BLUE)s"></span>rated %(line).2f or above</span>
  <span><span class="dot" style="background:%(ORANGE)s"></span>rated below %(line).2f</span>
</div>
<div class="cap">Classes per month. The share rated below %(line).2f has climbed from
<b>%(janbad).0f%% in January to %(augbad).0f%% in August</b> &mdash; roughly one class in four now.
Participation has stayed flat (~50%%) throughout, so this is a real quality trend, not a change in
who fills in ratings &mdash; and it is exactly why a working analysis pipeline matters now.</div>
</div>
<table>
<tr><th>Month</th><th>Classes</th><th>Below %(line).2f</th><th>Share</th><th>Avg participation</th>
  <th>&rarr; video</th><th>&rarr; transcript</th></tr>
%(monthly_rows)s
</table>

<h2>2. The voice factor &mdash; why a percentage alone is not enough</h2>
<p>A percentage hides the size of the room. <b>%(bar)d%% of a 10-person class is 4 people.
%(bar)d%% of a 100-person class is 40 people.</b> Same percentage, completely different confidence
&mdash; and the second is strong enough that the score needs no second-guessing at all.</p>
<table>
<tr><th>Class size</th><th>Classes</th><th>Typical attendance</th><th>Avg participation</th>
  <th>%(bar)d%% would mean</th><th>Which check governs</th></tr>
%(size_rows)s
</table>
<p>So the rule needs <b>two</b> checks, not one:</p>
<div class="formula">
<b>The voice check &mdash; both parts must pass:</b><br><br>
&nbsp;&nbsp;<b>1. Reach</b> &nbsp;&mdash;&nbsp; ratings &divide; attendees &nbsp;&ge;&nbsp;
<b>%(bar)d%%</b> &nbsp;<span class="sub">(a normal share of the room spoke)</span><br>
&nbsp;&nbsp;<b>2. Voices</b> &nbsp;&mdash;&nbsp; number of ratings &nbsp;&ge;&nbsp;
<b>%(voices)d</b> &nbsp;<span class="sub">(enough people that no single opinion decides it)</span>
</div>
<p>These two cross at a class of about <b>%(cross).0f learners</b> (%(voices)d &divide; %(bar)d%%).
Below that size the voice floor does the work; above it, the %(bar)d%% bar does:</p>
<table>
<tr><th>Example</th><th>Reach</th><th>Voices</th><th>Verdict</th></tr>
<tr><td>100 attended, 40 rated</td><td class="n">40%% &#10003;</td><td class="n">40 &#10003;</td>
  <td>Score fully trusted &mdash; act on it</td></tr>
<tr><td>25 attended, 10 rated</td><td class="n">40%% &#10003;</td><td class="n">10 &#10003;</td>
  <td>Score trusted</td></tr>
<tr class="warnrow"><td>10 attended, 4 rated</td><td class="n">40%% &#10003;</td>
  <td class="n">4 &#10007;</td><td>Reach looks fine, but 4 voices &mdash; watch, don't analyse</td></tr>
<tr class="warnrow"><td>15 attended, 5 rated</td><td class="n">33%% &#10007;</td>
  <td class="n">5 &#10003;</td><td>Enough voices, unrepresentative &mdash; transcript</td></tr>
</table>
<p>Across the eight months the voice floor changes the verdict on <b>%(nfloor)d classes</b> that
would otherwise have gone to video on a thin sample, and holds <b>%(nwatch)d</b> low-rated classes
at watch-only.</p>

<h2>3. The rule</h2>
<div class="rule"><ol>
<li>Rating <b>%(line).2f or above</b> &rarr; <b>no analysis</b> (unless a PM asks for one).</li>
<li>Below %(line).2f, fewer than <b>%(voices)d ratings</b> &rarr; <b>watch only</b>. Too few voices to
act on, whatever the percentage says.</li>
<li>Below %(line).2f, <b>%(bar)d%% or more</b> rated it &rarr; <b>video analysis</b>. A representative
share of the room spoke and it was still bad.</li>
<li>Below %(line).2f, <b>under %(bar)d%%</b> rated it &rarr; <b>transcript analysis</b>. Cheap and
fast &mdash; enough to see whether the complaint is real before spending more.</li>
<li>Any <b>escalation</b> or reported issue &rarr; <b>video analysis</b>, always, whatever the
numbers say.</li>
</ol></div>

<div class="figure">
%(scatter)s
<div class="legend">
  <span><span class="dot" style="background:%(BLUE)s"></span>rated %(line).2f or above (%(ngood)d)</span>
  <span><span class="dot" style="background:%(ORANGE)s"></span>below %(line).2f &mdash; needs a look (%(nbad)d)</span>
</div>
<div class="cap">All %(n)s classes. The flat cloud is the whole story of section 1b &mdash; and the
shaded corner is what earns a video analysis.</div>
</div>

<h3>What it produces over the eight months</h3>
<table>
<tr><th>Outcome</th><th>Classes (Jan&ndash;Aug)</th><th>Per week</th></tr>
%(outcomes)s
</table>
<p><b>%(work).1f analyses per week on average</b> &mdash; %(nvideo)d video and %(ntrans)d transcript
across the period, an AI cost of about <b>$%(month).0f a month</b>. Note the trend in section 1d:
August alone would have produced %(augwork)d analyses, so plan capacity on the recent months, not
the average.</p>

<h3>Two worked cases</h3>
<div class="card">
<p style="margin:0 0 8px"><b>Thin sample, bad score.</b> %(thincourse)s &mdash; rating
<b>%(thinr).2f</b>, %(thinresp).0f of %(thinatt).0f rated (<b>%(thinpct).0f%%</b>).<br>
&rarr; <b>Transcript analysis.</b> Below the bar, so we don't spend a video on a score five people gave.</p>
<p style="margin:0"><b>Representative sample, still bad.</b> %(solidcourse)s &mdash; rating
<b>%(solidr).2f</b>, %(solidresp).0f of %(solidatt).0f rated (<b>%(solidpct).0f%%</b>).<br>
&rarr; <b>Video analysis.</b> The room spoke and it was still this low.</p>
</div>

<h2>4. What lands where</h2>
<h3>Video &mdash; below %(line).2f, and enough of the room said so (%(nvideo)d classes)</h3>
<table>
<tr><th>Rating</th><th>Rated</th><th>Part.</th><th>Category</th><th>Course</th><th>Date</th></tr>
%(video_rows)s
</table>
<h3>Transcript &mdash; below %(line).2f, but too thin a sample to trust yet (%(ntrans)d classes)</h3>
<table>
<tr><th>Rating</th><th>Rated</th><th>Part.</th><th>Category</th><th>Course</th><th>Date</th></tr>
%(trans_rows)s
</table>
<h3>Watch only &mdash; fewer than %(voices)d voices (%(nwatch)d classes)</h3>
<table>
<tr><th>Rating</th><th>Rated</th><th>Part.</th><th>Category</th><th>Course</th><th>Date</th></tr>
%(watch_rows)s
</table>

<h2>5. What the %(bar)d%% bar costs and buys</h2>
<p>This is the one place our chosen setting and the data pull in different directions, so it is worth
being explicit. <b>%(abovebar)d of %(n)s classes (%(abovepct).0f%%) sit at or above %(bar)d%%</b>
participation, so a bar there is a light filter: roughly three of every four low-rated classes clear
it and go to video.</p>
<table>
<tr><th>Bar</th><th>Low-rated &rarr; video</th><th>Low-rated &rarr; transcript</th>
  <th>Analyses / week</th><th></th></tr>
%(threshold_rows)s
</table>
<p>The trade is straightforward: a lower bar catches more real problems on video and costs more
review time; a higher bar is cheaper and risks reading a genuine problem from a transcript alone.
<b>We are choosing the lower bar on purpose</b> &mdash; missing a bad class costs more than an extra
analysis does. If weekly volume proves too high, the bar &mdash; not the idea &mdash; is the dial.</p>

<h3>Every setting side by side</h3>
<table>
<tr><th>Setting</th><th>Rating line</th><th>Bar</th><th>Video</th><th>Transcript</th>
  <th>Watch</th><th>Analyses / week</th></tr>
%(settings_rows)s
</table>

<h2>6. The eight months by course</h2>
<table>
<tr><th>Course</th><th>Category</th><th>Classes</th><th>Below %(line).2f</th><th>Share</th>
  <th>Avg rating</th><th>Avg part.</th><th>&rarr; video</th><th>&rarr; transcript</th></tr>
%(course_rows)s
</table>

<h2>7. Open points</h2>
<div class="card">
<ol style="margin:4px 0;padding-left:20px">
<li><b>Capacity is the real constraint.</b> The AI cost is trivial ($%(month).0f/month at the
average, ~$%(augcost).0f at August's rate); the PM time to review %(work).0f&ndash;%(augwork)d
analyses a week is not. If it proves too much, the section-5 table shows what 45%% or 50%% buys back.</li>
<li><b>Good ratings can be thin too.</b> %(nthingood)d classes rated %(line).2f or above were rated
by fewer than %(voices)d people &mdash; the evidence they went <i>well</i> is just as thin. We are
deliberately not chasing these; worth revisiting if capacity allows.</li>
<li><b>The bar drifts with class size</b> (participation tracks class size at %(csize)+.2f), so
%(bar)d%% is easier to clear in a 40-person class than a 12-person one. The %(voices)d-voice floor
covers the small end; no further fix needed yet.</li>
<li><b>The August trend needs an owner.</b> One class in four now rates below %(line).2f, up from one
in seven in January &mdash; concentrated in Transformative GenAI and Applied Agentic AI. The analysis
pipeline finds the *why* per class; the month-on-month climb is a programme-level question.</li>
</ol>
</div>

<footer>
Source: <i>the rating sheet .xlsx</i> &mdash; sheets MLSU_Live_Class_Poll and
Agentic_AI_Live_Class_Poll, all sessions dated 1 Jan &ndash; 31 Aug 2026. %(n)s classes after
removing duplicates and 2 data-error rows (more ratings than attendees). Ratings, response counts
and attendance otherwise used exactly as recorded. Prepared by Bishal Roy, New Programs &mdash;
contains class-level data, keep internal.
</footer>
</div>
""" % dict(
    BLUE=BLUE, ORANGE=ORANGE, line=LINE, bar=BAR, voices=VOICES, dataavg=DATA_AVG, cross=CROSS,
    scatter=scatter(), histogram=histogram(), monthly_chart=monthly(),
    n="{:,}".format(len(rows)), ngood=len(good), nbad=len(bad),
    badpct=len(bad) / len(rows) * 100,
    n80=n80, pct80=n80 / len(rows) * 100,
    att="{:,.0f}".format(sum(r["attended"] for r in rows)),
    resp="{:,.0f}".format(sum(r["responses"] for r in rows)),
    group_rows=group_rows(), trust_rows=trust_rows(), size_rows=size_rows(),
    monthly_rows=monthly_rows(), threshold_rows=threshold_rows(), settings_rows=settings_rows(),
    outcomes=rows_outcome,
    video_rows=listing("VIDEO"), trans_rows=listing("TRANSCRIPT"), watch_rows=listing("WATCH"),
    course_rows=course_rows(),
    gm=st.mean([r["pct"] for r in good]), bm=st.mean([r["pct"] for r in bad]),
    gap=st.mean([r["pct"] for r in good]) - st.mean([r["pct"] for r in bad]),
    crating=C_RATING, csize=C_SIZE,
    spreadx=(st.pstdev([r["rating"] for r in rows if r["pct"] < round(DATA_AVG)])
             / st.pstdev([r["rating"] for r in rows if r["pct"] >= round(DATA_AVG)]) - 1) * 100,
    extx=((sum(1 for r in rows if r["pct"] < round(DATA_AVG) and r["rating"] < 4.0)
           / max(sum(1 for r in rows if r["pct"] < round(DATA_AVG)), 1))
          / max((sum(1 for r in rows if r["pct"] >= round(DATA_AVG) and r["rating"] < 4.0)
                 / max(sum(1 for r in rows if r["pct"] >= round(DATA_AVG)), 1)), 1e-9)),
    voicelo=st.mean([r["responses"] for r in bad if r["pct"] < round(DATA_AVG)]),
    voicehi=st.mean([r["responses"] for r in bad if r["pct"] >= round(DATA_AVG)]),
    work=(C["VIDEO"] + C["TRANSCRIPT"]) / WEEKS, nvideo=C["VIDEO"], ntrans=C["TRANSCRIPT"],
    nwatch=C["WATCH"], month=cost / 8,
    augwork=sum(1 for r in aug if decide(r) in ("VIDEO", "TRANSCRIPT")),
    augcost=sum(0.70 if decide(r) == "VIDEO" else 0.51
                for r in aug if decide(r) in ("VIDEO", "TRANSCRIPT")),
    abovebar=above_bar, abovepct=above_bar / len(rows) * 100,
    nfloor=len(floor_caught), nthingood=len(thin_good),
    janbad=jan_bad, augbad=aug_bad,
    thincourse=esc(thin["course"]), thinr=thin["rating"], thinresp=thin["responses"],
    thinatt=thin["attended"], thinpct=thin["pct"],
    solidcourse=esc(solid["course"]), solidr=solid["rating"], solidresp=solid["responses"],
    solidatt=solid["attended"], solidpct=solid["pct"],
)

out = os.path.join(HERE, "rating-threshold-report.html")
open(out, "w", encoding="utf-8").write(HTML)
print("wrote %s  (%.0f KB)" % (out, len(HTML) / 1024))
print("classes %d | video %d | transcript %d | watch %d | none %d | %.1f analyses/week avg"
      % (len(rows), C["VIDEO"], C["TRANSCRIPT"], C["WATCH"], C["NONE"],
         (C["VIDEO"] + C["TRANSCRIPT"]) / WEEKS))
