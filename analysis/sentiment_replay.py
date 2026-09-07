"""Replay: every class of Jan-Aug 2026 through every candidate C0-C5, using the contract itself.

Writes analysis/out/replay_<cfg>.csv (one row per class: score, band, action, provisional, flags,
components, the guarded inputs, the reason sentence, today's rule) and replay_summary.json (band
mix, action counts, analyses per week, the Y2 counts, the Y4 shares, the Y5 slices, the per-course
workload and the plan's famous cases under every candidate).
"""
import os
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sentiment_common import (Study, Engine, OUT, LINE, BAR, VOICES, BAND_LABEL, BANDS, COST,  # noqa: E402
                              describe_cfg, write_csv, write_json)
from sentiment_score import CONFIGS, reason  # noqa: E402
from approval_weights import score_rating, score_approval, score_track  # noqa: E402
from approval_rule import verdict_v2  # noqa: E402


def rule_v2(r):
    """Today's shipped rule (v2), exactly as analysis/approval_rule.py computes it - raw names."""
    rr = {"responses": r["responses"], "rating": r["rating"], "approval": r["approval"], "pct": r["pct"],
          "R": score_rating(r["rating"]), "A": score_approval(r["approval"]), "T": score_track(r["track_instructor_raw"])}
    return verdict_v2(rr)


HEADER = ["id", "date", "course", "kind", "region", "topic", "instructor_raw", "instructor_resolved", "rating", "responses",
          "attended", "reach_pct", "yes", "no", "votes", "approval", "track_avg", "prior_rating", "prior_approval", "prior_source",
          "score", "band", "action", "provisional", "flags", "comp_rating", "comp_approval", "comp_sample", "comp_reach",
          "comp_track", "adj_rating", "adj_approval", "under_line_raw", "under_bar_raw", "rule_v2_today", "reason", "data_flags"]


def famous_cases(rows):
    """The plan's worked examples, matched to the nearest real class."""
    def nearest(pred, key):
        cands = [r for r in rows if pred(r)]
        return min(cands, key=key) if cands else None
    return {
        "4.87 rated, 2 of 3 yes": nearest(lambda r: r["votes"] == 3 and r["yes"] == 2, lambda r: abs(r["rating"] - 4.87)),
        "4.30 rated, 60% approval": nearest(lambda r: r["votes"] >= 5 and 55 <= r["approval"] <= 65, lambda r: abs(r["rating"] - 4.30)),
        "4.30 rated, everyone approves": nearest(lambda r: r["votes"] >= 5 and r["approval"] >= 100, lambda r: abs(r["rating"] - 4.30)),
        "3.60 rated, everyone approves": nearest(lambda r: r["votes"] >= 5 and r["approval"] >= 100, lambda r: abs(r["rating"] - 3.60)),
        "4.80 rated, 6 of 10 yes": nearest(lambda r: r["votes"] >= 8 and 55 <= r["approval"] <= 65, lambda r: abs(r["rating"] - 4.80)),
    }


def main():
    t0 = time.time()
    S = Study()
    E = Engine(S)
    rows = S.rows
    v2 = [rule_v2(r) for r in rows]
    v2c = Counter(v2)
    summary = {"meta": {"rows": len(rows), "weeks": round(S.weeks, 2), "window": "2026-01-01 .. 2026-08-31",
                        "aliases_applied": len(S.alias), "pairs_resolved": len(S.pairs["resolved"]), "pairs_raw": len(S.pairs["raw"]),
                        "flagged_rows": sum(1 for r in rows if r["flags"]),
                        "rule_v2_today": {"actions": dict(v2c), "per_week": (v2c["video"] + v2c["transcript"]) / S.weeks,
                                          "videos_per_week": v2c["video"] / S.weeks, "transcripts_per_week": v2c["transcript"] / S.weeks}},
               "configs": {}}
    fam = famous_cases(rows)
    summary["famous_cases"] = {label: (None if r is None else {"id": r["id"], "date": r["date"].date().isoformat(), "course": r["course"],
                                                               "rating": r["rating"], "yes": r["yes"], "no": r["no"], "approval": round(r["approval"], 1),
                                                               "responses": r["responses"], "attended": r["attended"], "by_config": {}})
                               for label, r in fam.items()}
    for key, cfg in CONFIGS.items():
        t1 = time.time()
        res = S.run_contract(cfg)                 # the contract, row by row
        m = E.metrics(cfg)                        # the yardsticks (fast path, verified against the contract)
        assert E.verify(cfg) == 0, "fast path disagrees with the contract for " + key
        out = []
        lifted = Counter()
        for r, x, v in zip(rows, res, v2):
            c = x["components"]
            adj = x["adjusted"]
            under_line = r["rating"] < LINE
            under_bar = r["approval"] is not None and r["approval"] < BAR
            if r["votes"] >= VOICES and x["band"] in ("good", "excellent") and (under_line or under_bar):
                # a class the contract shows as fine although a raw line is missed: because the guard
                # lifted the guarded value over the line (or because the config has no hard lines)
                if cfg["caps"]["rating_line"] is None:
                    lifted["no_hard_lines"] += 1
                else:
                    lifted["guard_lift_rating" if under_line else "guard_lift_approval"] += 1
            out.append([r["id"], r["date"].date().isoformat(), r["course"], r["kind"], r["region"], r["topic"], r["instructor_raw"],
                        r["instructor_resolved"], r["rating"], int(r["responses"]), int(r["attended"]), round(r["pct"], 1), int(r["yes"]),
                        int(r["no"]), int(r["votes"]), round(r["approval"], 2), (round(r["track_instructor_resolved"], 3) if r["track_instructor_resolved"] is not None else ""),
                        round(r["prior_rating"], 3), round(r["prior_approval"], 1), r["prior_source"],
                        x["score"], BAND_LABEL[x["band"]], x["action"], int(x["provisional"]), " ".join(x["flags"]),
                        c.get("rating"), c.get("approval"), c.get("sample"), c.get("reach"), c.get("track"),
                        adj["rating"], adj["approval"], int(under_line), int(under_bar), v, reason(S.inputs[r["id"]], x, cfg), " ".join(r["flags"])])
        write_csv(os.path.join(OUT, "replay_%s.csv" % key), HEADER, out)
        # per-course workload
        per_course = defaultdict(Counter)
        for r, x in zip(rows, res):
            per_course[r["course"]][x["action"]] += 1
            per_course[r["course"]]["classes"] += 1
        course_rows = {c: {"classes": v["classes"], "video": v["video"], "transcript": v["transcript"], "watch": v["watch"],
                           "per_week": (v["video"] + v["transcript"]) / S.weeks,
                           "cost_per_week": (v["video"] * COST["video"] + v["transcript"] * COST["transcript"]) / S.weeks}
                       for c, v in sorted(per_course.items(), key=lambda kv: -kv[1]["classes"])}
        # famous cases under this config
        for label, r in fam.items():
            if r is not None:
                x = res[r["id"]]
                summary["famous_cases"][label]["by_config"][key] = {"score": x["score"], "band": BAND_LABEL[x["band"]], "action": x["action"],
                                                                     "provisional": x["provisional"], "reason": reason(S.inputs[r["id"]], x, cfg)}
        m["Y2"]["shown_fine_but_under_a_raw_line"] = dict(lifted)
        summary["configs"][key] = {"name": cfg["name"], "description": describe_cfg(cfg), "config": cfg, "metrics": m,
                                   "per_course": course_rows, "seconds": round(time.time() - t1, 1)}
        print("%s %-40s bands %s | flips %.1f%% (verdict %.1f%%) | false comfort %.1f%% (%s) | %.1f/wk | scorecard %s%s" % (
            key, cfg["name"][:40], m["Y4"]["band_counts"], m["Y1"]["flip_all"], m["Y1"]["verdict_all"], m["Y2"]["false_comfort_share"],
            dict(lifted), m["Y4"]["per_week"], m["scorecard"]["total"], (" VETO: " + "; ".join(m["scorecard"]["vetoes"])) if m["scorecard"]["vetoes"] else ""))
    write_json(os.path.join(OUT, "replay_summary.json"), summary)
    print("replay done in %.1fs -> %s" % (time.time() - t0, OUT))


if __name__ == "__main__":
    main()
