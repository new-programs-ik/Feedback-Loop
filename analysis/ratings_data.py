"""Shared loader for the confidential ratings workbook.

One place that knows how to read the sheet, name the course, and tell a Live Class from a Test
Review - so every report agrees on the numbers. Local use only; the workbook is never committed.
"""
import datetime as dt
import os

import openpyxl

# The workbook lives in the project root, one level above this file - resolve it absolutely so the
# reports run from any working directory.
BOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "the rating sheet .xlsx")
SHEETS = ["MLSU_Live_Class_Poll", "Agentic_AI_Live_Class_Poll"]
GOOD = 4.55         # at or above this, the class is fine (team decision, Sep 2026; was 4.5)

# Cohort text -> the course a PM would name. First match wins: cohort strings often glue several
# programmes together ("Agentic AI SWE Deprecated, Forward Deployed Engineering - Early...").
COURSE_RULES = [
    ("PwC x IK Agentic AI Accelerator", ["pwc"]),
    ("FDE (Forward Deployed Engineering)", ["forward deployed engineering", "fde program"]),
    ("Advanced ML Program", ["advanced machine learning"]),
    ("ML Flagship (IND)", ["machine learning flagship"]),
    ("ML Program", ["machine learning program"]),
    ("AI Data Science SwitchUp", ["ai data science switchup"]),
    ("Transformative GenAI", ["transformative genai"]),
    ("Applied Agentic AI", ["applied agentic ai", "agentic ai"]),
]


def course_of(cohort, type_):
    text = (cohort or "").lower()
    for label, keys in COURSE_RULES:
        if any(k in text for k in keys):
            return label
    t = (type_ or "").lower()
    if "genai" in t:
        return "Transformative GenAI"
    if "agentic" in t:
        return "Applied Agentic AI"
    if "switchup" in t or "mlsu" in t:
        return "ML SwitchUp (unmapped cohort)"
    return "Other / unmapped"


def kind_of(type_):
    t = (type_ or "").lower()
    if "review" in t:
        return "Test Review"
    if "live" in t:
        return "Live Class"
    return "Other"


KIND_CODES = {"live class", "test review session", "review session"}


def region_of(type_):
    """'IND' when the class type says India, else 'US' (the sheet never says US explicitly)."""
    return "IND" if "india" in (type_ or "").lower() else "US"


def load(lo, hi, strict=True):
    """Every class with a session date in [lo, hi], de-duplicated across the sheets.

    strict=False keeps the rows the strict loader drops (responses > attended, zero attendance)
    and marks them with r["flags"], so edge-case studies can see them.

    The Agentic tab's "Topic" column holds the SESSION KIND ("Live Class"); the real class name is
    its "Class" column. So when both headers exist, "Class" wins - otherwise two thirds of the
    class names would be a kind code (the bug found on 3 Sep 2026).
    """
    wb = openpyxl.load_workbook(BOOK, read_only=True, data_only=True)
    out, seen = [], set()
    for name in SHEETS:
        rows = list(wb[name].iter_rows(values_only=True))
        idx = {}
        for i, h in enumerate(rows[0]):
            h = str(h).strip() if h is not None else ""
            if h and h not in idx:
                idx[h] = i
        d = idx["Session Date"]
        for r in rows[1:]:
            if len(r) <= d or not isinstance(r[d], dt.datetime) or not (lo <= r[d] <= hi):
                continue

            def g(k):
                return r[idx[k]] if k in idx and len(r) > idx[k] else None

            flags = []
            rating, resp, att = g("Overall Average"), g("Responses"), g("# Students Attended")
            if not isinstance(rating, (int, float)):
                continue
            if not isinstance(att, (int, float)) or not att:
                if strict:
                    continue
                att, flags = 0.0, flags + ["no_attendance"]
            if resp and att and resp > att:
                if strict:
                    continue    # data-entry error (e.g. 7 ratings in a class of 1) - 2 rows in Jan-Aug
                flags.append("responses_gt_attended")
            topic = str(g("Class") or g("Topic") or "").strip()
            if topic.lower() in KIND_CODES:
                topic = str(g("Topic") or "").strip() if g("Class") is None else topic
            instructor = str(g("Instructor") or "").strip()
            key = (r[d], instructor, topic, float(rating))
            if key in seen:
                continue
            seen.add(key)
            # The approval vote - "would you want this instructor to take the class again?" -
            # as Yes/No counts per class. Yes+No equals Responses on every Jan-Aug row.
            yes, no = g("Yes"), g("No")
            yes = float(yes) if isinstance(yes, (int, float)) else None
            no = float(no) if isinstance(no, (int, float)) else None
            votes = (yes + no) if yes is not None and no is not None else 0
            out.append({
                "date": r[d], "type": g("Type"),
                "course": course_of(str(g("Cohorts") or ""), str(g("Type") or "")),
                "kind": kind_of(str(g("Type") or "")),
                "topic": topic, "instructor": instructor,
                "rating": float(rating), "responses": float(resp or 0),
                "attended": float(att), "pct": (float(resp or 0) / float(att) * 100) if att else 0.0,
                "yes": yes, "no": no,
                "approval": (yes / votes * 100) if votes else None,
                "region": region_of(str(g("Type") or "")), "flags": flags,
            })
    return sorted(out, key=lambda r: r["date"])
