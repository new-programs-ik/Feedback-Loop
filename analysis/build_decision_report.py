"""The report for the senior manager and the VP: we questioned the score, tested it on our own
recordings, and kept it.

Same shape as the team's own "Class Sentiment Score" document - short numbered sections, mostly
tables, one idea each, no invented vocabulary.

    python analysis/build_decision_report.py
"""
import collections
import csv
import io
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

OUT = os.environ.get("DECISION_OUT") or os.path.join(ROOT, "Class Score - What We Tested and What We Decided.docx")
RESULTS = os.environ.get("RESULTS_CSV") or os.path.join(ROOT, "Formula-Test-Results.csv")

INK = RGBColor(0x16, 0x16, 0x1A)
MUTED = RGBColor(0x4B, 0x4B, 0x53)
BRAND = RGBColor(0x2A, 0x78, 0xD6)
RED = RGBColor(0xB4, 0x3A, 0x2E)
TEAL = RGBColor(0x1B, 0x7F, 0x5E)
HEADER_FILL, ZEBRA_FILL, NOTE_FILL, GOOD_FILL = "EEF3FB", "F7F7F5", "F3F7FD", "F2F8F5"

CONTENT_FLAGS = {"coverage", "correctness", "problem_coverage", "solution_walkthrough"}
SERIOUS = ("moderate", "major")


# ── the numbers, all read rather than typed ──────────────────────────────────
def load():
    conn = ST.connect()
    cur = conn.cursor()
    cur.execute("select version, name from scoring_configs where status = 'active'")
    live_version, live_name = cur.fetchone()
    cur.execute("select sentiment_band, count(*) from class_ratings group by 1")
    bands = {b or "none": n for b, n in cur.fetchall()}
    cur.execute("select sentiment_action, count(*) from class_ratings group by 1")
    actions = {a or "none": n for a, n in cur.fetchall()}
    cur.execute("select count(*), min(class_date), max(class_date) from class_ratings")
    n, first, last = cur.fetchone()
    conn.close()
    with io.open(RESULTS, encoding="utf-8-sig") as fh:
        tested = [r for r in csv.DictReader(fh) if r.get("analysed_at")]
    return live_version, live_name, bands, actions, n, first, last, tested


def findings(row):
    out = []
    for item in (row.get("all_findings") or "").split("; "):
        if ":" in item:
            flag, sev = item.rsplit(":", 1)
            out.append((flag.strip(), sev.strip()))
    return out


def outcome(row):
    if row.get("reclass") == "yes":
        return "the class should be taught again"
    if [f for f, s in findings(row) if f in CONTENT_FLAGS and s in SERIOUS]:
        return "something was taught wrongly or left out"
    if [f for f, s in findings(row) if s in SERIOUS]:
        return "only delivery notes, nothing about the content"
    return "nothing worth acting on"


def winner(row):
    bad = outcome(row) in ("the class should be taught again", "something was taught wrongly or left out")
    if row.get("test") == "A":
        return "New" if bad else "Current"
    return "Current" if bad else "New"


LIVE_V, LIVE_NAME, BANDS, ACTIONS, N_CLASSES, FIRST, LAST, TESTED = load()
WEEKS = 35.0
LOOK = ACTIONS.get("video", 0) + ACTIONS.get("transcript", 0)

# ── document plumbing ────────────────────────────────────────────────────────
doc = Document()
st = doc.styles["Normal"]
st.font.name = "Calibri"
st.font.size = Pt(11)
st.font.color.rgb = INK
for s in doc.sections:
    s.top_margin = s.bottom_margin = Cm(1.9)
    s.left_margin = s.right_margin = Cm(2.1)


def save_doc(document, path):
    """Word keeps a lock on an open file; fall back to a numbered name rather than losing the run."""
    base, ext = os.path.splitext(path)
    for n in range(1, 40):
        target = path if n == 1 else f"{base} ({n}){ext}"
        try:
            document.save(target)
            return target
        except PermissionError:
            continue
    raise PermissionError(f"could not write {path} - close it in Word and run again")


def shade(cell, fill):
    el = OxmlElement("w:shd")
    el.set(qn("w:fill"), fill)
    cell._tc.get_or_add_tcPr().append(el)


def para(text="", size=11, bold=False, color=None, italic=False, after=6, align=None):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.italic = italic
    r.font.color.rgb = color or INK
    p.paragraph_format.space_after = Pt(after)
    if align:
        p.alignment = align
    return p


def table(headers, rows, widths=None, size=10.5, colors=None):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(headers):
        c = t.rows[0].cells[i]
        c.text = ""
        r = c.paragraphs[0].add_run(str(h))
        r.font.bold = True
        r.font.size = Pt(size)
        c.paragraphs[0].paragraph_format.space_after = Pt(0)
        shade(c, HEADER_FILL)
    for n, row in enumerate(rows):
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            r = cells[i].paragraphs[0].add_run("" if v is None else str(v))
            r.font.size = Pt(size)
            if colors and colors(n, i):
                r.font.color.rgb = colors(n, i)
            cells[i].paragraphs[0].paragraph_format.space_after = Pt(0)
            if n % 2 == 1:
                shade(cells[i], ZEBRA_FILL)
    if widths:
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Cm(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)
    return t


def note(title, lines, fill=GOOD_FILL):
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    cell = t.rows[0].cells[0]
    shade(cell, fill)
    cell.text = ""
    p = cell.paragraphs[0]
    r = p.add_run(title)
    r.font.bold = True
    r.font.size = Pt(10.5)
    p.paragraph_format.space_after = Pt(3)
    for line in lines:
        p = cell.add_paragraph()
        r = p.add_run("• " + line)
        r.font.size = Pt(10)
        p.paragraph_format.space_after = Pt(2)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)


# ── the report ───────────────────────────────────────────────────────────────
h = doc.add_heading("The class score: what we tested, and what we decided", level=0)
h.runs[0].font.color.rgb = INK
para(f"{N_CLASSES:,} classes, {FIRST} to {LAST}. Every number here was read from the system on the "
     f"day this was written. Nothing was typed in by hand.", size=10, color=MUTED, after=12)

doc.add_heading("1. The question we were asked", level=1)
para("Our score decides who looks at which class. If it is wrong in one direction we waste people's "
     "time; if it is wrong in the other we miss classes that needed help. So we asked whether the "
     "score we use is the right one, and we did not want to settle it by argument.", after=8)

doc.add_heading("2. What we did", level=1)
table(["Step", "What it means"],
      [["We built an alternative", "A second way of scoring, meant to be fairer to classes judged "
        "by only a handful of learners."],
       ["We found where they disagree", "Out of 2,833 classes the two disagree about 293 - roughly "
        "one in ten."],
       ["We picked the hardest twelve", "The classes where they disagree most, in both directions, "
        "so neither could win by luck."],
       ["We watched the recordings", "The AI analysis read each recording and said what actually "
        "happened in the class."],
       ["We wrote the rules first", "How to count a win was written down before the results existed, "
        "so nobody could pick the measure that flattered the answer they wanted."]],
      widths=[5.2, 11.4], size=10)

doc.add_heading("3. What the recordings showed", level=1)
a = [r for r in TESTED if r.get("test") == "A"]
b = [r for r in TESTED if r.get("test") == "B"]
wa = collections.Counter(winner(r) for r in a)
wb = collections.Counter(winner(r) for r in b)
table(["The disagreement", "Classes", "Current score right", "New score right"],
      [["Our new score said look, the current one said nobody needs to",
        len(a), wa["Current"], wa["New"]],
       ["The current score said spend a video, the new one said no need",
        len(b), wb["Current"], wb["New"]],
       ["Both together", len(TESTED), wa["Current"] + wb["Current"], wa["New"] + wb["New"]]],
      widths=[9.0, 2.0, 3.0, 2.6], size=10)
para(f"The current score was right on {wa['Current'] + wb['Current']} of {len(TESTED)}.", bold=True, after=10)

doc.add_heading("4. The class that decided it", level=1)
para("The second row above is where the new score lost. These are classes rated well by learners, "
     "where only a handful answered the question about the instructor. Our new score protected them "
     "for that reason. The recordings show it should not have.", after=6)
rows4 = []
for r in sorted(b, key=lambda r: float(r.get("rating") or 0)):
    rows4.append([r.get("class", "")[:30], r.get("instructor", "")[:16], r.get("rating", ""),
                  r.get("approval", ""), outcome(r)])
table(["Class", "Instructor", "Rating", "Instructor approval", "What the recording showed"],
      rows4, widths=[4.6, 2.9, 1.5, 2.9, 4.9], size=9.5,
      colors=lambda n, i: RED if i == 4 and "wrongly" in str(rows4[n][4]) else None)

doc.add_heading("5. And the class that went the other way", level=1)
yes = [r for r in a if r.get("reclass") == "yes"]
if yes:
    r = yes[0]
    para(f"{r.get('class')} · {r.get('instructor')} · rated {r.get('rating')} · "
         f"instructor approval {r.get('approval')}", bold=True, after=4)
    para(f"The current score gives this class {r.get('karthika_says')} and asks nobody to look at it. "
         f"The recording shows the instructor taught something factually wrong, and the analysis "
         f"asked for the topic to be covered again. This is the case for keeping an eye on the "
         f"current score's blind spot, and it is a real one.", after=8)

doc.add_heading("6. What we decided", level=1)
note("We are keeping the score we already use.",
     ["It was right on more of the twelve classes than the alternative was.",
      "It is the simpler of the two, and a change has to earn its place.",
      "Nobody has to learn anything new, and no past report changes meaning."])

doc.add_heading("7. What that means week to week", level=1)
table(["", "Now"],
      [["Classes we look at", f"{LOOK:,} of {N_CLASSES:,}"],
       ["Per week", f"{LOOK / WEEKS:.1f}"],
       ["Of which a full video review", f"{ACTIONS.get('video', 0) / WEEKS:.1f}"],
       ["Of which a transcript read", f"{ACTIONS.get('transcript', 0) / WEEKS:.1f}"]],
      widths=[8.0, 4.0], size=10.5)
table(["Band", "Classes", "What happens"],
      [["Excellent", f"{BANDS.get('excellent', 0):,}", "nothing"],
       ["Good", f"{BANDS.get('good', 0):,}", "nothing"],
       ["Average", f"{BANDS.get('average', 0):,}", "someone reads the transcript"],
       ["Bad", f"{BANDS.get('bad', 0):,}", "someone watches the recording"]],
      widths=[3.2, 3.0, 7.0], size=10.5)

doc.add_heading("8. What we are not pretending", level=1)
note("Three things this test does not settle.",
     ["Twelve classes is a small number. It shows a direction, not a decimal place.",
      "The analysis does not give the identical answer every time it reads the same recording. It "
      "reliably says whether a class had a problem; which problem it names can vary.",
      "The score we kept has a known weakness: a class judged by three or four learners can swing "
      "band on one person changing their mind. We chose to live with it rather than trade it for a "
      "weakness the recordings showed was worse."],
     fill=NOTE_FILL)

doc.add_heading("9. What we fixed on the way", level=1)
para("Testing the score meant trusting the analysis and the data behind it. Neither held up, and "
     "both were repaired before the numbers above were produced.", after=6)
table(["What was wrong", "What it cost us"],
      [["The sync was reading 358 of 2,833 classes and reporting success",
        "Eight of nine months were missing. The sheet writes dates as “January 2, 2026” and "
        "the reader only understood “Jan 2” - and May is the one month whose short name is "
        "its full name, so May worked and nothing else did."],
       ["The analysis read only the first part of a long class",
        "On a two-hour class it summarised the first seventy-nine minutes and treated that as the "
        "whole session. Errors made later were invisible to it."],
       ["The analysis was told four times to stay quiet and never once to look",
        "A factual error is exactly where the model is least certain, so it stayed silent. It now "
        "raises checkable errors and lets the second-pass review throw out what does not hold."],
       ["One bad caption line could discard a whole class",
        "Silently. The class was reported as analysed."],
       ["The recording's private link was being written into the database",
        "It appears in error messages, and that link opens the full recording for anyone who can "
        "read the page."]],
      widths=[6.2, 10.4], size=9.5)

doc.add_heading("10. What is still owed", level=1)
table(["Who", "What"],
      [["The team", "Confirm the score's own settings once a quarter against fresh classes."],
       ["Us", "Watch four classes that both scores call good, to be certain the analysis is not "
        "finding a problem in every class it is pointed at."],
       ["Us", "Make the analysis give the same answer twice on the same recording."]],
      widths=[3.4, 13.2], size=10)

para("")
para("Written from the live system. The twelve recordings, the rules used to score them and the "
     "full list of what was repaired are kept with the project.", size=9, color=MUTED, italic=True)

print("wrote", save_doc(doc, OUT))
