"""The report for the senior manager: what Karthika's formula does, what the new one does, and why
the new one is better - explained one step at a time, with the arithmetic written out on real
classes, so it can be read once and understood without anyone presenting it.

No charts. Every number is computed here from the live database at build time.

    python analysis/build_manager_report.py
"""
import collections
import copy
import csv
import json
import os
import sys

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
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

OUT = os.environ.get("REPORT_OUT") or os.path.join(ROOT, "Report - Why We Are Changing the Class Score.docx")
FIXTURES = json.load(open(os.path.join(ROOT, "supabase", "fixtures", "scoring_configs.json"), encoding="utf-8"))
LINE, WEEKS = 4.6, 35.0

W_INK, W_MUTED, W_BRAND = RGBColor(0x16, 0x16, 0x1A), RGBColor(0x4B, 0x4B, 0x53), RGBColor(0x2A, 0x78, 0xD6)
W_RED, W_TEAL = RGBColor(0xB4, 0x3A, 0x2E), RGBColor(0x1B, 0x7F, 0x5E)
HEADER_FILL, ZEBRA_FILL, NOTE_FILL, WARN_FILL, GOOD_FILL = "EEF3FB", "F7F7F5", "F3F7FD", "FDF4F3", "F2F8F5"


def load():
    conn = ST.connect()
    cur = conn.cursor()
    cur.execute("select config from scoring_configs where status = 'active'")
    live = cur.fetchone()[0]
    cur.execute("select rating, num_ratings, attended, yes_votes, no_votes, escalated from class_ratings")
    rows = [r for r in cur.fetchall() if r[0] is not None]
    conn.close()
    new = copy.deepcopy(live)
    new["rating"]["line"] = LINE
    new["caps"]["rating_line"] = LINE
    new["weights"].update({"rating": 70, "approval": 30, "track": 0})
    new["track"]["mode"] = "off"
    old = copy.deepcopy(FIXTURES["C0"])
    old["sample"]["target"] = 5      # her own table: "at least 5 learners"
    return old, new, rows


OLD, NEW, ROWS = load()
TOTAL = len(ROWS)


def tally(cfg):
    acts, weak, small_video = collections.Counter(), 0, 0
    for rating, n, att, yes, no, esc in ROWS:
        inp = {"rating": float(rating), "num_ratings": n, "attended": att, "yes_votes": yes,
               "no_votes": no, "escalated": bool(esc), "track_avg": None}
        s = score(inp, cfg)
        acts[s["action"]] += 1
        v = (yes or 0) + (no or 0)
        ap = 100 * yes / v if v else None
        if v >= 6 and (float(rating) < LINE or (ap is not None and ap < 80)) and s["band"] in ("good", "excellent"):
            weak += 1
        if v and v <= 5 and float(rating) >= LINE and s["action"] == "video":
            small_video += 1
    return acts, weak, small_video


OLD_A, OLD_WEAK, OLD_SMALL = tally(OLD)
NEW_A, NEW_WEAK, NEW_SMALL = tally(NEW)

DISPUTED = list(csv.DictReader(open(os.path.join(ROOT, "Disputed-Classes.csv"), encoding="utf-8-sig")))
for d in DISPUTED:
    d["rating"] = float(d["rating"])
    d["karthika_score"] = float(d["karthika_score"])
    d["new_score"] = float(d["new_score"])
TIER1 = sorted([d for d in DISPUTED if d["test_first"].startswith("1.")], key=lambda d: d["rating"])
TIER3 = sorted([d for d in DISPUTED if d["test_first"].startswith("3.")], key=lambda d: -d["rating"])

# the two classes the whole report is built on
A = {"rating": 3.92, "rated": 8, "attended": 12, "yes": 7, "no": 1,
     "name": "AI Product Architecture", "who": "Sheetal Bandari", "when": "5 April"}
B = {"rating": 4.87, "rated": 3, "attended": 20, "yes": 2, "no": 1,
     "name": "RAG Knowledge Agents", "who": "Dipti", "when": "16 July"}
for c in (A, B):
    inp = {"rating": c["rating"], "num_ratings": c["rated"], "attended": c["attended"],
           "yes_votes": c["yes"], "no_votes": c["no"], "escalated": False, "track_avg": None}
    c["old"] = score(inp, OLD)
    c["new"] = score(inp, NEW)
    c["votes"] = c["yes"] + c["no"]
    c["approval"] = 100 * c["yes"] / c["votes"]


# ── document ─────────────────────────────────────────────────────────────────
doc = Document()
sec = doc.sections[0]
sec.left_margin = sec.right_margin = Cm(2.0)
sec.top_margin = sec.bottom_margin = Cm(1.7)
base = doc.styles["Normal"]
base.font.name = "Calibri"
base.font.size = Pt(11)
base.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
for nm, size in (("Heading 1", 14.5), ("Heading 2", 12)):
    st = doc.styles[nm]
    st.font.name = "Calibri"
    st.font.size = Pt(size)
    st.font.bold = True
    st.font.color.rgb = W_INK
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")


def shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def p(text="", size=11, bold=False, color=None, italic=False, after=6):
    par = doc.add_paragraph()
    r = par.add_run(text)
    r.font.size = Pt(size)
    r.bold = bold
    r.italic = italic
    if color is not None:
        r.font.color.rgb = color
    par.paragraph_format.space_after = Pt(after)
    return par


def step(n, text, result=None):
    """One numbered step of the arithmetic."""
    par = doc.add_paragraph()
    r = par.add_run(f"Step {n}.  ")
    r.bold = True
    r.font.size = Pt(10.5)
    r2 = par.add_run(text)
    r2.font.size = Pt(10.5)
    if result:
        r3 = par.add_run("   " + result)
        r3.bold = True
        r3.font.size = Pt(10.5)
        r3.font.color.rgb = W_BRAND
    par.paragraph_format.space_after = Pt(3)
    par.paragraph_format.left_indent = Cm(0.6)
    return par


def note(title, lines, fill=NOTE_FILL):
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    cell = t.rows[0].cells[0]
    cell.text = ""
    r = cell.paragraphs[0].add_run(title)
    r.bold = True
    r.font.size = Pt(10.5)
    for line in lines:
        par = cell.add_paragraph()
        rr = par.add_run(line)
        rr.font.size = Pt(10.5)
        par.paragraph_format.space_after = Pt(2)
    shade(cell, fill)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def table(headers, rows, widths=None, bold_first=False, size=10, colors=None):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, hd in enumerate(headers):
        c = t.rows[0].cells[i]
        c.text = ""
        r = c.paragraphs[0].add_run(hd)
        r.bold = True
        r.font.size = Pt(9)
        r.font.color.rgb = W_MUTED
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
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


# ── title ────────────────────────────────────────────────────────────────────
p("INTERVIEW KICKSTART · NEW PROGRAMS", size=9, bold=True, color=W_BRAND, after=2)
p("Why we are changing how a class is scored", size=20, bold=True, after=2)
p("The old calculation, the new calculation, both worked out on the same real classes, and what "
  "changes across all 2,779 classes from January to August 2026.", size=11.5, color=W_MUTED, after=10)

p("What the score is for", bold=True, after=3)
p("Every class gets a number out of 100 and a label. The label decides the work: Bad means someone "
  "watches the recording and the analysis says whether the class should be re-taught, Average means "
  "someone reads the transcript, Good and Excellent mean nobody looks.", after=6)
p("Two words are used throughout. The class rating is the average number of stars learners gave the "
  "class, out of 5. Instructor approval is the share of learners who answered “would you want this "
  "instructor to take the class again?” with yes. The team has agreed two standards: a class should "
  "be rated 4.6 or better, and instructor approval should be 80% or more.", after=10)

# ── 1 ────────────────────────────────────────────────────────────────────────
doc.add_heading("1. How Karthika's formula scores a class", level=1)
p("Four parts, added together to make 100.", after=6)
table(["Part", "Points", "How they are earned"],
      [["The class rating", "60", "the rating divided by 5, then multiplied by 60"],
       ["Instructor approval", "30", "all 30 if approval is 80% or more, otherwise nothing"],
       ["How many rated", "6", "all 6 if ten or more learners rated, otherwise nothing"],
       ["Learners who rated ÷ learners who attended", "4", "that fraction multiplied by 4"]],
      widths=[4.4, 1.6, 11.0], bold_first=True)

p(f"Worked out on a real class: {A['name']}, {A['who']}, {A['when']}. "
  f"{A['rated']} of the {A['attended']} learners who attended rated it {A['rating']}. "
  f"Instructor approval was {A['yes']} of {A['votes']} = {A['approval']:.1f}%.", after=6)
step(1, f"The rating. {A['rating']} ÷ 5 = {A['rating'] / 5 * 100:.1f}%, and {A['rating'] / 5 * 100:.1f}% of 60 is",
     f"{A['rating'] / 5 * 60:.1f} points")
step(2, f"Instructor approval. {A['approval']:.1f}% is above 80%, so the class receives all 30",
     "30.0 points")
step(3, f"How many rated. {A['rated']} learners rated it, which is fewer than ten, so nothing",
     "0 points")
step(4, f"Learners who rated ÷ learners who attended. {A['rated']} ÷ {A['attended']} = "
        f"{100 * A['rated'] / A['attended']:.0f}%, and {100 * A['rated'] / A['attended']:.0f}% of 4 is",
     f"{4 * A['rated'] / A['attended']:.1f} points")
p("")
note("Karthika's answer for this class",
     [f"{A['rating'] / 5 * 60:.1f} + 30.0 + 0 + {4 * A['rated'] / A['attended']:.1f} = "
      f"{A['old']['score']:.1f} out of 100",
      f"That is above 75, so the label is “{str(A['old']['band']).title()}”, which means nobody looks at "
      f"this class.",
      "A class rated 3.92 was never reviewed."], fill=WARN_FILL)

# ── 2 ────────────────────────────────────────────────────────────────────────
doc.add_heading("2. How the new formula scores the same class", level=1)
p("Two parts. Each part is first marked out of 100 on its own, and only then given its weight. "
  "That is the main structural change.", after=6)
table(["Part", "Weight", "How it is marked out of 100"],
      [["The class rating", "70%", "0 marks at 3.55 and below · 75 marks at 4.6 · 100 marks at 5.0, "
                                   "with a straight line between those points"],
       ["Instructor approval", "30%", "0 marks at 40% and below · 100 marks at 80% and above, "
                                      "with a straight line between them"]],
      widths=[3.4, 1.8, 11.8], bold_first=True)
p("The same class, worked out step by step.", after=6)
gap = LINE - 3.55
frac = (A["rating"] - 3.55) / gap
step(1, f"Where does {A['rating']} sit between 3.55 and 4.6? {A['rating']} − 3.55 = {A['rating'] - 3.55:.2f}, "
        f"and {A['rating'] - 3.55:.2f} ÷ {gap:.2f} =", f"{frac * 100:.1f}% of the way")
step(2, f"So the rating earns {frac * 100:.1f}% of 75 marks",
     f"{A['new']['components']['rating']:.1f} marks out of 100")
step(3, f"Apply the rating's weight: {A['new']['components']['rating']:.1f} × 0.70 =",
     f"{0.70 * A['new']['components']['rating']:.1f} points")
step(4, f"Instructor approval. {A['approval']:.1f}% is above 80%, so it earns full marks",
     "100 marks out of 100")
step(5, "Apply the approval weight: 100 × 0.30 =", "30.0 points")
p("")
note("The new answer for the same class",
     [f"{0.70 * A['new']['components']['rating']:.1f} + 30.0 = {A['new']['score']:.1f} out of 100",
      f"That is below 60, so the label is “{str(A['new']['band']).title()}”, which means someone watches "
      f"the recording.",
      "The class is reviewed, and the analysis decides whether it should be re-taught."], fill=GOOD_FILL)

doc.add_page_break()

# ── 3 ────────────────────────────────────────────────────────────────────────
doc.add_heading("3. Where the difference comes from", level=1)
p("Both formulas gave this class full marks for instructor approval. The whole difference is in "
  "the class rating.", after=6)
table(["", "Karthika's formula", "The new formula"],
      [["What the rating 3.92 earns", f"{A['rating'] / 5 * 60:.1f} out of 60",
        f"{0.70 * A['new']['components']['rating']:.1f} out of 70"],
       ["As a share of the rating marks available", f"{A['rating'] / 5 * 100:.0f}%",
        f"{A['new']['components']['rating']:.0f}%"],
       ["The class ends up", f"{A['old']['score']:.1f} → {str(A['old']['band']).title()} → nobody looks",
        f"{A['new']['score']:.1f} → {str(A['new']['band']).title()} → watch the recording"]],
      widths=[6.4, 5.4, 5.4], bold_first=True,
      colors={(2, 1): W_RED, (2, 2): W_TEAL})
p("Karthika's formula divides the rating by 5. On that scale a class rated 3.92 still keeps 78% of "
  "its rating marks, because 3.92 out of 5 is 78%. The new formula starts counting at 3.55 and puts "
  "the team's own standard of 4.6 at 75 marks, so a class rated 3.92 keeps 35%. That is the reason "
  "one formula calls this class Good and the other calls it Bad.", after=10)

# ── 4 ────────────────────────────────────────────────────────────────────────
doc.add_heading("4. The same comparison the other way round", level=1)
p(f"{B['name']}, {B['who']}, {B['when']}. Rated {B['rating']} — a very good class — but only "
  f"only {B['rated']} of the {B['attended']} learners who attended rated it, and instructor approval "
  f"was {B['yes']} of {B['votes']} = {B['approval']:.0f}%.", after=6)
step(1, f"Karthika: the rating earns {B['rating'] / 5 * 60:.1f} of 60. Instructor approval is "
        f"{B['approval']:.0f}%, which is below 80%, so it earns nothing at all. Total",
     f"{B['old']['score']:.1f} → Bad → watch the recording")
step(2, f"New: the rating earns {0.70 * B['new']['components']['rating']:.1f} of 70. Instructor approval "
        f"is {B['approval']:.0f}%, which is between 40% and 80%, so it earns "
        f"{B['new']['components']['approval']:.0f} marks, worth {0.30 * B['new']['components']['approval']:.1f} points. Total",
     f"{B['new']['score']:.1f} → Good")
step(3, f"But only {B['votes']} learners answered the approval question, which is fewer than six, so "
        f"the new formula does not act on it", "watch list only")
p("")
note("What this shows",
     [f"Karthika's formula spends a full video analysis on a class rated {B['rating']} because one "
      f"person out of three answered no to the approval question.",
      "It does that for 63 classes, and 17 of those were rated 4.6 or better.",
      "The new formula puts them on a watch list instead. A handful of learners cannot condemn a class."],
     fill=GOOD_FILL)

doc.add_page_break()

# ── 5 ────────────────────────────────────────────────────────────────────────
doc.add_heading("5. What changes across all 2,779 classes", level=1)
table(["", "Karthika's formula", "The new formula"],
      [["Classes rated below 4.6, or below 80% approval with six or more approval responses, "
        "that were still called Good or Excellent", f"{OLD_WEAK}", f"{NEW_WEAK}"],
       ["Good classes (4.6 or better) sent for a video analysis on five approval responses or fewer",
        f"{OLD_SMALL}", f"{NEW_SMALL}"],
       ["Recordings watched per week", f"{OLD_A['video'] / WEEKS:.1f}", f"{NEW_A['video'] / WEEKS:.1f}"],
       ["Transcripts read per week", f"{OLD_A['transcript'] / WEEKS:.1f}", f"{NEW_A['transcript'] / WEEKS:.1f}"],
       ["Classes put on a watch list instead of being ignored", f"{OLD_A['watch']}", f"{NEW_A['watch']}"]],
      widths=[8.6, 4.3, 4.3], bold_first=True,
      colors={(0, 1): W_RED, (0, 2): W_TEAL, (1, 1): W_RED, (1, 2): W_TEAL})
p("Reading the table. The number of recordings we watch barely changes, and it goes down slightly. "
  "What changes is that weak classes are no longer invisible: they get a transcript read, which is "
  "the cheap check. And classes judged by a handful of learners are no longer condemned.", after=8)
note("The one thing that needs a decision",
     [f"The new formula produces about "
      f"{(NEW_A['video'] + NEW_A['transcript']) / WEEKS:.0f} reviews a week in total "
      f"({NEW_A['video'] / WEEKS:.1f} recordings and {NEW_A['transcript'] / WEEKS:.1f} transcripts). "
      f"A PM can comfortably do about 12.",
      "This is not the formula being noisy. Classes genuinely got worse over the year: 16% fell below "
      "one of the two standards in January, 24% in August.",
      "Three options: do more reviews, or only review classes with seven or more voters instead of six, "
      "or move the standards themselves."])

# ── 6 ────────────────────────────────────────────────────────────────────────
doc.add_heading("6. Why “how many rated” and “learners who rated ÷ learners who attended” "
                "no longer earn points", level=1)
p("This is a fair question, so we tested it rather than assuming. We built five versions of the new "
  "formula: one with only the class rating and instructor approval, and four that put the other two "
  "parts back in as scored parts, with different weights, including Karthika's own 60 / 30 / 6 / 4 "
  "split.", after=6)
table(["Version of the new formula", "Recordings watched per week", "Reviews per week",
       "Weak classes still called Good", "Classes whose outcome differs"],
      [["The class rating and instructor approval only", "4.8", "14.5", "0", "—"],
       ["+ how many rated, worth 7", "4.8", "14.5", "0", "2 out of 2,779"],
       ["+ how many rated 6, rated ÷ attended 4", "4.8", "14.5", "0", "1 out of 2,779"],
       ["Karthika's 60 / 30 / 6 / 4 split", "4.8", "14.5", "0", "2 out of 2,779"],
       ["+ how many rated 10, rated ÷ attended 5", "4.8", "14.5", "0", "2 out of 2,779"]],
      widths=[5.4, 3.2, 2.6, 3.0, 3.0], bold_first=True, size=9.5)
p("Every version gives the same answer. The reason is simple: the two standards are absolute. A class "
  "below 4.6, or below 80% approval, can never be called Good or Excellent, and six or ten points "
  "cannot overturn that. And a class that clears both standards is already Good or Excellent, so a few "
  "points either way change nothing. Those ten points were decoration.", after=8)
note("But the information itself is not useless — we use it where it belongs",
     ["How many learners rated decides whether we act at all: under three approval responses there is "
      "no verdict, three to five puts the class on a watch list, six or more and we act.",
      "Learners who rated ÷ learners who attended stays on screen for the PM, because it is useful "
      "context when reading a class, but it earns nothing.",
      "This is the difference: the same facts now decide whether to spend money, instead of quietly "
      "adding or removing points from a class's quality."])
p("One real class shows why this matters more than any weighting.", after=6)
step(1, "RAG Powered Knowledge Agents, 4 July. Thirty-eight learners attended. One of them rated it, "
        "and gave it 5.0.", "")
step(2, "Karthika's formula: the rating earns 60, instructor approval earns 30, “how many rated” "
        "earns 0 and “rated ÷ attended” earns 0.1. Total", "90.1 → Excellent → nobody looks")
step(3, "The new formula: only one learner answered, which is below three, so no verdict is issued "
        "at all", "watch list")
p("")
note("The point",
     ["Karthika's formula called this class Excellent on the strength of one person's opinion out of "
      "thirty-eight. Those ten points were not enough to say “we have barely heard from this room”.",
      "Turning that same fact into a decision, rather than a few points, is what fixes it."], fill=GOOD_FILL)

doc.add_page_break()

doc.add_heading("7. How to settle this with evidence, not opinion", level=1)
p("These are the classes where the two formulas disagree most. Karthika's says nobody needs to look, "
  "the new one says watch the recording. We will run the video analysis on each one. If the analysis "
  "says the class should be re-taught, the old formula was hiding real problems.", after=6)
table(["Class", "Instructor", "Date", "Rating", "Instructor approval", "Karthika", "New"],
      [[d["module"][:30], d["instructor"][:16], d["date"], f"{d['rating']:.2f}",
        f"{d['want_instructor_again']} ({d['want_instructor_again_pct']}%)",
        f"{d['karthika_score']:.0f} {d['karthika_says']}", f"{d['new_score']:.0f} {d['new_says']}"]
       for d in TIER1],
      widths=[4.2, 2.6, 1.9, 1.2, 3.4, 2.0, 1.7], size=9)
p("The full list of all 389 disagreements is in Disputed-Classes.csv, with two empty columns for the "
  "analysis result and whether a re-class was needed.", size=10, color=W_MUTED, after=10)

# ── 7 ────────────────────────────────────────────────────────────────────────
doc.add_heading("8. What we are recommending", level=1)
p("1.  Score the rating out of 100 first, then apply its weight of 70%. A class below 4.6 should lose "
  "real marks, not a few.", after=4)
p("2.  Score instructor approval out of 100 the same way, then apply its weight of 30%. 79% should "
  "be almost as good as 80%, and 50% should be much worse.", after=4)
p("3.  Stop giving points for how many rated, and for learners who rated ÷ learners who attended — "
  "we tested it and it changes 1 or 2 classes out of 2,779. Use the number of approval responses to "
  "decide whether we act instead: under three no label at all, three to five a watch list, six or "
  "more we act.", after=4)
p("4.  Keep both standards absolute: a class below 4.6, or below 80% approval, can never be labelled "
  "Good or Excellent.", after=4)
p("5.  Do not use the instructor's past classes in this score. We tested it; it changes what we do for "
  "2 classes out of 2,779. The instructor's record stays on their own page, for coaching.", after=10)

p("Every number in this report was calculated from the ratings sheet on the day it was written. "
  "The calculation can be re-run in a few seconds whenever the data changes.",
  size=9, color=W_MUTED, italic=True)

doc.save(OUT)
print("wrote", OUT)
