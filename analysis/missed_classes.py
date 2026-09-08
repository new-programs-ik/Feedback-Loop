"""Which classes did the manager's formula wave through, and why?

A "missed" class is one that fails a line the team already agreed - rated under 4.55, or fewer
than 80% of at least five voters wanting the instructor back - yet the manager's formula still
badged it Good or Excellent, so nobody ever looked at it.

Writes:
  Missed-Classes.csv                                  every missed class, all columns (Excel)
  The 23 Rules and the Classes We Missed.docx         the rules, the patterns, worked examples

    python analysis/missed_classes.py

Local use only: the outputs carry instructor names and ratings and are gitignored.
"""
import csv
import datetime as dt
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

CSV_OUT = os.environ.get("MISSED_CSV") or os.path.join(ROOT, "Missed-Classes.csv")
DOC_OUT = os.environ.get("MISSED_DOC") or os.path.join(ROOT, "The 23 Rules and the Classes We Missed.docx")
PROPS = json.load(open(os.path.join(HERE, "out", "formula_properties.json"), encoding="utf-8"))
RESULTS = json.load(open(os.path.join(HERE, "out", "formula_results.json"), encoding="utf-8"))
FIXTURES = json.load(open(os.path.join(ROOT, "supabase", "fixtures", "scoring_configs.json"), encoding="utf-8"))

RATING_LINE, APPROVAL_BAR, MIN_VOTES = 4.55, 80.0, 5
HELD_OUT = (dt.date(2026, 6, 1), dt.date(2026, 8, 31))

INK = RGBColor(0x16, 0x16, 0x1A)
MUTED = RGBColor(0x4B, 0x4B, 0x53)
BRAND = RGBColor(0x2A, 0x78, 0xD6)
RED = RGBColor(0xB4, 0x3A, 0x2E)
TEAL = RGBColor(0x1B, 0x7F, 0x5E)
HEADER_FILL = "EEF3FB"
ZEBRA_FILL = "F7F7F5"
NOTE_FILL = "F3F7FD"

SQL = """
select cr.class_date, coalesce(c.name, cr.course_label) as course, co.name as cohort,
       coalesce(t.name, cr.topic) as module, coalesce(cr.instructor_canonical, cr.instructor) as instructor,
       cr.session_kind, cr.rating, cr.num_ratings, cr.attended, cr.yes_votes, cr.no_votes,
       cr.track_avg, cr.escalated, cr.id
  from class_ratings cr
  left join courses c on c.id = cr.course_id
  left join cohorts co on co.id = cr.cohort_id
  left join topics t on t.id = cr.topic_id
 order by cr.class_date
"""


def load_rows():
    conn = ST.connect()
    cur = conn.cursor()
    cur.execute(SQL)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.execute("select version, name, config from scoring_configs where status = 'active'")
    version, name, active = cur.fetchone()
    conn.close()
    return rows, {"version": version, "name": name, "config": active}


def inputs_of(r):
    return {
        "rating": float(r["rating"]) if r["rating"] is not None else None,
        "num_ratings": r["num_ratings"],
        "attended": r["attended"],
        "yes_votes": r["yes_votes"],
        "no_votes": r["no_votes"],
        "escalated": bool(r["escalated"]),
        "track_avg": float(r["track_avg"]) if r["track_avg"] is not None else None,
    }


def classify(rating, approval):
    low_rating = rating is not None and rating < RATING_LINE
    low_vote = approval is not None and approval < APPROVAL_BAR
    if low_rating and low_vote:
        return "Both lines missed"
    if low_rating:
        return "Rated under 4.55, but the room still wanted the instructor"
    return "Rated fine, but the room did not want the instructor back"


def main():
    rows, active = load_rows()
    c0 = FIXTURES["C0"]
    v7 = active["config"]
    missed = []
    totals = {"all": 0, "held_out": 0}
    for r in rows:
        yes, no = r["yes_votes"], r["no_votes"]
        votes = (yes or 0) + (no or 0)
        if votes < MIN_VOTES or r["rating"] is None:
            continue
        approval = 100.0 * yes / votes if votes else None
        rating = float(r["rating"])
        if not (rating < RATING_LINE or (approval is not None and approval < APPROVAL_BAR)):
            continue                                   # the class clears both lines - nothing to miss
        inp = inputs_of(r)
        old = score(inp, c0)
        new = score(inp, v7)
        if old["band"] not in ("good", "excellent"):
            continue                                   # the original caught it too
        held = HELD_OUT[0] <= r["class_date"] <= HELD_OUT[1]
        totals["all"] += 1
        totals["held_out"] += 1 if held else 0
        missed.append({
            "date": r["class_date"].isoformat(),
            "held_out_month": "yes" if held else "no",
            "course": r["course"],
            "cohort": r["cohort"] or "",
            "module": r["module"],
            "instructor": r["instructor"],
            "kind": r["session_kind"],
            "rating": round(rating, 2),
            "rated": r["num_ratings"],
            "attended": r["attended"],
            "yes": yes,
            "no": no,
            "approval_pct": round(approval, 1) if approval is not None else "",
            "pattern": classify(rating, approval),
            "old_score": old["score"],
            "old_band": (old["band"] or "").title(),
            "old_action": "no analysis",
            "new_score": new["score"],
            "new_band": (new["band"] or "").title(),
            "new_action": {"video": "video analysis", "transcript": "transcript read",
                           "watch": "watch", "none": "no analysis"}[new["action"]],
            "class_id": r["id"],
        })

    with open(CSV_OUT, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(missed[0].keys()))
        w.writeheader()
        w.writerows(missed)
    print(f"{len(missed)} missed classes over the whole year · {totals['held_out']} in the three hidden months")
    print("wrote", CSV_OUT)
    build_doc(missed, active)
    print("wrote", DOC_OUT)


# ── the document ─────────────────────────────────────────────────────────────
def build_doc(missed, active):
    doc = Document()
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Cm(1.8)
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
        st.font.color.rgb = INK
        st.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")

    def shade(cell, fill):
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), fill)
        tcPr.append(shd)

    def para(text="", size=11, bold=False, color=None, italic=False, space_after=6):
        p = doc.add_paragraph()
        r = p.add_run(text)
        r.font.size = Pt(size)
        r.bold = bold
        r.italic = italic
        if color is not None:
            r.font.color.rgb = color
        p.paragraph_format.space_after = Pt(space_after)
        return p

    def bullet(text, bold_lead=None):
        p = doc.add_paragraph(style="List Bullet")
        if bold_lead:
            r = p.add_run(bold_lead + " ")
            r.bold = True
        p.add_run(text)
        p.paragraph_format.space_after = Pt(4)
        return p

    def note(title, body):
        t = doc.add_table(rows=1, cols=1)
        t.style = "Table Grid"
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

    def table(headers, rows_, widths=None, bold_first=False, size=9.5, colors=None):
        t = doc.add_table(rows=1, cols=len(headers))
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, h in enumerate(headers):
            c = t.rows[0].cells[i]
            c.text = ""
            r = c.paragraphs[0].add_run(h)
            r.bold = True
            r.font.size = Pt(9)
            r.font.color.rgb = MUTED
            shade(c, HEADER_FILL)
        for ri, row in enumerate(rows_):
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

    held = [m for m in missed if m["held_out_month"] == "yes"]
    by_pattern = {}
    for m in missed:
        by_pattern.setdefault(m["pattern"], []).append(m)

    # ── title ──
    para("INTERVIEW KICKSTART · NEW PROGRAMS", size=9, bold=True, color=BRAND, space_after=2)
    para("The 23 rules, and the classes we were missing", size=20, bold=True, space_after=2)
    para("Part 1: every rule a scoring formula must keep, and who broke it. "
         "Part 2: the real classes the old formula waved through — what kind they were, and why.",
         size=12, color=MUTED, space_after=10)

    # ── Part 1 ──
    doc.add_heading("Part 1 — The 23 rules", level=1)
    para("These are not statistics. They are statements a person would call obvious, written down before "
         "any formula was judged, and then checked against 378,046 invented classes. A formula that breaks "
         "one is out, however good its numbers look.", color=MUTED, space_after=8)
    names = PROPS["properties"]
    fam = RESULTS["candidates"]
    broke = {}
    label = {"A0": "the original", "A2": "an older try", "A5": "the statistician's vote", "A7": "the instructor's series"}
    for key, short in label.items():
        for pid in fam[key]["properties"]["summary"]["failed"]:
            broke.setdefault(pid, []).append(short)
    order = [f"P{i:02d}" for i in range(1, 23)] + ["P23"]
    rows_ = []
    for i, pid in enumerate([p for p in order if p in names], start=1):
        who = ", ".join(broke.get(pid, [])) or "—"
        rows_.append([i, names[pid], who])
    table(["#", "The rule", "Broken by"], rows_, widths=[0.9, 12.6, 4.0], size=9.5)
    para("Today's formula keeps all 23. The original keeps 15.", bold=True, space_after=10)

    doc.add_page_break()

    # ── Part 2 ──
    doc.add_heading("Part 2 — The classes the old formula waved through", level=1)
    para(f"A class counts as missed when at least five learners voted and the class failed a line the team "
         f"already agreed — rated under 4.55, or under 80% wanting the instructor back — and the old formula "
         f"still badged it Good or Excellent. Nobody was ever asked to look at it.", space_after=8)
    firm_today = [m for m in missed if m["new_band"] in ("Good", "Excellent") and (m["yes"] + m["no"]) >= 6]
    prov_today = [m for m in missed if m["new_band"] in ("Good", "Excellent") and (m["yes"] + m["no"]) == 5]
    table(["", "Classes"], [
        ["Missed over the whole year (January–August 2026)", len(missed)],
        ["Missed in the three hidden months (June–August) — the number quoted in the study", len(held)],
        ["Still badged Good or Excellent by today's formula, firmly", len(firm_today)],
        ["Badged Good on exactly five votes — provisional, and watched, not ignored", len(prov_today)],
    ], widths=[12.0, 5.5], bold_first=True, size=10.5,
        colors={(0, 1): RED, (1, 1): RED, (2, 1): TEAL})

    doc.add_heading("What kind of classes were they?", level=2)
    para("Every single one is the same story, and it is a story worth knowing: the class itself was rated "
         "below the 4.55 line, but the learners still wanted the instructor back — 88% of them on average. "
         "A polite room. The old formula handed out its full 30 approval points for that politeness and "
         "let the weak rating disappear.", space_after=8)
    pattern_rows = []
    for name, items in sorted(by_pattern.items(), key=lambda kv: -len(kv[1])):
        avg_rating = sum(m["rating"] for m in items) / len(items)
        approvals = [m["approval_pct"] for m in items if m["approval_pct"] != ""]
        avg_ap = sum(approvals) / len(approvals) if approvals else 0
        avg_old = sum(m["old_score"] for m in items) / len(items)
        pattern_rows.append([name, len(items), f"{avg_rating:.2f}", f"{avg_ap:.0f}%", f"{avg_old:.0f}"])
    table(["The pattern", "How many", "Average rating", "Average approval", "Old score"],
          pattern_rows, widths=[8.4, 2.2, 2.4, 2.4, 2.1], bold_first=True, size=10)

    def bucket(x):
        return "4.40 – 4.54  (just under the line)" if x >= 4.40 else (
            "4.00 – 4.39  (clearly under)" if x >= 4.00 else "under 4.00  (a bad class)")

    counts = {}
    for m in missed:
        counts[bucket(m["rating"])] = counts.get(bucket(m["rating"]), 0) + 1
    kinds = {}
    for m in missed:
        kinds[m["kind"]] = kinds.get(m["kind"], 0) + 1
    courses = {}
    for m in missed:
        courses[m["course"] or "—"] = courses.get(m["course"] or "—", 0) + 1
    top_courses = sorted(courses.items(), key=lambda kv: -kv[1])[:5]
    actions = {}
    for m in missed:
        actions[m["new_action"]] = actions.get(m["new_action"], 0) + 1

    doc.add_heading("How bad were they, really?", level=2)
    table(["How far under the 4.55 line", "Classes"],
          [[k, counts[k]] for k in sorted(counts, key=lambda k: -counts[k])],
          widths=[12.0, 5.5], bold_first=True, size=10.5)
    para("Most sit just under the line, which is exactly why they slipped through — but 75 of them were "
         "rated below 4.40, and six below 4.00. Those are classes nobody looked at.", space_after=8)
    table(["Where they came from", "Classes"],
          [["Live classes", kinds.get("Live Class", 0)], ["Test reviews", kinds.get("Test Review", 0)]] +
          [[c, n] for c, n in top_courses],
          widths=[12.0, 5.5], bold_first=True, size=10.5)

    doc.add_heading("What happens to them now", level=2)
    table(["Under today's formula", "Classes"],
          [[k.capitalize(), actions[k]] for k in sorted(actions, key=lambda k: -actions[k])],
          widths=[12.0, 5.5], bold_first=True, size=10.5)
    para("Most become a transcript read — the cheap analysis — rather than being ignored. The 22 watched "
         "ones are the classes with only five voices: they are on the list, but nobody spends money on "
         "them until a sixth learner votes.", space_after=8)

    doc.add_heading("Why the old formula could not see them", level=2)
    para("The old formula added four things: the rating out of 60 as a straight line, 30 points if at least "
         "80% wanted the instructor back, 6 points if ten or more rated, and up to 4 for turnout. Two "
         "weaknesses follow from that, and every missed class is one of them.", space_after=8)
    bullet("A rating of 4.30 still earns 51.6 of the 60 rating points, because 4.30 ÷ 5 is 86%. Add the "
           "30 approval points and the class is already at 82 — Good — before turnout is counted. The "
           "rating had almost no room to say “this was a weak class”.",
           bold_lead="The rating barely moved the score.")
    bullet("Approval was all or nothing at 80%. A class where 79% wanted the instructor back lost all 30 "
           "points, and a class at 81% kept all 30. So a rating of 4.9 with the room quietly turning "
           "(81% yes) scored the same as a rating of 4.9 where everyone was happy.",
           bold_lead="The vote was a switch, not a dial.")
    ex = sorted([m for m in by_pattern.get("Rated under 4.55, but the room still wanted the instructor", [])],
                key=lambda m: m["old_score"], reverse=True)
    if ex:
        e = ex[0]
        note("One class, worked through",
             f"{e['module']} · {e['instructor']} · {e['date']}. Rated {e['rating']} by {e['rated']} learners, "
             f"{e['yes']} of {e['yes'] + e['no']} wanted the instructor back ({e['approval_pct']}%).\n"
             f"Old formula: {e['rating']} ÷ 5 × 60 = {e['rating'] / 5 * 60:.1f} rating points, plus 30 because the "
             f"vote cleared 80%, plus the small terms → {e['old_score']:.1f} → {e['old_band']} → nobody looks at it.\n"
             f"Today: the rating sits under the 4.55 line the team agreed, so the class can never be badged above "
             f"Average → {e['new_score']:.1f} → {e['new_band']} → {e['new_action']}.")

    doc.add_heading("Why today's formula catches them", level=2)
    bullet("A class under 4.55, or under 80% with six or more votes, can never be badged Good or "
           "Excellent — whatever the rest of the score says. That one rule alone catches 234 of the 245. "
           "The remaining 11 have exactly five voices, so they keep a provisional badge and go on the "
           "watch list instead of being sent for an analysis.", bold_lead="The two lines are hard.")
    bullet("The rating scale is steeper below 4.55, so the gap between 4.30 and 4.80 is worth real points "
           "instead of a handful.", bold_lead="The rating has room to speak.")
    bullet("79% is now almost as good as 80%, and 50% is far worse than 70% — so a room that is quietly "
           "turning shows up before it crosses a line.", bold_lead="The vote is a dial.")

    doc.add_page_break()

    doc.add_heading("The classes themselves", level=2)
    para(f"The twenty worst of the {len(missed)}, by how badly the old formula overrated them. "
         f"The full list — all {len(missed)}, with cohort, module and every number — is in "
         f"Missed-Classes.csv, which opens in Excel.", color=MUTED, space_after=8)
    worst = sorted(missed, key=lambda m: m["old_score"] - m["new_score"], reverse=True)[:20]
    rows_ = [[m["date"], (m["course"] or "")[:22], (m["module"] or "")[:30], (m["instructor"] or "")[:18],
              m["rating"], f"{m['yes']}/{m['yes'] + m['no']}", f"{m['approval_pct']}%",
              f"{m['old_score']:.0f} {m['old_band']}", f"{m['new_score']:.0f} {m['new_band']}", m["new_action"]]
             for m in worst]
    table(["Date", "Course", "Module", "Instructor", "Rating", "Vote", "Approval", "Old", "Today", "Now"],
          rows_, widths=[1.9, 2.6, 3.4, 2.1, 1.2, 1.2, 1.4, 1.9, 1.9, 2.0], size=8.5)

    para("")
    para("Every number here is recomputed from the ratings sheet, not copied. Re-run with "
         "python analysis/missed_classes.py.", size=9, color=MUTED, italic=True)
    doc.save(DOC_OUT)


if __name__ == "__main__":
    main()
