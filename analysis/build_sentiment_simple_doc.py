"""Builds 'Class Sentiment Score - The Simple Version.docx' - the manager's methodology, restated
in plain words with tables, for presenting to the VP. No maths beyond 'add them up'."""
import os

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Cm

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "Class Sentiment Score - The Simple Version.docx")

INK = RGBColor(0x16, 0x16, 0x1A)
MUTED = RGBColor(0x4B, 0x4B, 0x53)
BRAND = RGBColor(0x2A, 0x78, 0xD6)
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


# ------------------------------------------------------------------ title
para("INTERVIEW KICKSTART · NEW PROGRAMS", size=9, bold=True, color=BRAND, space_after=2)
para("Class Sentiment Score — the simple version", size=20, bold=True, space_after=2)
para("One number, 0 to 100, for every class. It says how happy the learners were with that class.",
     size=12, color=MUTED, space_after=10)

# ------------------------------------------------------------------ 1
doc.add_heading("1. What the score is", level=1)
para("Every class gets one score out of 100. Four things go into it. Two big ones decide the result; "
     "two small ones only nudge it. The score puts the class into one of four bands: Excellent, Good, "
     "Average or Bad.")

# ------------------------------------------------------------------ 2
doc.add_heading("2. What goes into the score", level=1)
table(
    ["What goes in", "Points", "In plain words"],
    [
        ["Class rating", "60", "The stars learners gave the class, out of 5."],
        ["Instructor approval", "30", "Did at least 80% of learners say “yes, I want this instructor again”? "
                                      "Yes = the full 30 points. No = 0."],
        ["Enough responses", "6", "Did at least 10 learners rate the class? Yes = 6 points. No = 0."],
        ["Reach", "4", "The share of the room that actually rated the class. Everyone rated = 4 points; "
                       "half the room = 2 points."],
    ],
    widths=[4.2, 1.8, 10.2], bold_first_col=True,
)
para("Add the four together — that is the score out of 100.", bold=True)

# ------------------------------------------------------------------ 3
doc.add_heading("3. The four bands", level=1)
table(
    ["Score", "The class is"],
    [["90 or more", "Excellent"], ["75 – 89", "Good"], ["60 – 74", "Average"], ["Below 60", "Bad"]],
    widths=[5, 11], bold_first_col=True,
)

# ------------------------------------------------------------------ 4
doc.add_heading("4. Three rules to remember", level=1)
bullet("The other two can move a class a few points up or down, but they can never change its band on their own.",
       bold_lead="Rating and approval decide the band.")
bullet("A 4.8-rated class whose instructor missed the 80% bar lands in Average — never Good or Excellent.",
       bold_lead="A great rating cannot save a class whose instructor is not wanted back.")
bullet("A 4.0-rated class whose instructor missed the 80% bar lands in Bad, whatever else happens.",
       bold_lead="Approval cannot save a weak rating either.")

# ------------------------------------------------------------------ 5
doc.add_heading("5. The four words, explained simply", level=1)
table(
    ["Word", "What it means", "Example"],
    [
        ["Class rating", "The average of the stars learners gave the class, out of 5.",
         "20 learners rate a class; the average is 4.6."],
        ["Instructor approval", "After every class, learners answer “would you want this instructor to take the "
                                "class again?” Approval is the share who said yes. The bar is 80%.",
         "13 of 15 said yes → 87% → clears the bar. 4 of 6 said yes → 67% → misses it."],
        ["Enough responses", "Whether at least 10 learners rated the class. Below 10 the rating rests on too "
                             "few opinions.", "12 rated → yes. 7 rated → no."],
        ["Reach", "People who rated ÷ people who attended. How much of the room the rating actually "
                  "represents.", "20 attended, 10 rated → 50% reach."],
    ],
    widths=[3.4, 7.4, 5.4], bold_first_col=True,
)

# ------------------------------------------------------------------ 6
doc.add_heading("6. Examples", level=1)
para("Six classes, chosen to show the whole range. “Approved” means at least 80% of learners wanted the "
     "instructor again.", color=MUTED)
table(
    ["Class", "Rating", "Instructor approved?", "Score", "Band"],
    [
        ["Ideal class", "5.0", "Yes", "100", "Excellent"],
        ["Strong class, small room", "4.9", "Yes", "93", "Excellent"],
        ["Great rating, instructor not wanted back", "4.8", "No", "68", "Average"],
        ["Okay rating, instructor not wanted back", "4.0", "No", "58", "Bad"],
        ["Very low rating, instructor still wanted", "1.5", "Yes", "58", "Bad"],
        ["Worst case", "2.5", "No", "30", "Bad"],
    ],
    widths=[6.6, 1.8, 3.6, 1.8, 2.4], bold_first_col=True,
)
para("Reading the table: the same rating and the same approval answer always land in the same band. "
     "Reach and enough-responses only move the score a few points inside that band.")

# ------------------------------------------------------------------ 7
doc.add_heading("7. How to read any class in ten seconds", level=1)
table(
    ["Step", "Look at", "What it tells you"],
    [
        ["1", "The rating", "How the class went."],
        ["2", "Instructor approval — above or below 80%", "Whether the room wants this instructor again."],
        ["3", "The band", "Excellent, Good, Average or Bad — decided by the two above."],
    ],
    widths=[1.4, 6.4, 8.4],
)

para("")
para("Source: “Class Sentiment Score — Methodology” (internal). This is the same method, in plain words.",
     size=9, color=MUTED, italic=True)

doc.save(OUT)
print("wrote", OUT)
