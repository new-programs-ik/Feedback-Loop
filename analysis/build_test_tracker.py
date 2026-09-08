"""The test tracker: the two lists of classes whose video analysis settles which formula is right,
with a column for what the analysis said and space for the verdict.

  Test A - our formula says look, Karthika's says nobody looks
  Test B - Karthika's says spend a video, our formula says it does not need one

Writes Formula-Test-Tracker.xlsx-style CSV plus a short document.

    python analysis/build_test_tracker.py
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IN = os.path.join(ROOT, "Disputed-Classes.csv")
OUT = os.environ.get("TRACKER_CSV") or os.path.join(ROOT, "Formula-Test-Tracker.csv")

rows = list(csv.DictReader(open(IN, encoding="utf-8-sig")))
for r in rows:
    r["rating_f"] = float(r["rating"])
    r["rated_n"] = int(r["learners_who_rated"] or 0)
    r["att_n"] = int(r["learners_who_attended"] or 0)

A = sorted([r for r in rows if r["test_first"].startswith("1.")], key=lambda r: r["rating_f"])
B = sorted([r for r in rows if r["test_first"].startswith("3.")],
           key=lambda r: (-r["rating_f"], -r["att_n"]))[:8]

FIELDS = ["test", "what_we_are_checking", "date", "course", "cohort", "module", "instructor", "kind",
          "rating", "learners_who_rated", "learners_who_attended", "want_instructor_again",
          "want_instructor_again_pct", "karthika_says", "karthika_action", "new_says", "new_action",
          "analysis_reclass", "analysis_found", "who_was_right", "class_id"]

CHECK_A = ("If the analysis finds real problems, the old formula was hiding them "
           "(it said nobody needed to look)")
CHECK_B = ("If the analysis finds nothing, the old formula wasted a video "
           "(it said Bad on a class rated 4.6+ judged by a handful of learners)")

out = []
for tag, group, check in (("A", A, CHECK_A), ("B", B, CHECK_B)):
    for r in group:
        out.append({
            "test": tag,
            "what_we_are_checking": check,
            "date": r["date"], "course": r["course"], "cohort": r["cohort"], "module": r["module"],
            "instructor": r["instructor"], "kind": r["kind"], "rating": r["rating"],
            "learners_who_rated": r["learners_who_rated"],
            "learners_who_attended": r["learners_who_attended"],
            "want_instructor_again": r["want_instructor_again"],
            "want_instructor_again_pct": r["want_instructor_again_pct"],
            "karthika_says": f"{float(r['karthika_score']):.0f} · {r['karthika_says']}",
            "karthika_action": r["karthika_action"],
            "new_says": f"{float(r['new_score']):.0f} · {r['new_says']}",
            "new_action": r["new_action"],
            "analysis_reclass": "",     # yes / maybe / no
            "analysis_found": "",       # what it actually found
            "who_was_right": "",        # new formula / Karthika / neither
            "class_id": r["class_id"],
        })

with open(OUT, "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=FIELDS)
    w.writeheader()
    w.writerows(out)

print(f"Test A (ours says look, Karthika says nobody looks): {len(A)} classes")
print(f"Test B (Karthika says video, ours says no need):     {len(B)} classes")
print("wrote", OUT)
