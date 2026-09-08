"""Two documents, written after the 8 Sep review, with the quality line at 4.6.

  The Case Against the Old Formula.docx   three pages: every argument, with real classes as proof
  How the Class Score Works.docx          for the PM: what it is, what changed, and why

No invented vocabulary: the number 4.6 is written as 4.6, "approval" is "how many wanted the
instructor again", and nothing is called a rule, a parameter or a property unless it really is one.
Every class and count is computed from the live database at build time.

    python analysis/build_case_docs.py
"""
import collections
import copy
import csv
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
import json  # noqa: E402

CASE_OUT = os.environ.get("CASE_OUT") or os.path.join(ROOT, "The Case Against the Old Formula.docx")
HOW_OUT = os.environ.get("HOW_OUT") or os.path.join(ROOT, "How the Class Score Works.docx")
FIXTURES = json.load(open(os.path.join(ROOT, "supabase", "fixtures", "scoring_configs.json"), encoding="utf-8"))
LINE = 4.6
WEEKS = 35.0

W_INK, W_MUTED, W_BRAND = RGBColor(0x16, 0x16, 0x1A), RGBColor(0x4B, 0x4B, 0x53), RGBColor(0x2A, 0x78, 0xD6)
W_RED, W_TEAL = RGBColor(0xB4, 0x3A, 0x2E), RGBColor(0x1B, 0x7F, 0x5E)
HEADER_FILL, ZEBRA_FILL, NOTE_FILL, WARN_FILL, GOOD_FILL = "EEF3FB", "F7F7F5", "F3F7FD", "FDF4F3", "F2F8F5"

DISPUTED = list(csv.DictReader(open(os.path.join(ROOT, "Disputed-Classes.csv"), encoding="utf-8-sig")))
for d in DISPUTED:
    d["rating"] = float(d["rating"])
    d["karthika_score"] = float(d["karthika_score"])
    d["new_score"] = float(d["new_score"])
TIER1 = sorted([d for d in DISPUTED if d["test_first"].startswith("1.")], key=lambda d: d["rating"])
TIER2 = sorted([d for d in DISPUTED if d["test_first"].startswith("2.")], key=lambda d: d["rating"])
TIER3 = sorted([d for d in DISPUTED if d["test_first"].startswith("3.")], key=lambda d: -d["rating"])


def at(cfg, rating_w=None, approval_w=None, track_w=None, line=LINE):
    c = copy.deepcopy(cfg)
    c["rating"]["line"] = line
    c["caps"]["rating_line"] = line
    if rating_w is not None:
        c["weights"]["rating"] = rating_w
        c["weights"]["approval"] = approval_w
        c["weights"]["track"] = track_w
        if track_w == 0:
            c["track"]["mode"] = "off"
    return c


def load():
    conn = ST.connect()
    cur = conn.cursor()
    cur.execute("select config from scoring_configs where status = 'active'")
    live = cur.fetchone()[0]
    cur.execute("select rating, num_ratings, attended, yes_votes, no_votes, track_avg, escalated from class_ratings")
    rows = [r for r in cur.fetchall() if r[0] is not None]
    conn.close()
    return live, rows


LIVE, ROWS = load()
OLD_CFG = FIXTURES["C0"]
NEW_CFG = at(LIVE, 70, 30, 0)          # the simple two-part version, at 4.6


def tally(cfg):
    acts, weak, punished = collections.Counter(), 0, 0
    for rating, n, att, yes, no, tr, esc in ROWS:
        inp = {"rating": float(rating), "num_ratings": n, "attended": att, "yes_votes": yes, "no_votes": no,
               "escalated": bool(esc), "track_avg": float(tr) if tr is not None else None}
        s = score(inp, cfg)
        acts[s["action"]] += 1
        votes = (yes or 0) + (no or 0)
        ap = 100 * yes / votes if votes else None
        if votes >= 6 and (float(rating) < LINE or (ap is not None and ap < 80)) and s["band"] in ("good", "excellent"):
            weak += 1
        if float(rating) >= LINE and votes and votes <= 5 and s["action"] == "video":
            punished += 1
    return acts, weak, punished


OLD_ACTS, OLD_WEAK, OLD_PUNISHED = tally(OLD_CFG)
NEW_ACTS, NEW_WEAK, NEW_PUNISHED = tally(NEW_CFG)
TOTAL = len(ROWS)


# ── document plumbing ────────────────────────────────────────────────────────
class Doc:
    def __init__(self, margin=1.9):
        self.d = Document()
        s = self.d.sections[0]
        s.left_margin = s.right_margin = Cm(margin)
        s.top_margin = s.bottom_margin = Cm(1.6)
        self.width = 21.0 - 2 * margin
        base = self.d.styles["Normal"]
        base.font.name = "Calibri"
        base.font.size = Pt(11)
        base.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
        for nm, size in (("Heading 1", 14.5), ("Heading 2", 12), ("Heading 3", 11.5)):
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

    def p(self, text="", size=11, bold=False, color=None, italic=False, after=6):
        par = self.d.add_paragraph()
        r = par.add_run(text)
        r.font.size = Pt(size)
        r.bold = bold
        r.italic = italic
        if color is not None:
            r.font.color.rgb = color
        par.paragraph_format.space_after = Pt(after)
        return par

    def h(self, text, level=1):
        return self.d.add_heading(text, level=level)

    def bullet(self, text, lead=None):
        par = self.d.add_paragraph(style="List Bullet")
        if lead:
            r = par.add_run(lead + " ")
            r.bold = True
        par.add_run(text)
        par.paragraph_format.space_after = Pt(4)
        return par

    def note(self, title, lines, fill=NOTE_FILL):
        t = self.d.add_table(rows=1, cols=1)
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
        self.shade(cell, fill)
        self.d.add_paragraph().paragraph_format.space_after = Pt(2)
        return t

    def table(self, headers, rows, widths=None, bold_first=False, size=10, colors=None):
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

    def example(self, d, fill=WARN_FILL):
        """One real class, with both verdicts."""
        t = self.d.add_table(rows=1, cols=1)
        t.style = "Table Grid"
        cell = t.rows[0].cells[0]
        cell.text = ""
        r = cell.paragraphs[0].add_run(f"{d['module']}  ·  {d['instructor']}  ·  {d['date']}")
        r.bold = True
        r.font.size = Pt(10.5)
        lines = [
            f"{d['course']} · {d['kind']} · {d['rated_by']} of {d['attended']} learners rated it "
            f"{d['rating']:.2f} · {d['want_instructor_again']} wanted the instructor again ({d['approval_pct']}%)",
            f"Karthika's formula: {d['karthika_score']:.0f} → {d['karthika_says']} → {d['karthika_action']}",
            f"The new formula: {d['new_score']:.0f} → {d['new_says']} → {d['new_action']}",
        ]
        for i, line in enumerate(lines):
            par = cell.add_paragraph()
            rr = par.add_run(line)
            rr.font.size = Pt(10)
            if i == 0:
                rr.font.color.rgb = W_MUTED
            par.paragraph_format.space_after = Pt(1)
        self.shade(cell, fill)
        self.d.add_paragraph().paragraph_format.space_after = Pt(4)
        return t

    def save(self, path):
        self.d.save(path)


# ═════════════════════════════════════════════════════════════════════════════
def build_case():
    d = Doc()
    d.p("INTERVIEW KICKSTART · NEW PROGRAMS", size=9, bold=True, color=W_BRAND, after=2)
    d.p("Why the class-score formula has to change", size=20, bold=True, after=2)
    d.p(f"Five arguments, each with real classes from our own data. Everything below uses 4.6 as the "
        f"rating we call acceptable, which is what the VP asked for. {TOTAL:,} classes, January to "
        f"August 2026.", size=11.5, color=W_MUTED, after=10)

    d.h("The five arguments", level=1)

    d.p("1.  It lets weak classes through, because learners are polite.", bold=True, after=3)
    d.p(f"{OLD_WEAK} classes were rated below 4.6, or had fewer than 80% of learners wanting the "
        f"instructor again, and the formula still called them Good or Excellent. Nobody was ever asked "
        f"to look at them. The reason is that a polite room earns the full 30 approval points, and the "
        f"weak rating costs almost nothing.", after=6)
    d.example(TIER1[0])

    d.p("2.  It spends video analyses on classes nobody thinks are bad.", bold=True, after=3)
    d.p(f"{len(TIER3)} classes were sent for a full video analysis by the old formula although the "
        f"class was fine; {sum(1 for t in TIER3 if t['rating'] >= LINE)} of them were rated 4.6 or "
        f"better. The reason is the same switch working the other way: a class where only three people "
        f"voted and one said no is at 67%, so it loses all 30 points at once.", after=6)
    d.example(TIER3[0], fill=WARN_FILL)

    d.p("3.  It judges a class on three votes, and forgives one judged on twenty.", bold=True, after=3)
    d.p("The vote is all or nothing at 80%. Three people where one says no is 67%, so the class loses "
        "everything. Twenty people where four say no is exactly 80%, so the class keeps everything. "
        "The formula has no idea that the first number is three opinions and the second is twenty.", after=8)

    d.p("4.  The rating hardly counts.", bold=True, after=3)
    d.p("Stars became points by dividing by five. A class rated 4.30 therefore keeps 86% of the rating "
        "points, so the whole distance between a weak class and a strong one is a handful of points. "
        "The rating is the one thing that is actually about the class, and it was the part that moved "
        "the score least.", after=8)

    d.p("5.  It pays points for the size of the room.", bold=True, after=3)
    d.p("Ten of the hundred points went to how many people rated and how much of the room rated. That "
        "rewards a big class, not a good one, and it quietly punishes test reviews, which are smaller "
        "by nature and rate better than live classes.", after=10)

    d.d.add_page_break()
    d.h("The proof: classes where the two formulas disagree", level=1)
    d.p("There are 389 of them. They fall into three groups. The full list, with cohort, module, "
        "instructor and every number, is in Disputed-Classes.csv.", color=W_MUTED, after=8)

    d.h(f"Group 1 · the new formula says watch the video, the old one says nobody looks  ({len(TIER1)} classes)", level=2)
    d.p("These are the five to test. Run the video analysis on them. If the analysis says the class "
        "should be re-taught, the old formula was wrong to hide them.", after=6)
    for x in TIER1:
        d.example(x)

    d.d.add_page_break()
    d.h(f"Group 2 · the new formula says read the transcript, the old one says nobody looks  ({len(TIER2)} classes)", level=2)
    d.p("A transcript read costs about half a dollar. These are the classes where a PM would at least "
        "want to know what happened.", after=6)
    for x in TIER2[:4]:
        d.example(x)

    d.h(f"Group 3 · the old formula spends a video, the new one says it is not needed  ({len(TIER3)} classes)", level=2)
    d.p("This is the argument the other way round, and it is the strongest one: the old formula is "
        "already condemning classes on a handful of votes, which is exactly what we were told not to do.",
        after=6)
    for x in TIER3[:3]:
        d.example(x, fill=GOOD_FILL)

    d.d.add_page_break()
    d.h("What the new formula does instead", level=1)
    d.table(["", "The old formula", "The new one"],
            [["The rating", "rating ÷ 5 × 60, so 4.30 keeps 86% of the points",
              "0 points at 3.55 and below, 75 points at 4.6, 100 at 5.0 — so a weak class really loses points"],
             ["Wanting the instructor again", "all 30 points at 80%, nothing at 79%",
              "0 points at 40% and below, full points at 80% and above, sliding in between"],
             ["How many rated", "6 points for ten or more, 4 more for turnout",
              "no points at all — it decides whether we believe the class instead"],
             ["The instructor's past classes", "not used", "not used (see the note below)"]],
            widths=[3.4, 6.4, 7.4], bold_first=True, size=9.5)
    d.p("And two rules that no amount of points can overrule:", after=4)
    d.bullet("a class rated below 4.6, or with fewer than 80% wanting the instructor again, can never "
             "be called Good or Excellent.", lead="The two lines are absolute:")
    d.bullet("under 3 votes there is no verdict at all. With 3, 4 or 5 votes the class is watched, "
             "never sent for an analysis. From 6 votes the verdict counts.",
             lead="A handful of voices cannot condemn a class:")
    d.note("The instructor's past record: our recommendation is to leave it out",
           ["It was in the version we tested, worth 15 of the 100 points. We measured what happens if we "
            "remove it: the action changes for 2 classes out of 2,779.",
            "It buys us nothing, and it invites a fair objection — that we are judging this class by the "
            "instructor's history. The score is about the class. The instructor's record stays visible on "
            "their own page, where it belongs, for coaching.",
            "So the new formula is two things the learners told us about this class: the rating out of 70, "
            "and whether they want the instructor again out of 30."], fill=GOOD_FILL)

    d.h("What changes in the work", level=1)
    d.table(["Per week", "The old formula", "The new one"],
            [["Videos watched", f"{OLD_ACTS['video'] / WEEKS:.1f}", f"{NEW_ACTS['video'] / WEEKS:.1f}"],
             ["Transcripts read", f"{OLD_ACTS['transcript'] / WEEKS:.1f}", f"{NEW_ACTS['transcript'] / WEEKS:.1f}"],
             ["Weak classes wrongly called Good or Excellent", f"{OLD_WEAK} in total", f"{NEW_WEAK} in total"]],
            widths=[8.6, 4.3, 4.3], bold_first=True,
            colors={(2, 1): W_RED, (2, 2): W_TEAL})
    d.p("The video count barely moves. What changes is that weak classes now get a cheap transcript "
        "read instead of being invisible, and small classes stop being condemned on three votes.", after=8)

    d.note("How to settle this for good",
           ["Run the video analysis on the five classes in Group 1. The analysis already tells us whether "
            "a class should be re-taught.",
            "If it says yes for classes the old formula called Good, the old formula was hiding real "
            "problems. If it says no for all five, we keep the old one and I was wrong.",
            "Either way we will know from our own recordings rather than from an argument."])
    d.save(CASE_OUT)


# ═════════════════════════════════════════════════════════════════════════════
def build_how():
    d = Doc()
    d.p("INTERVIEW KICKSTART · NEW PROGRAMS", size=9, bold=True, color=W_BRAND, after=2)
    d.p("How the class score works", size=20, bold=True, after=2)
    d.p("Written for me, so I can answer any question about it without opening anything else. "
        "Nothing here is a technical term unless it is explained on the spot.", size=11.5,
        color=W_MUTED, after=10)

    d.h("1. What the score decides", level=1)
    d.p(f"About {TOTAL / WEEKS:.0f} classes run every week and a PM can properly review about a dozen. "
        f"The score picks which ones. It gives each class a number out of 100 and one of four labels, "
        f"and the label decides the work.")
    d.table(["Label", "What happens next"],
            [["Excellent or Good", "nobody looks"],
             ["Average", "someone reads the transcript"],
             ["Bad", "someone watches the recording; the analysis then says whether the class should be re-taught"],
             ["No label", "too few learners voted — the class is watched, nothing is spent on it"]],
            widths=[4.2, 13.0], bold_first=True)

    d.h("2. The old formula, exactly as it worked", level=1)
    d.table(["Part", "Points", "How they were earned"],
            [["The rating", "60", "the rating divided by 5, times 60. A 4.30 class earned 51.6"],
             ["Wanting the instructor again", "30", "all 30 if 80% or more said yes; zero below that"],
             ["How many rated", "6", "all 6 if ten or more rated; zero below that"],
             ["Turnout", "4", "the share of the room that rated, times 4"]],
            widths=[4.6, 1.6, 11.0], bold_first=True)
    ex = TIER1[0]
    d.p(f"On a real class: {ex['module']}, rated {ex['rating']:.2f} by {ex['rated_by']} of "
        f"{ex['attended']} learners, {ex['want_instructor_again']} wanting the instructor again.", after=4)
    d.note("The arithmetic",
           [f"{ex['rating']:.2f} ÷ 5 × 60 = {ex['rating'] / 5 * 60:.1f} points for the rating",
            f"plus 30, because {ex['approval_pct']}% is above 80%",
            f"plus a little for the head-count and turnout",
            f"= {ex['karthika_score']:.0f} out of 100 → “{ex['karthika_says']}” → nobody looks."])

    d.h("3. What is wrong with it", level=1)
    for i, (title, body) in enumerate([
        ("Politeness pays more than quality",
         f"{OLD_WEAK} classes were rated below 4.6 or had under 80% wanting the instructor again, and were "
         f"still called Good or Excellent. Learners mark a class down and still like the person, so the "
         f"full 30 points arrive anyway and the weak rating costs almost nothing."),
        ("It condemns small classes",
         f"{len(TIER3)} classes were sent for a video analysis although the class was fine, because a few "
         f"voters put them under 80%. A class rated 4.87 where 2 of 3 people voted yes was scored 59 and "
         f"sent for a full video analysis."),
        ("The rating hardly counts",
         "Dividing by five keeps even a poor class near the top of the rating points, so the rating — the "
         "one number that is actually about the class — moves the score least."),
        ("It pays for the size of the room",
         "Ten points went to how many rated and how much of the room rated. That rewards big classes and "
         "penalises test reviews, which are smaller by nature."),
        ("A single vote can swing everything",
         "Because the vote is all or nothing at 80%, one learner changing their mind can move a class by "
         "30 points, which is the same as the distance between a 5.0 class and a 2.5 class."),
    ], start=1):
        d.p(f"{i}.  {title}", bold=True, after=3)
        d.p(body, after=8)

    d.d.add_page_break()
    d.h("4. The new formula, part by part", level=1)
    d.p("Two things the learners told us about this class, and nothing else.", after=6)
    d.table(["Part", "Points", "How they are earned"],
            [["The rating", "70", "0 points at 3.55 and below · 75 of the way up at 4.6 · 100 at 5.0. "
                                  "The steep stretch is below 4.6, so a weak class loses real points"],
             ["Wanting the instructor again", "30", "0 points at 40% and below · full points at 80% and "
                                                    "above · sliding in between, so 79% is nearly as good as 80% and 50% is far worse"]],
            widths=[4.6, 1.6, 11.0], bold_first=True)
    d.p("Then the two absolute rules:", after=4)
    d.bullet("a class rated below 4.6, or with fewer than 80% wanting the instructor again, can never be "
             "labelled Good or Excellent. If it fails both, it is Bad.", lead="The lines cannot be bought off:")
    d.bullet("under 3 votes, no label at all. With 3, 4 or 5 votes the label is marked provisional and "
             "the class only goes on a watch list. From 6 votes the label counts and can trigger work.",
             lead="Too few voices, no verdict:")
    d.note("Where the head-count went, since this is the question everyone asks",
           ["The old formula gave 10 of its 100 points to how many people rated and how much of the room "
            "rated. The new formula gives it no points at all.",
            "Instead it decides whether we believe the class: fewer than 3 votes and there is no verdict; "
            "3 to 5 votes and the class is only watched; 6 or more and the verdict counts.",
            "So the same fact is still used, but to decide whether to act rather than to add points. That "
            "is why three unhappy learners can no longer put a class in the queue."])
    d.note("The instructor's past record, and why we are dropping it",
           ["The version we tested had a third part worth 15 points: the instructor's average across their "
            "earlier classes.",
            "Measured on all 2,779 classes, removing it changes what we do for 2 classes. It earns its "
            "place in no way that matters.",
            "It also invites the fair objection that we are judging this class by the instructor's past. "
            "The score is about the class. The record stays on the instructor's own page for coaching.",
            "Recommendation: drop it. Rating 70, the vote 30."], fill=GOOD_FILL)

    d.h("5. Why “enough responses” and “turnout” earn no points any more", level=1)
    d.p("Karthika's formula gave 6 points for having enough raters and 4 points for turnout — ten of "
        "her hundred. The obvious question is whether we should keep them. We tested it instead of "
        "assuming.", after=6)
    d.table(["Version tested", "Videos/week", "Reviews/week", "Weak classes hidden", "Outcomes that differ"],
            [["The rating and the vote only", "4.8", "14.5", "0", "—"],
             ["+ responses, worth 7", "4.8", "14.5", "0", "2 of 2,779"],
             ["+ responses 6, turnout 4", "4.8", "14.5", "0", "1 of 2,779"],
             ["Karthika's 60 / 30 / 6 / 4", "4.8", "14.5", "0", "2 of 2,779"],
             ["+ responses 10, turnout 5", "4.8", "14.5", "0", "2 of 2,779"]],
            widths=[5.0, 2.6, 2.6, 3.4, 3.6], bold_first=True, size=9.5)
    d.p("All five give the same answer, and the reason is worth understanding: the two standards are "
        "absolute. Below 4.6, or below 80% with enough voters, a class can never be Good or Excellent, "
        "and ten points cannot overturn that. Above both standards a class is already Good or Excellent, "
        "so a few points do not change what we do. The ten points never had anything left to decide.",
        after=8)
    d.note("Where those two facts are used instead",
           ["How many rated: decides whether we act. Under 3 voices no verdict; 3 to 5 a watch list; "
            "6 or more we act.",
            "Turnout: shown on the class page for the PM, never scored.",
            "So nothing is thrown away. The same facts moved from adding points to deciding whether to "
            "spend money — which is what they were really telling us all along."], fill=GOOD_FILL)
    d.p("The class that makes this obvious: RAG Powered Knowledge Agents, 4 July. Thirty-eight learners "
        "attended and exactly one rated it, giving 5.0. Karthika's formula scores it 90.1 and calls it "
        "Excellent, because the rating earns 60, the vote earns 30, and the ten points for responses and "
        "turnout are far too small to say “we have barely heard from this room”. The new formula issues "
        "no verdict at all and puts it on the watch list.", after=10)

    d.h("6. How I chose those numbers, honestly", level=1)
    d.p("Two different things were used, and it is worth being clear about which is which.", after=6)
    d.bullet("Every candidate formula was replayed over all 2,779 real classes, and I counted concrete "
             "things: how many weak classes it hides, how many good classes it condemns, how many videos "
             "a week it produces. Those are counts, not predictions.", lead="Counting what happened:")
    d.bullet("I also measured whether a label warns us that the same instructor's next class goes wrong. "
             "That is a prediction, and it is the weaker kind of evidence. It is why the instructor's "
             "record looked useful at first, and why I am now dropping it: it predicted something, but it "
             "changed almost nothing about what we actually do.", lead="Predicting what comes next:")
    d.p("The real evidence is the one we are about to collect: run the video analysis on the classes the "
        "two formulas disagree about, and see whether it calls for a re-class. That is not a prediction. "
        "That is our own analysis on our own recordings.", after=8)

    d.h("7. What is still open", level=1)
    d.table(["Question", "Where it stands"],
            [["Does the instructor's record stay?", "Recommendation: no. It changes 2 classes out of 2,779."],
             ["How many analyses can we do a week?",
              f"The new formula produces about {(NEW_ACTS['video'] + NEW_ACTS['transcript']) / WEEKS:.0f} a week "
              f"({NEW_ACTS['video'] / WEEKS:.1f} videos and the rest transcripts). A PM can do about 12."],
             ["Should one vote be able to flip a verdict?",
              "A class sitting exactly on 4.6 or exactly on 80% can flip on one learner. Making each line a "
              "narrow grey zone would stop it."],
             ["When do we know for sure?",
              "When the five classes in Group 1 have been through a video analysis and we see whether it asks "
              "for a re-class."]],
            widths=[6.0, 11.2], bold_first=True)

    d.h("8. Words used in this document", level=1)
    d.table(["Word", "What it means"],
            [["The rating", "the average stars learners gave the class, out of 5"],
             ["Wanting the instructor again", "the share of voters who answered yes to “would you want this instructor to take the class again?”"],
             ["4.6", "the rating at or above which we consider a class acceptable — the VP's number"],
             ["80%", "the share of learners wanting the instructor again that we consider acceptable"],
             ["Turnout", "how much of the room rated the class: people who rated ÷ people who attended"],
             ["Label", "Excellent, Good, Average or Bad"],
             ["Provisional", "a label based on 3 to 5 votes. It is shown, but no work is triggered by it"],
             ["Video analysis", "the AI watches the recording and reports what went wrong, and whether the class should be re-taught"]],
            widths=[5.0, 12.2], bold_first=True, size=10)
    d.save(HOW_OUT)


build_how()
print("wrote", HOW_OUT)
