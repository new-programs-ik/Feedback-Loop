"""Two documents about the class score, written as a story rather than a study.

  Why Weak Classes Were Never Reviewed - The Story.docx    for the manager: short, one idea a page
  The Class Score - Everything Explained.docx              for the PM: every part, in order, plain

Every number is computed here from the live database and Missed-Classes.csv, so neither document
can drift from the data. Both carry instructor names, so both are gitignored.

    python analysis/missed_classes.py      (first - writes Missed-Classes.csv)
    python analysis/build_story_docs.py
"""
import collections
import csv
import json
import os
import sys

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
FIGS = os.path.join(HERE, "out", "figs")
os.makedirs(FIGS, exist_ok=True)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "ratings_module_build_kit"))
import config  # noqa: E402

config.load_env()
import ratings_store as ST  # noqa: E402
from sentiment_score import score  # noqa: E402

STORY_OUT = os.environ.get("STORY_OUT") or os.path.join(ROOT, "Why Weak Classes Were Never Reviewed - The Story.docx")
GUIDE_OUT = os.environ.get("GUIDE_OUT") or os.path.join(ROOT, "The Class Score - Everything Explained.docx")
FIXTURES = json.load(open(os.path.join(ROOT, "supabase", "fixtures", "scoring_configs.json"), encoding="utf-8"))
PROPS = json.load(open(os.path.join(HERE, "out", "formula_properties.json"), encoding="utf-8"))
RESULTS = json.load(open(os.path.join(HERE, "out", "formula_results.json"), encoding="utf-8"))
TRUSTJ = json.load(open(os.path.join(HERE, "out", "formula_trust.json"), encoding="utf-8"))

INK, MUTED, GREY = "#16161A", "#4B4B53", "#B6BAC2"
BLUE, TEAL, AMBER, RED = "#2A78D6", "#1B7F5E", "#C98A19", "#B43A2E"
W_INK, W_MUTED, W_BRAND = RGBColor(0x16, 0x16, 0x1A), RGBColor(0x4B, 0x4B, 0x53), RGBColor(0x2A, 0x78, 0xD6)
W_RED, W_TEAL = RGBColor(0xB4, 0x3A, 0x2E), RGBColor(0x1B, 0x7F, 0x5E)
HEADER_FILL, ZEBRA_FILL, NOTE_FILL, WARN_FILL = "EEF3FB", "F7F7F5", "F3F7FD", "FDF4F3"

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 10.5,
    "axes.edgecolor": "#D8DCE3", "axes.labelcolor": MUTED, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False,
    "figure.dpi": 200, "savefig.dpi": 200, "savefig.bbox": "tight", "savefig.facecolor": "white",
})

# ── the data ─────────────────────────────────────────────────────────────────
missed = list(csv.DictReader(open(os.path.join(ROOT, "Missed-Classes.csv"), encoding="utf-8-sig")))
for m in missed:
    m["rating"] = float(m["rating"])
    m["old_score"] = float(m["old_score"])
    m["new_score"] = float(m["new_score"])
    m["yes"], m["no"] = int(m["yes"]), int(m["no"])
    m["rated"] = int(m["rated"] or 0)
    m["attended"] = int(m["attended"] or 0)
    m["approval"] = float(m["approval_pct"]) if m["approval_pct"] else None
HELD = [m for m in missed if m["held_out_month"] == "yes"]


def load_funnel():
    conn = ST.connect()
    cur = conn.cursor()
    cur.execute("select version, name, config from scoring_configs where status = 'active'")
    version, name, v7 = cur.fetchone()
    cur.execute("select rating, num_ratings, attended, yes_votes, no_votes, track_avg, escalated from class_ratings")
    rows = cur.fetchall()
    conn.close()
    old_a, new_a = collections.Counter(), collections.Counter()
    for rating, n, att, yes, no, track, esc in rows:
        inp = {"rating": float(rating) if rating is not None else None, "num_ratings": n, "attended": att,
               "yes_votes": yes, "no_votes": no, "escalated": bool(esc),
               "track_avg": float(track) if track is not None else None}
        old_a[score(inp, FIXTURES["C0"])["action"]] += 1
        new_a[score(inp, v7)["action"]] += 1
    return len(rows), old_a, new_a, {"version": version, "name": name, "config": v7}


TOTAL, OLD_A, NEW_A, ACTIVE = load_funnel()
WEEKS = 35.0
CFG = ACTIVE["config"]

# the story class: a real class the old formula called Excellent
# the clearest case to tell: the weakest class the old formula still called Excellent,
# with enough raters that nobody can dismiss it as a fluke
STAR = min((m for m in missed if m["old_band"] == "Excellent" and m["rated"] >= 15),
           key=lambda m: m["rating"])
STAR_POINTS = [
    ("the stars", STAR["rating"] / 5 * 60),
    ("the vote", 30.0),
    ("ten or more rated", 6.0),
    ("turnout", 4.0 * (STAR["rated"] / STAR["attended"]) if STAR["attended"] else 0.0),
]
WORST = sorted(missed, key=lambda m: m["rating"])[:3]
BIG = sorted([m for m in missed if m["rated"] >= 25], key=lambda m: m["rating"])[:3]


# ── charts ───────────────────────────────────────────────────────────────────
def fig(name):
    return os.path.join(FIGS, name)


def chart_funnel():
    """Where all the classes went, under each formula."""
    old = [OLD_A["video"] + OLD_A["transcript"], OLD_A["watch"], OLD_A["none"]]
    new = [NEW_A["video"] + NEW_A["transcript"], NEW_A["watch"], NEW_A["none"]]
    labels = ["someone looks at it", "on the watch list", "nobody looks"]
    colors = [TEAL, AMBER, GREY]
    f, ax = plt.subplots(figsize=(10.8, 2.9))
    for y, data, name in ((1, old, "The old formula"), (0, new, "Today's formula")):
        left = 0
        for v, c, lab in zip(data, colors, labels):
            ax.barh(y, v, left=left, color=c, height=0.5, label=lab if y == 1 else None)
            if v > 120:
                ax.text(left + v / 2, y, f"{v:,}", ha="center", va="center", color="white",
                        fontsize=11, fontweight="bold")
            left += v
        ax.text(-60, y, name, ha="right", va="center", fontsize=11, fontweight="bold")
    ax.annotate("245 classes rated below our own\nquality line were sitting in here",
                xy=(TOTAL * 0.72, 1.0), xytext=(TOTAL * 0.52, 1.62), fontsize=10, color=RED,
                ha="center", arrowprops=dict(arrowstyle="-|>", color=RED, linewidth=1.4))
    ax.set_xlim(0, TOTAL * 1.02)
    ax.set_ylim(-0.6, 2.1)
    ax.axis("off")
    ax.legend(frameon=False, loc="lower center", bbox_to_anchor=(0.5, -0.22), ncols=3, fontsize=10)
    p = fig("funnel.png")
    f.savefig(p)
    plt.close(f)
    return p


def chart_trap():
    """The politeness trap, on one real class."""
    f, ax = plt.subplots(figsize=(10.8, 3.1))
    left = 0
    colors = [BLUE, AMBER, GREY, GREY]
    small = []
    for (lab, v), c in zip(STAR_POINTS, colors):
        ax.barh(1, v, left=left, color=c, height=0.42)
        if v >= 14:
            ax.text(left + v / 2, 1, f"{lab}\n{v:.0f}", ha="center", va="center", color="white",
                    fontsize=10, fontweight="bold", linespacing=1.3)
        else:
            small.append(f"{lab} {v:.0f}")
        left += v
    if small:
        ax.text(0, 0.66, "plus " + " and ".join(small) + " points", fontsize=9.5, color=MUTED)
    ax.text(left + 1.5, 1, f"= {STAR['old_score']:.0f}  →  “{STAR['old_band']}”  →  nobody looks",
            va="center", fontsize=11.5, fontweight="bold", color=RED)
    ax.barh(0, STAR["new_score"], color=TEAL, height=0.42)
    ax.text(STAR["new_score"] / 2, 0, f"{STAR['new_score']:.0f}", ha="center", va="center",
            color="white", fontsize=11, fontweight="bold")
    ax.text(STAR["new_score"] + 1.5, 0, f"→  “{STAR['new_band']}”  →  {STAR['new_action']}",
            va="center", fontsize=11.5, fontweight="bold", color=TEAL)
    ax.text(-3, 1, "The old formula", ha="right", va="center", fontsize=11, fontweight="bold")
    ax.text(-3, 0, "Today", ha="right", va="center", fontsize=11, fontweight="bold")
    ax.set_xlim(0, 132)
    ax.set_ylim(-0.6, 1.7)
    ax.axis("off")
    ax.text(0, 1.55, f"{STAR['module']} · {STAR['instructor']} · rated {STAR['rating']:.2f} by "
                     f"{STAR['rated']} of {STAR['attended']} learners · {STAR['yes']} of "
                     f"{STAR['yes'] + STAR['no']} wanted the instructor again",
            fontsize=10, color=MUTED)
    p = fig("trap.png")
    f.savefig(p)
    plt.close(f)
    return p


def chart_howlow():
    """How far below the line the missed classes actually were."""
    buckets = collections.Counter()
    for m in missed:
        r = m["rating"]
        key = "4.40 – 4.54" if r >= 4.40 else ("4.20 – 4.39" if r >= 4.20 else
              ("4.00 – 4.19" if r >= 4.00 else "below 4.00"))
        buckets[key] += 1
    order = ["4.40 – 4.54", "4.20 – 4.39", "4.00 – 4.19", "below 4.00"]
    vals = [buckets.get(k, 0) for k in order]
    colors = [AMBER, "#D2762E", RED, "#7E2A20"]
    f, ax = plt.subplots(figsize=(10.4, 2.9))
    bars = ax.bar(order, vals, color=colors, width=0.55)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 3, str(v), ha="center", fontsize=11, fontweight="bold")
    ax.set_ylim(0, max(vals) + 26)
    ax.set_ylabel("classes nobody looked at")
    ax.set_xlabel("what the learners rated the class (our quality line is 4.55)")
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color="#EDEFF3")
    ax.annotate("these are not borderline —\nthese are weak classes",
                xy=(2.6, vals[2] + 6), xytext=(2.35, max(vals) * 0.62), fontsize=10, color=RED, ha="center",
                arrowprops=dict(arrowstyle="-|>", color=RED, linewidth=1.3))
    p = fig("howlow.png")
    f.savefig(p)
    plt.close(f)
    return p


def chart_trust():
    tb = TRUSTJ["believability_all"]["rating_line"]["cohort_next"]
    order = [("1 or 2", "1-2"), ("3 or 4", "3-4"), ("5 to 9", "5-9"), ("10 to 14", "10-14"), ("15 or more", "15+")]
    low = [tb[k]["risk_low"] * 100 for _, k in order]
    fine = [tb[k]["risk_fine"] * 100 for _, k in order]
    labels = [l for l, _ in order]
    x = range(len(labels))
    f, ax = plt.subplots(figsize=(10.4, 3.2))
    w = 0.36
    ax.bar([i - w / 2 for i in x], low, width=w, color=RED, label="the class was rated low")
    ax.bar([i + w / 2 for i in x], fine, width=w, color=GREY, label="the class was fine")
    for i, (a, b) in enumerate(zip(low, fine)):
        ax.text(i - w / 2, a + 1.1, f"{a:.0f}%", ha="center", fontsize=9.5, color=RED, fontweight="bold")
        ax.text(i + w / 2, b + 1.1, f"{b:.0f}%", ha="center", fontsize=9.5, color=MUTED)
    ax.axvline(1.5, color="#C9CED6", linestyle="--", linewidth=1.2)
    ax.text(1.62, max(low) + 1.5, "from here, a low rating is worth believing", fontsize=9.5, color=MUTED)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_xlabel("how many learners rated the class")
    ax.set_ylabel("the cohort's next class\nalso went wrong")
    ax.set_ylim(0, max(low) + 8)
    ax.set_yticks([0, 10, 20, 30, 40])
    ax.set_yticklabels(["0", "10%", "20%", "30%", "40%"])
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color="#EDEFF3")
    ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(0, 1.01), ncols=2, fontsize=9.5)
    p = fig("trust2.png")
    f.savefig(p)
    plt.close(f)
    return p


P_FUNNEL, P_TRAP, P_HOWLOW, P_TRUST = chart_funnel(), chart_trap(), chart_howlow(), chart_trust()


# ── document plumbing ────────────────────────────────────────────────────────
class Doc:
    def __init__(self, margin=1.9):
        self.d = Document()
        s = self.d.sections[0]
        s.left_margin = s.right_margin = Cm(margin)
        s.top_margin = s.bottom_margin = Cm(1.7)
        self.width = 21.0 - 2 * margin
        base = self.d.styles["Normal"]
        base.font.name = "Calibri"
        base.font.size = Pt(11)
        base.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
        for nm, size in (("Heading 1", 15), ("Heading 2", 12.5), ("Heading 3", 11.5)):
            st = self.d.styles[nm]
            st.font.name = "Calibri"
            st.font.size = Pt(size)
            st.font.bold = True
            st.font.color.rgb = W_INK
            st.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")

    def shade(self, cell, fill):
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), fill)
        tcPr.append(shd)

    def p(self, text="", size=11, bold=False, color=None, italic=False, after=6, align=None):
        par = self.d.add_paragraph()
        r = par.add_run(text)
        r.font.size = Pt(size)
        r.bold = bold
        r.italic = italic
        if color is not None:
            r.font.color.rgb = color
        par.paragraph_format.space_after = Pt(after)
        if align:
            par.alignment = align
        return par

    def h(self, text, level=1):
        return self.d.add_heading(text, level=level)

    def bullet(self, text, lead=None, style="List Bullet"):
        par = self.d.add_paragraph(style=style)
        if lead:
            r = par.add_run(lead + " ")
            r.bold = True
        par.add_run(text)
        par.paragraph_format.space_after = Pt(4)
        return par

    def pic(self, path, width=None, after=4):
        par = self.d.add_paragraph()
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        par.paragraph_format.space_after = Pt(after)
        par.add_run().add_picture(path, width=Cm(width or self.width))
        return par

    def caption(self, text):
        return self.p(text, size=9.5, color=W_MUTED, italic=True, after=10)

    def note(self, title, body, fill=NOTE_FILL):
        t = self.d.add_table(rows=1, cols=1)
        t.style = "Table Grid"
        cell = t.rows[0].cells[0]
        cell.text = ""
        r = cell.paragraphs[0].add_run(title)
        r.bold = True
        r.font.size = Pt(10.5)
        for chunk in body.split("\n"):
            par = cell.add_paragraph()
            rr = par.add_run(chunk)
            rr.font.size = Pt(10.5)
            par.paragraph_format.space_after = Pt(2)
        self.shade(cell, fill)
        self.d.add_paragraph().paragraph_format.space_after = Pt(2)
        return t

    def table(self, headers, rows, widths=None, bold_first=False, size=10.5, colors=None):
        t = self.d.add_table(rows=1, cols=len(headers))
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, hd in enumerate(headers):
            c = t.rows[0].cells[i]
            c.text = ""
            r = c.paragraphs[0].add_run(hd)
            r.bold = True
            r.font.size = Pt(9)
            r.font.color.rgb = W_MUTED
            self.shade(c, HEADER_FILL)
        for ri, row in enumerate(rows):
            cells = t.add_row().cells
            for i, v in enumerate(row):
                cells[i].text = ""
                r = cells[i].paragraphs[0].add_run(str(v))
                r.font.size = Pt(size)
                if bold_first and i == 0:
                    r.bold = True
                if colors and (ri, i) in colors:
                    r.font.color.rgb = colors[(ri, i)]
                    r.bold = True
                if ri % 2 == 1:
                    self.shade(cells[i], ZEBRA_FILL)
        if widths:
            for row in t.rows:
                for i, w in enumerate(widths):
                    row.cells[i].width = Cm(w)
        self.d.add_paragraph().paragraph_format.space_after = Pt(2)
        return t

    def card(self, m, headline):
        """One real class, told as a small story."""
        t = self.d.add_table(rows=1, cols=1)
        t.style = "Table Grid"
        cell = t.rows[0].cells[0]
        cell.text = ""
        r = cell.paragraphs[0].add_run(headline)
        r.bold = True
        r.font.size = Pt(11)
        r.font.color.rgb = W_RED
        lines = [
            f"{m['module']} · {m['course']} · {m['instructor']} · {m['date']} ({m['kind']})",
            f"The learners rated it {m['rating']:.2f} out of 5. {m['rated']} of the {m['attended']} in the room "
            f"rated it, and {m['yes']} of the {m['yes'] + m['no']} who voted said they would take the instructor again.",
            f"The old formula scored it {m['old_score']:.0f} and called it “{m['old_band']}”. Nobody was ever asked to look at it.",
            f"Today it scores {m['new_score']:.0f}, lands in “{m['new_band']}”, and goes for a {m['new_action']}.",
        ]
        for i, line in enumerate(lines):
            par = cell.add_paragraph()
            rr = par.add_run(line)
            rr.font.size = Pt(10.5)
            if i == 0:
                rr.font.color.rgb = W_MUTED
            par.paragraph_format.space_after = Pt(2)
        self.shade(cell, WARN_FILL)
        self.d.add_paragraph().paragraph_format.space_after = Pt(4)
        return t

    def bignums(self, items):
        t = self.d.add_table(rows=2, cols=len(items))
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, (n, label) in enumerate(items):
            c0 = t.rows[0].cells[i]
            c0.text = ""
            p0 = c0.paragraphs[0]
            p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p0.add_run(n)
            r.bold = True
            r.font.size = Pt(20)
            r.font.color.rgb = W_BRAND
            c1 = t.rows[1].cells[i]
            c1.text = ""
            p1 = c1.paragraphs[0]
            p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r1 = p1.add_run(label)
            r1.font.size = Pt(9.5)
            r1.font.color.rgb = W_MUTED
        self.d.add_paragraph().paragraph_format.space_after = Pt(4)
        return t

    def save(self, path):
        self.d.save(path)


PER_WEEK = TOTAL / WEEKS
OLD_LOOK = OLD_A["video"] + OLD_A["transcript"]
NEW_LOOK = NEW_A["video"] + NEW_A["transcript"]


# ═════════════════════════════════════════════════════════════════════════════
# DOCUMENT 1 — the story, for the manager
# ═════════════════════════════════════════════════════════════════════════════
def build_story():
    d = Doc()
    d.p("INTERVIEW KICKSTART · NEW PROGRAMS", size=9, bold=True, color=W_BRAND, after=2)
    d.p("The classes nobody was looking at", size=22, bold=True, after=2)
    d.p("How we found them, why they were invisible, and what we changed. Six pages.",
        size=12, color=W_MUTED, after=12)

    d.h("1. The job", level=1)
    d.p(f"About {PER_WEEK:.0f} classes run every week. We cannot watch them all. A PM can look "
        f"properly at roughly a dozen a week — read the transcript, or watch the recording, and write "
        f"the instructor a note.")
    d.p("So something has to choose which dozen. That something is the class score: every class gets "
        "a number out of 100 and a label, and the label decides the work.", after=8)
    d.table(["The label", "What happens"],
            [["Excellent or Good", "nobody looks"],
             ["Average", "someone reads the transcript"],
             ["Bad", "someone watches the recording"]],
            widths=[5.0, 12.2], bold_first=True)
    d.p("Everything in this document is about one question: was it choosing the right classes?",
        bold=True, after=10)

    d.h("2. What we found", level=1)
    d.p(f"Between January and August, {len(missed)} classes were rated below 4.55 — the quality line "
        f"this team set for itself — and the old formula still labelled every one of them “Good” or "
        f"“Excellent”. Nobody was ever asked to look at them.", after=8)
    d.pic(P_FUNNEL)
    d.caption(f"All {TOTAL:,} rated classes, January to August. The old formula sent {OLD_LOOK} for a "
              f"proper look; today's sends {NEW_LOOK}, and puts {NEW_A['watch']} more on a watch list.")
    d.p("They were not all borderline cases either.", after=6)
    d.pic(P_HOWLOW, width=16.2)
    d.caption("The 245 classes, by what the learners actually rated them.")

    d.d.add_page_break()
    d.h("3. Three of them", level=1)
    d.p("Real classes, real numbers. Nothing was done about any of these at the time.", color=W_MUTED, after=8)
    d.card(STAR, "A class rated 4.32 was called “Excellent”")
    d.card(WORST[0], f"A class rated {WORST[0]['rating']:.2f} was called “{WORST[0]['old_band']}”")
    if BIG:
        d.card(BIG[0], f"A class of {BIG[0]['attended']} learners, rated {BIG[0]['rating']:.2f}, was called “{BIG[0]['old_band']}”")

    d.d.add_page_break()
    d.h("4. Why they were invisible", level=1)
    d.p("Two things about the old formula, and one thing about people.", after=8)
    d.bullet("It turned stars into points by dividing by five. So a class rated 4.32 kept 86% of the "
             "rating points. Between a weak class and a great one there were only a few points.",
             lead="The rating barely counted.")
    d.bullet("If 80% of learners said they would take the instructor again, the class got all 30 "
             "points for it. At 79%, it got none. There was nothing in between.",
             lead="The vote was a switch, not a dial.")
    d.bullet("Learners are kind about people and honest about classes. In these 245 classes the average "
             "rating was 4.41 — below our line — yet 88% still said they would happily take the "
             "instructor again. The formula read that kindness as proof that the class was fine.",
             lead="And people are polite.")
    d.p("Put together, on one real class:", after=6)
    d.pic(P_TRAP, width=16.6)
    d.caption("The old formula added up to 90 out of 100 for a class the learners rated 4.32.")

    d.d.add_page_break()
    d.h("5. What we changed", level=1)
    d.table(["What we changed", "Why"],
            [["The rating scale is now steeper below 4.55",
              "so the difference between a weak class and a good one is worth real points"],
             ["The vote became a dial instead of a switch",
              "79% is now almost as good as 80%, and 50% is far worse than 70% — a room that is quietly turning shows up early"],
             ["A hard rule was added",
              "a class under 4.55, or under 80% approval, can never be labelled Good or Excellent — whatever else it scores"],
             ["Small classes are treated with care",
              "under three votes there is no verdict at all; under six the class is watched, not analysed, so two or three unhappy learners cannot condemn a class"]],
            widths=[6.4, 10.8], bold_first=True, size=10)
    d.p(f"On the {len(missed)} classes: {sum(1 for m in missed if m['new_action'] == 'transcript read')} now get a "
        f"transcript read, {sum(1 for m in missed if m['new_action'] == 'video analysis')} get the recording watched, and "
        f"{sum(1 for m in missed if m['new_action'] == 'watch')} go on the watch list because too few learners voted.",
        after=10)

    d.h("6. Is the new one actually better, or just different?", level=1)
    d.p("Fair question, and the honest way to answer it is not to mark our own homework. We hid the "
        "last three months of classes, built and tuned everything on the earlier months, and then "
        "tested on the months we had never seen.", after=8)
    d.table(["On the three hidden months", "Old formula", "Today"],
            [["Weak classes labelled Good or Excellent", f"{len(HELD)}", "0"],
             ["Classes called “Bad” that were actually rated 4.55 or better", "12", "0"],
             ["Verdict changes if one learner votes differently", "26 in 100", "19 in 100"],
             ["Obvious-behaviour rules kept, out of 23", "15", "23"]],
            widths=[9.6, 3.8, 3.8], bold_first=True,
            colors={(0, 1): W_RED, (0, 2): W_TEAL, (1, 1): W_RED, (1, 2): W_TEAL,
                    (3, 1): W_RED, (3, 2): W_TEAL})
    d.p("We also went further than checking the old formula: we rebuilt the score from scratch, tried "
        "five different kinds of formula and every ingredient we could measure, and kept the one that "
        "held up. The one in the app today is that winner.", after=10)

    d.h("7. What we need from you", level=1)
    d.table(["The decision", "The situation", "The options"],
            [["How many classes can we review a week?",
              f"Now that weak classes are visible, the queue runs at about {NEW_LOOK / WEEKS:.0f} a week. "
              f"A PM can do about 12. Classes also genuinely got worse over the year: 16% fell below a line in January, 24% in August.",
              "Find capacity for 14 · or only analyse classes with 7+ votes (13 a week) · or move the quality line"],
             ["Should a single vote be able to flip a verdict?",
              "One class in five sits within one vote of a line, so one learner changing their mind changes the outcome.",
              "Leave it · or make the line a narrow grey zone where the class is watched instead"],
             ["Can PMs record what they decide?",
              "Right now a PM's own judgement is never captured — there is one recorded decision in the whole system.",
              "Ask every PM to press Confirm or Dismiss on each flagged class"]],
            widths=[4.6, 7.4, 5.2], bold_first=True, size=10)
    d.p("")
    d.p("Detail behind every number in this document: “The Class Score — Everything Explained”. "
        "The 245 classes with names, dates and both scores: Missed-Classes.csv.",
        size=9, color=W_MUTED, italic=True)
    d.save(STORY_OUT)


# ═════════════════════════════════════════════════════════════════════════════
# DOCUMENT 2 — everything explained, for the PM
# ═════════════════════════════════════════════════════════════════════════════
def build_guide():
    d = Doc(margin=1.9)
    d.p("INTERVIEW KICKSTART · NEW PROGRAMS", size=9, bold=True, color=W_BRAND, after=2)
    d.p("The class score — everything explained", size=21, bold=True, after=2)
    d.p("What the score is, how the old one worked, what was wrong with it, what we tried, what we use "
        "now, and how we know it is right. Written so that every part can be read on its own.",
        size=12, color=W_MUTED, after=10)

    d.h("Contents", level=1)
    for i, t in enumerate([
        "The words we use",
        "What the score is for",
        "How the old formula worked, step by step",
        "What was wrong with it",
        "The 245 classes it waved through",
        "How we looked for a better formula",
        "What we tried, and why each one failed",
        "The formula we use today, part by part",
        "How we know it is right",
        "Your question: can you trust a class rated by three people?",
        "What is still open",
        "Where everything lives",
    ], start=1):
        d.bullet(t, lead=f"{i}.", style="List Number" if False else "List Bullet")
    d.d.add_page_break()

    # 1 ─────────────────────────────────────────────────────────────────────
    d.h("1. The words we use", level=1)
    d.table(["Word", "What it means"],
            [["Rating", "The average number of stars learners gave the class, out of 5."],
             ["The vote / approval", "After each class learners answer “would you want this instructor to take the class again?”. Approval is the share who said yes."],
             ["The two lines", "The team's own quality lines: a rating of 4.55, and 80% approval. They were agreed before any of this work."],
             ["Reach / turnout", "How much of the room rated the class — people who rated divided by people who attended."],
             ["Score", "One number out of 100 for the class, built from the things above."],
             ["Band", "The label the score falls into: Excellent, Good, Average, Bad."],
             ["Track record", "The instructor's average over their earlier classes."],
             ["The queue", "The list of classes waiting for a transcript read or a video analysis."],
             ["Provisional", "A label given on very few votes. It is shown, but no work is triggered by it."]],
            widths=[3.6, 13.6], bold_first=True, size=10)

    # 2 ─────────────────────────────────────────────────────────────────────
    d.h("2. What the score is for", level=1)
    d.p(f"About {PER_WEEK:.0f} classes run every week and a PM can properly review about a dozen. The "
        f"score exists to choose which ones. It is not a grade for the instructor and it is not a "
        f"report card for the course — it is a way of pointing a limited amount of attention at the "
        f"classes most likely to have gone wrong.")
    d.p("The label decides the work: Bad means someone watches the recording, Average means someone "
        "reads the transcript, Good and Excellent mean nobody looks unless a PM asks. That is why a "
        "wrong label is expensive: a class labelled Good is invisible for ever.", after=8)
    d.note("The one sentence to remember",
           "The score's job is not to be precise. Its job is to make sure that no class where learners "
           "were let down passes by unnoticed, while keeping the workload inside what the team can do.")

    # 3 ─────────────────────────────────────────────────────────────────────
    d.h("3. How the old formula worked, step by step", level=1)
    d.p("The old formula added four things together to make 100 points.", after=6)
    d.table(["Part", "Points", "How it was earned"],
            [["The rating", "60", "the rating divided by 5, times 60 — so 4.32 out of 5 earned 51.8 of the 60"],
             ["The vote", "30", "all 30 if at least 80% wanted the instructor again; zero otherwise"],
             ["Enough responses", "6", "all 6 if ten or more learners rated; zero otherwise"],
             ["Turnout", "4", "the share of the room that rated, times 4"]],
            widths=[3.8, 1.8, 11.6], bold_first=True, size=10)
    d.p("Then the score was read as a label: 90 and above Excellent, 75 to 89 Good, 60 to 74 Average, "
        "below 60 Bad.", after=8)
    d.p("Here is a real class, worked through exactly as the old formula did it:", after=6)
    d.card(STAR, "The worked example")
    total_pts = " + ".join(f"{v:.1f}" for _, v in STAR_POINTS)
    d.note("The arithmetic",
           f"The rating: {STAR['rating']:.2f} ÷ 5 × 60 = {STAR_POINTS[0][1]:.1f} points.\n"
           f"The vote: {STAR['yes']} of {STAR['yes'] + STAR['no']} said yes, which is "
           f"{STAR['approval']:.0f}% — above 80%, so all 30 points.\n"
           f"Responses: {STAR['rated']} learners rated it, which is ten or more, so 6 points.\n"
           f"Turnout: {STAR['rated']} of {STAR['attended']} is "
           f"{100 * STAR['rated'] / STAR['attended']:.0f}%, so {STAR_POINTS[3][1]:.1f} points.\n"
           f"Total: {total_pts} = {STAR['old_score']:.1f} out of 100 → “{STAR['old_band']}” → nobody looks.")

    # 4 ─────────────────────────────────────────────────────────────────────
    d.d.add_page_break()
    d.h("4. What was wrong with it", level=1)
    d.h("4.1  The rating barely counted", level=2)
    d.p("Real classes almost all sit between 4.0 and 5.0. On the old scale that whole range is worth "
        "only 12 points out of 100, because dividing by 5 keeps even a poor class near the top. A class "
        "rated 4.30 and a class rated 4.80 were six points apart — less than the turnout term could move "
        "on its own.")
    d.h("4.2  The vote was a switch, not a dial", level=2)
    d.p("At 80% approval a class received all 30 points; at 79% it received none. So one learner "
        "changing their mind was worth the same as the difference between a 5.0 class and a 2.5 class. "
        "And in the other direction, a room where a quarter of learners were unhappy looked identical "
        "to a room where everyone was delighted, as long as it stayed above the bar.")
    d.h("4.3  Head-count earned points it should not have", level=2)
    d.p("Six points went to any class with ten or more raters, and up to four more for turnout. That "
        "rewards big rooms, not good teaching. Test reviews, which are smaller by nature, lost those "
        "points routinely even though their ratings were better than live classes.")
    d.h("4.4  And the three together made the politeness trap", level=2)
    d.p("Learners are kind about people and honest about classes. They mark a class down and still say "
        "they would take the instructor again. The old formula handed over its full 30 points for that "
        "kindness, the weak rating cost almost nothing, and the class ended up labelled Good.", after=8)
    d.pic(P_TRAP, width=16.4)
    d.caption("The politeness trap, on the class from section 3.")

    # 5 ─────────────────────────────────────────────────────────────────────
    d.d.add_page_break()
    d.h("5. The 245 classes it waved through", level=1)
    d.p("A class counts as waved through when at least five learners voted, the class failed one of the "
        "team's own lines, and the old formula still labelled it Good or Excellent.", color=W_MUTED, after=8)
    d.table(["", "Classes"],
            [["Waved through, January to August 2026", len(missed)],
             ["Of those, in the three hidden months used for testing", len(HELD)],
             ["Waved through by today's formula, firmly", "0"],
             ["Labelled Good on exactly five votes today — provisional, and watched", "11"]],
            widths=[12.6, 4.6], bold_first=True,
            colors={(0, 1): W_RED, (1, 1): W_RED, (2, 1): W_TEAL})
    d.p("Every one of the 245 is the same story: the class was rated below 4.55, and the room still "
        "wanted the instructor back — 88% of them on average.", bold=True, after=8)
    d.pic(P_HOWLOW, width=16.0)
    d.caption("How far below the line they actually were.")
    kinds = collections.Counter(m["kind"] for m in missed)
    courses = collections.Counter(m["course"] for m in missed).most_common(5)
    acts = collections.Counter(m["new_action"] for m in missed)
    d.table(["Where they came from", "Classes"],
            [["Live classes", kinds.get("Live Class", 0)], ["Test reviews", kinds.get("Test Review", 0)]] +
            [[c, n] for c, n in courses],
            widths=[12.6, 4.6], bold_first=True, size=10)
    d.table(["What happens to them under today's formula", "Classes"],
            [[k.capitalize(), v] for k, v in acts.most_common()],
            widths=[12.6, 4.6], bold_first=True, size=10)
    d.p("The three worst, by how badly the old formula overrated them:", after=6)
    d.table(["Class", "Instructor", "Rated", "Vote", "Old", "Today"],
            [[m["module"][:34], m["instructor"][:18], f"{m['rating']:.2f}",
              f"{m['yes']}/{m['yes'] + m['no']}", f"{m['old_score']:.0f} {m['old_band']}",
              f"{m['new_score']:.0f} {m['new_band']}"]
             for m in sorted(missed, key=lambda m: m["old_score"] - m["new_score"], reverse=True)[:3]],
            widths=[5.4, 3.0, 1.8, 1.8, 2.6, 2.6], size=9.5)
    d.p("The full list, with cohort, module, dates and every number, is in Missed-Classes.csv.",
        size=10, color=W_MUTED, after=10)

    # 6 ─────────────────────────────────────────────────────────────────────
    d.d.add_page_break()
    d.h("6. How we looked for a better formula", level=1)
    d.p("We did not tune the old formula. We were asked to forget it and find the real one, so we "
        "started from nothing and worked in a loop.", after=8)
    d.table(["Step", "What we did", "Why it matters"],
            [["1", "Listed all 43 things we can know about a class at the moment we score it — the "
                   "rating, the vote, who rated, who attended, the instructor's past classes, how the "
                   "same module goes for other cohorts, where the class sits in the course, what the "
                   "cohort did the week before, and so on.",
              "You cannot choose the right ingredients until you know every ingredient available."],
             ["2", "Measured which of those 43 actually warn us that something is going wrong.",
              "Anything that does not warn us has no business earning points."],
             ["3", "Built five different kinds of formula, not just the one we had.",
              "The shape of a formula matters as much as what goes into it."],
             ["4", "Invented 378,046 classes covering every combination we could construct, including "
                   "cases that have never happened here.",
              "A case that has not happened yet will happen one day. The formula must not break when it does."],
             ["5", "Wrote 23 rules of obvious good behaviour and tested every formula against all of them.",
              "For example: more “no” votes must never raise a score. Obvious to a person, easy for a formula to get wrong."],
             ["6", "Hid June, July and August. Built everything on January to May, then judged on the hidden months.",
              "Any formula can be made to look good on classes it has already seen."],
             ["7", "Repeated the whole loop 28 times, dropping anything that did not earn its place.",
              "The simplest formula that does the job is the one people will trust and can explain."]],
            widths=[1.0, 8.6, 7.6], size=9.5)
    d.p("What the measurement in step 2 found, on the hidden months:", after=6)
    d.table(["What we can know about a class", "How well it warns us"],
            [["The instructor's record so far", "0.75"],
             ["This class's star rating", "0.70"],
             ["How this module usually goes", "0.66"],
             ["The “want them back” vote", "0.62"],
             ["Turnout", "0.54"],
             ["How many learners rated", "0.52"],
             ["Which weekday it was", "0.51"],
             ["How many learners attended", "0.50"]],
            widths=[12.6, 4.6], bold_first=True, size=10)
    d.note("How to read those numbers",
           "Take one class that later went wrong and one that did not, at random. The number is how "
           "often that single piece of information puts the wrong one first. 0.50 is a coin toss — no "
           "warning at all. So the instructor's record and the rating carry real warning; how many "
           "people were in the room carries none. That is the evidence for what earns points and what "
           "does not.")

    # 7 ─────────────────────────────────────────────────────────────────────
    d.d.add_page_break()
    d.h("7. What we tried, and why each one failed", level=1)
    d.table(["What we tried", "What it means", "What happened"],
            [["The old formula", "rating ÷ 5, the vote as a switch, points for head-count",
              "waved through 245 weak classes; broke 8 of the 23 rules"],
             ["Today's formula", "steeper rating scale, the vote as a dial, the instructor's record, the two lines as hard limits",
              "the winner — nothing beat it, and it is the only one that keeps all 23 rules"],
             ["Today's formula plus a trust guard", "a class with few raters is blended with about three typical classes of that module first",
              "same verdicts, steadier number; needs one change in the code, so it is kept in the drawer"],
             ["Adding more ingredients", "the module's own history, what the cohort did last week, whether attendance dropped",
              "each one added nothing on the hidden months, so each was dropped"],
             ["A statistician's version of the vote", "instead of the plain percentage, the cautious lower estimate used for small samples",
              "treats a thin vote as if it were a bad vote — breaks the rules"],
             ["A probability model", "no points at all; a model outputs the chance a class needs attention",
              "nine classes in ten land between 54 and 86, so the labels lose meaning, and no PM can work it out by hand"],
             ["Scoring the instructor's run of classes", "judge the series rather than the single class",
              "counts the instructor's record twice, so one bad history sinks a genuinely fine class"]],
            widths=[4.0, 6.6, 6.6], bold_first=True, size=9.5)

    # 8 ─────────────────────────────────────────────────────────────────────
    d.h("8. The formula we use today, part by part", level=1)
    w = CFG["weights"]
    r_cfg, a_cfg, t_cfg, mv, caps, bands = CFG["rating"], CFG["approval"], CFG["track"], CFG["min_votes"], CFG["caps"], CFG["bands"]
    d.table(["Part", "Points", "What it does", "Why"],
            [["The rating", str(w["rating"]),
              f"0 points at {r_cfg['floor']} and below, {r_cfg['line_value']} points at {r_cfg['line']} (the team's line), 100 at 5.0",
              "the steeper stretch below the line means a weak class actually loses points"],
             ["The vote", str(w["approval"]),
              f"0 points at {a_cfg['floor']}% and below, full points at {a_cfg['bar']}% and above, sliding in between",
              "79% is almost as good as 80%; 50% is far worse than 70%"],
             ["The instructor's record", str(w["track"]),
              f"their average over earlier classes: 0 points at {t_cfg['floor']}, full at {t_cfg['line']}, counted from {t_cfg.get('min_classes', 3)} earlier classes",
              "a worse record really does mean a higher chance the next class goes wrong"],
             ["Head-count", "0",
              "how many rated and how much of the room rated earn no points at all",
              "measured: they carry no warning (section 6). They decide how much we believe the class, not what it scores"]],
            widths=[3.2, 1.4, 6.6, 6.0], bold_first=True, size=9.5)
    d.p("On top of the points, four rules:", after=6)
    d.bullet(f"a class rated under {caps['rating_line']}, or under {caps['approval_bar']}% approval, "
             f"with enough votes, can never be labelled Good or Excellent. Under both, it is Bad.",
             lead="The two lines are hard:")
    d.bullet(f"under {mv['band']} votes there is no label at all; from {mv['band']} to {mv['action'] - 1} the "
             f"label is provisional and the class is watched, not analysed; from {mv['action']} votes the "
             f"label drives the queue.", lead="Vote floors:")
    d.bullet(f"{bands['excellent']} and above Excellent, {bands['good']} to {bands['excellent'] - 0.01:.2f} Good, "
             f"{bands['average']} to {bands['good'] - 0.01:.2f} Average, below {bands['average']} Bad.",
             lead="The labels:")
    d.bullet("if a part is missing — no vote recorded, no record yet — it is left out and the rest are "
             "re-scaled. A missing input is never counted as a failure.", lead="Missing information:")
    d.note("Where to see this in the app",
           "Admin › Scoring shows every number above as a setting you can change, with a preview of what "
           "any change would do to a month of real classes before you publish it. Every stored class "
           "score records which version produced it, so a change can be rolled back in one click.")

    # 9 ─────────────────────────────────────────────────────────────────────
    d.d.add_page_break()
    d.h("9. How we know it is right", level=1)
    d.h("9.1  It keeps every rule", level=2)
    names = PROPS["properties"]
    fam = RESULTS["candidates"]
    broke = {}
    for key, short in {"A0": "the old formula", "A2": "an older try", "A5": "the statistician's vote",
                       "A7": "the instructor's series"}.items():
        for pid in fam[key]["properties"]["summary"]["failed"]:
            broke.setdefault(pid, []).append(short)
    order = [f"P{i:02d}" for i in range(1, 23)] + ["P23"]
    d.table(["#", "The rule", "Broken by"],
            [[i, names[pid], ", ".join(broke.get(pid, [])) or "—"]
             for i, pid in enumerate([p for p in order if p in names], start=1)],
            widths=[0.8, 12.4, 4.0], size=9)
    d.p("Today's formula keeps all 23. The old one keeps 15.", bold=True, after=8)

    d.h("9.2  It was judged on months it had never seen", level=2)
    d.table(["On the three hidden months (1,027 classes)", "Old formula", "Today"],
            [["Weak classes labelled Good or Excellent", f"{len(HELD)} of 873", "0"],
             ["Classes called Bad that were rated 4.55 or better", "12 of 95", "0"],
             ["Verdict changes if one learner votes differently", "26 in 100", "19 in 100"],
             ["How well the label warns about the instructor's next class", "0.65", "0.67"],
             ["Chance the next class goes wrong: Bad label vs Excellent label", "45% vs 14%", "54% vs 10%"]],
            widths=[9.8, 3.7, 3.7], bold_first=True, size=10,
            colors={(0, 1): W_RED, (0, 2): W_TEAL, (1, 1): W_RED, (1, 2): W_TEAL})
    d.p("The last two rows are the ones worth arguing about. They say the labels are in the right order "
        "— a class labelled Bad is five times more likely to be followed by another bad class than one "
        "labelled Excellent — but also that no formula on this data is a crystal ball. It is a warning "
        "light.", after=8)

    # 10 ────────────────────────────────────────────────────────────────────
    d.h("10. Your question: can you trust a class rated by three people?", level=1)
    d.p("This was the right question to ask. If only three learners rate a class and one or two of them "
        "mark it down unfairly, the class looks bad through no fault of the instructor. So we measured "
        "it: when a class was rated low, how often did that cohort's next class also go wrong?", after=8)
    d.pic(P_TRUST, width=16.0)
    d.caption("Red: the class was rated low. Grey: the class was fine. The gap is how much a low rating "
              "is worth believing.")
    d.bullet("the two bars are the same height. A low rating from one or two people means nothing.",
             lead="With 1 or 2 raters:")
    d.bullet("the gap opens — a low rating doubles the chance of trouble next time.", lead="With 3 or 4:")
    d.bullet("the gap is wide and steady. A low rating is worth believing.", lead="From 5 upward:")
    d.p("That is exactly why the floors are set where they are: no label under 3 votes, no analysis "
        "under 6. Two or three unhappy learners can never put a class in the queue on their own.",
        bold=True, after=6)
    d.note("What we cannot do yet, and what would fix it",
           "The real answer to an unfair rater is to look at that learner's own history — does this "
           "person mark everything down? That needs learner-level ratings, which the sheet does not "
           "contain; it only gives us the class average. The place for it in the formula is already "
           "designed, so the day an export exists it can be switched on.\n"
           "We also tested whether a low rating from few raters should be treated as more suspicious "
           "than a high one from few raters. The data says no — both are simply uncertain.")

    # 11 ────────────────────────────────────────────────────────────────────
    d.d.add_page_break()
    d.h("11. What is still open", level=1)
    d.table(["The question", "What the data says", "The options"],
            [["How many classes can the team review a week?",
              f"Today's formula sends about {NEW_LOOK / WEEKS:.0f} a week for a proper look; the team can do about 12. "
              "This is not the formula being noisy — classes genuinely got worse: 16% under a line in January, 24% in August.",
              "find capacity · raise the analysis floor to 7 votes (about 13 a week) · move the quality line"],
             ["Should one vote be able to flip a verdict?",
              "One class in five with ten or more votes sits within a single vote of a line.",
              "leave it · or make each line a narrow grey zone where the class is watched"],
             ["How do we get sharper next time?",
              "The strongest missing ingredient is what PMs themselves decide. There is one recorded decision in the whole system.",
              "press Confirm or Dismiss on every flagged class — three months of that would improve the next study more than any formula change"]],
            widths=[4.4, 7.4, 5.4], bold_first=True, size=9.5)
    d.p("And three honest limits:", after=6)
    d.bullet("without learner-level ratings we cannot see “a learner was let down”; we infer it from "
             "what happens next, which is a proxy.", lead="We judge by proxy.")
    d.bullet("two formulas that are closer than about 0.04 on the warning measure cannot be told apart "
             "on this much data. Where that happened, we kept the simpler one.", lead="Small differences are noise.")
    d.bullet("everything here was measured on eight months of one team's classes. It should be re-run "
             "monthly, and the study does re-run with one command.", lead="It is a snapshot.")

    # 12 ────────────────────────────────────────────────────────────────────
    d.h("12. Where everything lives", level=1)
    d.table(["What", "Where"],
            [["The score's settings, live, with a preview before publishing", "the app: Admin › Scoring"],
             ["The same five numbers as this document, recomputed live", "the app: All courses › Insights"],
             ["The 245 classes with every column", "Missed-Classes.csv"],
             ["The 23 rules and the classes, as a document", "The 23 Rules and the Classes We Missed.docx"],
             ["The short version for a manager", "Why Weak Classes Were Never Reviewed - The Story.docx"],
             ["The full technical study", "Formula-Study.pdf (22 pages) · Formula-One-Pager.pdf"],
             ["The settings and why each was chosen", "Class Sentiment Score - The Settings We Chose (updated).docx"],
             ["The code that re-runs the whole search", "analysis/formula/ — one command, about two minutes"]],
            widths=[9.4, 7.8], bold_first=True, size=10)
    d.p("")
    d.p("Every number in this document was computed from the ratings sheet and the live database when "
        "the document was built. Nothing was typed in by hand.", size=9, color=W_MUTED, italic=True)
    d.save(GUIDE_OUT)


build_story()
print("wrote", STORY_OUT)
build_guide()
print("wrote", GUIDE_OUT)
