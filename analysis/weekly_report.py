"""One week of class ratings - how many went well, how many didn't, by category and by course.

Reusable: run it for any week.
    python analysis/weekly_report.py --from 2026-08-24 --to 2026-08-30
Writes a local HTML report (and prints the same numbers to the terminal). Local only.
"""
import argparse
import datetime as dt
import os
import statistics as st
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ratings_data import GOOD, load  # noqa: E402

BLUE, ORANGE = "#2a78d6", "#eb6834"      # validated pair (light + dark, all-pairs)
SERIOUS, MIN_VOICES = 4.25, 3


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def decide(r):
    if r["responses"] < MIN_VOICES:
        return "WATCH"
    if r["rating"] >= GOOD:
        return "NONE"
    return "VIDEO" if r["rating"] < SERIOUS else "TRANSCRIPT"


def band(r):
    if r["rating"] >= 4.75:
        return "Excellent (4.75+)"
    if r["rating"] >= GOOD:
        return "Good (4.50-4.74)"
    if r["rating"] >= SERIOUS:
        return "Weak (4.25-4.49)"
    if r["rating"] >= 4.0:
        return "Poor (4.00-4.24)"
    return "Worst (below 4.00)"


BANDS = ["Excellent (4.75+)", "Good (4.50-4.74)", "Weak (4.25-4.49)",
         "Poor (4.00-4.24)", "Worst (below 4.00)"]


# ------------------------------------------------------------------ chart: good vs bad by course
def course_chart(rows):
    by = defaultdict(list)
    for r in rows:
        by[r["course"]].append(r)
    order = sorted(by, key=lambda c: -len(by[c]))
    # the chart needs shorter names than the tables do, or the row labels run off the canvas
    SHORT = {"FDE (Forward Deployed Engineering)": "FDE",
             "PwC x IK Agentic AI Accelerator": "PwC x IK Accelerator",
             "ML SwitchUp (unmapped cohort)": "ML SwitchUp (other)"}
    W, rowh, ml, mr, mt = 720, 34, 190, 120, 26
    H = mt + rowh * len(order) + 26
    top = max(len(v) for v in by.values())
    scale = (W - ml - mr) / top
    p = ['<svg viewBox="0 0 %d %d" role="img" aria-label="Classes per course this week, split '
         'into those rated 4.5 and above and those below.">' % (W, H)]
    p.append('<text x="%d" y="14" class="tick">classes run this week</text>' % ml)
    for i, c in enumerate(order):
        g = [r for r in by[c] if r["rating"] >= GOOD]
        b = [r for r in by[c] if r["rating"] < GOOD]
        y = mt + i * rowh
        p.append('<text x="%d" y="%d" text-anchor="end" class="rowlab">%s</text>'
                 % (ml - 12, y + 15, esc(SHORT.get(c, c))))
        wg, wb = len(g) * scale, len(b) * scale
        if wg:
            p.append('<rect x="%d" y="%d" width="%.1f" height="18" rx="4" fill="%s">'
                     '<title>%s: %d rated 4.5+</title></rect>' % (ml, y + 2, wg, BLUE, esc(c), len(g)))
        if wb:
            p.append('<rect x="%.1f" y="%d" width="%.1f" height="18" rx="4" fill="%s">'
                     '<title>%s: %d below 4.5</title></rect>'
                     % (ml + wg + 2, y + 2, max(wb - 2, 2), ORANGE, esc(c), len(b)))
        if len(g):
            p.append('<text x="%.1f" y="%d" class="inbar">%d</text>' % (ml + 7, y + 16, len(g)))
        if len(b):
            p.append('<text x="%.1f" y="%d" class="tick">%d below 4.5</text>'
                     % (ml + wg + wb + 8, y + 16, len(b)))
    p.append("</svg>")
    return "".join(p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="lo", default="2026-08-24")
    ap.add_argument("--to", dest="hi", default="2026-08-30")
    a = ap.parse_args()
    lo = dt.datetime.strptime(a.lo, "%Y-%m-%d")
    hi = dt.datetime.strptime(a.hi, "%Y-%m-%d").replace(hour=23, minute=59, second=59)

    rows = load(lo, hi)
    bad = [r for r in rows if r["rating"] < GOOD]
    good = [r for r in rows if r["rating"] >= GOOD]
    label = "%s to %s %s" % (lo.strftime("%d"), hi.strftime("%d"), hi.strftime("%B %Y"))

    # ---------------------------------------------------------------- terminal output
    print("=" * 72)
    print("WEEK OF %s" % label.upper())
    print("=" * 72)
    print("Classes run          : %d" % len(rows))
    print("Rated 4.5 and above  : %d  (%.1f%%)" % (len(good), len(good) / len(rows) * 100))
    print("Rated below 4.5      : %d  (%.1f%%)" % (len(bad), len(bad) / len(rows) * 100))
    print("Average rating       : %.2f" % st.mean([r["rating"] for r in rows]))

    print("\nBY CATEGORY")
    print("  %-14s%7s%9s%9s%12s" % ("", "classes", "4.5+", "below", "avg rating"))
    for kind in ("Live Class", "Test Review"):
        g = [r for r in rows if r["kind"] == kind]
        if not g:
            continue
        b = [r for r in g if r["rating"] < GOOD]
        print("  %-14s%7d%9d%9d%12.2f"
              % (kind, len(g), len(g) - len(b), len(b), st.mean([r["rating"] for r in g])))

    print("\nBY COURSE")
    print("  %-36s%-13s%8s%7s%8s" % ("Course", "category", "classes", "4.5+", "below"))
    by = defaultdict(list)
    for r in rows:
        by[r["course"]].append(r)
    for c in sorted(by, key=lambda c: -len(by[c])):
        for kind in ("Live Class", "Test Review"):
            g = [r for r in by[c] if r["kind"] == kind]
            if not g:
                continue
            b = [r for r in g if r["rating"] < GOOD]
            print("  %-36s%-13s%8d%7d%8d" % (c, kind, len(g), len(g) - len(b), len(b)))

    print("\nWORST CLASSES THIS WEEK")
    for r in sorted(bad, key=lambda r: r["rating"])[:10]:
        print("  %.2f  %2.0f/%2.0f rated  %-12s %-34s %s"
              % (r["rating"], r["responses"], r["attended"], r["kind"], r["course"], r["topic"][:30]))

    # ---------------------------------------------------------------- rows for the HTML
    cat_rows = ""
    for kind in ("Live Class", "Test Review"):
        g = [r for r in rows if r["kind"] == kind]
        if not g:
            continue
        b = [r for r in g if r["rating"] < GOOD]
        cat_rows += ("<tr><td><b>%s</b></td><td class='n'>%d</td><td class='n'>%d</td>"
                     "<td class='n'>%d</td><td class='n'>%.1f%%</td><td class='n'>%.2f</td></tr>"
                     % (kind, len(g), len(g) - len(b), len(b), len(b) / len(g) * 100,
                        st.mean([r["rating"] for r in g])))

    band_rows = ""
    counts = Counter(band(r) for r in rows)
    for bn in BANDS:
        n = counts[bn]
        cls = " class='warnrow'" if bn.startswith(("Poor", "Worst")) else ""
        band_rows += ("<tr%s><td>%s</td><td class='n'>%d</td><td class='n'>%.1f%%</td></tr>"
                      % (cls, bn, n, n / len(rows) * 100))

    course_rows = ""
    for c in sorted(by, key=lambda c: (-len([r for r in by[c] if r["rating"] < GOOD]), -len(by[c]))):
        for kind in ("Live Class", "Test Review"):
            g = [r for r in by[c] if r["kind"] == kind]
            if not g:
                continue
            b = [r for r in g if r["rating"] < GOOD]
            course_rows += ("<tr><td>%s</td><td>%s</td><td class='n'>%d</td><td class='n'>%d</td>"
                            "<td class='n'>%s</td><td class='n'>%.2f</td></tr>"
                            % (esc(c), kind, len(g), len(g) - len(b),
                               ("<b style='color:var(--warn)'>%d</b>" % len(b)) if b else "0",
                               st.mean([r["rating"] for r in g])))
        tot, tb = by[c], [r for r in by[c] if r["rating"] < GOOD]
        course_rows += ("<tr class='sumrow'><td></td><td>all</td><td class='n'>%d</td>"
                        "<td class='n'>%d</td><td class='n'>%d</td><td class='n'>%.2f</td></tr>"
                        % (len(tot), len(tot) - len(tb), len(tb),
                           st.mean([r["rating"] for r in tot])))

    worst_rows = "".join(
        "<tr><td class='n'><b style='color:var(--warn)'>%.2f</b></td><td class='n'>%.0f of %.0f</td>"
        "<td>%s</td><td>%s</td><td>%s</td><td class='n'>%s</td></tr>"
        % (r["rating"], r["responses"], r["attended"], r["kind"], esc(r["course"]),
           esc(r["instructor"]), decide(r).title())
        for r in sorted(bad, key=lambda r: r["rating"]))

    d = Counter(decide(r) for r in rows)
    HTML = TEMPLATE % dict(
        BLUE=BLUE, ORANGE=ORANGE, label=label,
        n=len(rows), ngood=len(good), nbad=len(bad),
        pgood=len(good) / len(rows) * 100, pbad=len(bad) / len(rows) * 100,
        avg=st.mean([r["rating"] for r in rows]),
        chart=course_chart(rows), cat_rows=cat_rows, band_rows=band_rows,
        course_rows=course_rows, worst_rows=worst_rows,
        nvideo=d["VIDEO"], ntrans=d["TRANSCRIPT"], nwatch=d["WATCH"],
        cost=d["VIDEO"] * 0.70 + d["TRANSCRIPT"] * 0.51,
        worstcourse=max(by, key=lambda c: len([r for r in by[c] if r["rating"] < GOOD])),
        generated=dt.date.today().strftime("%d %B %Y"),
    )
    out = os.path.join(HERE, "week-%s-to-%s.html") % (lo.strftime("%d%b").lower(), hi.strftime("%d%b").lower())
    open(out, "w", encoding="utf-8").write(HTML)
    print("\nwrote %s" % out)


TEMPLATE = """<title>Class Ratings - Week of %(label)s</title>
<style>
:root{--bg:#f7f7f5;--surface:#fff;--surface2:#f2f2ef;--ink:#16161a;--ink2:#4b4b53;--ink3:#7a7a85;
  --line:#dededa;--brand:%(BLUE)s;--warn:%(ORANGE)s;--radius:12px}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#131315;--surface:#1b1b1e;
  --surface2:#232326;--ink:#f3f3f5;--ink2:#bdbdc4;--ink3:#8c8c95;--line:#33333a;
  --brand:#3987e5;--warn:#d95926}}
:root[data-theme="dark"]{--bg:#131315;--surface:#1b1b1e;--surface2:#232326;--ink:#f3f3f5;
  --ink2:#bdbdc4;--ink3:#8c8c95;--line:#33333a;--brand:#3987e5;--warn:#d95926}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 ui-sans-serif,system-ui,
  "Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:860px;margin:0 auto;padding:44px 28px 70px}
h1{font-size:33px;line-height:1.1;letter-spacing:-.02em;margin:0 0 6px}
h2{font-size:20px;margin:36px 0 10px;padding-top:14px;border-top:1px solid var(--line)}
.kicker{font-size:11.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;
  color:var(--brand);margin-bottom:10px}
.lede{font-size:17px;color:var(--ink2);margin:0 0 4px}
p{margin:10px 0}
.big{display:flex;gap:14px;flex-wrap:wrap;margin:18px 0}
.stat{flex:1 1 140px;background:var(--surface);border:1px solid var(--line);
  border-radius:var(--radius);padding:14px 16px}
.stat .v{font-size:28px;font-weight:750;letter-spacing:-.02em}
.stat .l{font-size:12.5px;color:var(--ink2);margin-top:2px}
.figure{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);
  padding:16px 14px 10px;margin:16px 0}
.figure svg{display:block;width:100%%;height:auto}
.cap{color:var(--ink2);font-size:13px;padding:8px 4px 2px}
.legend{display:flex;gap:18px;padding:4px 4px 8px;font-size:13px;color:var(--ink2)}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%%;margin-right:6px;vertical-align:-1px}
.tick{font-size:11.5px;fill:var(--ink3)}
.rowlab{font-size:13px;fill:var(--ink)}
.inbar{font-size:12px;font-weight:700;fill:#fff}
table{width:100%%;border-collapse:collapse;margin:10px 0;font-size:14px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}
th{font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--ink2);
  background:var(--surface2)}
td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tr.sumrow td{background:var(--surface2);font-weight:650}
tr.warnrow td{background:color-mix(in srgb,%(ORANGE)s 9%%,transparent)}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);
  padding:16px 18px;margin:14px 0}
.card.flag{border-left:4px solid var(--warn)}
footer{margin-top:40px;padding-top:14px;border-top:1px solid var(--line);color:var(--ink3);font-size:12.5px}
@media print{body{background:#fff}.wrap{max-width:none;padding:0}
  h2{break-after:avoid}.figure,.card,table{break-inside:avoid}}
</style>
<div class="wrap">
<div class="kicker">Interview Kickstart &middot; New Programs &middot; weekly class ratings</div>
<h1>Week of %(label)s</h1>
<p class="lede">Every live class and test review session run this week, split by how it was rated.</p>

<div class="big">
  <div class="stat"><div class="v">%(n)d</div><div class="l">classes run</div></div>
  <div class="stat"><div class="v" style="color:%(BLUE)s">%(ngood)d</div>
    <div class="l">rated 4.5 and above (%(pgood).0f%%)</div></div>
  <div class="stat"><div class="v" style="color:var(--warn)">%(nbad)d</div>
    <div class="l">rated below 4.5 (%(pbad).0f%%)</div></div>
  <div class="stat"><div class="v">%(avg).2f</div><div class="l">average rating</div></div>
</div>

<h2>Live classes vs test reviews</h2>
<table>
<tr><th>Category</th><th>Classes</th><th>4.5 and above</th><th>Below 4.5</th><th>Share below</th>
  <th>Avg rating</th></tr>
%(cat_rows)s
</table>

<h2>How the week spread out</h2>
<table>
<tr><th>Rating band</th><th>Classes</th><th>Share</th></tr>
%(band_rows)s
</table>

<h2>By course</h2>
<div class="figure">
%(chart)s
<div class="legend">
  <span><span class="dot" style="background:%(BLUE)s"></span>rated 4.5 and above</span>
  <span><span class="dot" style="background:%(ORANGE)s"></span>rated below 4.5</span>
</div>
<div class="cap">Courses are ordered by how many classes they ran this week.</div>
</div>
<table>
<tr><th>Course</th><th>Category</th><th>Classes</th><th>4.5 and above</th><th>Below 4.5</th>
  <th>Avg rating</th></tr>
%(course_rows)s
</table>
<div class="card flag">
<b>Where the problems are concentrated:</b> %(worstcourse)s has the most classes below 4.5 this week.
</div>

<h2>Every class below 4.5 this week</h2>
<p>Sorted worst first. The last column is what the recommended rule would do with each one
(video below 4.25, transcript 4.25&ndash;4.49, watch-only when fewer than 3 people rated it).</p>
<table>
<tr><th>Rating</th><th>Rated</th><th>Category</th><th>Course</th><th>Instructor</th><th>Action</th></tr>
%(worst_rows)s
</table>

<h2>What this week would cost to analyse</h2>
<table>
<tr><th>Action</th><th>Classes</th></tr>
<tr><td><b>Video analysis</b> (rating below 4.25)</td><td class="n">%(nvideo)d</td></tr>
<tr><td><b>Transcript analysis</b> (4.25 &ndash; 4.49)</td><td class="n">%(ntrans)d</td></tr>
<tr><td>Watch only (fewer than 3 ratings)</td><td class="n">%(nwatch)d</td></tr>
</table>
<p><b>%(nvideo)d + %(ntrans)d = %(nvideo)d video and %(ntrans)d transcript analyses</b>, about
<b>$%(cost).2f</b> of AI cost for the whole week.</p>

<footer>
Source: <i>the rating sheet .xlsx</i> (sheets MLSU_Live_Class_Poll, Agentic_AI_Live_Class_Poll),
sessions dated %(label)s. Duplicates removed; no rows excluded. Generated %(generated)s.
Contains class and instructor level data &mdash; keep internal.
</footer>
</div>
"""

if __name__ == "__main__":
    main()
