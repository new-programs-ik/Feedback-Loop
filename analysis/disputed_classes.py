"""The classes the two formulas disagree about, so a video analysis can settle the argument.

Karthika's formula says Good or Excellent, so nobody looks. The new formula says Bad, so it wants
a video analysis. If the video analysis then says the class should be re-taught, the new formula
was right. If it says the class was fine, Karthika's formula was right.

Everything is computed with 4.6 as the acceptable rating (the VP's final number, 8 Sep 2026) and
with the recommended two-part formula: the rating out of 70, whether learners want the instructor
again out of 30, and no instructor record. The app is still running the older settings.

    python analysis/disputed_classes.py

Writes Disputed-Classes.csv (gitignored: it carries instructor names and ratings).
"""
import copy
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "ratings_module_build_kit"))
import config  # noqa: E402

config.load_env()
import ratings_store as ST  # noqa: E402
from sentiment_score import score  # noqa: E402

ACTION = {"video": "watch the video", "transcript": "read the transcript",
          "watch": "watch list only", "none": "nobody looks"}

OUT = os.environ.get("DISPUTED_CSV") or os.path.join(ROOT, "Disputed-Classes.csv")
FIXTURES = json.load(open(os.path.join(ROOT, "supabase", "fixtures", "scoring_configs.json"), encoding="utf-8"))
LINE = 4.6

SQL = """
select cr.class_date, coalesce(c.name, cr.course_label) as course, co.name as cohort,
       coalesce(t.name, cr.topic) as module, coalesce(cr.instructor_canonical, cr.instructor) as instructor,
       cr.session_kind, cr.rating, cr.num_ratings, cr.attended, cr.yes_votes, cr.no_votes,
       cr.track_avg, cr.escalated, cr.id
  from class_ratings cr
  left join courses c on c.id = cr.course_id
  left join cohorts co on co.id = cr.cohort_id
  left join topics t on t.id = cr.topic_id
 order by cr.class_date desc
"""


def at_line(cfg, line):
    """The recommended formula: two parts only (the rating out of 70, the vote out of 30), with
    the team's acceptable rating moved to `line`. The instructor's past record is switched off -
    it changed what we do for 2 classes out of 2,779, so it is not worth the argument it costs."""
    out = copy.deepcopy(cfg)
    out["rating"]["line"] = line
    out["caps"]["rating_line"] = line
    out["weights"]["rating"] = 70
    out["weights"]["approval"] = 30
    out["weights"]["track"] = 0
    out["track"]["mode"] = "off"
    return out


def main():
    conn = ST.connect()
    cur = conn.cursor()
    cur.execute("select version, config from scoring_configs where status = 'active'")
    version, live = cur.fetchone()
    cur.execute(SQL)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()

    old_cfg = copy.deepcopy(FIXTURES["C0"])
    old_cfg["sample"]["target"] = 5          # her document's own table: "at least 5 learners"
    new_cfg = at_line(live, LINE)
    disputed = []
    counts = {"new_video": 0, "old_looks": 0, "agree_video": 0}
    for r in rows:
        if r["rating"] is None:
            continue
        inp = {
            "rating": float(r["rating"]), "num_ratings": r["num_ratings"], "attended": r["attended"],
            "yes_votes": r["yes_votes"], "no_votes": r["no_votes"], "escalated": bool(r["escalated"]),
            "track_avg": float(r["track_avg"]) if r["track_avg"] is not None else None,
        }
        old = score(inp, old_cfg)
        new = score(inp, new_cfg)
        if new["action"] == "video":
            counts["new_video"] += 1
            if old["action"] == "video":
                counts["agree_video"] += 1
        if old["action"] in ("video", "transcript"):
            counts["old_looks"] += 1
        looks = ("video", "transcript")
        if new["action"] == "video" and old["action"] not in looks:
            tier = "1. New says WATCH THE VIDEO, Karthika says nobody looks"
        elif new["action"] == "transcript" and old["action"] not in looks:
            tier = "2. New says read the transcript, Karthika says nobody looks"
        elif old["action"] == "video" and new["action"] in ("none", "watch"):
            tier = "3. Karthika spends a video, new says it does not need one"
        else:
            continue
        yes, no = r["yes_votes"] or 0, r["no_votes"] or 0
        votes = yes + no
        disputed.append({
            "test_first": tier,
            "date": r["class_date"].isoformat(),
            "course": r["course"],
            "cohort": r["cohort"] or "",
            "module": r["module"],
            "instructor": r["instructor"],
            "kind": r["session_kind"],
            "rating": round(float(r["rating"]), 2),
            "learners_who_rated": r["num_ratings"],
            "learners_who_attended": r["attended"],
            "want_instructor_again": f"{yes} of {votes}" if votes else "no approval responses",
            "want_instructor_again_pct": round(100 * yes / votes, 1) if votes else "",
            "karthika_score": old["score"],
            "karthika_says": (old["band"] or "").title(),
            "karthika_action": ACTION[old["action"]],
            "new_score": new["score"],
            "new_says": (new["band"] or "").title(),
            "new_action": ACTION[new["action"]],
            "why_they_disagree": why(float(r["rating"]), yes, votes, r["num_ratings"], r["attended"]),
            "video_analysis_says": "",          # you fill this in after running the analysis
            "reclass_needed": "",               # yes / no
            "class_id": r["id"],
        })

    disputed.sort(key=lambda d: (d["test_first"], d["rating"], -(d["learners_who_rated"] or 0)))
    with open(OUT, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(disputed[0].keys()))
        w.writeheader()
        w.writerows(disputed)

    print(f"quality line used: {LINE}   (the app is still running 4.55)")
    print(f"classes the new formula sends for a video analysis: {counts['new_video']}")
    print(f"   of those, Karthika's formula also wanted a look: {counts['agree_video']}")
    tiers = {}
    for d in disputed:
        tiers[d["test_first"]] = tiers.get(d["test_first"], 0) + 1
    print(f"DISAGREEMENTS: {len(disputed)}")
    for t in sorted(tiers):
        print(f"   {tiers[t]:4d}  {t}")
    print("wrote", OUT)
    print("\nthe five to test first:")
    for d in [x for x in disputed if x["test_first"].startswith("1.")][:10]:
        print(f"   {d['date']}  {d['rating']:.2f}  approval {d['want_instructor_again']:>9s}  "
              f"| Karthika {d['karthika_score']:.0f} {d['karthika_says']:9s} | new {d['new_score']:.0f} {d['new_says']}"
              f"  | {d['module'][:38]} · {d['instructor']}")


def why(rating, yes, votes, rated, attended):
    approval = 100 * yes / votes if votes else None
    bits = [f"{rated or 0} of the {attended or 0} learners who attended rated it {rating:.2f}"]
    if approval is not None:
        bits.append(f"instructor approval {yes} of {votes} = {approval:.0f}%")
    bits.append(f"Karthika's formula gave {rating / 5 * 60:.1f} of 60 for that rating"
                + (" and all 30 approval points" if approval is not None and approval >= 80 else ""))
    return " · ".join(bits)


if __name__ == "__main__":
    main()
