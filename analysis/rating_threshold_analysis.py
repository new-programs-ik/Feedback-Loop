"""Rating-participation threshold study - 16-30 Aug 2026.

Question: the 80% "rating participation" gate we invented for deciding when to run an AI
analysis does not match reality. What does the real data say the trigger should be?

Reads the confidential ratings workbook (never committed) and writes a local report only.
"""
import datetime as dt
import json
import statistics as st
from collections import defaultdict

import openpyxl

BOOK = "the rating sheet .xlsx"
LO, HI = dt.datetime(2026, 8, 16), dt.datetime(2026, 8, 30, 23, 59, 59)
SHEETS = ["MLSU_Live_Class_Poll", "Agentic_AI_Live_Class_Poll"]
GOOD = 4.5           # the rating line we currently draw

# Cohort text -> the course a PM would name. Order matters: first match wins, because cohort
# strings often glue several programmes together ("Agentic AI SWE Deprecated, FDE - Early...").
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
    t = (type_ or "").lower()                      # fall back to the session Type
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


def load():
    wb = openpyxl.load_workbook(BOOK, read_only=True, data_only=True)
    out = []
    for name in SHEETS:
        rows = list(wb[name].iter_rows(values_only=True))
        idx = {}
        for i, h in enumerate(rows[0]):
            h = str(h).strip() if h is not None else ""
            if h and h not in idx:
                idx[h] = i
        d = idx["Session Date"]
        for r in rows[1:]:
            if len(r) <= d or not isinstance(r[d], dt.datetime) or not (LO <= r[d] <= HI):
                continue

            def g(k):
                return r[idx[k]] if k in idx and len(r) > idx[k] else None

            rating, resp, att = g("Overall Average"), g("Responses"), g("# Students Attended")
            if not isinstance(rating, (int, float)) or not isinstance(att, (int, float)) or not att:
                continue
            out.append({
                "sheet": name, "date": r[d], "type": g("Type"),
                "course": course_of(str(g("Cohorts") or ""), str(g("Type") or "")),
                "kind": kind_of(str(g("Type") or "")),
                "topic": str(g("Topic") or g("Class") or "").strip(),
                "instructor": str(g("Instructor") or "").strip(),
                "rating": float(rating), "responses": float(resp or 0),
                "attended": float(att), "pct": float(resp or 0) / float(att) * 100,
            })
    return out


def pct_stats(rows):
    v = [r["pct"] for r in rows]
    return (st.mean(v), st.median(v)) if v else (0.0, 0.0)


def main():
    rows = load()

    # de-duplicate: the same session can appear in both sheets
    seen, uniq = set(), []
    for r in rows:
        key = (r["date"], r["instructor"], r["topic"], r["rating"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    dupes = len(rows) - len(uniq)
    rows = uniq

    bad = [r for r in rows if r["rating"] < GOOD]
    good = [r for r in rows if r["rating"] >= GOOD]

    print("=" * 78)
    print("RATING PARTICIPATION STUDY - %s to %s" % (LO.strftime("%d %b"), HI.strftime("%d %b %Y")))
    print("=" * 78)
    print("Classes analysed : %d   (duplicates removed: %d)" % (len(rows), dupes))
    print("Source sheets    : %s" % ", ".join(SHEETS))
    days = (HI - LO).days + 1
    print("Window           : %d days  ->  %.0f classes/week" % (days, len(rows) / days * 7))

    print("\n" + "-" * 78)
    print("1. THE HEADLINE - does rating participation tell you anything about quality?")
    print("-" * 78)
    for label, grp in (("Rating >= 4.5 (fine)", good), ("Rating <  4.5 (needs a look)", bad)):
        m, med = pct_stats(grp)
        rs = [r["responses"] for r in grp]
        print("  %-30s  n=%3d  (%4.1f%% of classes)" % (label, len(grp), len(grp) / len(rows) * 100))
        print("  %-30s  avg rated%% = %5.1f   median = %5.1f   avg responses = %4.1f   median responses = %4.1f"
              % ("", m, med, st.mean(rs), st.median(rs)))
    gm, _ = pct_stats(good)
    bm, _ = pct_stats(bad)
    print("\n  Difference in avg rated%%: %+.1f points (%s for the bad classes)"
          % (bm - gm, "lower" if bm < gm else "higher"))

    print("\n" + "-" * 78)
    print("2. WHAT THE 80%% GATE WOULD ACTUALLY DO to the classes that need attention")
    print("-" * 78)
    print("  Classes below 4.5 in the window            : %d" % len(bad))
    for t in (80, 70, 60, 50, 40, 30):
        keep = [r for r in bad if r["pct"] >= t]
        print("    participation >= %2d%%  -> video for %3d (%5.1f%%)   transcript-only for %3d"
              % (t, len(keep), len(keep) / len(bad) * 100, len(bad) - len(keep)))

    print("\n" + "-" * 78)
    print("3. BY CATEGORY")
    print("-" * 78)
    print("  %-14s%4s%5s%7s%12s%12s%13s%12s"
          % ("Category", "n", "bad", "bad%", "avg rating", "avg rated%", "rated% good", "rated% bad"))
    for kind in ("Live Class", "Test Review", "Other"):
        grp = [r for r in rows if r["kind"] == kind]
        if not grp:
            continue
        b = [r for r in grp if r["rating"] < GOOD]
        g = [r for r in grp if r["rating"] >= GOOD]
        print("  %-14s%4d%5d%6.1f%%%12.2f%11.1f%%%12.1f%%%11.1f%%"
              % (kind, len(grp), len(b), len(b) / len(grp) * 100,
                 st.mean([r["rating"] for r in grp]), st.mean([r["pct"] for r in grp]),
                 pct_stats(g)[0] if g else 0, pct_stats(b)[0] if b else 0))

    print("\n" + "-" * 78)
    print("4. BY COURSE  (each course split into Live Class / Test Review)")
    print("-" * 78)
    by = defaultdict(list)
    for r in rows:
        by[r["course"]].append(r)
    print("  %-36s%-13s%4s%5s%9s%12s%12s"
          % ("Course", "cat", "n", "bad", "avg rtg", "avg rated%", "rated% bad"))
    for course in sorted(by, key=lambda c: -len(by[c])):
        for kind in ("Live Class", "Test Review", "Other"):
            grp = [r for r in by[course] if r["kind"] == kind]
            if not grp:
                continue
            b = [r for r in grp if r["rating"] < GOOD]
            print("  %-36s%-13s%4d%5d%9.2f%11.1f%%%11.1f%%"
                  % (course, kind, len(grp), len(b), st.mean([r["rating"] for r in grp]),
                     st.mean([r["pct"] for r in grp]), pct_stats(b)[0] if b else 0))
        tot = by[course]
        tb = [r for r in tot if r["rating"] < GOOD]
        print("  %-36s%-13s%4d%5d%9.2f%11.1f%%%11.1f%%"
              % ("", "ALL", len(tot), len(tb), st.mean([r["rating"] for r in tot]),
                 st.mean([r["pct"] for r in tot]), pct_stats(tb)[0] if tb else 0))
        print()

    print("-" * 78)
    print("5. WORKLOAD - how many classes would we actually analyse?")
    print("-" * 78)
    wk1 = [r for r in rows if r["date"] < dt.datetime(2026, 8, 23)]
    wk2 = [r for r in rows if r["date"] >= dt.datetime(2026, 8, 23)]
    for label, grp in (("16-22 Aug", wk1), ("23-30 Aug", wk2)):
        b = [r for r in grp if r["rating"] < GOOD]
        print("  %s:  %3d classes   %3d below 4.5  (%.1f%%)"
              % (label, len(grp), len(b), len(b) / len(grp) * 100))
    print("  => on average %.0f classes below 4.5 per week" % (len(bad) / 2))

    print("\n" + "-" * 78)
    print("6. IS THE RATING TRUSTWORTHY? responses behind the low-rated classes")
    print("-" * 78)
    for lo_, hi_ in ((1, 2), (3, 4), (5, 9), (10, 19), (20, 10 ** 6)):
        grp = [r for r in bad if lo_ <= r["responses"] <= hi_]
        if not grp:
            continue
        label = ("%d-%d" % (lo_, hi_)) if hi_ < 10 ** 6 else ("%d+" % lo_)
        print("  responses %6s: %3d classes (%5.1f%% of the bad ones)   avg rating %.2f   avg rated%% %.1f%%"
              % (label, len(grp), len(grp) / len(bad) * 100,
                 st.mean([r["rating"] for r in grp]), st.mean([r["pct"] for r in grp])))

    print("\n" + "-" * 78)
    print("7. THE CASE YOU RAISED - rating 3.75, 15 attended, 7 rated (46.7%)")
    print("-" * 78)
    like = [r for r in bad if r["responses"] >= 5 and r["pct"] < 80]
    print("  Classes below 4.5 with >=5 responses but under 80%% participation: %d" % len(like))
    print("  The 80%% rule would send every one of these to transcript-only (%.0f%% of all low-rated)."
          % (len(like) / len(bad) * 100))
    worst = sorted(like, key=lambda r: r["rating"])[:12]
    print("\n  The %d worst of them (the classes you say must be analysed):" % len(worst))
    print("    %7s%6s%5s%8s  %-12s %s" % ("rating", "resp", "att", "rated%", "category", "course"))
    for r in worst:
        print("    %7.2f%6.0f%5.0f%7.1f%%  %-12s %s"
              % (r["rating"], r["responses"], r["attended"], r["pct"], r["kind"], r["course"]))

    payload = [{k: (v.isoformat() if isinstance(v, dt.datetime) else v) for k, v in r.items()}
               for r in rows]
    with open("analysis/window_rows.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1)
    print("\n  (clean rows written to analysis/window_rows.json - %d classes)" % len(rows))


if __name__ == "__main__":
    main()
