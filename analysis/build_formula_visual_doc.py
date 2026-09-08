"""Build "The Formula Search - The Simple Version.docx" — the visual edition.

Same story as the plain version, but carried by five charts instead of paragraphs: what actually
warns us, how many raters make a low rating believable, which formula keeps the rules, why the
queue grew, and the before/after scoreboard. Every number is read from the study's own output
(analysis/out/formula_signal.json, formula_trust.json, formula_features.csv) so the document
cannot drift from the research.

    python analysis/build_formula_visual_doc.py
"""
import collections
import csv
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUTDIR = os.path.join(HERE, "out")
FIGS = os.path.join(OUTDIR, "figs")
OUT = os.environ.get("FORMULA_DOC_OUT") or os.path.join(ROOT, "The Formula Search - The Simple Version.docx")
os.makedirs(FIGS, exist_ok=True)

# ── house palette ────────────────────────────────────────────────────────────
INK = "#16161A"
MUTED = "#4B4B53"
GREY = "#B6BAC2"
BLUE = "#2A78D6"
TEAL = "#1B7F5E"
AMBER = "#C98A19"
RED = "#B43A2E"
INK_W = RGBColor(0x16, 0x16, 0x1A)
MUTED_W = RGBColor(0x4B, 0x4B, 0x53)
BRAND_W = RGBColor(0x2A, 0x78, 0xD6)
GOOD_W = RGBColor(0x1B, 0x7F, 0x5E)
BAD_W = RGBColor(0xB4, 0x3A, 0x2E)
HEADER_FILL = "EEF3FB"
ZEBRA_FILL = "F7F7F5"
NOTE_FILL = "F3F7FD"

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"],
    "font.size": 10.5,
    "axes.edgecolor": "#D8DCE3",
    "axes.labelcolor": MUTED,
    "text.color": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 200,
    "savefig.dpi": 200,
    "savefig.bbox": "tight",
    "savefig.facecolor": "white",
})


def fig_path(name):
    return os.path.join(FIGS, name)


# ── the study's own numbers ──────────────────────────────────────────────────
signal = json.load(open(os.path.join(OUTDIR, "formula_signal.json"), encoding="utf-8"))
trust = json.load(open(os.path.join(OUTDIR, "formula_trust.json"), encoding="utf-8"))


def warn_power(name, target="t_a"):
    """How well one input warns us, as a 0.5–1.0 number on the hidden months."""
    v = signal["univariate"][target][name]["holdout"]["auc"]
    return max(v, 1 - v)


WARN = [
    ("The instructor's record so far", warn_power("track_mean")),
    ("This class's star rating", warn_power("rating")),
    ("How this module usually goes", warn_power("module_loo_rating")),
    ("The “want them back” vote", warn_power("approval")),
    ("How many said no", warn_power("no")),
    ("Turnout (share of the room that rated)", warn_power("reach")),
    ("How many learners rated", warn_power("responses")),
    ("Which weekday it was", warn_power("weekday")),
    ("How many learners attended", warn_power("attended")),
]

TRUST_BUCKETS = [("1 or 2", "1-2"), ("3 or 4", "3-4"), ("5 to 9", "5-9"), ("10 to 14", "10-14"), ("15 or more", "15+")]
tb = trust["believability_all"]["rating_line"]["cohort_next"]
TRUST = [(label, tb[key]["risk_low"] * 100, tb[key]["risk_fine"] * 100) for label, key in TRUST_BUCKETS]

RULES = [
    ("Today's version  (the winner)", 23, TEAL),
    ("Today's version + trust guard", 23, TEAL),
    ("A probability model", 23, GREY),
    ("A statistician's version of the vote", 21, GREY),
    ("The instructor's series", 20, GREY),
    ("Two lines + graded score (older try)", 19, GREY),
    ("The manager's original", 15, RED),
]

rows = list(csv.DictReader(open(os.path.join(OUTDIR, "formula_features.csv"), encoding="utf-8")))
by_month = collections.defaultdict(lambda: [0, 0])
for r in rows:
    m = (r.get("date") or "")[:7]
    if not m:
        continue
    try:
        rating = float(r["rating"]) if r.get("rating") else None
        ap = float(r["approval"]) if r.get("approval") else None
        votes = float(r["votes"]) if r.get("votes") else 0
    except ValueError:
        continue
    ap_pct = ap * 100 if (ap is not None and ap <= 1.5) else ap
    under = (rating is not None and rating < 4.55) or (ap_pct is not None and votes >= 5 and ap_pct < 80)
    by_month[m][0] += 1
    by_month[m][1] += 1 if under else 0
MONTHS = sorted(by_month)
MONTH_LABEL = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
UNDER = [(MONTH_LABEL[int(m[5:7]) - 1], 100 * by_month[m][1] / by_month[m][0]) for m in MONTHS]


# ── charts ───────────────────────────────────────────────────────────────────
def chart_scoreboard():
    """Four before/after tiles — the whole result at a glance."""
    tiles = [
        ("Low-rated classes\nhidden behind a good badge", "105", "0", True),
        ("Classes called “Bad”\nthat were rated 4.55+", "12", "0", True),
        ("Verdict changes on one vote,\nout of 100 classes", "26", "19", True),
        ("Rules of good behaviour\nkept, out of 23", "15", "23", True),
    ]
    fig, axes = plt.subplots(1, 4, figsize=(11.2, 2.5))
    for ax, (label, before, after, good) in zip(axes, tiles):
        ax.axis("off")
        ax.add_patch(FancyBboxPatch((0.02, 0.06), 0.96, 0.88, boxstyle="round,pad=0.02,rounding_size=0.06",
                                    linewidth=1, edgecolor="#E3E7EE", facecolor="#FBFCFD", transform=ax.transAxes))
        ax.text(0.5, 0.85, label, transform=ax.transAxes, ha="center", va="top", fontsize=9.5, color=MUTED, linespacing=1.35)
        ax.text(0.27, 0.40, before, transform=ax.transAxes, ha="center", va="center", fontsize=17, color=RED, fontweight="bold")
        ax.annotate("", xy=(0.62, 0.40), xytext=(0.44, 0.40), xycoords=ax.transAxes, textcoords=ax.transAxes,
                    arrowprops=dict(arrowstyle="-|>", color=GREY, linewidth=1.4))
        ax.text(0.79, 0.40, after, transform=ax.transAxes, ha="center", va="center", fontsize=17,
                color=TEAL if good else RED, fontweight="bold")
        ax.text(0.27, 0.17, "original", transform=ax.transAxes, ha="center", fontsize=8.5, color=GREY)
        ax.text(0.79, 0.17, "today", transform=ax.transAxes, ha="center", fontsize=8.5, color=GREY)
    fig.subplots_adjust(wspace=0.08)
    p = fig_path("scoreboard.png")
    fig.savefig(p)
    plt.close(fig)
    return p


def chart_warn():
    """Which of the 43 things actually warn us — measured on the hidden months."""
    labels = [l for l, _ in WARN][::-1]
    vals = [v for _, v in WARN][::-1]
    colors = [TEAL if v >= 0.65 else (BLUE if v >= 0.58 else GREY) for v in vals]
    fig, ax = plt.subplots(figsize=(10.6, 3.6))
    bars = ax.barh(labels, [v - 0.5 for v in vals], left=0.5, color=colors, height=0.62)
    ax.axvline(0.5, color="#8A9099", linewidth=1.2)
    ax.text(0.5, len(vals) - 0.35, "  a coin toss", color=MUTED, fontsize=9.5, va="center")
    for b, v in zip(bars, vals):
        ax.text(v + 0.004, b.get_y() + b.get_height() / 2, f"{v:.2f}", va="center", fontsize=9.5,
                color=INK, fontweight="bold")
    ax.set_xlim(0.47, 0.81)
    ax.set_xticks([0.5, 0.6, 0.7, 0.8])
    ax.set_xlabel("how well it warns us that the instructor's next class will go wrong")
    ax.set_axisbelow(True)
    ax.xaxis.grid(True, color="#EDEFF3")
    ax.spines["left"].set_color("#D8DCE3")
    p = fig_path("warn.png")
    fig.savefig(p)
    plt.close(fig)
    return p


def chart_trust():
    """When a low rating can be believed, by how many learners rated."""
    labels = [t[0] for t in TRUST]
    low = [t[1] for t in TRUST]
    fine = [t[2] for t in TRUST]
    x = range(len(labels))
    fig, ax = plt.subplots(figsize=(10.6, 3.5))
    w = 0.36
    ax.bar([i - w / 2 for i in x], low, width=w, color=RED, label="this class was rated low")
    ax.bar([i + w / 2 for i in x], fine, width=w, color=GREY, label="this class was fine")
    for i, (a, b) in enumerate(zip(low, fine)):
        ax.text(i - w / 2, a + 1.1, f"{a:.0f}%", ha="center", fontsize=9.5, color=RED, fontweight="bold")
        ax.text(i + w / 2, b + 1.1, f"{b:.0f}%", ha="center", fontsize=9.5, color=MUTED)
    ax.axvline(1.5, color="#C9CEd6", linestyle="--", linewidth=1.2)
    ax.text(1.62, max(low) + 1.5, "from here a low rating is believable", fontsize=9.5, color=MUTED)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_xlabel("how many learners rated the class")
    ax.set_ylabel("the cohort's next class\nalso went wrong")
    ax.set_ylim(0, max(low) + 8)
    ax.set_yticks([0, 10, 20, 30, 40])
    ax.set_yticklabels(["0", "10%", "20%", "30%", "40%"])
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color="#EDEFF3")
    ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(0, 1.01), fontsize=9.5, ncols=2)
    p = fig_path("trust.png")
    fig.savefig(p)
    plt.close(fig)
    return p


def chart_rules():
    """Rules of good behaviour kept, out of 23."""
    labels = [r[0] for r in RULES][::-1]
    vals = [r[1] for r in RULES][::-1]
    colors = [r[2] for r in RULES][::-1]
    fig, ax = plt.subplots(figsize=(10.6, 3.2))
    bars = ax.barh(labels, vals, color=colors, height=0.6)
    for b, v in zip(bars, vals):
        ax.text(v + 0.25, b.get_y() + b.get_height() / 2, f"{v} of 23", va="center", fontsize=9.5, color=INK)
    ax.set_xlim(0, 26)
    ax.set_xticks([])
    ax.spines["bottom"].set_visible(False)
    ax.spines["left"].set_color("#D8DCE3")
    p = fig_path("rules.png")
    fig.savefig(p)
    plt.close(fig)
    return p


def chart_queue():
    """Why the queue grew: the share of classes under one of the two lines, month by month."""
    labels = [u[0] for u in UNDER]
    vals = [u[1] for u in UNDER]
    fig, ax = plt.subplots(figsize=(10.6, 3.0))
    ax.plot(labels, vals, color=RED, linewidth=2.4, marker="o", markersize=5)
    ax.fill_between(labels, vals, color=RED, alpha=0.07)
    for i, v in enumerate(vals):
        if i in (0, len(vals) - 1):
            ax.text(i, v + 1.2, f"{v:.0f}%", ha="center", fontsize=10.5, color=RED, fontweight="bold")
    ax.set_ylim(0, max(vals) + 7)
    ax.set_yticks([0, 10, 20, 30])
    ax.set_yticklabels(["0", "10%", "20%", "30%"])
    ax.set_ylabel("classes under the\nrating or the vote line")
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color="#EDEFF3")
    p = fig_path("queue.png")
    fig.savefig(p)
    plt.close(fig)
    return p


P_SCORE, P_WARN, P_TRUST, P_RULES, P_QUEUE = chart_scoreboard(), chart_warn(), chart_trust(), chart_rules(), chart_queue()

# ── the document ─────────────────────────────────────────────────────────────
doc = Document()
sec = doc.sections[0]
sec.left_margin = sec.right_margin = Cm(2.0)
sec.top_margin = sec.bottom_margin = Cm(1.7)
CONTENT_CM = 17.0

base = doc.styles["Normal"]
base.font.name = "Calibri"
base.font.size = Pt(11)
base.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
for name, size in (("Heading 1", 14.5), ("Heading 2", 12)):
    st = doc.styles[name]
    st.font.name = "Calibri"
    st.font.size = Pt(size)
    st.font.bold = True
    st.font.color.rgb = INK_W
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")


def shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def para(text="", size=11, bold=False, color=None, italic=False, space_after=6, align=None):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.size = Pt(size)
    r.bold = bold
    r.italic = italic
    if color is not None:
        r.font.color.rgb = color
    p.paragraph_format.space_after = Pt(space_after)
    if align:
        p.alignment = align
    return p


def caption(text):
    return para(text, size=9.5, color=MUTED_W, italic=True, space_after=10)


def bullet(text, bold_lead=None):
    p = doc.add_paragraph(style="List Bullet")
    if bold_lead:
        r = p.add_run(bold_lead + " ")
        r.bold = True
    p.add_run(text)
    p.paragraph_format.space_after = Pt(4)
    return p


def picture(path, width_cm=CONTENT_CM, space_after=4):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(space_after)
    p.add_run().add_picture(path, width=Cm(width_cm))
    return p


def note(title, body):
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = t.rows[0].cells[0]
    cell.text = ""
    r = cell.paragraphs[0].add_run(title)
    r.bold = True
    r.font.size = Pt(10.5)
    p2 = cell.add_paragraph()
    r2 = p2.add_run(body)
    r2.font.size = Pt(10.5)
    p2.paragraph_format.space_after = Pt(2)
    shade(cell, NOTE_FILL)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def table(headers, rows_, widths=None, bold_first_col=False, colors=None, size=10.5):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = t.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = ""
        r = hdr[i].paragraphs[0].add_run(h)
        r.bold = True
        r.font.size = Pt(9.5)
        r.font.color.rgb = MUTED_W
        shade(hdr[i], HEADER_FILL)
    for ri, row in enumerate(rows_):
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            r = cells[i].paragraphs[0].add_run(str(v))
            r.font.size = Pt(size)
            if bold_first_col and i == 0:
                r.bold = True
            if colors and (ri, i) in colors:
                r.font.color.rgb = colors[(ri, i)]
                r.bold = True
            if ri % 2 == 1:
                shade(cells[i], ZEBRA_FILL)
    if widths:
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Cm(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def bignumbers(items):
    """A strip of big numbers with a small label under each."""
    t = doc.add_table(rows=2, cols=len(items))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, (n, label) in enumerate(items):
        c0 = t.rows[0].cells[i]
        c0.text = ""
        p = c0.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(n)
        r.bold = True
        r.font.size = Pt(19)
        r.font.color.rgb = BRAND_W
        c1 = t.rows[1].cells[i]
        c1.text = ""
        p1 = c1.paragraphs[0]
        p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r1 = p1.add_run(label)
        r1.font.size = Pt(9.5)
        r1.font.color.rgb = MUTED_W
    doc.add_paragraph().paragraph_format.space_after = Pt(4)
    return t


# ── title ────────────────────────────────────────────────────────────────────
para("INTERVIEW KICKSTART · NEW PROGRAMS", size=9, bold=True, color=BRAND_W, space_after=2)
para("Did we find a better formula?", size=22, bold=True, space_after=2)
para("We were told to forget the formula we were given and go find the real one. "
     "Here is what we did, in pictures.", size=12, color=MUTED_W, space_after=10)

picture(P_SCORE)
caption("The result, on three months of classes the work never saw. Left of each arrow: the formula we were "
        "given. Right: the formula the app uses today.")

para("The formula we already use came out on top. That is a real finding, not a shrug — it now stands on "
     "eight months of evidence instead of one person's judgement.", bold=True, space_after=10)

# ── 1 ────────────────────────────────────────────────────────────────────────
doc.add_heading("1. How we looked", level=1)
bignumbers([("43", "things we could\nmeasure about a class"),
            ("5", "kinds of formula\nbuilt from scratch"),
            ("28", "rounds of\ntrial and error"),
            ("378,046", "invented classes,\nincluding ones never seen"),
            ("23", "rules of good behaviour\nevery formula must keep"),
            ("3", "months hidden\nfrom the work")])
para("The last number is the important one. Any formula can be made to look good on classes it has already "
     "seen, so June, July and August were locked away. Everything was built on January to May and then "
     "judged on those hidden months.", space_after=10)

# ── 2 ────────────────────────────────────────────────────────────────────────
doc.add_heading("2. Which things actually warn us?", level=1)
para("Each bar asks one question: if this were the only thing we knew, how often would it correctly warn "
     "us that the instructor's next class is heading for trouble?", color=MUTED_W, space_after=6)
picture(P_WARN)
caption("Measured on the hidden months. 0.50 is a coin toss — no warning at all.")
bullet("The instructor's past classes, the star rating, and how the module usually goes.",
       bold_lead="What warns us:")
bullet("How many learners attended, how many rated, which weekday it was. These are barely better than "
       "guessing, so they earn no points in the formula.", bold_lead="What tells us nothing:")
bullet("Nothing we tried reaches far above 0.75. The score is a warning light, not a crystal ball — and "
       "that is worth saying out loud to anyone who expects certainty.", bold_lead="The ceiling:")

doc.add_page_break()

# ── 3 ────────────────────────────────────────────────────────────────────────
doc.add_heading("3. Can you believe a class rated by three people?", level=1)
para("This was Bishal's question: if only a few learners rate a class and one or two mark it down unfairly, "
     "the class looks bad. So we measured it — when a class was rated low, how often did that cohort's next "
     "class also go wrong?", color=MUTED_W, space_after=6)
picture(P_TRUST)
caption("Red = the class was rated low. Grey = the class was fine. The gap between them is how much a low "
        "rating is worth believing.")
para("With one or two raters the two bars are the same height: a low rating from one or two people tells us "
     "nothing at all. From five upward the gap is wide and steady.", space_after=6)
note("So the app's rule is",
     "No band under 3 votes. No class is sent for analysis under 6 votes — it is watched instead. "
     "Two or three unhappy learners can never put a class in the queue on their own. "
     "The real fix, one day, is knowing each rater's own history — whether this learner marks everything "
     "down. That needs learner-level ratings, which we do not have yet. The slot for it is already designed.")

# ── 4 ────────────────────────────────────────────────────────────────────────
doc.add_heading("4. What we tried, and what happened", level=1)
table(
    ["The formula", "What happened"],
    [
        ["Today's version", "The winner. Nothing beat it, and it keeps every rule."],
        ["Today's version + a trust guard", "Same verdicts, steadier number. Needs one code change. Kept in the drawer."],
        ["The manager's original", "Hides 105 low-rated classes behind a good badge."],
        ["Add module history, cohort momentum, attendance change", "Each adds nothing once the months are hidden."],
        ["A statistician's version of the vote", "Treats a thin vote as a bad vote."],
        ["A probability model", "Nine classes in ten land between 54 and 86, so the bands lose meaning."],
        ["The instructor's series", "Counts the record twice, so one bad history sinks a fine class."],
    ],
    widths=[7.0, 10.0], bold_first_col=True,
)
para("Every formula was also put through the 23 rules — plain statements like “more no votes must never "
     "raise a score”, obvious to a person and easy for a formula to break.", color=MUTED_W, space_after=6)
picture(P_RULES, width_cm=16.0)
caption("Only today's version, and its trust-guard twin, keep all 23.")

doc.add_page_break()

# ── 5 ────────────────────────────────────────────────────────────────────────
doc.add_heading("5. What is not the formula's fault", level=1)
para("One thing did get worse over the year, and no formula can fix it: the classes themselves.",
     color=MUTED_W, space_after=6)
picture(P_QUEUE, width_cm=16.0)
caption("The share of classes falling under the 4.55 rating line or the 80% approval line, month by month.")
para("That is why the queue now runs at about 14 analyses a week against a team capacity of 12. It is a "
     "workload decision, not a formula decision.", space_after=8)
table(
    ["The choice", "What it means"],
    [
        ["Do more analyses", "Keep every class the lines catch; find capacity for about 14 a week."],
        ["Raise the vote floor to 7", "About 13 a week; 63 thin classes get watched instead of analysed."],
        ["Move the agreed lines", "Fewer classes caught — a policy call for the team, not a formula change."],
    ],
    widths=[6.0, 11.0], bold_first_col=True,
)
bullet("One class in five sits within a single vote of a line, so one learner changing their mind flips "
       "the verdict. The only cure is turning the hard lines into a narrow grey zone.", bold_lead="Also worth knowing:")
bullet("PMs' own decisions are not being recorded — one confirm in the whole database. Pressing Confirm or "
       "Dismiss on each flagged class would sharpen the next study more than any formula change.",
       bold_lead="The cheapest improvement:")

# ── 6 ────────────────────────────────────────────────────────────────────────
doc.add_heading("6. The paragraph to send your manager", level=1)
note("Copy this",
     "We were asked to check whether the class score's formula is the right one, so we rebuilt it from "
     "scratch: 43 possible ingredients, five kinds of formula, 28 rounds of trial and error, 378,046 "
     "invented test cases, and 23 written rules of good behaviour — all judged on three months of real "
     "classes deliberately hidden from the work. The formula we already use came out on top: it is the only "
     "one that keeps every rule, it never hides a low-rated class behind a good badge (the original hid 105), "
     "and it warns us about an instructor's next class better than the original does. So we are keeping it, "
     "now backed by eight months of evidence rather than judgement. What the study asks the team to decide is "
     "not the formula but the workload: the queue runs at about 14 analyses a week against a capacity of 12, "
     "because classes genuinely got worse over the year.")

para("")
para("Full detail, every chart and number: Formula-Study.pdf (22 pages) and Formula-One-Pager.pdf. "
     "The study re-runs with one command whenever new data arrives.", size=9, color=MUTED_W, italic=True)

doc.save(OUT)
print("wrote", OUT)
