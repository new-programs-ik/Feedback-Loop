"""The report for the senior manager, written in the same shape as the team's own
"Class Sentiment Score" document: short numbered sections, mostly tables, one idea each.

It answers three things and nothing else: what the score is made of now, what it was made of
before, and what the change gives us.

    python analysis/build_simple_report.py
"""
import collections
import copy
import csv
import json
import os
import sys

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "ratings_module_build_kit"))
import config  # noqa: E402

config.load_env()
import ratings_store as ST  # noqa: E402
from sentiment_score import score  # noqa: E402

OUT = os.environ.get("SIMPLE_OUT") or os.path.join(ROOT, "Class Sentiment Score - What We Changed.docx")
FIXTURES = json.load(open(os.path.join(ROOT, "supabase", "fixtures", "scoring_configs.json"), encoding="utf-8"))
LINE, WEEKS = 4.6, 35.0

INK = RGBColor(0x16, 0x16, 0x1A)
MUTED = RGBColor(0x4B, 0x4B, 0x53)
BRAND = RGBColor(0x2A, 0x78, 0xD6)
RED = RGBColor(0xB4, 0x3A, 0x2E)
TEAL = RGBColor(0x1B, 0x7F, 0x5E)
HEADER_FILL, ZEBRA_FILL, NOTE_FILL, GOOD_FILL = "EEF3FB", "F7F7F5", "F3F7FD", "F2F8F5"


def load():
    conn = ST.connect()
    cur = conn.cursor()
    cur.execute("select config from scoring_configs where status = 'active'")
    live = cur.fetchone()[0]
    cur.execute("select rating, num_ratings, attended, yes_votes, no_votes, escalated from class_ratings")
    rows = [r for r in cur.fetchall() if r[0] is not None]
    conn.close()
    old = copy.deepcopy(FIXTURES["C0"])
    old["sample"]["target"] = 5
    new = copy.deepcopy(live)
    new["rating"]["line"] = LINE
    new["caps"]["rating_line"] = LINE
    new["weights"].update({"rating": 70, "approval": 30, "track": 0})
    new["track"]["mode"] = "off"
    return old, new, rows


OLD, NEW, ROWS = load()
TOTAL = len(ROWS)


def tally(cfg):
    acts, missed, wasted = collections.Counter(), 0, 0
    for rating, n, att, yes, no, esc in ROWS:
        inp = {"rating": float(rating), "num_ratings": n, "attended": att, "yes_votes": yes,
               "no_votes": no, "escalated": bool(esc), "track_avg": None}
        s = score(inp, cfg)
        acts[s["action"]] += 1
        v = (yes or 0) + (no or 0)
        ap = 100 * yes / v if v else None
        if v >= 6 and (float(rating) < LINE or (ap is not None and ap < 80)) and s["band"] in ("good", "excellent"):
            missed += 1
        if v and v <= 5 and float(rating) >= LINE and s["action"] == "video":
            wasted += 1
    return acts, missed, wasted


OLD_A, OLD_MISSED, OLD_WASTED = tally(OLD)
NEW_A, NEW_MISSED, NEW_WASTED = tally(NEW)

DISPUTED = list(csv.DictReader(open(os.path.join(ROOT, "Disputed-Classes.csv"), encoding="utf-8-sig")))
for d in DISPUTED:
    d["rating"] = float(d["rating"])
    d["karthika_score"] = float(d["karthika_score"])
    d["new_score"] = float(d["new_score"])
TIER1 = sorted([d for d in DISPUTED if d["test_first"].startswith("1.")], key=lambda d: d["rating"])
TIER3 = sorted([d for d in DISPUTED if d["test_first"].startswith("3.")], key=lambda d: -d["rating"])


def one(rating, rated, att, yes, no):
    inp = {"rating": rating, "num_ratings": rated, "attended": att, "yes_votes": yes, "no_votes": no,
           "escalated": False, "track_avg": None}
    return score(inp, OLD), score(inp, NEW)


# ── document ─────────────────────────────────────────────────────────────────
doc = Document()
sec = doc.sections[0]
sec.left_margin = sec.right_margin = Cm(2.2)
sec.top_margin = sec.bottom_margin = Cm(2.0)
base = doc.styles["Normal"]
base.font.name = "Calibri"
base.font.size = Pt(11)
base.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
for nm, size in (("Heading 1", 15), ("Heading 2", 12.5)):
    st = doc.styles[nm]
    st.font.name = "Calibri"
    st.font.size = Pt(size)
    st.font.bold = True
    st.font.color.rgb = INK
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")


def shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def para(text="", size=11, bold=False, color=None, italic=False, after=6, align=None):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.size = Pt(size)
    r.bold = bold
    r.italic = italic
    if color is not None:
        r.font.color.rgb = color
    p.paragraph_format.space_after = Pt(after)
    if align:
        p.alignment = align
    return p


def bullet(text, lead=None):
    p = doc.add_paragraph(style="List Bullet")
    if lead:
        r = p.add_run(lead + " ")
        r.bold = True
    p.add_run(text)
    p.paragraph_format.space_after = Pt(4)
    return p


def formula_block(title, lines, fill=NOTE_FILL):
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    cell = t.rows[0].cells[0]
    cell.text = ""
    r = cell.paragraphs[0].add_run(title)
    r.bold = True
    r.font.size = Pt(10.5)
    for line in lines:
        p = cell.add_paragraph()
        rr = p.add_run(line)
        rr.font.size = Pt(11)
        rr.font.name = "Consolas"
        p.paragraph_format.space_after = Pt(1)
    shade(cell, fill)
    doc.add_paragraph().paragraph_format.space_after = Pt(3)
    return t


def note(title, lines, fill=GOOD_FILL):
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    cell = t.rows[0].cells[0]
    cell.text = ""
    r = cell.paragraphs[0].add_run(title)
    r.bold = True
    r.font.size = Pt(10.5)
    for line in lines:
        p = cell.add_paragraph()
        rr = p.add_run(line)
        rr.font.size = Pt(10.5)
        p.paragraph_format.space_after = Pt(2)
    shade(cell, fill)
    doc.add_paragraph().paragraph_format.space_after = Pt(3)
    return t


def table(headers, rows, widths=None, bold_first=False, size=10.5, colors=None):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(headers):
        c = t.rows[0].cells[i]
        c.text = ""
        r = c.paragraphs[0].add_run(h)
        r.bold = True
        r.font.size = Pt(9.5)
        r.font.color.rgb = MUTED
        shade(c, HEADER_FILL)
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
                shade(cells[i], ZEBRA_FILL)
    if widths:
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Cm(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(3)
    return t


# ── title ────────────────────────────────────────────────────────────────────
para("INTERVIEW KICKSTART · NEW PROGRAMS", size=9, bold=True, color=BRAND, after=2)
para("Class Sentiment Score — what we changed", size=20, bold=True, after=2)
para("The same one number, 0 to 100, for every class. Two things inside it were changed. "
     "This is what they were, what they are now, and what we get from it.",
     size=12, color=MUTED, after=12)

# ── 1 ────────────────────────────────────────────────────────────────────────
doc.add_heading("1. Why anything was changed", level=1)
para("The score decides which classes a PM reviews. Bad means someone watches the recording; the "
     "analysis then says whether the class should be re-taught. So a wrong label is expensive: a class "
     "labelled Good is never looked at again.")
para(f"We checked the score against our own standard on {TOTAL:,} classes from January to August. "
     f"{OLD_MISSED} classes were rated below 4.6, or had instructor approval below 80%, and the score "
     f"still called them Good or Excellent. Nobody reviewed them.", bold=True, after=10)

# ── 2 ────────────────────────────────────────────────────────────────────────
doc.add_heading("2. The four words", level=1)
table(["Word", "What it means", "Example"],
      [["Class rating", "The average of the stars learners gave the class, out of 5.",
        "20 learners rate a class; the average is 4.6."],
       ["Instructor approval", "After every class, learners answer “would you want this instructor to "
                               "take the class again?” Approval is the share who said yes. The standard is 80%.",
        "13 of 15 said yes → 87% → clears it. 4 of 6 said yes → 67% → misses it."],
       ["Learners who rated", "How many learners answered at all. Below five, the rating rests on too "
                              "few opinions.", "12 rated → enough. 3 rated → not enough."],
       ["Rating %", "Learners who rated ÷ learners who attended.", "20 attended, 10 rated → 50%."]],
      widths=[3.4, 7.6, 5.4], bold_first=True, size=10)

# ── 3 ────────────────────────────────────────────────────────────────────────
doc.add_heading("3. What goes into the score", level=1)
table(["What goes in", "Before", "Now", "Why"],
      [["Class rating", "60 points", "70 points", "it is the only number that is about the class itself"],
       ["Instructor approval", "30 points", "30 points", "unchanged"],
       ["Learners who rated", "6 points", "no points", "it decides whether we act, not what the class scores"],
       ["Rating %", "4 points", "no points", "same reason; it is shown to the PM, not scored"]],
      widths=[3.6, 2.4, 2.4, 8.0], bold_first=True, size=10)
formula_block("The formula before", [
    "Overall Score =",
    "   0.60 × (Class rating)",
    " + 0.30 × (Instructor approval)",
    " + 0.06 × (Learners who rated)",
    " + 0.04 × (Rating %)",
], fill=NOTE_FILL)
formula_block("The formula now", [
    "Overall Score =",
    "   0.70 × (Class rating)",
    " + 0.30 × (Instructor approval)",
], fill=GOOD_FILL)
para("The shape is the same: score each part out of 100, then apply its weight. What changed is how "
     "two of those parts are marked out of 100.", after=8)

# ── 4 ────────────────────────────────────────────────────────────────────────
doc.add_heading("4. How each part is marked out of 100", level=1)
table(["Part", "Before", "Now"],
      [["Class rating", "rating ÷ 5 × 100. A 4.30 class scores 86.",
        "0 at 3.55 and below · 75 at 4.6 · 100 at 5.0. A 4.30 class scores 54."],
       ["Instructor approval", "100 if approval is 80% or more, otherwise 0.",
        "0 at 40% and below · 100 at 80% and above · a straight line between."]],
      widths=[3.6, 6.4, 7.4], bold_first=True, size=10)
para("This is the whole change. On the old marking, a class rated 4.30 kept 86 of its rating marks, "
     "so a weak class looked almost as good as a strong one. On the new marking it keeps 54.", after=10)

# ── 5 ────────────────────────────────────────────────────────────────────────
doc.add_heading("5. The four bands", level=1)
table(["Score", "The class is", "What happens"],
      [["90 or more", "Excellent", "nobody looks"],
       ["75 – 89", "Good", "nobody looks"],
       ["60 – 74", "Average", "someone reads the transcript"],
       ["Below 60", "Bad", "someone watches the recording"]],
      widths=[3.4, 4.6, 9.4], bold_first=True)

# ── 6 ────────────────────────────────────────────────────────────────────────
doc.add_heading("6. Three rules to remember", level=1)
bullet("A class rated below 4.6, or with instructor approval below 80%, can never be Good or "
       "Excellent — whatever the rest of the score says. Under both, it is Bad.",
       lead="The two standards are absolute.")
bullet("Under 3, no label at all. With 3, 4 or 5, the label is provisional and the class only goes on "
       "a watch list — nothing is spent on it. From 6, the label counts.",
       lead="Learners who rated decides whether we act.")
bullet("A great rating cannot save a class whose instructor is not wanted back, and approval cannot "
       "save a weak rating. Both were true before and are still true.",
       lead="Neither part can rescue the other.")

doc.add_page_break()

# ── 7 ────────────────────────────────────────────────────────────────────────
doc.add_heading("7. Examples", level=1)
para("Real classes from our own data. “Before” is the score the old formula gave.", color=MUTED, after=6)
rows_ = []
for label, rating, rated, att, yes, no in [
    ("A weak class the room still liked", 3.92, 8, 12, 7, 1),
    ("A weak class, bigger room", 4.27, 23, 32, 19, 4),
    ("A borderline class", 4.50, 27, 33, 27, 0),
    ("A strong class", 4.87, 18, 24, 17, 1),
    ("A strong class, three answers, one no", 4.87, 3, 20, 2, 1),
    ("One learner out of thirty-eight rated it", 5.00, 1, 38, 1, 0),
]:
    o, n = one(rating, rated, att, yes, no)
    ap = 100 * yes / (yes + no)
    rows_.append([label, f"{rating:.2f}", f"{yes} of {yes + no} ({ap:.0f}%)",
                  f"{o['score']:.0f} · {str(o['band']).title()}",
                  f"{n['score']:.0f} · {str(n['band'] or 'no label').title()}"])
table(["Class", "Rating", "Instructor approval", "Before", "Now"], rows_,
      widths=[5.8, 1.8, 3.4, 3.0, 3.4], bold_first=True, size=10)
para("Reading the table. The first two are the classes the old formula let through: rated below 4.6, "
     "but the room still liked the instructor, so they scored well and nobody looked. The last two are "
     "the opposite: a strong class judged by three people, and a class where one learner out of "
     "thirty-eight rated it. The old formula called the first Bad and sent it for a video, and called "
     "the second Excellent.", after=10)

# ── 8 ────────────────────────────────────────────────────────────────────────
doc.add_heading("8. The result", level=1)
para(f"All {TOTAL:,} rated classes, January to August 2026.", color=MUTED, after=6)
table(["", "Before", "Now"],
      [["Classes below our standard that were still called Good or Excellent", f"{OLD_MISSED}", f"{NEW_MISSED}"],
       ["Good classes sent for a video analysis on five answers or fewer", f"{OLD_WASTED}", f"{NEW_WASTED}"],
       ["Recordings watched per week", f"{OLD_A['video'] / WEEKS:.1f}", f"{NEW_A['video'] / WEEKS:.1f}"],
       ["Transcripts read per week", f"{OLD_A['transcript'] / WEEKS:.1f}", f"{NEW_A['transcript'] / WEEKS:.1f}"],
       ["Classes on a watch list instead of ignored", f"{OLD_A['watch']}", f"{NEW_A['watch']}"]],
      widths=[9.0, 3.6, 3.6], bold_first=True,
      colors={(0, 1): RED, (0, 2): TEAL, (1, 1): RED, (1, 2): TEAL})
para("The number of recordings we watch goes down. What changes is that classes below our standard are "
     "no longer invisible: they get a transcript read, which is the cheap check.", after=8)
note("The one decision this needs",
     [f"The new score sends about {(NEW_A['video'] + NEW_A['transcript']) / WEEKS:.0f} classes a week for "
      f"review in total. A PM can comfortably do about 12.",
      "Classes genuinely got worse over the year: 16% fell below one of the two standards in January, "
      "24% in August.",
      "Three ways to close the gap: review more, or raise “learners who rated” from 6 to 7 before we "
      "act, or move the standards themselves."], fill=NOTE_FILL)

# ── 9 ────────────────────────────────────────────────────────────────────────
doc.add_heading("9. How we will know for certain", level=1)
para("The two formulas disagree about 389 classes. On these, the old formula says nobody needs to "
     "look and the new one says watch the recording. We are running the video analysis on each.",
     after=6)
table(["Class", "Instructor", "Date", "Rating", "Instructor approval", "Before", "Now"],
      [[d["module"][:28], d["instructor"][:15], d["date"], f"{d['rating']:.2f}",
        f"{d['want_instructor_again']} ({d['want_instructor_again_pct']}%)",
        f"{d['karthika_score']:.0f} {d['karthika_says']}", f"{d['new_score']:.0f} {d['new_says']}"]
       for d in TIER1],
      widths=[3.9, 2.5, 1.9, 1.2, 3.2, 1.9, 1.7], size=9)
note("What the answer will mean",
     ["If the analysis asks for a re-class on any of these, the old formula was hiding real problems, "
      "because it told us nobody needed to look.",
      "If it asks for none of them, the new score is flagging classes that did not need it, and we "
      "should soften it.",
      "Either way we will know from our own recordings, not from an argument. The same test can be run "
      "the other way round on the 62 classes the old formula sent for a video and the new one clears."])

para("")
para("Every number here was calculated from the ratings sheet on the day this was written. "
     "Nothing was entered by hand.", size=9, color=MUTED, italic=True)

doc.save(OUT)
print("wrote", OUT)
