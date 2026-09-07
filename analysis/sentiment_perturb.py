"""Y1 - stable under one vote. Every class replayed twice: one "yes" becomes a "no", and one rater
gives one point less (the average drops by 1 / number of ratings). A flip is a change of the band
label; a verdict flip is a change of the action (video / transcript / none / watch).

Outputs analysis/out/perturb.csv (config x vote bucket) and perturb.json (everything, including
which band moved to which, and how many classes sit within two points of a band edge).
"""
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sentiment_common import Study, Engine, OUT, BUCKETS, BAND_LABEL, write_csv, write_json  # noqa: E402
from sentiment_score import CONFIGS  # noqa: E402


def edge_distance(sc, cfg):
    if sc is None:
        return None
    return min(abs(sc - float(v)) for v in cfg["bands"].values())


def main():
    t0 = time.time()
    S = Study()
    E = Engine(S)
    rows = S.rows
    csv_rows, out = [], {"meta": {"rows": len(rows), "perturbations": ["one yes -> no", "one rater one point less (rating - 1/n)"]}, "configs": {}}
    for key, cfg in CONFIGS.items():
        base, yes, rat = E.run(cfg)
        m = E.metrics(cfg)
        y1 = m["Y1"]
        shifts = [abs(a["score"] - c["score"]) for a, c in zip(base, rat) if a["score"] is not None and c["score"] is not None]
        near = sum(1 for a in base if a["score"] is not None and edge_distance(a["score"], cfg) < 2.0)
        ge = sum(v for k, v in y1["transitions"].items() if {k.split(">")[0], k.split(">")[1]} == {"Excellent", "Good"})
        decisions = sum(v for k, v in y1["transitions"].items() if {k.split(">")[0], k.split(">")[1]} != {"Excellent", "Good"})
        for name, lo, hi in BUCKETS:
            b = y1["by_bucket"].get(name, {"n": 0, "flips": 0, "share": 0.0, "verdict_share": 0.0})
            csv_rows.append([key, name, b["n"], b["flips"], round(b["share"], 1), round(b["verdict_share"], 1)])
        csv_rows.append([key, "10+", y1["n"] and sum(1 for r in rows if r["votes"] >= 10), None, round(y1["flip_10plus"], 1), round(y1["verdict_10plus"], 1)])
        csv_rows.append([key, "all", y1["n"], y1["flips"], round(y1["flip_all"], 1), round(y1["verdict_all"], 1)])
        out["configs"][key] = {
            "name": cfg["name"], "flip_all": y1["flip_all"], "flip_10plus": y1["flip_10plus"], "flip_yes": y1["flip_yes"],
            "flip_rating": y1["flip_rating"], "flip_firm": y1["flip_firm"], "verdict_all": y1["verdict_all"], "verdict_10plus": y1["verdict_10plus"],
            "by_bucket": y1["by_bucket"], "transitions": y1["transitions"],
            "label_only_flips_good_excellent": ge, "decision_flips": decisions,
            "within_2_points_of_an_edge": near, "within_2_points_share": near / len(rows) * 100,
            "median_score_shift_one_point_less": sorted(shifts)[len(shifts) // 2] if shifts else None,
            "pass_all": y1["flip_all"] < 10.0, "pass_10plus": y1["flip_10plus"] < 5.0,
        }
        print("%s flips: all %.1f%% | 10+ votes %.1f%% | yes->no %.1f%% | one point less %.1f%% | verdict changes %.1f%% (10+: %.1f%%) | Good<->Excellent label flips %d of %d | near an edge %.0f%%" % (
            key, y1["flip_all"], y1["flip_10plus"], y1["flip_yes"], y1["flip_rating"], y1["verdict_all"], y1["verdict_10plus"], ge, ge + decisions, near / len(rows) * 100))
    write_csv(os.path.join(OUT, "perturb.csv"), ["config", "vote_bucket", "classes", "flips", "flip_share_pct", "verdict_flip_share_pct"], csv_rows)
    write_json(os.path.join(OUT, "perturb.json"), out)
    print("perturb done in %.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
