"""Build "Class Sentiment Score - The Settings We Chose.docx": every setting of the live scoring
version, the value, and the reason, in plain words - the document a PM hands to a VP who asks
"what exactly did you fix, and why?". Numbers come from analysis/out/recommended_config.json (the
settings) and analysis/out/scorecard.json + scoring_results.json (the study) when present; the
study figures quoted in the text are the ones printed in Sentiment-Score-One-Pager.pdf.

    python analysis/build_scoring_settings_doc.py
"""
import json
import os

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.environ.get("SETTINGS_DOC_OUT") or os.path.join(ROOT, "Class Sentiment Score - The Settings We Chose.docx")
CFG_PATH = os.path.join(HERE, "out", "recommended_config.json")

INK = RGBColor(0x16, 0x16, 0x1A)
MUTED = RGBColor(0x4B, 0x4B, 0x53)
HEADER_FILL = "EEF3FB"
ZEBRA_FILL = "F7F7F5"

doc = Document()
sec = doc.sections[0]
sec.left_margin = sec.right_margin = Cm(2.2)
sec.top_margin = sec.bottom_margin = Cm(2.0)
base = doc.styles["Normal"]
base.font.name = "Calibri"
base.font.size = Pt(11)
base.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
for name, size in (("Heading 1", 15), ("Heading 2", 12.5)):
    st = doc.styles[name]
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


def bullet(text, bold_lead=None):
    p = doc.add_paragraph(style="List Bullet")
    if bold_lead:
        r = p.add_run(bold_lead + " ")
        r.bold = True
    p.add_run(text)
    p.paragraph_format.space_after = Pt(4)
    return p


def table(headers, rows, widths=None, bold_first_col=False):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = t.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = ""
        r = hdr[i].paragraphs[0].add_run(h)
        r.bold = True
        r.font.size = Pt(10)
        r.font.color.rgb = MUTED
        shade(hdr[i], HEADER_FILL)
    for ri, row in enumerate(rows):
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            r = cells[i].paragraphs[0].add_run(str(v))
            r.font.size = Pt(10.5)
            if bold_first_col and i == 0:
                r.bold = True
            if ri % 2 == 1:
                shade(cells[i], ZEBRA_FILL)
    if widths:
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Cm(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


cfg = json.load(open(CFG_PATH, encoding="utf-8")) if os.path.isfile(CFG_PATH) else {}
rating = cfg.get("rating", {"mode": "knee", "floor": 3.55, "line": 4.55, "line_value": 75, "scale": 5})
approval = cfg.get("approval", {"mode": "graded", "bar": 80, "floor": 40})
track = cfg.get("track", {"mode": "on", "floor": 4.05, "line": 4.55, "min_classes": 3})
weights = cfg.get("weights", {"rating": 60, "approval": 25, "sample": 0, "reach": 0, "track": 15})
guard = cfg.get("guard", {"k": 0})
mv = cfg.get("min_votes", {"band": 3, "action": 6})
caps = cfg.get("caps", {"rating_line": 4.55, "approval_bar": 80})
bands = cfg.get("bands", {"excellent": 90, "good": 75, "average": 60})

# ── title ──
para("Class Sentiment Score", size=22, bold=True, space_after=2)
para("The settings we chose, and why — version 7, live since 7 September 2026", size=13, color=MUTED, space_after=2)
para("Validated on 2,779 real classes from January to August 2026. Every number below is a setting on Admin › Scoring; "
     "the full test is in Sentiment-Score-Validation.pdf, the two-page version in Sentiment-Score-One-Pager.pdf.",
     size=10.5, color=MUTED, italic=True, space_after=12)

# ── 1 ──
doc.add_heading("1. What the score is, in one paragraph", level=1)
para("Every rated class gets one number from 0 to 100. It is built from three things the sheet already records: the star "
     "rating, the vote (\"would you want this instructor back?\"), and the instructor's track record over earlier classes. "
     "The number is read as one of four bands, and the band decides the work: a Bad class gets a video analysis, an Average "
     "class a transcript read, a Good or Excellent class nothing unless a PM asks. The manager's method gave us the shape; "
     "eight months of real classes decided the exact settings.")

# ── 2 ──
doc.add_heading("2. The four bands and what happens", level=1)
table(["Band", "Score", "What it means", "What happens"], [
    ["Excellent", f"{bands['excellent']} and up", "clears every bar with room to spare", "nothing, unless a PM asks"],
    ["Good", f"{bands['good']} – {bands['excellent'] - 0.01:.2f}", "fine on both lines", "nothing, unless a PM asks"],
    ["Average", f"{bands['average']} – {bands['good'] - 0.01:.2f}", "one line missed", "transcript analysis"],
    ["Bad", f"under {bands['average']}", "both lines missed, or the score itself is low", "video analysis"],
    ["no band", "—", f"fewer than {mv['band']} votes", "watch"],
], widths=[2.6, 3.0, 6.0, 4.4], bold_first_col=True)

# ── 3 ──
doc.add_heading("3. Every setting, its value, and the reason", level=1)
para("Each row is one switch on the Scoring page. \"Original\" is the manager's method as first written; \"Now\" is what is live.",
     size=10.5, color=MUTED)
table(["Setting", "Original", "Now", "Why"], [
    ["How stars become points",
     "straight line: rating ÷ 5 (a 4.0 class earns 80 of 100)",
     f"a knee: 0 points at {rating['floor']} and below, {rating['line_value']} at {rating['line']} (the team's line), 100 at 5.0",
     "Real classes live between 4.0 and 5.0. On a straight line the whole range moved the score by 12 points, so the rating barely mattered; the knee makes the 4.55 line mean something."],
    ["The vote (approval)",
     "all or nothing: 30 points at 80 %, none at 79 %",
     f"graded: 0 points at {approval['floor']} %, full points at {approval['bar']} %",
     "One \"no\" out of three used to cost the same as dropping from a 5.0 class to a 2.5 class. Graded, 79 % is almost as good as 80 % and 50 % is a lot worse than 70 %."],
    ["How many rated (responses)",
     "6 points if 10 or more rated, none otherwise",
     "no points of its own — it decides how much the rating and the vote are believed",
     "The intent was trust, not room size: with two or three raters, one or two biased learners can drag a class down on purpose, so a low average from a tiny sample should be believed less. Points for the count did not do that (a big room with a bad class still earned them, and test reviews with 8.5 raters on average lost them); the minimum-votes rule and the provisional band do. Until we can see each rater's own history (per-learner ratings do not exist yet) the count works as a confidence dial, never as a score."],
    ["Reach (share of the room that rated)",
     "4 points, graded",
     "off (kept as a switch)",
     "Same reason: a measure of turnout and trust, not of teaching. It stays visible on every page; it just does not score."],
    ["Track record",
     "off",
     f"on: the instructor's average over earlier classes, 0 points at {track['floor']}, full at {track['line']}, counted from {track.get('min_classes', 3)} earlier classes",
     "A worse record today predicts a worse next class; 15 % of the score is enough to separate a one-off from a pattern without hiding a bad class behind a good history."],
    ["Weights",
     "rating 60 · approval 30 · responses 6 · reach 4",
     f"rating {weights['rating']} · approval {weights['approval']} · track record {weights['track']}",
     "Derived from how well each part predicts the instructor's next class; when a part is missing (no vote yet) the others are re-scaled, never penalised."],
    ["Small-sample guard",
     "none",
     f"off (k = {guard.get('k', 0)})",
     "The guard is the other half of the trust idea: a few votes are blended with a few typical votes for the course, so a small sample moves the score less. With it on today the two hard lines read the guarded values and 134 classes under a line showed as Good, so it stays off until the lines read raw values; the switch and the tests are ready."],
    ["Minimum votes",
     "none — one vote could give a band",
     f"{mv['band']} votes before a band is shown; {mv['action']} before an analysis is triggered",
     f"This is where the trust lives. Under {mv['band']} votes there is no verdict at all. From {mv['band']} to {mv['action'] - 1} the band is provisional and the class is watched, not analysed — two or three raters cannot sink a class on their own. From {mv['action']} the band drives the queue; this is also the dial that keeps the queue near 12 analyses a week."],
    ["The two hard lines",
     "none",
     f"rating {caps['rating_line']} and approval {caps['approval_bar']} %: with 5 or more votes a class under either line can never sit above Average; under both it is Bad",
     "The two numbers the team already agreed. They stop a 3.0-rated class with an approved instructor from scoring Good."],
    ["Band edges",
     "90 / 75 / 60",
     f"{bands['excellent']} / {bands['good']} / {bands['average']}",
     "Unchanged: the edges were not the problem, the inputs were. The band reads the score rounded to two decimals."],
    ["Missing inputs",
     "zero points",
     "neutral: the part is left out and the rest re-scaled",
     "A class without a vote column is not a worse class."],
    ["Band → action",
     "not defined",
     "Bad → video · Average → transcript · Good, Excellent → none · too few votes → watch · any escalation → video",
     "The band drives the queue (decided with Bishal, 3 September)."],
], widths=[3.2, 3.6, 4.2, 5.0], bold_first_col=True)

# ── 4 ──
doc.add_heading("4. How we tested it", level=1)
para("Six settings of the same formula were replayed on every class from January to August 2026 and marked against six yardsticks "
     "that were written down before anything ran. A setting that hides low-rated classes, or overloads the team, is out regardless of its mark.")
table(["Yardstick", "Plain meaning", "Pass mark"], [
    ["Stable under one vote", "one person changing their mind should not change the verdict", "under 10 % of classes flip"],
    ["Agrees with the two human signals", "a Good class must not sit under the 4.55 line or the 80 % bar (5+ votes)", "false comfort under 2 %"],
    ["Predicts the next class", "a worse band today should mean a higher chance the next class goes wrong", "Bad at least twice Excellent"],
    ["Sensible band sizes and workload", "every band has classes; the queue fits the team", "no band under 5 %; about 12 analyses a week"],
    ["Fair to small classes and test reviews", "the band reflects how the class went, not how big the room was", "differ by under 10 points"],
    ["Explainable in one sentence", "a PM can say why a class got its band", "8 of 10 right"],
], widths=[4.2, 7.4, 4.4], bold_first_col=True)
table(["Setting tested", "Marks (of 200)", "Vetoed?"], [
    ["Manager's original (60/30/6/4, pass/fail)", "89", "yes — hides 245 low-rated classes"],
    ["Original + minimum votes", "104", "yes"],
    ["Graded approval", "88", "yes"],
    ["Graded + small-sample guard", "139", "yes"],
    ["Data-derived weights", "106", "yes"],
    ["Two lines + graded score (guard on)", "120", "yes — the guard hides 134 classes under a line"],
    ["Two lines + graded score, guard off, analysis from 6 votes — LIVE", "148", "no"],
], widths=[8.6, 3.0, 4.4], bold_first_col=True)

# ── 5 ──
doc.add_heading("5. The five numbers a VP should know", level=1)
para("Measured on the real classes, January to August 2026. The same table is computed live on All courses › Insights.", size=10.5, color=MUTED)
table(["", "Manager's original", "Live now (version 7)"], [
    ["Classes whose band flips if one learner votes differently", "39 %", "37 %  (the verdict flips for 17 %, was 31 %)"],
    ["\"Bad\" classes that were actually rated 4.55 or better", "38 of 199", "0 of 179"],
    ["Low-rated classes (under 4.55 or 80 %, 5+ votes) shown as Good or Excellent", "249", "0 (11 provisional, watched)"],
    ["Analyses a week", "7.1  (5.7 video + 1.4 transcript)", "11.8  (4.6 video + 7.2 transcript)"],
    ["Chance the instructor's next class is low: Bad vs Excellent", "41 % vs 14 %", "45 % vs 11 %"],
], widths=[7.4, 4.3, 4.3], bold_first_col=True)
para("The honest trade-off: the original did less work because it ignored about 250 low-rated classes whose instructor was approved. "
     "The data says those carry twice the baseline risk for the next class. The live settings read them from the transcript, the cheap analysis.")

# ── 6 ──
doc.add_heading("6. Where to see it, and how it changes", level=1)
bullet("shows every setting above with the live values, a preview of what any change would do to a month of real classes, and the version history. A change is draft → preview → activate → rollback in one click.", "Admin › Scoring")
bullet("recomputes the five numbers from the database for the original and the live version, next to what the study measured.", "All courses › Insights")
bullet("every class shows its score, its band and what each input earned; hover any score.", "Any class")
bullet("the settings are data, not code. Re-run the study monthly and whenever a course reaches 30 classes; the study scripts live in analysis/ and print both PDFs.", "As data changes")

# ── 7 ──
doc.add_heading("7. Known limits, said plainly", level=1)
bullet("About a third of labels sit within reach of a band edge, so a single rater can move a label (Good ↔ Excellent mostly). The verdict — whether work happens — flips for 17 % of classes; that number is the one to watch.")
bullet("Eleven classes with exactly 5 votes carry a provisional Good or Excellent while sitting under a line; they are watched, not analysed, until the sixth vote.")
bullet("The small-sample guard is off until the hard lines are made to read raw values; the tested setting with the guard on is stored beside the live one.")

doc.save(OUT)
print("wrote", OUT)
