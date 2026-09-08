"""Builds the validation study as HTML in the house style (inline SVG, no CDN) and prints it to
PDF with headless Chrome, plus the two-page VP one-pager.

  Sentiment-Score-Validation.pdf   the full study (repo root, gitignored)
  Sentiment-Score-One-Pager.pdf    the VP one-pager (repo root, gitignored)
  analysis/out/*.html              the HTML sources

Reads the outputs of sentiment_decide.py and the other sentiment_*.py scripts. Local only: the
workbook is confidential and the outputs carry instructor names.
"""
import json
import os
import statistics as st
import subprocess
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sentiment_common import (Study, Engine, OUT, BANDS, BAND_LABEL, LINE, BAR, VOICES, CEILING, COST, MONTHS, WEIGHTS,  # noqa: E402
                              standardised_share, read_json, describe_cfg, needs_contract_change)
from sentiment_score import CONFIGS  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BLUE, ORANGE, GREEN = "#2a78d6", "#eb6834", "#2f9e6e"
BC = {"Excellent": "#1f8a70", "Good": "#4f7cac", "Average": "#d99a2b", "Bad": "#b5432f", "no band": "#b9b9b4"}
CK = ["C0", "C1", "C2", "C3", "C4", "C5"]
SHORT = {"C0": "C0 original", "C1": "C1 + min votes", "C2": "C2 graded approval", "C3": "C3 graded + guard", "C4": "C4 data weights", "C5": "C5 two lines"}


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def pct(v, d=1):
    return ("%." + str(d) + "f%%") % v


def n1(v, d=1):
    return ("%." + str(d) + "f") % v


# ------------------------------------------------------------------ SVG kit
def hbars(items, maxv=None, w=720, colour=None, fmt="%.1f", mark=None, mark_label="", aria=""):
    """items: [(label, value, colour?)]; horizontal bars with the value at the end."""
    rowh, ml, mr = 26, 170, 70
    h = rowh * len(items) + 14
    maxv = maxv or max(max(v for _, v, *_ in items), 1e-9)
    pw = w - ml - mr
    p = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (w, h, esc(aria))]
    for i, it in enumerate(items):
        label, v = it[0], it[1]
        col = it[2] if len(it) > 2 else (colour or BLUE)
        y = 6 + i * rowh
        bw = max(0.0, min(1.0, v / maxv)) * pw
        p.append('<text x="%d" y="%.1f" text-anchor="end" class="tick" style="font-size:12px">%s</text>' % (ml - 8, y + 15, esc(label)))
        p.append('<rect x="%d" y="%.1f" width="%.1f" height="%d" rx="3" fill="%s"/>' % (ml, y + 3, bw, rowh - 8, col))
        p.append('<text x="%.1f" y="%.1f" class="tick" style="fill:var(--ink);font-size:12px">%s</text>' % (ml + bw + 6, y + 15, fmt % v))
    if mark is not None:
        x = ml + min(1.0, mark / maxv) * pw
        p.append('<line x1="%.1f" y1="2" x2="%.1f" y2="%d" stroke="%s" stroke-width="1.5" stroke-dasharray="5 4"/>' % (x, x, h - 4, ORANGE))
        if mark_label:
            p.append('<text x="%.1f" y="%d" class="gate" text-anchor="middle" style="font-size:11px">%s</text>' % (x, h - 1, esc(mark_label)))
    p.append("</svg>")
    return "".join(p)


def stacked(rows, keys, w=720, aria=""):
    """rows: [(label, {key: share})]; 100% stacked horizontal bars."""
    rowh, ml, mr = 28, 170, 16
    h = rowh * len(rows) + 30
    pw = w - ml - mr
    p = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (w, h, esc(aria))]
    for i, (label, shares) in enumerate(rows):
        y = 6 + i * rowh
        x = ml
        p.append('<text x="%d" y="%.1f" text-anchor="end" class="tick" style="font-size:12px">%s</text>' % (ml - 8, y + 16, esc(label)))
        for k in keys:
            v = shares.get(k, 0.0)
            bw = v / 100 * pw
            if bw > 0:
                p.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%d" fill="%s"/>' % (x, y + 3, bw, rowh - 8, BC.get(k, BLUE)))
                if bw > 34:
                    p.append('<text x="%.1f" y="%.1f" text-anchor="middle" style="font-size:11px;fill:#fff;font-weight:700">%.0f%%</text>' % (x + bw / 2, y + 17, v))
            x += bw
    lx = ml
    for k in keys:
        p.append('<rect x="%.1f" y="%d" width="10" height="10" fill="%s"/>' % (lx, h - 16, BC.get(k, BLUE)))
        p.append('<text x="%.1f" y="%d" class="tick" style="font-size:11px">%s</text>' % (lx + 14, h - 7, esc(k)))
        lx += 16 + 8 * len(k) + 14
    p.append("</svg>")
    return "".join(p)


def grouped(cats, series, w=720, h=240, ymax=None, fmt="%.0f%%", aria="", ylab=""):
    """cats: [labels]; series: [(name, colour, [values])]."""
    ml, mr, mt, mb = 46, 12, 20, 40
    pw, ph = w - ml - mr, h - mt - mb
    ymax = ymax or max(max(v for v in s[2]) for s in series) * 1.15 or 1
    p = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (w, h, esc(aria))]
    for g in range(5):
        v = ymax * g / 4
        yy = mt + ph - v / ymax * ph
        p.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="var(--grid)"/>' % (ml, yy, w - mr, yy))
        p.append('<text x="%d" y="%.1f" text-anchor="end" class="tick">%s</text>' % (ml - 6, yy + 4, fmt % v))
    gw = pw / len(cats)
    bw = (gw - 10) / len(series)
    for ci, c in enumerate(cats):
        for si, (name, col, vals) in enumerate(series):
            v = vals[ci]
            x = ml + ci * gw + 5 + si * bw
            bh = min(1.0, v / ymax) * ph
            p.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="2" fill="%s"/>' % (x, mt + ph - bh, bw - 2, bh, col))
            p.append('<text x="%.1f" y="%.1f" text-anchor="middle" class="tick" style="fill:var(--ink);font-size:10.5px">%s</text>' % (x + bw / 2 - 1, mt + ph - bh - 4, fmt % v))
        p.append('<text x="%.1f" y="%d" text-anchor="middle" class="tick">%s</text>' % (ml + ci * gw + gw / 2, h - mb + 16, esc(c)))
    lx = ml
    for name, col, _ in series:
        p.append('<rect x="%.1f" y="%d" width="10" height="10" fill="%s"/>' % (lx, h - 12, col))
        p.append('<text x="%.1f" y="%d" class="tick" style="font-size:11px">%s</text>' % (lx + 14, h - 3, esc(name)))
        lx += 16 + 6.5 * len(name) + 16
    if ylab:
        p.append('<text x="%d" y="%d" class="axis" transform="rotate(-90 12 %d)" text-anchor="middle">%s</text>' % (12, mt + ph / 2, mt + ph / 2, esc(ylab)))
    p.append("</svg>")
    return "".join(p)


def histogram(scores, edges, w=720, h=230, aria=""):
    ml, mr, mt, mb = 46, 12, 18, 36
    pw, ph = w - ml - mr, h - mt - mb
    bins = [0] * 40
    for s in scores:
        bins[min(39, int(s // 2.5))] += 1
    mx = max(bins) or 1
    p = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (w, h, esc(aria))]
    zones = [(0, edges["average"], "Bad"), (edges["average"], edges["good"], "Average"), (edges["good"], edges["excellent"], "Good"), (edges["excellent"], 100, "Excellent")]
    for lo, hi, name in zones:
        p.append('<rect x="%.1f" y="%d" width="%.1f" height="%d" fill="%s" fill-opacity=".10"/>' % (ml + lo / 100 * pw, mt, (hi - lo) / 100 * pw, ph, BC[name]))
        p.append('<text x="%.1f" y="%d" text-anchor="middle" class="note">%s</text>' % (ml + (lo + hi) / 2 / 100 * pw, mt + 12, name))
    for i, c in enumerate(bins):
        x = ml + i * 2.5 / 100 * pw
        bh = c / mx * (ph - 16)
        p.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"/>' % (x + 0.5, mt + ph - bh, 2.5 / 100 * pw - 1, bh, BLUE))
    for v in (0, 20, 40, 60, 75, 90, 100):
        p.append('<text x="%.1f" y="%d" text-anchor="middle" class="tick">%d</text>' % (ml + v / 100 * pw, h - mb + 16, v))
    for name, v in edges.items():
        x = ml + v / 100 * pw
        p.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s" stroke-width="1.5" stroke-dasharray="4 3"/>' % (x, mt, x, mt + ph, ORANGE))
    p.append('<text x="%.1f" y="%d" class="axis" text-anchor="middle">score (two-and-a-half-point bins)</text>' % (ml + pw / 2, h - 4))
    p.append("</svg>")
    return "".join(p)


def scatter(points, marks, w=720, h=360, xmax=None, ymax=None, aria=""):
    """points: [(x, y, colour, alpha)]; marks: [(x, y, label, colour)]. x = flip share, y = analyses a week."""
    ml, mr, mt, mb = 50, 12, 16, 44
    pw, ph = w - ml - mr, h - mt - mb
    xmax = xmax or max(max(x for x, *_ in points), max(x for x, *_ in marks)) * 1.05
    ymax = ymax or max(max(y for _, y, *_ in points), max(y for _, y, *_ in marks)) * 1.05
    X = lambda v: ml + v / xmax * pw      # noqa: E731
    Y = lambda v: mt + ph - v / ymax * ph  # noqa: E731
    p = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (w, h, esc(aria))]
    for g in range(6):
        v = ymax * g / 5
        p.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="var(--grid)"/>' % (ml, Y(v), w - mr, Y(v)))
        p.append('<text x="%d" y="%.1f" text-anchor="end" class="tick">%.0f</text>' % (ml - 6, Y(v) + 4, v))
    for g in range(6):
        v = xmax * g / 5
        p.append('<text x="%.1f" y="%d" text-anchor="middle" class="tick">%.0f%%</text>' % (X(v), h - mb + 16, v))
    p.append('<rect x="%d" y="%.1f" width="%.1f" height="%.1f" fill="%s" fill-opacity=".06"/>' % (ml, Y(CEILING["per_week"]), pw, mt + ph - Y(CEILING["per_week"]), GREEN))
    p.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s" stroke-dasharray="5 4"/>' % (ml, Y(CEILING["per_week"]), w - mr, Y(CEILING["per_week"]), GREEN))
    p.append('<text x="%d" y="%.1f" class="note" style="fill:%s">capacity: 12 a week</text>' % (ml + 6, Y(CEILING["per_week"]) - 5, GREEN))
    for x, y, col, a in points:
        p.append('<circle cx="%.1f" cy="%.1f" r="2.2" fill="%s" fill-opacity="%.2f"/>' % (X(min(x, xmax)), Y(min(y, ymax)), col, a))
    for x, y, label, col in marks:
        p.append('<circle cx="%.1f" cy="%.1f" r="5.5" fill="%s" stroke="#fff" stroke-width="1.5"/>' % (X(min(x, xmax)), Y(min(y, ymax)), col))
        p.append('<text x="%.1f" y="%.1f" class="barlab" style="fill:%s">%s</text>' % (X(min(x, xmax)) + 8, Y(min(y, ymax)) + 4, col, esc(label)))
    p.append('<text x="%.1f" y="%d" class="axis" text-anchor="middle">classes whose band flips on one vote</text>' % (ml + pw / 2, h - 4))
    p.append('<text x="%d" y="%d" class="axis" transform="rotate(-90 12 %d)" text-anchor="middle">analyses a week</text>' % (12, mt + ph / 2, mt + ph / 2))
    p.append("</svg>")
    return "".join(p)


def lines_chart(cats, series, w=720, h=230, ymax=None, fmt="%.0f%%", aria=""):
    ml, mr, mt, mb = 46, 14, 18, 34
    pw, ph = w - ml - mr, h - mt - mb
    ymax = ymax or max(max(s[2]) for s in series) * 1.2 or 1
    X = lambda i: ml + i / max(1, len(cats) - 1) * pw   # noqa: E731
    Y = lambda v: mt + ph - v / ymax * ph               # noqa: E731
    p = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (w, h, esc(aria))]
    for g in range(5):
        v = ymax * g / 4
        p.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="var(--grid)"/>' % (ml, Y(v), w - mr, Y(v)))
        p.append('<text x="%d" y="%.1f" text-anchor="end" class="tick">%s</text>' % (ml - 6, Y(v) + 4, fmt % v))
    for i, c in enumerate(cats):
        p.append('<text x="%.1f" y="%d" text-anchor="middle" class="tick">%s</text>' % (X(i), h - mb + 16, esc(c)))
    for name, col, vals in series:
        d = " ".join("%s%.1f,%.1f" % ("M" if i == 0 else "L", X(i), Y(v)) for i, v in enumerate(vals))
        p.append('<path d="%s" fill="none" stroke="%s" stroke-width="2.5"/>' % (d, col))
        for i, v in enumerate(vals):
            p.append('<circle cx="%.1f" cy="%.1f" r="3.2" fill="%s"/>' % (X(i), Y(v), col))
        p.append('<text x="%.1f" y="%.1f" class="barlab" style="fill:%s" text-anchor="end">%s</text>' % (X(len(vals) - 1) - 6, Y(vals[-1]) - 8, col, esc(name)))
    p.append("</svg>")
    return "".join(p)


# ------------------------------------------------------------------ house CSS
CSS = """
:root{--bg:#f7f7f5;--surface:#fff;--surface2:#f2f2ef;--ink:#16161a;--ink2:#4b4b53;--ink3:#7a7a85;--grid:#e2e2dd;--line:#dededa;--brand:%(BLUE)s;--warn:%(ORANGE)s;--radius:12px}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#131315;--surface:#1b1b1e;--surface2:#232326;--ink:#f3f3f5;--ink2:#bdbdc4;--ink3:#8c8c95;--grid:#33333a;--line:#33333a;--brand:#3987e5;--warn:#d95926}}
:root[data-theme="dark"]{--bg:#131315;--surface:#1b1b1e;--surface2:#232326;--ink:#f3f3f5;--ink2:#bdbdc4;--ink3:#8c8c95;--grid:#33333a;--line:#33333a;--brand:#3987e5;--warn:#d95926}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 ui-sans-serif,system-ui,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:860px;margin:0 auto;padding:40px 28px 60px}
h1{font-size:31px;line-height:1.12;letter-spacing:-.02em;margin:0 0 6px}
h2{font-size:20px;letter-spacing:-.01em;margin:36px 0 10px;padding-top:14px;border-top:1px solid var(--line)}
h3{font-size:15.5px;margin:22px 0 6px}
.kicker{font-size:11.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--brand);margin-bottom:10px}
.sub{color:var(--ink2);font-size:12.5px;font-weight:400}
p{margin:9px 0}
.lede{font-size:17px;color:var(--ink2)}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:16px 20px;margin:14px 0}
.finding{border-left:4px solid var(--warn)}
.ok{border-left:4px solid %(BLUE)s}
.figure{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:14px 14px 8px;margin:16px 0}
.figure svg{display:block;width:100%%;height:auto}
.cap{color:var(--ink2);font-size:12.5px;padding:6px 4px 4px}
.tick{font-size:11px;fill:var(--ink3)}
.axis{font-size:12px;fill:var(--ink2)}
.note{font-size:11.5px;fill:var(--ink3)}
.gate{font-size:12px;font-weight:700;fill:%(ORANGE)s}
.barlab{font-size:12px;font-weight:700;fill:%(BLUE)s}
table{width:100%%;border-collapse:collapse;margin:10px 0;font-size:13px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--ink2);background:var(--surface2)}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tr.pickrow td{background:color-mix(in srgb,%(BLUE)s 10%%,transparent);font-weight:650}
tr.warnrow td{background:color-mix(in srgb,%(ORANGE)s 9%%,transparent)}
tr.dim td{color:var(--ink2)}
.formula{background:var(--surface2);border-radius:var(--radius);padding:14px 20px;margin:14px 0;font-size:14px}
.big{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0}
.stat{flex:1 1 150px;background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:12px 14px}
.stat .v{font-size:26px;font-weight:750;letter-spacing:-.02em}
.stat .l{font-size:12px;color:var(--ink2);margin-top:2px}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11.5px;font-weight:700;color:#fff}
.term{font-size:13px;color:var(--ink2);background:var(--surface2);border-radius:8px;padding:8px 12px;margin:8px 0}
code,pre{font-family:ui-monospace,Consolas,"Cascadia Mono",monospace;font-size:12px}
pre{background:var(--surface2);border-radius:var(--radius);padding:12px 14px;overflow-x:auto;white-space:pre-wrap}
footer{margin-top:40px;padding-top:14px;border-top:1px solid var(--line);color:var(--ink3);font-size:12px}
ul{padding-left:20px}li{margin:4px 0}
@page{size:A4;margin:13mm 12mm}
@media print{body{background:#fff;font-size:12.5px}.wrap{max-width:none;padding:0}h1{font-size:26px}h2{font-size:17px;break-after:avoid}
  .figure,.card,table,.formula,.big{break-inside:avoid}.pagebreak{break-before:page}}
""" % {"BLUE": BLUE, "ORANGE": ORANGE}


def pill(band):
    return '<span class="pill" style="background:%s">%s</span>' % (BC.get(band, "#888"), esc(band))


def print_pdf(html_path, pdf_path):
    if not os.path.exists(CHROME):
        print("Chrome not found at %s - PDF skipped" % CHROME)
        return False
    cmd = [CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--print-to-pdf=" + pdf_path, "file:///" + html_path.replace("\\", "/")]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    ok = os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 1000
    print("pdf %s -> %s (%s)" % (os.path.basename(pdf_path), "ok %.0f KB" % (os.path.getsize(pdf_path) / 1024) if ok else "FAILED", (r.stderr or "")[-200:].strip() if not ok else "chrome"))
    return ok


# ------------------------------------------------------------------ the study
def build():
    t0 = time.time()
    R = read_json(os.path.join(OUT, "scoring_results.json"))
    replay = read_json(os.path.join(OUT, "replay_summary.json"))
    perturb = read_json(os.path.join(OUT, "perturb.json"))
    predict = read_json(os.path.join(OUT, "predict.json"))
    workload = read_json(os.path.join(OUT, "workload.json"))
    drift = read_json(os.path.join(OUT, "drift.json"))
    fairness = read_json(os.path.join(OUT, "fairness.json"))
    edges = read_json(os.path.join(OUT, "edge_cases.json"))
    frontier = read_json(os.path.join(OUT, "frontier.json"))
    stages = read_json(os.path.join(OUT, "sweep_stages.json"))["stages"]
    S = Study(write_aliases=False)
    E = Engine(S)
    rec = R["recommended"]
    rcfg = rec["config_json"]
    rec_res = E.base.run(rcfg)
    c0_res = E.base.run(CONFIGS["C0"])
    c5_res = E.base.run(CONFIGS["C5"])
    rec_m = E.metrics(rcfg)
    vp = R["vp_table"]
    O, Rc = vp["original"], vp["recommended"]
    cand = R["candidates"]
    sc = R["scorecard"]
    weeks = S.weeks
    rec_needs = needs_contract_change(rcfg)
    asis = R.get("recommended_as_is")
    rec_label = "the recommended settings"
    n_settings = stages["total_settings"]

    # -- extra numbers for the recommended setting ------------------------------------------------
    per_course = defaultdict(Counter)
    per_month = defaultdict(Counter)
    for r, x in zip(S.rows, rec_res):
        per_course[r["course"]][x["action"]] += 1
        per_course[r["course"]]["classes"] += 1
        per_month[r["month"]][x["action"]] += 1
        per_month[r["month"]]["classes"] += 1
    import calendar
    month_weeks = {m: calendar.monthrange(2026, m)[1] / 7.0 for m in range(1, 9)}
    rec_scores = [x["score"] for x in rec_res if x["score"] is not None]
    rec_kind = standardised_share(S.rows, rec_res, lambda r: r["kind"])
    rec_size = standardised_share(S.rows, rec_res, lambda r: "<10" if r["responses"] < 10 else "10+")
    rec_region = standardised_share(S.rows, rec_res, lambda r: r["region"])
    c0_kind = standardised_share(S.rows, c0_res, lambda r: r["kind"])
    c0_size = standardised_share(S.rows, c0_res, lambda r: "<10" if r["responses"] < 10 else "10+")
    c0_region = standardised_share(S.rows, c0_res, lambda r: r["region"])
    gl = R["guard_lift"]

    H = []
    A = H.append
    A('<title>Sentiment Score Validation</title><style>%s</style><div class="wrap">' % CSS)
    A('<div class="kicker">Feedback Loop v3 · Validation study · New Programs</div>')
    A('<h1>The Class Sentiment Score, tested on eight months of real classes</h1>')
    A('<p class="sub">%d classes, 1 January to 31 August 2026 · six candidate settings · %s settings swept · %d synthetic edge cases · generated %s</p>' % (
        R["meta"]["rows"], "{:,}".format(n_settings), edges["summary"]["cases"], R["meta"]["generated"]))
    A('<p class="lede">The manager\'s score is easy to explain, and that is worth keeping. Replayed on every real class it is also unstable '
      '(one learner changing their mind moves the band of %s of classes), it hides %d low-rated classes behind a "Good" or "Excellent" label, '
      'and it treats a small room as a bad class. The recommended settings keep the same four inputs and four bands, make approval gradual, '
      'protect thin votes, keep the two agreed lines (4.55 and 80%%) as hard lines, and score %s of 200 on the scorecard against %s for the original.</p>' % (
          pct(O["flip_band_pct"], 0), O["low_shown_fine"], n1(rec["total"]), n1(sc["C0"]["total"])))

    # -- 1. the answer -----------------------------------------------------------------------------
    A('<h2>1. The answer in one table</h2>')
    A('<p>Five numbers, measured on the same %d classes. "Original" is the manager\'s method exactly as written (60/30/6/4, pass/fail); '
      '"recommended" is the setting this study picks.</p>' % R["meta"]["rows"])
    A('<table><tr><th></th><th class="n">Manager\'s original</th><th class="n">Recommended</th></tr>')
    A('<tr><td>Classes whose band flips if one learner votes differently<br><span class="sub">label changes; in brackets: the verdict (video / transcript / none) changes</span></td>'
      '<td class="n">%s <span class="sub">(%s)</span></td><td class="n">%s <span class="sub">(%s)</span></td></tr>' % (
          pct(O["flip_band_pct"]), pct(O["flip_verdict_pct"]), pct(Rc["flip_band_pct"]), pct(Rc["flip_verdict_pct"])))
    A('<tr><td>"Bad" classes that were actually rated 4.55 or better</td><td class="n">%d of %d</td><td class="n">%d of %d</td></tr>' % (
        O["bad_rated_fine"], O["bad_total"], Rc["bad_rated_fine"], Rc["bad_total"]))
    A('<tr><td>Low classes (under 4.55 or under 80%% with 5+ votes) shown as Good or Excellent</td><td class="n">%d</td><td class="n">%d <span class="sub">(+%d provisional labels on 5-vote classes, watched)</span></td></tr>' % (
        O["low_shown_fine"], Rc["low_shown_fine_firm"], Rc["low_shown_fine"] - Rc["low_shown_fine_firm"]))
    A('<tr><td>Analyses a week<br><span class="sub">today\'s shipped rule v2 runs %s a week (%s video)</span></td><td class="n">%s <span class="sub">(%s video + %s transcript)</span></td>'
      '<td class="n">%s <span class="sub">(%s video + %s transcript)</span></td></tr>' % (
          n1(vp["today_rule_v2"]["per_week"]), n1(vp["today_rule_v2"]["videos_per_week"]), n1(O["per_week"]), n1(O["videos_per_week"]), n1(O["transcripts_per_week"]),
          n1(Rc["per_week"]), n1(Rc["videos_per_week"]), n1(Rc["transcripts_per_week"])))
    A('<tr><td>Chance the instructor\'s next class is low: Bad vs Excellent<br><span class="sub">next class with 5+ votes; resolved instructor names</span></td>'
      '<td class="n">%s vs %s</td><td class="n">%s vs %s</td></tr>' % (pct(O["risk_bad"], 0), pct(O["risk_excellent"], 0), pct(Rc["risk_bad"], 0), pct(Rc["risk_excellent"], 0)))
    A('<tr class="pickrow"><td>Scorecard (of 200)</td><td class="n">%s</td><td class="n">%s</td></tr></table>' % (n1(sc["C0"]["total"]), n1(rec["total"])))
    A('<div class="card finding"><b>Two things to know before this ships.</b> (1) <b>The small-sample guard is off in v3.</b> As the scoring contract stands, the guard '
      'checks the two hard lines on the <i>blended</i> values and lets %d borderline classes past them (finding F1, section 5); with the guard off the lines are literal. '
      'A one-line contract change (a <code>caps.basis</code> switch) brings the guard back: that variant scores %s of 200, flips fewer labels (%s against %s) and changes no verdict '
      '(<code>recommended_config_guarded.json</code>). (2) <b>An analysis starts at 6 votes, not 5.</b> With literal lines the 5-vote floor flags %s classes a week - today\'s queue - '
      'against the default ceiling of 12; the 6-vote floor gives %s. The 5-vote variant is <code>recommended_config_floor5.json</code>; classes with exactly 5 votes get a '
      'provisional band and sit in Watch.</div>' % (gl["classes"], n1(R["guarded"]["total"]), pct(R["guarded"]["flip_all"]), pct(rec["flip_all"]), n1(R["floor5"]["per_week"]), n1(rec["per_week"])))

    # -- 2. what the score is -----------------------------------------------------------------------
    A('<h2>2. What is being tested</h2>')
    A('<p>One number from 0 to 100 per class, from four inputs: the star rating, the "would you have this instructor back?" vote, how many '
      'people rated, and how many of the room rated (reach). Four bands - Excellent, Good, Average, Bad - and the band decides the work: '
      '<b>Bad → video analysis</b>, <b>Average → transcript analysis</b>, Good and Excellent → nothing unless a PM asks. Every choice inside the '
      'formula is a switch, so the six candidates below are the same formula with different switches.</p>')
    A('<table><tr><th>Candidate</th><th>What changes</th><th>What it tests</th></tr>')
    tests = {"C0": "the baseline", "C1": "is it just tiny samples?", "C2": "is the 30-point cliff the damage?", "C3": "the two changes worth selling",
             "C4": "the study\'s weights as four bands", "C5": "today\'s shipped rule, as four bands"}
    for k in CK:
        A('<tr%s><td><b>%s</b> %s</td><td class="sub">%s</td><td>%s</td></tr>' % (' class="pickrow"' if k == rec["label"] else "", k, esc(CONFIGS[k]["name"]),
                                                                                    esc(cand[k]["description"]), tests[k]))
    A('</table>')
    A('<div class="term"><b>Terms used once, defined once.</b> <b>Guard</b>: when few people voted, their votes are blended with a few typical votes for '
      'that course (k of them), so three opinions cannot sink a class on their own. <b>Graded approval</b>: approval earns points gradually from 40% to 80% '
      'instead of all-or-nothing at 80%. <b>Hard lines</b>: under 4.55 or under 80% with 5+ votes can never sit above Average; both missed is Bad. '
      '<b>Track record</b>: the instructor\'s average over at least three earlier classes. <b>Provisional</b>: a band shown for 3-4 votes, never analysed. '
      '<b>Knee</b>: a steeper rating scale below 4.55 (0 at 3.55, 75 at 4.55, 100 at 5.0).</div>')

    # -- 3. the yardsticks and the scorecard ------------------------------------------------------
    A('<h2>3. Six yardsticks, pass marks set before running</h2>')
    A('<table><tr><th>#</th><th>Plain meaning</th><th>Pass mark</th><th class="n">Weight</th></tr>')
    ys = [("Y1 Stable under one vote", "one person changing their mind should not change the band", "under 10% of classes flip; under 5% of classes with 10+ votes", 25),
          ("Y2 Agrees with the two lines", "never contradict 4.55 / 80% when 5+ people voted", "false comfort under 2%; false alarm under 5%; veto above 5% false comfort", 20),
          ("Y3 Predicts the next class", "a worse band today means a riskier next class", "Bad worst, then Average, Good, Excellent; Bad at least twice Excellent; 100+ per band", 20),
          ("Y4 Sensible sizes and workload", "every band has classes; the queue fits the team", "no band under 5% or over 75%; at most 12 analyses and 5 videos a week", 15),
          ("Y5 Fair to small rooms and reviews", "the band reflects the class, not the room", "Excellent share at equal rating differs by under 10 points; no firm band under the vote floor", 15),
          ("Y6 Explainable in one sentence", "a PM can say why without a calculator", "8 of 10 bands predicted from the sentence (PM test still to run; a proxy is used here)", 5)]
    for name, meaning, mark, w in ys:
        A('<tr><td><b>%s</b></td><td>%s</td><td class="sub">%s</td><td class="n">%d</td></tr>' % (name, meaning, mark, w))
    A('</table><p class="sub">Each yardstick has two sub-marks worth its weight each (200 in total). Partial credit falls to zero at twice the pass mark. '
      'Two vetoes: false comfort above 5%, or a queue above capacity that no band edge can fix.</p>')
    A('<h3>The scorecard, filled with the measured numbers</h3>')
    A('<table><tr><th>Setting</th>' + "".join('<th class="n">%s</th>' % y for y in ("Y1 /50", "Y2 /40", "Y3 /40", "Y4 /30", "Y5 /30", "Y6 /10")) + '<th class="n">Total /200</th><th>Veto</th></tr>')
    order = CK + ["REC"]
    for k in order:
        if k == "REC":
            pts, tot, vet, label = rec["points"], rec["total"], rec["vetoes"], "Recommended (%s)" % rec["label"]
        else:
            pts, tot, vet, label = sc[k]["points"], sc[k]["total"], sc[k]["vetoes"], "%s %s" % (k, CONFIGS[k]["name"])
        A('<tr class="%s"><td>%s</td>%s<td class="n"><b>%s</b></td><td class="sub">%s</td></tr>' % (
            "pickrow" if k == "REC" else ("warnrow" if vet else ""), esc(label), "".join('<td class="n">%s</td>' % n1(pts[y]) for y in ("Y1", "Y2", "Y3", "Y4", "Y5", "Y6")),
            n1(tot), "; ".join(vet) if vet else "-"))
    A('</table>')
    A('<div class="figure">%s<div class="cap">Scorecard totals. Every one of the six hand-written candidates is vetoed on false comfort as measured - including C5, '
      'whose %d guard-lifted classes (finding F1) push it to 6.0%%. The recommendation is C5 with the guard off and the analysis floor at 6 votes.</div></div>' % (
          hbars([(("%s" % SHORT[k]), sc[k]["total"], ORANGE if sc[k]["vetoes"] else BLUE) for k in CK] + [("Recommended", rec["total"], GREEN)], maxv=200, fmt="%.0f",
                aria="Scorecard totals out of 200 for the six candidates and the recommended setting."), gl["classes"]))

    # -- 4. Y1 -----------------------------------------------------------------------------------------
    A('<h2>4. Y1 - one vote</h2>')
    A('<p>Every class was replayed twice: once with one "yes" turned into a "no", once with one rater giving one point less (the average drops by '
      '1 divided by the number of ratings). A <b>label flip</b> is any change of band; a <b>verdict flip</b> is a change of what happens '
      '(video, transcript, nothing, watch).</p>')
    A('<div class="figure">%s<div class="cap">Share of all %d classes whose band label changes (dark) and whose verdict changes (light) when one learner '
      'votes differently. Pass mark for labels: under 10%%.</div></div>' % (
          grouped([SHORT[k] for k in CK] + ["Recommended"], [("label flips", BLUE, [perturb["configs"][k]["flip_all"] for k in CK] + [Rc["flip_band_pct"]]),
                                                             ("verdict flips", "#9cc0ea", [perturb["configs"][k]["verdict_all"] for k in CK] + [Rc["flip_verdict_pct"]])],
                  aria="Label and verdict flip shares per candidate."), R["meta"]["rows"]))
    A('<div class="figure">%s<div class="cap">Where the %s score lands: 60%% of classes sit between 85 and 97.5, straddling the Excellent edge at %g. Any '
      'one-rater change of 2-4 points flips the label of a class on the edge - most flips are Good ↔ Excellent, which changes no work. That is finding F3.</div></div>' % (
          histogram(rec_scores, rcfg["bands"], aria="Histogram of the recommended setting's scores with the band zones shaded."), "recommended", rcfg["bands"]["excellent"]))
    A('<table><tr><th>Setting</th><th class="n">All classes</th><th class="n">10+ votes</th><th class="n">yes → no</th><th class="n">one point less</th><th class="n">Verdict flips</th><th class="n">Good ↔ Excellent share of flips</th></tr>')
    for k in CK:
        pk = perturb["configs"][k]
        tot = pk["label_only_flips_good_excellent"] + pk["decision_flips"]
        A('<tr><td>%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td></tr>' % (
            SHORT[k], pct(pk["flip_all"]), pct(pk["flip_10plus"]), pct(pk["flip_yes"]), pct(pk["flip_rating"]), pct(pk["verdict_all"]), pct(pk["label_only_flips_good_excellent"] / tot * 100 if tot else 0, 0)))
    y1 = rec_m["Y1"]
    tr = y1["transitions"]
    ge = sum(v for kk, v in tr.items() if {kk.split(">")[0], kk.split(">")[1]} == {"Excellent", "Good"})
    A('<tr class="pickrow"><td>Recommended</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td></tr></table>' % (
        pct(y1["flip_all"]), pct(y1["flip_10plus"]), pct(y1["flip_yes"]), pct(y1["flip_rating"]), pct(y1["verdict_all"]), pct(ge / max(1, sum(tr.values())) * 100, 0)))
    A('<p>By how many people voted (recommended setting): %s.</p>' % "; ".join(
        "%s votes %s" % (b, pct(y1["by_bucket"][b]["share"])) for b in ("1-2", "3-4", "5-9", "10-19", "20+") if b in y1["by_bucket"]))

    # -- 5. Y2 -----------------------------------------------------------------------------------------
    A('<h2>5. Y2 - the two human signals</h2>')
    A('<p><b>False comfort</b>: a class with 5+ votes that is under 4.55 or under 80%% and yet shows Good or Excellent. <b>False alarm</b>: a Bad class that '
      'clears both lines. Shares are of the %d classes with 5+ votes.</p>' % cand["C0"]["false_comfort"] and 0 or '')
    A('<table><tr><th>Setting</th><th class="n">False comfort</th><th class="n">of which under 4.55</th><th class="n">Share</th><th class="n">False alarm</th><th class="n">Bad rated 4.55+</th><th>Why</th></tr>')
    why = {"C0": "no hard lines: a 3.0 class with an approved instructor scores 76", "C1": "same, minus the classes with under 5 votes",
           "C2": "the slope lifts more classes over 75 than the cliff did", "C3": "graded approval and the guard lift almost everything to Excellent",
           "C4": "no hard lines", "C5": "hard lines, but read on the guarded values (F1)"}
    for k in CK:
        c = cand[k]
        A('<tr%s><td>%s</td><td class="n">%d</td><td class="n">%d</td><td class="n">%s</td><td class="n">%d</td><td class="n">%d of %d</td><td class="sub">%s</td></tr>' % (
            ' class="warnrow"' if c["false_comfort_share"] > 5 else "", SHORT[k], c["false_comfort"], replay["configs"][k]["metrics"]["Y2"]["false_comfort_rating"],
            pct(c["false_comfort_share"]), c["false_alarm"], c["bad_rated_fine"], c["bad_total"], why[k]))
    A('<tr class="pickrow"><td>Recommended</td><td class="n">%d</td><td class="n">%d</td><td class="n">%s</td><td class="n">%d</td><td class="n">%d of %d</td><td class="sub">%s</td></tr></table>' % (
        rec["false_comfort"], rec_m["Y2"]["false_comfort_rating"], pct(rec["false_comfort_share"]), rec["false_alarm"], rec["bad_rated_fine"], rec["bad_total"],
        "guard off, so the lines are literal; the %d are provisional labels on 5-vote classes (none firm)" % rec["false_comfort"]))
    A('<div class="card finding"><b>Finding F1 - the guard lifts borderline classes over the hard lines.</b> Under C5, %d classes with 5+ votes sit under a raw line '
      '(%d rated %.2f-%.2f, %d with approval 71-79%%) but show Good, because the contract checks the line on the guarded value: a 4.54 with 10 votes in a 4.70 course '
      'becomes 4.59 and clears 4.55. Those classes are not harmless: their next class goes wrong %s of the time, against %s for classes fine on both lines '
      '(base rate %s). The fix is a one-line contract change - read the lines on the raw values, let the guard shape the score only; until it lands, '
      'v3 ships with the guard off.</div>' % (gl["classes"], gl["rating_line"], gl["raw_rating_range"][0], gl["raw_rating_range"][1], gl["approval_bar"],
                                               pct(gl["next_low_pct"] or 0, 0), pct(gl["fine_on_both_next_low_pct"] or 0, 0), pct(gl["base_rate"], 0)))

    # -- 6. Y3 -----------------------------------------------------------------------------------------
    A('<h2>6. Y3 - does the band predict the next class?</h2>')
    A('<p>For every class with 5+ votes whose instructor\'s next class also has 5+ votes (%d pairs on resolved names, %d on raw names): the share of next '
      'classes that go wrong (under 4.55 or under 80%%). The base rate is %s.</p>' % (predict["meta"]["pairs_resolved"], predict["meta"]["pairs_raw"], pct(predict["two_lines"]["resolved"]["base_rate"], 0)))
    cats = ["Excellent", "Good", "Average", "Bad"]
    series = [("C0 original", "#9aa3ad", [cand["C0"]["y3"][b.lower()]["share"] for b in cats]),
              ("C5 two lines", "#7aa7d9", [cand["C5"]["y3"][b.lower()]["share"] for b in cats]),
              ("Recommended", GREEN, [rec["y3"][b.lower()]["share"] for b in cats])]
    A('<div class="figure">%s<div class="cap">Next-class risk per band. The original\'s Average (46%%) is riskier than its Bad (41%%) - the order is wrong because the '
      'cliff sends the 4.87-with-one-no classes to Bad. The recommended setting orders the bands correctly and its Bad is %sx its Excellent.</div></div>' % (
          grouped(cats, series, aria="Next-class risk per band for C0, C5 and the recommended setting.", ymax=70), n1(rec["y3_ratio"])))
    A('<table><tr><th>Setting</th>' + "".join('<th class="n">%s</th>' % b for b in cats) + '<th class="n">Order</th><th class="n">Bad ÷ Excellent</th><th class="n">Smallest band (pairs)</th></tr>')
    for k in CK:
        c = cand[k]
        A('<tr><td>%s</td>%s<td class="n">%d/3</td><td class="n">%s</td><td class="n">%d</td></tr>' % (
            SHORT[k], "".join('<td class="n">%s <span class="sub">(%d)</span></td>' % (pct(c["y3"][b.lower()]["share"], 0), c["y3"][b.lower()]["n"]) for b in cats),
            replay["configs"][k]["metrics"]["Y3"]["order_ok"], n1(c["y3_ratio"]) if c["y3_ratio"] not in (None, float("inf")) else "n/a", c["y3_min_pairs"]))
    A('<tr class="pickrow"><td>Recommended</td>%s<td class="n">%d/3</td><td class="n">%s</td><td class="n">%d</td></tr></table>' % (
        "".join('<td class="n">%s <span class="sub">(%d)</span></td>' % (pct(rec["y3"][b.lower()]["share"], 0), rec["y3"][b.lower()]["n"]) for b in cats),
        rec_m["Y3"]["order_ok"], n1(rec["y3_ratio"]), rec["y3_min_pairs"]))
    pr, pw_ = predict["configs"]["C5"]["resolved"], predict["configs"]["C5"]["raw"]
    A('<p>Raw versus resolved names (C5): Bad %s vs %s, Excellent %s vs %s. Resolving the %d aliases adds %d pairs and barely moves the shares - the '
      'finding does not depend on the name clean-up.</p>' % (pct(pw_["bad"]["share"], 0), pct(pr["bad"]["share"], 0), pct(pw_["excellent"]["share"], 0), pct(pr["excellent"]["share"], 0),
                                                            R["meta"]["identity"]["aliases"], predict["meta"]["pairs_resolved"] - predict["meta"]["pairs_raw"]))

    # -- 7. Y4 -----------------------------------------------------------------------------------------
    A('<h2>7. Y4 - band sizes and workload</h2>')
    rows_mix = [(SHORT[k], {**cand[k]["band_shares_labels"]} if "band_shares_labels" in cand[k] else {BAND_LABEL[b]: cand[k]["band_shares"][b] for b in BANDS}) for k in CK]
    rows_mix.append(("Recommended", {BAND_LABEL[b]: rec["band_shares"][b] for b in BANDS}))
    A('<div class="figure">%s<div class="cap">Band mix among classes that get a band (classes under the vote floor are not counted: %s of classes under the '
      'recommended setting). The original is near-binary: Average holds %s. Pass mark: no band under 5%% or over 75%%.</div></div>' % (
          stacked(rows_mix, ["Excellent", "Good", "Average", "Bad"], aria="Band mix per candidate as 100 percent stacked bars."), pct(rec["no_band_share"], 0), pct(cand["C0"]["band_shares"]["average"])))
    A('<div class="figure">%s<div class="cap">Analyses a week (video + transcript) against the team\'s capacity of 12 a week and 5 videos. Today\'s rule v2 runs %s a week.</div></div>' % (
        hbars([(SHORT[k], cand[k]["per_week"], ORANGE if cand[k]["per_week"] > CEILING["per_week"] else BLUE) for k in CK] + [("Recommended", rec["per_week"], GREEN), ("Today's rule v2", vp["today_rule_v2"]["per_week"], "#9aa3ad")],
              maxv=16, fmt="%.1f", mark=CEILING["per_week"], mark_label="ceiling 12", aria="Analyses per week per candidate against the 12 a week ceiling."), n1(vp["today_rule_v2"]["per_week"])))
    A('<table><tr><th>Setting</th><th class="n">Video / wk</th><th class="n">Transcript / wk</th><th class="n">Total / wk</th><th class="n">Cost / wk</th><th class="n">Peak month</th><th class="n">Today\'s analyses kept</th><th class="n">Added vs today</th></tr>')
    for k in CK:
        wk = workload["configs"][k]
        A('<tr><td>%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">$%s</td><td class="n">%s</td><td class="n">%d of %d</td><td class="n">%d</td></tr>' % (
            SHORT[k], n1(wk["total"]["videos_per_week"]), n1(wk["total"]["transcripts_per_week"]), n1(wk["total"]["per_week"]), n1(wk["total"]["cost_per_week"], 2),
            n1(wk["month_peak_per_week"]), wk["todays_analyses_kept"], wk["todays_analyses_kept"] + wk["todays_analyses_dropped"], wk["vs_rule_v2_today"].get("added", 0)))
    peak = max((per_month[m]["video"] + per_month[m]["transcript"]) / month_weeks[m] for m in per_month)
    A('<tr class="pickrow"><td>Recommended</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">$%s</td><td class="n">%s</td><td class="n">-</td><td class="n">-</td></tr></table>' % (
        n1(rec["videos_per_week"]), n1(rec["transcripts_per_week"]), n1(rec["per_week"]), n1(rec["cost_per_week"], 2), n1(peak)))
    A('<h3>Per course, recommended setting</h3><table><tr><th>Course</th><th class="n">Classes</th><th class="n">Video</th><th class="n">Transcript</th><th class="n">Watch</th><th class="n">Analyses / wk</th><th class="n">Cost / wk</th></tr>')
    for c, v in sorted(per_course.items(), key=lambda kv: -kv[1]["classes"]):
        if v["classes"] < 20:
            continue
        A('<tr><td>%s</td><td class="n">%d</td><td class="n">%d</td><td class="n">%d</td><td class="n">%d</td><td class="n">%s</td><td class="n">$%s</td></tr>' % (
            esc(c), v["classes"], v["video"], v["transcript"], v["watch"], n1((v["video"] + v["transcript"]) / weeks), n1((v["video"] * COST["video"] + v["transcript"] * COST["transcript"]) / weeks, 2)))
    A('</table>')
    A('<div class="figure">%s<div class="cap">Analyses a week by month, recommended setting: the queue grows with the year because the classes got worse (section 11), not because the rule changed.</div></div>' % (
        lines_chart([MONTHS[m - 1] for m in range(1, 9)], [("video", ORANGE, [per_month[m]["video"] / month_weeks[m] for m in range(1, 9)]),
                                                           ("transcript", BLUE, [per_month[m]["transcript"] / month_weeks[m] for m in range(1, 9)]),
                                                           ("total", "#555", [(per_month[m]["video"] + per_month[m]["transcript"]) / month_weeks[m] for m in range(1, 9)])],
                    fmt="%.0f", aria="Monthly analyses per week under the recommended setting.")))

    # -- 8. Y5 -----------------------------------------------------------------------------------------
    A('<h2>8. Y5 - fair to small rooms and test reviews</h2>')
    A('<p>At <b>equal rating</b> (classes grouped in 0.1-rating buckets and re-weighted to the same rating mix), how often does each group get Excellent? '
      'A fair score gives the same answer for a class of 8 and a class of 20, and for a live class and a test review.</p>')
    cats5 = ["<10 responses", "10+ responses", "Live class", "Test review", "US", "India"]
    A('<div class="figure">%s<div class="cap">Excellent share at equal rating. Under the original, the same 4.7 class is Excellent in a big room (%s) and rarely in a small one (%s) - '
      'the "10 responses" cliff and reach do that. The recommended setting closes the gap to %s points.</div></div>' % (
          grouped(cats5, [("C0 original", "#9aa3ad", [c0_size.get("<10", 0), c0_size.get("10+", 0), c0_kind.get("Live Class", 0), c0_kind.get("Test Review", 0), c0_region.get("US", 0), c0_region.get("IND", 0)]),
                          ("Recommended", GREEN, [rec_size.get("<10", 0), rec_size.get("10+", 0), rec_kind.get("Live Class", 0), rec_kind.get("Test Review", 0), rec_region.get("US", 0), rec_region.get("IND", 0)])],
                  ymax=100, aria="Excellent share at equal rating by group for C0 and the recommended setting."), pct(c0_size.get("10+", 0), 0), pct(c0_size.get("<10", 0), 0), n1(rec["size_gap"])))
    A('<table><tr><th>Setting</th><th class="n">Small vs big room gap</th><th class="n">Live vs review gap</th><th class="n">Firm Bad/Excellent with ≤ 3 votes</th><th class="n">Pass</th></tr>')
    for k in CK:
        f = fairness["configs"][k]
        A('<tr><td>%s</td><td class="n">%s pts</td><td class="n">%s pts</td><td class="n">%d</td><td class="n">%s</td></tr>' % (SHORT[k], n1(f["size_gap"]), n1(f["kind_gap"]), f["thin_firm"]["total"], "yes" if (f["pass_gaps"] and f["pass_thin"]) else "no"))
    A('<tr class="pickrow"><td>Recommended</td><td class="n">%s pts</td><td class="n">%s pts</td><td class="n">%d</td><td class="n">%s</td></tr></table>' % (
        n1(rec["size_gap"]), n1(rec["kind_gap"]), rec["thin_firm"], "yes" if (rec["size_gap"] < 10 and rec["kind_gap"] < 10 and rec["thin_firm"] == 0) else "no"))
    wd = fairness["configs"]["C5"]["slices"]["weekday"]
    A('<p>By weekday (C5, share of banded classes in Bad): %s. The week is lopsided - 83%% of classes fall on Thursday to Sunday - and Friday and Saturday carry more Bad classes; the score does not create that, the data does.</p>' % "; ".join(
        "%s %s" % (d, pct(v["Bad"], 0)) for d, v in wd.items() if v["classes"] >= 50))

    # -- 9. Y6 ----------------------------------------------------------------------------------------
    A('<h2>9. Y6 - explainable in one sentence</h2>')
    A('<p>The real test - three PMs predicting ten bands from the reason sentence - has not been run yet; the scorecard uses a proxy: the manager\'s formula '
      '(four parts) scores 10 of 10, every extra idea costs a point, and the two hard lines give one back because they let a PM read "Bad" or "Average" '
      'straight off the sentence ("Rated 4.31 · 12 of 20 would have the instructor back (60%%) → Bad → video analysis"). The recommended setting scores %d of 10 '
      'with %d moving parts. Worth 5%% of the total, so it cannot decide the outcome either way.</p>' % (rec["points"]["Y6"], rec["parts"]))

    # -- 10. the sweep --------------------------------------------------------------------------------
    A('<h2>10. The sweep - %s settings in %d minutes</h2>' % ("{:,}".format(n_settings), max(1, round(stages["seconds"] / 60))))
    A('<p>Three stages on a laptop: <b>(a)</b> %s shapes at fixed weights (straight or knee rating with floors 3.3 / 3.55 / 3.8; approval cliff or slope with floors 30 / 40 / 50; '
      'guard 0 / 3 / 5 / 10; responses off / cliff / slope; reach on / off; track record on / off; hard lines off / on guarded values / on raw values; vote floors off / 3 and 5); '
      '<b>(b)</b> %s weight settings on the best shapes (%d weight mixes in 5-point steps summing to 100 × approval bar 70-90 in 2.5 steps × response target 5-15 × vote floor 3 or 5%s); '
      '<b>(c)</b> %s band-edge settings (Excellent 85-95, Good 70-80, Average 55-65 in 2.5 steps) over the stored scores of the best settings and C4 / C5. All six yardsticks recorded for '
      'every setting; every top setting the contract can express was re-run through the contract itself and matched exactly.</p>' % (
          "{:,}".format(stages["a"]["settings"]), "{:,}".format(stages["b"]["settings"]), stages["b"]["weight_combos"],
          (" - thinned evenly by %d to keep it to minutes" % stages["b"]["thinning_step"]) if stages["b"]["thinning_step"] > 1 else "", "{:,}".format(stages["c"]["settings"])))
    pts = frontier["all"]
    marks = [(frontier["candidates"][k]["flip_all"], frontier["candidates"][k]["per_week"], k, ORANGE) for k in CK] + [(rec["flip_all"], rec["per_week"], "Recommended", GREEN)]
    A('<div class="figure">%s<div class="cap">Every swept setting (grey: vetoed on false comfort; blue: not vetoed) by one-vote flip share and analyses a week. '
      'The six candidates and the recommended setting are marked. Settings with few flips and a light queue exist - they are the ones that hide low classes.</div></div>' % (
          scatter([(p["flip_all"], p["per_week"], "#c4c4bf" if p["vetoed"] else BLUE, 0.35) for p in pts], marks, xmax=45, ymax=16, aria="Sweep settings: flip share against analyses per week.")))
    for track, title in (("as_is", "contract as written (hard lines on the guarded values)"), ("raw_lines", "hard lines on the raw values (needs the contract change)")):
        top = R["sweep_top15"][track]
        A('<h3>Top settings - %s</h3>' % title)
        A('<table><tr><th class="n">#</th><th>Setting</th><th class="n">Total</th><th class="n">Flips</th><th class="n">False comfort</th><th class="n">Bad→Exc risk</th><th class="n">Analyses / wk</th><th class="n">Parts</th></tr>')
        for i, r in enumerate(top[:15], 1):
            A('<tr%s><td class="n">%d</td><td class="sub">%s</td><td class="n">%s%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s → %s</td><td class="n">%s</td><td class="n">%d</td></tr>' % (
                ' class="pickrow"' if r["signature"] == rec["signature"] else "", i, esc(r["description"]), n1(r["total"]), " (veto)" if r["vetoed"] else "", pct(r["flip_all"]),
                pct(r["false_comfort_pct"]), pct(r["y3_bad"], 0), pct(r["y3_excellent"], 0), n1(r["per_week"]), r["parts"]))
        A('</table>')

    # -- 11. edge cases -------------------------------------------------------------------------------
    A('<h2>11. The 44 edge cases the data lacks</h2>')
    A('<p>Each synthetic case carries the outcome the plan expects under C5 and the switch that controls it. The contract met the plan\'s expectation on '
      '%d of %d; the one difference is finding F1. These cases are also a permanent unit test (<code>analysis/test_sentiment_score.py</code>, 9 tests, passing).</p>' % (
          edges["summary"]["plan_matches_C5"], edges["summary"]["cases"]))
    A('<table><tr><th>Case</th><th>Switch</th><th>C0</th><th>C5</th><th>Plan met</th></tr>')
    for e in edges["cases"]:
        x0, x5 = e["by_config"]["C0"], e["by_config"]["C5"]
        A('<tr%s><td><b>%s</b> %s</td><td class="sub">%s</td><td>%s %s</td><td>%s %s%s</td><td>%s</td></tr>' % (
            "" if e["plan_match_C5"] else ' class="warnrow"', e["id"], esc(e["label"]), esc(e["switch"]), pill(BAND_LABEL[x0["band"]]), x0["action"],
            pill(BAND_LABEL[x5["band"]]), x5["action"], " (provisional)" if x5["provisional"] else "", "yes" if e["plan_match_C5"] else "<b>no</b> - " + esc(e["plan"]["band"] or "no band") + " expected"))
    A('</table>')

    # -- 12. drift -------------------------------------------------------------------------------------
    A('<h2>12. Drift - did the classes change, or is the model wrong?</h2>')
    dw = drift["weights"]
    A('<table><tr><th>Window</th><th class="n">Classes</th><th class="n">Pairs</th><th class="n">Rating share</th><th class="n">Approval share</th><th class="n">Track share</th><th class="n">Derived weights</th></tr>')
    for half in ("Jan-Apr", "May-Aug", "Jan-Aug"):
        d = dw[half + "|resolved"]
        A('<tr><td>%s</td><td class="n">%d</td><td class="n">%d</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">%d / %d / %d</td></tr>' % (
            half, d["classes"], d["pairs"], n1(d["average_share"]["R"], 0), n1(d["average_share"]["A"], 0), n1(d["average_share"]["T"], 0), d["derived_weights"]["R"], d["derived_weights"]["A"], d["derived_weights"]["T"]))
    A('</table>')
    md, cd = drift["model_drift"], drift["class_drift"]
    A('<p><b>Model drift: %s.</b> The largest move of a derived weight between the halves is %s points (the alert line is 10). <b>Class drift: real.</b> From the first half to the second the '
      'share of classes under 4.55 rose %s points, the share under the 80%% bar %s points, and the average room grew by %s people. The weights hold; the classes got harder.</p>' % (
          "flagged" if md["flag"] else "none", n1(md["max_shift_points"]), n1(cd["under_line_shift_points"]), n1(cd["under_bar_shift_points"]), n1(cd["attended_shift"])))
    mon = [m for m in drift["monthly"] if m["config"] == "data"]
    A('<div class="figure">%s<div class="cap">Share of classes under 4.55 by month - the single most important line for leadership: the decline is in the classes, not the model.</div></div>' % (
        lines_chart([m["month"] for m in mon], [("under 4.55", ORANGE, [m["under_line"] for m in mon])], ymax=35, aria="Monthly share of classes under 4.55.")))
    bm = drift["band_mix"]
    A('<p>Band mix per half, C0: Bad %s → %s; C5: Bad %s → %s, Average %s → %s. Both settings see the second half as worse, C5 more visibly.</p>' % (
        pct(bm["C0"]["Jan-Apr"]["Bad"]), pct(bm["C0"]["May-Aug"]["Bad"]), pct(bm["C5"]["Jan-Apr"]["Bad"]), pct(bm["C5"]["May-Aug"]["Bad"]), pct(bm["C5"]["Jan-Apr"]["Average"]), pct(bm["C5"]["May-Aug"]["Average"])))

    # -- 13. identity ---------------------------------------------------------------------------------
    A('<h2>13. Instructor identity</h2>')
    idn = R["meta"]["identity"]
    A('<p>%d raw name strings; %d automatic aliases (case and punctuation variants, an initial for a surname, a one-word name that matches exactly one full name in the same '
      'programme family) resolve them to %d names; 35 proposals need a human - a name and the same name with one letter more, a first name shared by several people, '
      'two surnames one letter apart - all deliberately left for the name review, never merged (the pairs are listed in the review file). Files: <code>analysis/out/instructor_aliases.csv</code>, '
      '<code>instructor_needs_review.csv</code>. Every instructor figure in this study is reported on resolved names, with the raw-name version alongside where it matters (section 6).</p>' % (
          idn["raw_names"], idn["aliases"], idn["resolved_names"]))

    # -- 14. the recommendation -----------------------------------------------------------------------
    A('<h2>14. The recommended configuration</h2>')
    A('<p><b>%s</b></p>' % esc(describe_cfg(rcfg)))
    mb, ma = rcfg["min_votes"]["band"], rcfg["min_votes"]["action"]
    A('<div class="formula"><b>How it reads to a PM.</b> Fewer than %d votes: no band, watch. %d-%d votes: a provisional band, no analysis. From %d votes: under 4.55 or under %g%% → at most Average '
      '(transcript); both missed → Bad (video). Otherwise the score splits Good from Excellent at %g: rating %d%%, approval %d%% (gradual from %d%% to %g%%), track record %d%%.</div>' % (
          mb, mb, ma - 1, ma, rcfg["approval"]["bar"], rcfg["bands"]["excellent"], rcfg["weights"]["rating"], rcfg["weights"]["approval"], rcfg["approval"]["floor"], rcfg["approval"]["bar"], rcfg["weights"]["track"]))
    A('<p>Settings within 5 points of the best (%s): %s. The pick is the simplest of them. It is not one of the swept grid points - the 6-vote floor was added as the workload dial '
      'after the sweep - and it beats the sweep\'s own top setting (%s of 200, which moves the bar to 82.5%%; finding F6).</p>' % (
          n1(R["best_total_non_vetoed"]) if R["best_total_non_vetoed"] else "n/a",
          "; ".join("%s (%s, %d parts)" % (c["label"], n1(c["total"]), c["parts"]) for c in rec["considered_within_5_points"][:6]), n1(R["sweep_top_as_is"]["total"])))
    A('<pre>%s</pre>' % esc(json.dumps({k: v for k, v in rcfg.items() if k != "note"}, indent=1)))
    A('<p class="sub">Stored as <code>analysis/out/recommended_config.json</code> (with a note). %s</p>' % (
        "The <code>caps.basis</code> key is the proposed contract change; the contract ignores it today." if rec_needs else "Loadable by the contract as it is."))
    f5, gd = R["floor5"], R["guarded"]
    A('<div class="card ok"><b>Variant: analysis from 5 votes</b> (<code>recommended_config_floor5.json</code>) - the plan\'s default floor: %s of 200, %s analyses a week (today\'s queue), '
      '%s above the default ceiling of 12, otherwise the same numbers. Choose it if the 5-vote floor matters more than the ceiling.</div>' % (
          n1(f5["total"]), n1(f5["per_week"]), n1(f5["per_week"] - CEILING["per_week"])))
    A('<div class="card ok"><b>Variant: the guard back on</b> (<code>recommended_config_guarded.json</code>, needs the contract change) - k = 5 with the lines read on the raw values: '
      '%s of 200, label flips %s (against %s), the same verdicts and the same queue (%s a week). The <code>caps.basis</code> key is the proposed change; the contract ignores it today.</div>' % (
          n1(gd["total"]), pct(gd["flip_all"]), pct(rec["flip_all"]), n1(gd["per_week"])))
    fc = R["famous_cases"]
    A('<h3>The famous cases, on real classes</h3><table><tr><th>Case (nearest real class)</th><th>C0 original</th><th>C5</th><th>Recommended</th></tr>')
    for label, f in fc.items():
        if not f:
            continue
        x = E.base.run(rcfg)[f["id"]]
        A('<tr><td>%s<br><span class="sub">%s · rated %.2f · %d of %d yes (%.0f%%) · %d rated of %d</span></td><td>%s %s</td><td>%s %s%s</td><td>%s %s%s</td></tr>' % (
            esc(label), esc(f["course"]), f["rating"], f["yes"], f["yes"] + f["no"], f["approval"], f["responses"], f["attended"],
            pill(f["by_config"]["C0"]["band"]), f["by_config"]["C0"]["action"], pill(f["by_config"]["C5"]["band"]), f["by_config"]["C5"]["action"], " (prov.)" if f["by_config"]["C5"]["provisional"] else "",
            pill(BAND_LABEL[x["band"]]), x["action"], " (prov.)" if x["provisional"] else ""))
    A('</table>')

    # -- 15. findings ---------------------------------------------------------------------------------
    A('<h2>15. Where the contract surprised us</h2>')
    for f in R["findings"]:
        A('<div class="card finding"><b>%s - %s.</b> %s<br><span class="sub"><b>Suggested:</b> %s</span></div>' % (f["id"], esc(f["title"]), esc(f["detail"]), esc(f["recommendation"])))

    # -- 16. how to re-run ----------------------------------------------------------------------------
    A('<h2>16. How to re-run</h2>')
    A('<pre>python analysis/sentiment_run_all.py        # everything, in order (about %d minutes; the sweep is most of it)\n'
      'python -m unittest analysis.test_sentiment_score\n'
      'python analysis/build_sentiment_report.py    # this document and the one-pager</pre>' % max(2, round((stages["seconds"] + 60) / 60)))
    A('<p class="sub">Pure Python, no numpy or pandas. The sweep runs on a fast scorer that precomputes each class\'s components and is checked against the contract on the candidates, '
      '40 random settings and every top setting. Outputs live in <code>analysis/out/</code> (gitignored: they carry instructor names).</p>')
    A('<footer>Class Sentiment Score validation · Feedback Loop v3 · data: the ratings workbook, Jan-Aug 2026 (confidential, local only) · scorer: analysis/sentiment_score.py · built %s</footer></div>' % time.strftime("%d %b %Y"))
    html = "".join(H)
    path = os.path.join(OUT, "sentiment-validation.html")
    open(path, "w", encoding="utf-8").write(html)
    print("wrote %s (%.0f KB) in %.1fs" % (path, len(html) / 1024, time.time() - t0))
    return path, R, rec_m


# ------------------------------------------------------------------ the VP one-pager
def one_pager(R, rec_m):
    rec = R["recommended"]
    rcfg = rec["config_json"]
    vp = R["vp_table"]
    O, Rc = vp["original"], vp["recommended"]
    sc = R["scorecard"]
    gl = R["guard_lift"]
    rec_needs = needs_contract_change(rcfg)
    H = []
    A = H.append
    A('<title>Sentiment Score One-Pager</title><style>%s .wrap{max-width:820px}'
      '@page{size:A4;margin:9mm 11mm}'
      '@media print{body{font-size:10.6px;line-height:1.4}h1{font-size:21px;margin-bottom:2px}h2{font-size:15px}h3{font-size:12.5px;margin:9px 0 3px}'
      'p{margin:5px 0}.lede{font-size:11.6px}table{font-size:10.2px;margin:6px 0}th,td{padding:2.5px 6px}.card{padding:7px 11px;margin:6px 0}'
      '.big{gap:8px;margin:8px 0}.stat{padding:6px 10px;flex-basis:120px}.stat .v{font-size:18px}.stat .l{font-size:10px}.sub{font-size:10px}ul{margin:4px 0}li{margin:2px 0}'
      'footer{margin-top:10px;padding-top:6px;font-size:10px}.pill{font-size:9.5px}}'
      '</style><div class="wrap">' % CSS)
    A('<div class="kicker">Feedback Loop v3 · Class Sentiment Score · for the VP</div>')
    A('<h1>Same score, same four bands - proven on 2,784 real classes</h1>')
    A('<p class="sub">New Programs · January to August 2026 · full study: Sentiment-Score-Validation.pdf</p>')
    A('<p class="lede">The score as written is, in practice, a one-question test - <i>did 80% of voters want the instructor back?</i> - with the stars adding a few points either side. '
      'Over the range real classes live in (4.0-5.0), the rating can move the score by 12 points while the approval switch moves it by 30 in one jump. We kept the same four inputs and four bands, '
      'made approval gradual, put floors under thin votes, kept the two lines the team already agreed (4.55 and 80%) as hard lines, and let eight months of real classes set the numbers.</p>')
    A('<table><tr><th></th><th class="n">Manager\'s original</th><th class="n">Recommended</th></tr>')
    A('<tr><td>Classes whose band flips if one learner votes differently<br><span class="sub">in brackets: the work itself changes</span></td><td class="n">%s <span class="sub">(%s)</span></td><td class="n">%s <span class="sub">(%s)</span></td></tr>' % (
        pct(O["flip_band_pct"], 0), pct(O["flip_verdict_pct"], 0), pct(Rc["flip_band_pct"], 0), pct(Rc["flip_verdict_pct"], 0)))
    A('<tr><td>"Bad" classes that were actually rated 4.55 or better</td><td class="n">%d of %d</td><td class="n">%d of %d</td></tr>' % (O["bad_rated_fine"], O["bad_total"], Rc["bad_rated_fine"], Rc["bad_total"]))
    A('<tr><td>Low classes (under 4.55 or under 80%%, 5+ votes) shown as Good or Excellent</td><td class="n">%d</td><td class="n">%d <span class="sub">(%d provisional labels on 5-vote classes, watched)</span></td></tr>' % (
        O["low_shown_fine"], Rc["low_shown_fine_firm"], Rc["low_shown_fine"] - Rc["low_shown_fine_firm"]))
    A('<tr><td>Analyses a week<br><span class="sub">the rule running today: %s</span></td><td class="n">about %s <span class="sub">(%s video + %s transcript)</span></td><td class="n">about %s <span class="sub">(%s video + %s transcript), with a dial</span></td></tr>' % (
        n1(vp["today_rule_v2"]["per_week"]), n1(O["per_week"]), n1(O["videos_per_week"]), n1(O["transcripts_per_week"]), n1(Rc["per_week"]), n1(Rc["videos_per_week"]), n1(Rc["transcripts_per_week"])))
    A('<tr><td>Chance the instructor\'s next class is low: Bad vs Excellent</td><td class="n">%s vs %s <span class="sub">(order wrong: Average %s)</span></td><td class="n">%s vs %s</td></tr>' % (
        pct(O["risk_bad"], 0), pct(O["risk_excellent"], 0), pct(O["risk_average"], 0), pct(Rc["risk_bad"], 0), pct(Rc["risk_excellent"], 0)))
    A('</table>')
    A('<div class="big"><div class="stat"><div class="v">%s</div><div class="l">of 200 on the scorecard - original</div></div><div class="stat"><div class="v">%s</div><div class="l">of 200 - recommended</div></div>'
      '<div class="stat"><div class="v">%s</div><div class="l">settings tried on the same classes</div></div><div class="stat"><div class="v">44</div><div class="l">edge cases, now a permanent test</div></div></div>' % (
          n1(sc["C0"]["total"], 0), n1(rec["total"], 0), "{:,}".format(R["sweep_top15"]["stages"]["total_settings"])))
    A('<h3>The two new ideas, in one sentence each</h3>')
    A('<div class="card ok"><b>Vote floors.</b> Fewer than three voices: no band at all; three to five: a band marked provisional, watched, never analysed on its own; from six, the band '
      'stands and drives the work - so three opinions cannot sink a class on their own.</div>')
    A('<div class="card ok"><b>Graded approval.</b> Instead of all 30 points at 80% and none at 79%, a class earns them gradually - 79% is almost as good as 80%, and 50% is a lot worse than 70%.</div>')
    A('<p class="sub"><b>And one idea tested and parked:</b> the small-sample guard (blending a handful of votes with a few typical votes for the course). As the scoring contract stands it '
      'checks the two agreed lines on the blended values and lets %d borderline classes past them, so it is switched off in v3; a one-line contract change brings it back '
      '(%s of 200, fewer label flips, the same verdicts).</p>' % (gl["classes"], n1(R["guarded"]["total"])))
    A('<p class="sub">The honest trade-off: the original does less work because it ignores %d low classes whose instructor was approved; the data says a low class carries %s risk for the next class against %s for a fine one. '
      'The recommended settings read them from the transcript - the cheap analysis ($0.51 against $0.70 for a video).</p>' % (O["low_shown_fine"], pct(gl["next_low_pct"] or 0, 0), pct(gl["fine_on_both_next_low_pct"] or 0, 0)))
    # page 2
    A('<div class="pagebreak"></div><h2 style="border:0;margin-top:0">The scorecard, filled with measured numbers</h2>')
    A('<p class="sub">Six yardsticks with pass marks set before anything was run; two sub-marks each; 200 in total. Veto: hiding more than 5% of low classes, or a queue the team cannot run.</p>')
    A('<table><tr><th>Yardstick</th><th>Pass mark</th><th class="n">Original</th><th class="n">C5 (today\'s rule as bands)</th><th class="n">Recommended</th></tr>')
    names = {"Y1": ("Stable under one vote", "under 10% flip; under 5% at 10+ votes", 50), "Y2": ("Agrees with the two lines", "false comfort under 2%, false alarm under 5%", 40),
             "Y3": ("Predicts the next class", "Bad worst … Excellent best; Bad ≥ 2× Excellent; 100+ per band", 40), "Y4": ("Sensible sizes and workload", "no band under 5% or over 75%; ≤ 12 a week, ≤ 5 videos", 30),
             "Y5": ("Fair to small rooms and reviews", "gaps under 10 points; no firm band under the vote floor", 30), "Y6": ("Explainable in one sentence", "PM test pending; proxy used", 10)}
    for y, (nm, mk, mx) in names.items():
        A('<tr><td><b>%s</b> %s</td><td class="sub">%s</td><td class="n">%s / %d</td><td class="n">%s / %d</td><td class="n"><b>%s / %d</b></td></tr>' % (
            y, nm, mk, n1(sc["C0"]["points"][y]), mx, n1(sc["C5"]["points"][y]), mx, n1(rec["points"][y]), mx))
    A('<tr class="pickrow"><td>Total</td><td class="sub">vetoes</td><td class="n">%s%s</td><td class="n">%s%s</td><td class="n"><b>%s</b>%s</td></tr></table>' % (
        n1(sc["C0"]["total"]), " (vetoed)" if sc["C0"]["vetoes"] else "", n1(sc["C5"]["total"]), " (vetoed)" if sc["C5"]["vetoes"] else "", n1(rec["total"]), " (vetoed)" if rec["vetoes"] else ""))
    A('<h3>The recommended configuration, in plain words</h3>')
    w = rcfg["weights"]
    A('<table><tr><th>Setting</th><th>Value</th><th>Why</th></tr>')
    A('<tr><td>Rating</td><td>%s</td><td>a low rating falls fast; above the line the stars split Good from Excellent</td></tr>' % ("steeper below 4.55 (0 at %.2f, 75 at 4.55, 100 at 5.0)" % rcfg["rating"]["floor"] if rcfg["rating"]["mode"] == "knee" else "rating ÷ 5"))
    A('<tr><td>Approval</td><td>%s</td><td>no 30-point cliff; 79%% is nearly 80%%</td></tr>' % ("gradual: 0 at %d%%, full at %g%%" % (rcfg["approval"]["floor"], rcfg["approval"]["bar"]) if rcfg["approval"]["mode"] == "graded" else "cliff at %g%%" % rcfg["approval"]["bar"]))
    A('<tr><td>Responses / reach</td><td>%s / %s</td><td>the size of the room is not the quality of the class</td></tr>' % ("off" if rcfg["sample"]["mode"] == "off" else "%s at %d" % (rcfg["sample"]["mode"], rcfg["sample"]["target"]), "off" if rcfg["reach"]["mode"] == "off" else "on"))
    A('<tr><td>Track record</td><td>%s</td><td>a repeat pattern counts; a first class is neutral</td></tr>' % ("on: 0 at 4.05, full at 4.55, needs 3 earlier classes" if rcfg["track"]["mode"] == "on" else "off"))
    A('<tr><td>Weights</td><td>rating %d · approval %d · track %d%s</td><td>within 5 points of the data-derived split</td></tr>' % (w["rating"], w["approval"], w["track"], (" · responses %d · reach %d" % (w["sample"], w["reach"])) if (w["sample"] or w["reach"]) else ""))
    A('<tr><td>Small-sample guard</td><td>%s</td><td>%s</td></tr>' % (
        ("k = %d" % rcfg["guard"]["k"]) if rcfg["guard"]["k"] else "off in v3",
        "blends thin votes with the course's typical votes" if rcfg["guard"]["k"] else "parked: as the contract stands it lets borderline classes past the lines (finding F1); back on after the contract change"))
    A('<tr><td>Vote floors</td><td>band from %d votes; analysis from %d</td><td>no fake certainty from two voters</td></tr>' % (rcfg["min_votes"]["band"], rcfg["min_votes"]["action"]))
    A('<tr><td>Hard lines</td><td>%s</td><td>the two lines the team already agreed stay literal</td></tr>' % ("under 4.55 or under %g%% (5+ votes) → at most Average; both → Bad%s" % (rcfg["caps"]["approval_bar"], "; read on the raw values" if rec_needs else "") if rcfg["caps"]["rating_line"] is not None else "off"))
    A('<tr><td>Bands</td><td>Excellent ≥ %g · Good ≥ %g · Average ≥ %g</td><td>Bad → video · Average → transcript · Good / Excellent → nothing</td></tr></table>' % (rcfg["bands"]["excellent"], rcfg["bands"]["good"], rcfg["bands"]["average"]))
    A('<h3>What needs deciding</h3><ul>')
    A('<li><b>The vote floor</b>: analysis from 6 votes (%s a week, under the default ceiling of 12) or from 5 (%s a week - today\'s queue). Under the first, classes with exactly 5 votes are watched, not analysed.</li>' % (
        n1(Rc["per_week"]), n1(R["floor5"]["per_week"])))
    A('<li><b>One contract change</b> to bring the guard back: the hard lines must read the raw rating and vote (today they read the blended values, which lets %d borderline classes past - the study\'s main finding). One line in the scorer, the database function and the web mirror.</li>' % gl["classes"])
    A('<li><b>The PM test</b> for Y6 (three PMs, ten classes each, from the sentence alone) - 30 minutes, not yet run.</li>')
    A('<li><b>The instructor-name review</b>: 35 proposals need a human; nothing ambiguous was merged.</li></ul>')
    A('<p class="sub">Re-run monthly (first Monday), whenever a course reaches 30 classes, and quarterly for the full sweep. Every configuration is a stored, reversible version.</p>')
    A('<footer>Class Sentiment Score · validation on Jan-Aug 2026 · New Programs · %s</footer></div>' % time.strftime("%d %b %Y"))
    html = "".join(H)
    path = os.path.join(OUT, "sentiment-one-pager.html")
    open(path, "w", encoding="utf-8").write(html)
    print("wrote %s (%.0f KB)" % (path, len(html) / 1024))
    return path


if __name__ == "__main__":
    study_html, R, rec_m = build()
    pager_html = one_pager(R, rec_m)
    print_pdf(study_html, os.path.join(ROOT, "Sentiment-Score-Validation.pdf"))
    print_pdf(pager_html, os.path.join(ROOT, "Sentiment-Score-One-Pager.pdf"))
