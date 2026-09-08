"""Run the AI analysis over a list of classes and record what it concluded, so the two formulas
can be judged on our own recordings instead of on argument.

Input: Formula-Test-Tracker.csv with a `vimeo_url` column filled in (any row without a link is
skipped). Output: Formula-Test-Results.csv, one row per class, with the re-class call, the reason
as the PM would read it, and every finding that survived verification.

    python analysis/run_batch_analysis.py                  # transcript only
    python analysis/run_batch_analysis.py --video          # also sample the recording's frames
    python analysis/run_batch_analysis.py --only A         # just one test group
    python analysis/run_batch_analysis.py --limit 3        # a few first, to check cost

Nothing is written to the database: this is a measurement run, not production work. Results are
saved after every class, so a stop or a failure never loses what was already analysed.
"""
import argparse
import csv
import datetime as dt
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "ratings_module_build_kit"))
import config  # noqa: E402

config.load_env()
import engine as E  # noqa: E402
import vimeo as V  # noqa: E402

IN = os.environ.get("TRACKER_CSV") or os.path.join(ROOT, "Formula-Test-Tracker.csv")
OUT = os.environ.get("RESULTS_CSV") or os.path.join(ROOT, "Formula-Test-Results.csv")

FIELDS = ["test", "date", "course", "cohort", "module", "instructor", "kind", "rating",
          "learners_who_rated", "learners_who_attended", "want_instructor_again",
          "karthika_says", "karthika_action", "new_says", "new_action",
          "reclass", "reclass_was", "reclass_reason", "major_findings", "all_findings",
          "who_was_right", "analysed_at", "cost_usd", "error", "class_id"]


def context_of(row):
    return {
        "course": row.get("course") or "(unspecified)",
        "cohort": row.get("cohort") or "(unspecified)",
        "topic": row.get("module") or "(unspecified)",
        "instructor": row.get("instructor") or "(unspecified)",
        "rating": row.get("rating") or "(unspecified)",
        "num_ratings": row.get("learners_who_rated") or None,
    }


def ctx_string(row):
    c = context_of(row)
    return (f"Course: {c['course']}\nCohort: {c['cohort']}\nTopic: {c['topic']}\n"
            f"Instructor: {c['instructor']}\nClass date: {row.get('date','')}\n"
            f"Learner rating: {c['rating']} (from {c['num_ratings'] or 'unknown'} learners)\n"
            f"Planned agenda: (not provided)")


def verdict(row, reclass):
    """Who the analysis supports, in the terms of the two-sided test."""
    if not reclass:
        return ""
    if row["test"] == "A":          # ours said look, Karthika's said nobody looks
        return {"yes": "the new formula", "maybe": "leaning to the new formula",
                "no": "Karthika's formula"}.get(reclass, "")
    return {"yes": "Karthika's formula", "maybe": "leaning to Karthika's formula",
            "no": "the new formula"}.get(reclass, "")


def load_done():
    if not os.path.isfile(OUT):
        return {}
    with open(OUT, encoding="utf-8-sig") as fh:
        return {r["class_id"]: r for r in csv.DictReader(fh) if r.get("analysed_at")}


def save(rows):
    with open(OUT, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--video", action="store_true", help="also sample the recording's frames")
    ap.add_argument("--only", choices=["A", "B"], help="run one test group only")
    ap.add_argument("--limit", type=int, help="stop after this many classes")
    ap.add_argument("--redo", action="store_true", help="re-analyse classes already done")
    args = ap.parse_args()

    with open(IN, encoding="utf-8-sig") as fh:
        todo = list(csv.DictReader(fh))
    if "vimeo_url" not in (todo[0] if todo else {}):
        print(f"No 'vimeo_url' column in {os.path.basename(IN)}.")
        print("Add one, paste each class's recording link, and run this again.")
        return
    done = {} if args.redo else load_done()
    rows_out = list(done.values())

    queue = [r for r in todo
             if (r.get("vimeo_url") or "").strip()
             and (not args.only or r["test"] == args.only)
             and (args.redo or r["class_id"] not in done)]
    if args.limit:
        queue = queue[: args.limit]
    print(f"{len(queue)} class(es) to analyse"
          + (f" · {len(done)} already done" if done else "")
          + (" · with video frames" if args.video else " · transcript only"))

    for n, row in enumerate(queue, 1):
        label = f"{row['module'][:44]} · {row['instructor']} · {row['date']}"
        print(f"\n[{n}/{len(queue)}] {label}")
        out = {k: row.get(k, "") for k in FIELDS if k in row}
        out["analysed_at"] = ""
        t0 = time.time()
        try:
            info = V.fetch_transcript(row["vimeo_url"].strip())
            cues = E.parse_cues(info["text"])
            print(f"    transcript: {len(info['text']):,} chars, {len(cues)} cues")
            kind = "ars" if "review" in (row.get("kind") or "").lower() else "live_class"
            result, meta = E.analyse_cues(cues, ctx_string(row), kind)
            rc = result.get("reclass") or {}
            flags = result.get("flags") or []
            majors = [f"{f.get('flag')} ({f.get('severity')})" for f in flags
                      if isinstance(f, dict) and f.get("severity") == "major"]
            out.update({
                "reclass": rc.get("recommended", ""),
                "reclass_was": rc.get("softened_from", ""),
                "reclass_reason": rc.get("reason", ""),
                "major_findings": "; ".join(majors) or "none",
                "all_findings": "; ".join(
                    f"{f.get('flag')}:{f.get('severity')}" for f in flags if isinstance(f, dict)),
                "who_was_right": verdict(row, rc.get("recommended", "")),
                "analysed_at": dt.datetime.now().isoformat(timespec="seconds"),
                "cost_usd": f"{meta.get('cost_usd', 0):.2f}" if meta.get("cost_usd") else "",
                "error": "",
            })
            print(f"    re-class: {out['reclass']}"
                  + (f"  (was '{out['reclass_was']}' before verification)" if out["reclass_was"] else "")
                  + f"   majors: {out['major_findings']}")
            print(f"    reason: {out['reclass_reason'][:160]}")
        except Exception as e:  # noqa: BLE001
            out["error"] = f"{type(e).__name__}: {e}"[:300]
            print(f"    FAILED: {out['error']}")
        print(f"    took {time.time() - t0:.0f}s")
        rows_out = [r for r in rows_out if r.get("class_id") != out.get("class_id")] + [out]
        save(rows_out)

    done_rows = [r for r in rows_out if r.get("analysed_at")]
    print(f"\nwrote {OUT}")
    if done_rows:
        tally = {}
        for r in done_rows:
            key = (r.get("test", "?"), r.get("reclass", "?"))
            tally[key] = tally.get(key, 0) + 1
        print("\nwhere it stands:")
        for (test, call), k in sorted(tally.items()):
            side = "ours said look, Karthika's said nobody looks" if test == "A" \
                else "Karthika's said watch the video, ours said no need"
            print(f"   test {test} ({side}): re-class {call} on {k} class(es)")


if __name__ == "__main__":
    main()
