"""Workload: analyses per week by candidate x course x kind x month, the cost at $0.70 a video and
$0.51 a transcript, and the classes that MOVE against the manager's original (C0) and against
today's shipped rule v2 (analysis/approval_rule.py verdict_v2).

Outputs analysis/out/workload.csv (long: config, dimension, key, classes, videos, transcripts,
per_week, cost_per_week) and workload.json (plus the movement tables).
"""
import calendar
import os
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sentiment_common import Study, Engine, OUT, COST, MONTHS, write_csv, write_json  # noqa: E402
from sentiment_score import CONFIGS  # noqa: E402
from sentiment_replay import rule_v2  # noqa: E402

ANALYSED = ("video", "transcript")


def movement(before, after):
    """How the queue changes between two action lists."""
    c = Counter()
    for a, b in zip(before, after):
        if a in ANALYSED and b not in ANALYSED:
            c["dropped"] += 1
        elif a not in ANALYSED and b in ANALYSED:
            c["added"] += 1
        elif a == "transcript" and b == "video":
            c["deeper"] += 1
        elif a == "video" and b == "transcript":
            c["shallower"] += 1
        elif a != b:
            c["other"] += 1
        else:
            c["same"] += 1
    c["moved"] = sum(v for k, v in c.items() if k != "same")
    return dict(c)


def table(rows, actions, weeks, keyfn, weeks_of=None):
    acc = defaultdict(Counter)
    for r, a in zip(rows, actions):
        k = keyfn(r)
        acc[k]["classes"] += 1
        acc[k][a] += 1
    out = {}
    for k, v in acc.items():
        w = weeks_of(k) if weeks_of else weeks
        out[k] = {"classes": v["classes"], "video": v["video"], "transcript": v["transcript"], "watch": v["watch"], "none": v["none"],
                  "per_week": (v["video"] + v["transcript"]) / w, "videos_per_week": v["video"] / w,
                  "cost_per_week": (v["video"] * COST["video"] + v["transcript"] * COST["transcript"]) / w}
    return out


def main():
    t0 = time.time()
    S = Study()
    E = Engine(S)
    rows = S.rows
    v2 = [rule_v2(r) for r in rows]
    c0 = E.base.run(CONFIGS["C0"])
    c0_actions = [x["action"] for x in c0]
    month_weeks = lambda m: calendar.monthrange(2026, m)[1] / 7.0            # noqa: E731
    csv_rows, out = [], {"meta": {"weeks": S.weeks, "cost": COST}, "rule_v2_today": {}, "configs": {}}
    # today's rule as the reference row
    for dim, keyfn, wk in (("course", lambda r: r["course"], None), ("kind", lambda r: r["kind"], None),
                           ("month", lambda r: MONTHS[r["month"] - 1], lambda m: month_weeks(MONTHS.index(m) + 1))):
        t = table(rows, v2, S.weeks, keyfn, wk)
        out["rule_v2_today"][dim] = t
        for k, v in t.items():
            csv_rows.append(["rule_v2_today", dim, k, v["classes"], v["video"], v["transcript"], round(v["per_week"], 2), round(v["cost_per_week"], 2)])
    tot = Counter(v2)
    out["rule_v2_today"]["total"] = {"video": tot["video"], "transcript": tot["transcript"], "per_week": (tot["video"] + tot["transcript"]) / S.weeks,
                                     "videos_per_week": tot["video"] / S.weeks, "transcripts_per_week": tot["transcript"] / S.weeks,
                                     "cost_per_week": (tot["video"] * COST["video"] + tot["transcript"] * COST["transcript"]) / S.weeks}
    csv_rows.append(["rule_v2_today", "total", "all", len(rows), tot["video"], tot["transcript"], round(out["rule_v2_today"]["total"]["per_week"], 2),
                     round(out["rule_v2_today"]["total"]["cost_per_week"], 2)])
    for key, cfg in CONFIGS.items():
        res = E.base.run(cfg)
        actions = [x["action"] for x in res]
        tot = Counter(actions)
        entry = {"name": cfg["name"], "total": {"video": tot["video"], "transcript": tot["transcript"], "watch": tot["watch"], "none": tot["none"],
                                                "per_week": (tot["video"] + tot["transcript"]) / S.weeks, "videos_per_week": tot["video"] / S.weeks,
                                                "transcripts_per_week": tot["transcript"] / S.weeks,
                                                "cost_per_week": (tot["video"] * COST["video"] + tot["transcript"] * COST["transcript"]) / S.weeks,
                                                "cost_total": tot["video"] * COST["video"] + tot["transcript"] * COST["transcript"]},
                 "vs_C0": movement(c0_actions, actions), "vs_rule_v2_today": movement(v2, actions),
                 "todays_analyses_dropped": sum(1 for a, b in zip(v2, actions) if a in ANALYSED and b not in ANALYSED),
                 "todays_analyses_kept": sum(1 for a, b in zip(v2, actions) if a in ANALYSED and b in ANALYSED)}
        csv_rows.append([key, "total", "all", len(rows), tot["video"], tot["transcript"], round(entry["total"]["per_week"], 2), round(entry["total"]["cost_per_week"], 2)])
        for dim, keyfn, wk in (("course", lambda r: r["course"], None), ("kind", lambda r: r["kind"], None),
                               ("month", lambda r: MONTHS[r["month"] - 1], lambda m: month_weeks(MONTHS.index(m) + 1)),
                               ("region", lambda r: r["region"], None)):
            t = table(rows, actions, S.weeks, keyfn, wk)
            entry[dim] = t
            for k, v in t.items():
                csv_rows.append([key, dim, k, v["classes"], v["video"], v["transcript"], round(v["per_week"], 2), round(v["cost_per_week"], 2)])
        # course x month (peak weeks)
        cm = table(rows, actions, S.weeks, lambda r: "%s|%s" % (r["course"], MONTHS[r["month"] - 1]), lambda k: month_weeks(MONTHS.index(k.split("|")[1]) + 1))
        entry["course_month_peak"] = max(cm.items(), key=lambda kv: kv[1]["per_week"])[0] if cm else None
        entry["month_peak_per_week"] = max(v["per_week"] for v in entry["month"].values())
        out["configs"][key] = entry
        print("%s %.1f analyses/wk (%.1f video + %.1f transcript, $%.2f/wk) | vs C0: +%d -%d | vs today's rule: +%d -%d, deeper %d, shallower %d | today's analyses dropped %d of %d" % (
            key, entry["total"]["per_week"], entry["total"]["videos_per_week"], entry["total"]["transcripts_per_week"], entry["total"]["cost_per_week"],
            entry["vs_C0"].get("added", 0), entry["vs_C0"].get("dropped", 0), entry["vs_rule_v2_today"].get("added", 0), entry["vs_rule_v2_today"].get("dropped", 0),
            entry["vs_rule_v2_today"].get("deeper", 0), entry["vs_rule_v2_today"].get("shallower", 0), entry["todays_analyses_dropped"],
            entry["todays_analyses_dropped"] + entry["todays_analyses_kept"]))
    write_csv(os.path.join(OUT, "workload.csv"), ["config", "dimension", "key", "classes", "videos", "transcripts", "per_week", "cost_per_week"], csv_rows)
    write_json(os.path.join(OUT, "workload.json"), out)
    print("today's rule: %.1f/wk (%.1f video) | done in %.1fs" % (out["rule_v2_today"]["total"]["per_week"], out["rule_v2_today"]["total"]["videos_per_week"], time.time() - t0))


if __name__ == "__main__":
    main()
