"""Decide: fill the scorecard for every candidate and the sweep's best settings, pick the
recommended configuration, and write everything the app's scoring page might show.

The rule, as the plan states it, applied with one constraint the study declares openly:
  * the two agreed lines stay at 4.55 and 80% (the sweep over the approval bar is a check on the
    80, not a licence to move it - the sweep's own top setting moves it to 82.5 and is reported,
    not adopted);
  * vetoes: false comfort above 5%; a queue above the default ceiling (12 a week, 5 videos)
    unless a band edge fixes it;
  * best non-vetoed total, then the simplest setting within 5 points.

Three configurations are written, one recommendation:
  recommended_config.json          C5 with the guard off (k = 0) and analysis from 6 votes: the
                                   hard lines are literal, the contract is unchanged, 11.8 a week
  recommended_config_floor5.json   the same with analysis from 5 votes (the plan's default):
                                   12.6 a week = today's queue, 0.6 above the default ceiling
  recommended_config_guarded.json  the recommendation with the guard back on (k = 5) once the
                                   contract reads the hard lines on the raw values (finding F1)
Reads the outputs of the other sentiment_*.py scripts; writes scoring_results.json, scorecard.json.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sentiment_common import (Study, Engine, OUT, BANDS, LINE, BAR, VOICES, CEILING, WEIGHTS, cfg_signature,  # noqa: E402
                              describe_cfg, needs_contract_change, low_next, make_cfg, read_json, write_json, _under)
from sentiment_score import CONFIGS  # noqa: E402

WITHIN = 5.0     # "prefer the simplest setting within 5 points of the best"
AGREED = dict(rating_mode="knee", rating_floor=3.55, approval_mode="graded", approval_floor=40, approval_bar=80, sample_mode="off",
              reach_mode="off", track_mode="on", min_band=3, min_action=5, caps=True, weights={"rating": 60, "approval": 25, "sample": 0, "reach": 0, "track": 15})
NAMED = {
    "D:guard-off": ("C5 with the guard off (k=0), analysis from 5 votes", make_cfg(name="D", guard_k=0, **AGREED)),
    "D6:guard-off,6-votes": ("C5 with the guard off (k=0), analysis from 6 votes", make_cfg(name="D6", guard_k=0, **{**AGREED, "min_action": 6})),
    "A:raw-lines,k5": ("C5 with the lines on raw values, k=5 (contract change)", make_cfg(name="A", guard_k=5, caps_basis="raw", **AGREED)),
    "A6:raw-lines,k5,6-votes": ("C5 with the lines on raw values, k=5, analysis from 6 votes (contract change)",
                                make_cfg(name="A6", guard_k=5, caps_basis="raw", **{**AGREED, "min_action": 6})),
    "A2:raw-rating-line,k5": ("C5 with only the rating line on raw values, k=5 (contract change)", make_cfg(name="A2", guard_k=5, caps_basis="raw_rating", **AGREED)),
    "B:k3": ("C5 with a lighter guard (k=3)", make_cfg(name="B", guard_k=3, **AGREED)),
}


def at_agreed_lines(cfg):
    caps = cfg["caps"]
    return float(cfg["approval"]["bar"]) == BAR and (caps.get("rating_line") is None or float(caps["rating_line"]) == LINE) \
        and (caps.get("approval_bar") is None or float(caps["approval_bar"]) == BAR)


def pick(pool):
    ok = [r for r in pool if not r["vetoed"]]
    if not ok:
        return None, []
    best = max(r["total"] for r in ok)
    near = sorted([r for r in ok if r["total"] >= best - WITHIN], key=lambda r: (r["parts"], -r["total"]))
    return near[0], near


def summarise(rec, m):
    y1, y2, y3, y4, y5 = m["Y1"], m["Y2"], m["Y3"], m["Y4"], m["Y5"]
    tr = y1["transitions"]
    ge = sum(v for k, v in tr.items() if {k.split(">")[0], k.split(">")[1]} == {"Excellent", "Good"})
    alt = m["scorecard"]["total"] - m["scorecard"]["points"]["Y1"] + _under(y1["verdict_all"], 10.0, WEIGHTS["Y1"]) + _under(y1["verdict_10plus"], 5.0, WEIGHTS["Y1"])
    return {"label": rec["label"], "signature": rec["signature"], "description": describe_cfg(rec["config"]), "needs_contract_change": needs_contract_change(rec["config"]),
            "total": m["scorecard"]["total"], "points": m["scorecard"]["points"], "vetoes": m["scorecard"]["vetoes"], "passes": m["scorecard"]["passes"],
            "alt_total_verdict_y1": round(alt, 1), "parts": m["parts"], "verified": rec.get("verified"),
            "flip_all": y1["flip_all"], "flip_10plus": y1["flip_10plus"], "verdict_all": y1["verdict_all"], "verdict_10plus": y1["verdict_10plus"],
            "flip_yes": y1["flip_yes"], "flip_rating": y1["flip_rating"], "good_excellent_share_of_flips": (ge / sum(tr.values()) * 100) if tr else 0.0,
            "by_bucket": y1["by_bucket"], "transitions": tr,
            "false_comfort": y2["false_comfort"], "false_comfort_firm": rec.get("fc_firm"), "false_comfort_rating": y2["false_comfort_rating"],
            "false_comfort_share": y2["false_comfort_share"], "false_alarm": y2["false_alarm"], "bad_total": y2["bad_total"], "bad_rated_fine": y2["bad_rated_fine"],
            "y3": {b: y3[b] for b in BANDS}, "y3_order": y3["order_ok"], "y3_ratio": y3["ratio_bad_excellent"], "y3_min_pairs": y3["min_band_n"],
            "band_counts": y4["band_counts"], "band_shares": y4["band_shares"], "no_band_share": y4["no_band_share"], "provisional": y4["provisional"],
            "actions": y4["actions"], "per_week": y4["per_week"], "videos_per_week": y4["videos_per_week"], "transcripts_per_week": y4["transcripts_per_week"],
            "cost_per_week": y4["cost_per_week"], "size_gap": y5["size_gap"], "kind_gap": y5["kind_gap"], "thin_firm": y5["thin_firm"],
            "excellent_lt10": y5["excellent_lt10"], "excellent_10plus": y5["excellent_10plus"], "excellent_live": y5["excellent_live"], "excellent_review": y5["excellent_review"],
            "config": rec["config"]}


def main():
    t0 = time.time()
    S = Study(write_aliases=False)
    E = Engine(S)
    replay = read_json(os.path.join(OUT, "replay_summary.json"))
    sweep = read_json(os.path.join(OUT, "sweep_stages.json"))
    predict = read_json(os.path.join(OUT, "predict.json"))
    workload = read_json(os.path.join(OUT, "workload.json"))
    drift = read_json(os.path.join(OUT, "drift.json"))
    edges = read_json(os.path.join(OUT, "edge_cases.json"))
    rv2 = workload["rule_v2_today"]["total"]
    today_load = rv2["per_week"]

    def entry(label, cfg):
        m = E.metrics(cfg)
        res = E.base.run(cfg)
        fc_firm = sum(1 for r, x in zip(S.rows, res) if r["votes"] >= VOICES and x["band"] in ("good", "excellent") and not x["provisional"]
                      and (r["rating"] < LINE or r["approval"] < BAR))
        return {"label": label, "signature": cfg_signature(cfg), "total": m["scorecard"]["total"], "vetoed": bool(m["scorecard"]["vetoes"]),
                "parts": m["parts"], "config": cfg, "metrics": m, "verified": E.verify(cfg), "fc_firm": fc_firm}

    pool = [entry(k, cfg) for k, cfg in CONFIGS.items()]
    for track in ("top_asis", "top_raw"):
        for i, r in enumerate(sweep[track], 1):
            pool.append(entry("%s#%d" % ("sweep as-is" if track == "top_asis" else "sweep raw-lines", i), r["config"]))
    for k, (title, cfg) in NAMED.items():
        pool.append(entry(k, cfg))
    for r in pool:
        r["agreed_lines"] = at_agreed_lines(r["config"])
    by = {r["label"]: r for r in pool}

    # ---- the picks ----------------------------------------------------------------------------------
    recommended, near_rec = pick([r for r in pool if r["agreed_lines"] and not needs_contract_change(r["config"])])
    sweep_best = by["sweep as-is#1"]                     # the sweep's own top setting (moves the bar)
    floor5 = by["D:guard-off"]
    guarded = by["A6:raw-lines,k5,6-votes"]
    best_nonveto = max((r["total"] for r in pool if not r["vetoed"]), default=None)
    m = recommended["metrics"]
    c0m, c5m = by["C0"]["metrics"], by["C5"]["metrics"]

    def write_cfg(rec, fname, name, note):
        cfg = dict(rec["config"])
        cfg["name"], cfg["note"] = name, note
        write_json(os.path.join(OUT, fname), cfg)
        return cfg

    rec_cfg = write_cfg(recommended, "recommended_config.json", "v3 — validated on Jan–Aug 2026",
                        ("C5 (today's rule as four bands) with the small-sample guard switched off, so the two agreed hard lines (4.55 rating, 80%% approval) are literal, "
                         "and an analysis from 6 votes (a provisional band, watched, from 3 to 5). Scorecard %s of 200: the best non-vetoed setting at the agreed lines under the "
                         "contract as-is; the sweep's unconstrained top setting (%s) moves the bar to 82.5%% and was not adopted. Measured on 2,784 classes: one vote flips %.1f%% of labels "
                         "but %.1f%% of verdicts (original %.1f%% / %.1f%%); low classes with a FIRM Good/Excellent: %d (%d provisional 5-vote labels); Bad rated 4.55+: %d of %d; "
                         "next-class risk Bad %.0f%% vs Excellent %.0f%%; %.1f analyses a week (%.1f video, %.1f transcript; today's queue is %.1f). "
                         "Dial: analysis from 5 votes gives %.1f a week (recommended_config_floor5.json). Once the contract reads the lines on raw values (finding F1) turn the guard "
                         "back on: k=5 cuts label flips to %.1f%% with the same verdicts (recommended_config_guarded.json).") % (
                            m["scorecard"]["total"], sweep_best["signature"], m["Y1"]["flip_all"], m["Y1"]["verdict_all"], c0m["Y1"]["flip_all"], c0m["Y1"]["verdict_all"],
                            recommended["fc_firm"], m["Y2"]["false_comfort"] - recommended["fc_firm"], m["Y2"]["bad_rated_fine"], m["Y2"]["bad_total"], m["Y3"]["bad"]["share"],
                            m["Y3"]["excellent"]["share"], m["Y4"]["per_week"], m["Y4"]["videos_per_week"], m["Y4"]["transcripts_per_week"], today_load,
                            floor5["metrics"]["Y4"]["per_week"], guarded["metrics"]["Y1"]["flip_all"]))
    write_cfg(floor5, "recommended_config_floor5.json", "v3 (analysis from 5 votes) — validated on Jan–Aug 2026",
              "The recommended setting with analysis from 5 votes, the plan's default: %.1f analyses a week - today's queue under rule v2 - which is %.1f above the default ceiling of 12 "
              "(scorecard %s, vetoed on that ceiling alone). Choose this if the 5-vote floor matters more than the ceiling." % (
                  floor5["metrics"]["Y4"]["per_week"], floor5["metrics"]["Y4"]["per_week"] - CEILING["per_week"], floor5["metrics"]["scorecard"]["total"]))
    write_cfg(guarded, "recommended_config_guarded.json", "v3 + guard (needs contract change) — validated on Jan–Aug 2026",
              "The recommended setting with the guard back on (k=5) and caps.basis='raw': the hard lines read the RAW rating and approval, the guard shapes the score only. "
              "Requires the contract change (sentiment_score.py, the SQL function, the TS mirror); until then this JSON scores with guarded lines and hides borderline classes "
              "(finding F1). Scorecard %s; label flips %.1f%% against %.1f%% with the guard off; verdicts unchanged." % (
                  guarded["metrics"]["scorecard"]["total"], guarded["metrics"]["Y1"]["flip_all"], m["Y1"]["flip_all"]))

    # ---- the VP table -------------------------------------------------------------------------------
    def five(r):
        mm = r["metrics"]
        return {"flip_band_pct": mm["Y1"]["flip_all"], "flip_verdict_pct": mm["Y1"]["verdict_all"], "flip_10plus_pct": mm["Y1"]["flip_10plus"], "verdict_10plus_pct": mm["Y1"]["verdict_10plus"],
                "bad_rated_fine": mm["Y2"]["bad_rated_fine"], "bad_total": mm["Y2"]["bad_total"], "low_shown_fine": mm["Y2"]["false_comfort"], "low_shown_fine_firm": r["fc_firm"],
                "low_shown_fine_rating": mm["Y2"]["false_comfort_rating"],
                "per_week": mm["Y4"]["per_week"], "videos_per_week": mm["Y4"]["videos_per_week"], "transcripts_per_week": mm["Y4"]["transcripts_per_week"], "cost_per_week": mm["Y4"]["cost_per_week"],
                "risk_bad": mm["Y3"]["bad"]["share"], "risk_excellent": mm["Y3"]["excellent"]["share"], "risk_average": mm["Y3"]["average"]["share"], "risk_good": mm["Y3"]["good"]["share"],
                "risk_bad_n": mm["Y3"]["bad"]["n"], "risk_excellent_n": mm["Y3"]["excellent"]["n"], "total": mm["scorecard"]["total"]}
    vp = {"original": five(by["C0"]), "recommended": five(recommended), "floor5": five(floor5), "guarded": five(guarded), "C5": five(by["C5"]),
          "today_rule_v2": {"per_week": today_load, "videos_per_week": rv2["videos_per_week"], "transcripts_per_week": rv2.get("transcripts_per_week", rv2["transcript"] / S.weeks)}}

    # ---- the guard's lifts, quantified (C5) ---------------------------------------------------------
    res5 = E.base.run(CONFIGS["C5"])
    nxt = {i: j for i, j in S.pairs["resolved"]}
    lifted = [r for r, x in zip(S.rows, res5) if r["votes"] >= VOICES and x["band"] in ("good", "excellent") and (r["rating"] < LINE or r["approval"] < BAR)]
    lp = [r for r in lifted if r["id"] in nxt]
    fine = [r for r, x in zip(S.rows, res5) if r["votes"] >= VOICES and x["band"] in ("good", "excellent") and r["rating"] >= LINE and r["approval"] >= BAR and r["id"] in nxt]
    guard_lift = {"classes": len(lifted), "rating_line": sum(1 for r in lifted if r["rating"] < LINE), "approval_bar": sum(1 for r in lifted if r["rating"] >= LINE),
                  "with_next": len(lp), "next_low_pct": (sum(1 for r in lp if low_next(S.rows[nxt[r["id"]]])) / len(lp) * 100) if lp else None,
                  "fine_on_both_next_low_pct": (sum(1 for r in fine if low_next(S.rows[nxt[r["id"]]])) / len(fine) * 100) if fine else None, "fine_on_both_n": len(fine),
                  "base_rate": predict["two_lines"]["resolved"]["base_rate"],
                  "raw_rating_range": [min(r["rating"] for r in lifted if r["rating"] < LINE), max(r["rating"] for r in lifted if r["rating"] < LINE)]}

    # ---- findings -----------------------------------------------------------------------------------
    e44 = next(e for e in edges["cases"] if e["id"] == "E44")
    e01 = next(e for e in edges["cases"] if e["id"] == "E01")
    rec_sum = summarise(recommended, m)
    findings = [
        {"id": "F1", "title": "The hard lines read the guarded values, so borderline classes clear them",
         "detail": "Under C5, %d classes with 5+ votes sit under a raw line (%d rated %.2f-%.2f, %d with approval 71-79%%) yet show Good or Excellent, because the guard blends "
                   "them with the course prior before the line is checked. That is 6.0%% false comfort - above the 5%% veto - and the reason every hand-written candidate fails Y2. "
                   "Failing case E44: 4.54 with 10 votes, everyone approves, prior 4.70 -> guarded 4.59 -> Good (the plan says Average). Their next class goes wrong %.0f%% of the time "
                   "against %.0f%% for classes fine on both lines." % (guard_lift["classes"], guard_lift["rating_line"], guard_lift["raw_rating_range"][0], guard_lift["raw_rating_range"][1],
                                                                       guard_lift["approval_bar"], guard_lift["next_low_pct"] or 0, guard_lift["fine_on_both_next_low_pct"] or 0),
         "case": {"inputs": e44["inputs"], "contract": e44["by_config"]["C5"]},
         "recommendation": "Add caps.basis ('guarded' | 'raw') to the contract and read the raw values for the lines when votes >= min_votes.action. Until then ship with the guard off (k=0)."},
        {"id": "F2", "title": "The guard and the hard lines cannot both hold at once",
         "detail": "Any k above 0 with guarded lines hides classes (k=3: %d, 3.6%%; k=5: %d, 6.0%%; k=10: 10.2%%); k=0 or raw lines hides none but flags every class the two lines flag: "
                   "%.1f analyses a week from 5 votes, which is today's queue under rule v2 and %.1f above the default ceiling of 12. No band edge changes that - the lines set the queue; "
                   "the analysis floor is the dial (6 votes: %.1f a week)." % (
                       by["B:k3"]["metrics"]["Y2"]["false_comfort"], c5m["Y2"]["false_comfort"], floor5["metrics"]["Y4"]["per_week"], floor5["metrics"]["Y4"]["per_week"] - CEILING["per_week"],
                       m["Y4"]["per_week"]),
         "recommendation": "Ship with the guard off and the floor at 6 votes; or keep the floor at 5 and raise the ceiling to today's throughput (%.1f)." % today_load},
        {"id": "F3", "title": "Label flips are structural; the hard lines protect the verdict, not the label",
         "detail": "60%% of classes score between 85 and 97.5, so wherever the Excellent edge sits, one rater giving one point less (3.3 points for a 10-rater class) flips about a third of "
                   "labels: %.1f%% under the recommended setting, %.1f%% under the original; %.0f%% of those flips are Good <-> Excellent, which changes no work. Verdict flips "
                   "(video / transcript / none) fall from %.1f%% to %.1f%%. Y1's label pass mark (under 10%%) is out of reach for any four-band setting on this data; every one of the "
                   "%s swept settings scores 0 on it, so the ranking is decided by Y2-Y5." % (m["Y1"]["flip_all"], c0m["Y1"]["flip_all"], rec_sum["good_excellent_share_of_flips"],
                                                                                              c0m["Y1"]["verdict_all"], m["Y1"]["verdict_all"], "{:,}".format(sweep["stages"]["total_settings"])),
         "recommendation": "Judge Y1 on verdict flips as well (alternative totals are in the report); show a class within 2 points of an edge with a 'near the line' hint."},
        {"id": "F4", "title": "A class nobody rated is scored as the course prior",
         "detail": "E01 (nobody attended, 0 ratings): the guard computes (0 x rating + k x prior) / k = the prior, so the class gets score %.2f with no band. Harmless on screen, but the stored score is a fiction." % e01["by_config"]["C5"]["score"],
         "recommendation": "Return no score when num_ratings is 0 (treat like no_rating)."},
        {"id": "F5", "title": "A missing track record is 'neutral' but not weightless",
         "detail": "With no history the weights re-scale to 60/25 (70.6% / 29.4%), so a 4.70 class with full approval scores 88.2 (Good) on an instructor's first class and 90.0 (Excellent) once a fine history exists.",
         "recommendation": "Acceptable; say so in the product's tooltip ('first class - no history yet')."},
        {"id": "F6", "title": "The sweep's own top setting moves the agreed bar",
         "detail": "The best scorecard total the sweep found under the contract as-is (%.1f) comes from an approval cliff at 82.5%%, the response count back at 5 points, a knee floor of 3.80 "
                   "and a Good band of 80-85: the higher bar caps the classes the guard lifts, which buys Y2 and Y3 points. It moves the VP's 80%% and is harder to explain, so it is "
                   "reported, not adopted; the recommendation (%.1f) beats it at the agreed lines anyway." % (sweep_best["total"], m["scorecard"]["total"]),
         "recommendation": "Keep the bar at 80; re-run the sweep if the team ever changes the bar."},
        {"id": "F7", "title": "The Bad band is thinner than the plan's 100 once next classes are paired",
         "detail": "C5 puts %d classes in Bad, but only %d of them have a next class with 5+ votes on both sides; the recommended setting reaches %d pairs (56%% against 12%% is far outside the error bars either way)." % (
             c5m["Y4"]["band_counts"].get("Bad", 0), c5m["Y3"]["bad"]["n"], m["Y3"]["bad"]["n"]),
         "recommendation": "Report both counts; keep the strict pairs count in the scorecard."},
    ]

    # ---- everything for the scoring page -----------------------------------------------------------
    cand = {k: {**summarise(by[k], by[k]["metrics"]), "name": CONFIGS[k]["name"]} for k in CONFIGS}
    named = {k: {**summarise(by[k], by[k]["metrics"]), "name": NAMED[k][0]} for k in NAMED}
    results = {
        "meta": {"window": "2026-01-01 .. 2026-08-31", "rows": len(S.rows), "weeks": round(S.weeks, 2), "generated": time.strftime("%Y-%m-%d %H:%M"),
                 "scorecard_weights": WEIGHTS, "scorecard_max": 200, "vetoes": {"false_comfort_pct_over": 5.0, "per_week_over": CEILING["per_week"], "videos_over": CEILING["videos"]},
                 "today_load_per_week": today_load,
                 "identity": {"raw_names": len({r["instructor_raw"] for r in S.rows if r["instructor_raw"]}),
                              "resolved_names": len({r["instructor_resolved"] for r in S.rows if r["instructor_resolved"]}), "aliases": len(S.alias)}},
        "candidates": cand, "named": named,
        "scorecard": {k: {"total": v["total"], "points": v["points"], "vetoes": v["vetoes"], "passes": v["passes"], "alt_total_verdict_y1": v["alt_total_verdict_y1"]} for k, v in {**cand, **named}.items()},
        "recommended": {**rec_sum, "config_json": rec_cfg, "why": "the plan's rule at the agreed lines, contract as-is: best non-vetoed total, simplest within 5 points",
                        "considered_within_5_points": [{"label": r["label"], "total": r["total"], "parts": r["parts"]} for r in near_rec]},
        "floor5": summarise(floor5, floor5["metrics"]), "guarded": summarise(guarded, guarded["metrics"]),
        "sweep_top_as_is": summarise(sweep_best, sweep_best["metrics"]), "best_total_non_vetoed": best_nonveto,
        "vp_table": vp, "guard_lift": guard_lift, "findings": findings,
        "sweep_top15": {"as_is": [{k: v for k, v in r.items() if k != "config"} for r in sweep["top_asis"]],
                        "raw_lines": [{k: v for k, v in r.items() if k != "config"} for r in sweep["top_raw"]], "stages": sweep["stages"]},
        "edge_cases": edges["summary"], "drift": {"model_drift": drift["model_drift"], "class_drift": drift["class_drift"], "halves": drift["halves"],
                                                   "weights": {k: v["derived_weights"] for k, v in drift["weights"].items()}},
        "famous_cases": replay["famous_cases"], "today_rule_v2": rv2,
    }
    write_json(os.path.join(OUT, "scoring_results.json"), results)
    write_json(os.path.join(OUT, "scorecard.json"), {"candidates": results["scorecard"], "recommended": {"label": recommended["label"], "total": recommended["total"], "points": m["scorecard"]["points"]},
                                                    "floor5": {"label": floor5["label"], "total": floor5["total"]}, "guarded": {"label": guarded["label"], "total": guarded["total"]},
                                                    "sweep_top_as_is": {"label": sweep_best["label"], "total": sweep_best["total"]}})
    print("SCORECARD (of 200)          total    Y1    Y2    Y3    Y4    Y5  Y6   alt(Y1 on verdicts)")
    for k, v in {**cand, **named}.items():
        print("  %-24s %6.1f  %4.1f  %4.1f  %4.1f  %4.1f  %4.1f  %2d   %6.1f  %s" % (k, v["total"], v["points"]["Y1"], v["points"]["Y2"], v["points"]["Y3"], v["points"]["Y4"], v["points"]["Y5"], v["points"]["Y6"],
                                                                                     v["alt_total_verdict_y1"], ("VETO: " + "; ".join(v["vetoes"])) if v["vetoes"] else ""))
    print("SWEEP TOP AS-IS (moves the bar): %.1f | %s" % (sweep_best["total"], describe_cfg(sweep_best["config"])))
    print("RECOMMENDED: %s %.1f parts %d verified %s\n  %s\n  within 5 points: %s" % (recommended["label"], recommended["total"], recommended["parts"], recommended["verified"], describe_cfg(rec_cfg),
                                                                                    [(r["label"], r["total"], r["parts"]) for r in near_rec]))
    o, r_ = vp["original"], vp["recommended"]
    print("VP TABLE                     original | recommended")
    print("  band flips on one vote    %5.1f%% (verdict %4.1f%%) | %5.1f%% (verdict %4.1f%%)" % (o["flip_band_pct"], o["flip_verdict_pct"], r_["flip_band_pct"], r_["flip_verdict_pct"]))
    print("  Bad but rated 4.55+       %3d of %3d | %3d of %3d" % (o["bad_rated_fine"], o["bad_total"], r_["bad_rated_fine"], r_["bad_total"]))
    print("  low (5+ votes) shown fine %5d (firm %d) | %5d (firm %d)" % (o["low_shown_fine"], o["low_shown_fine_firm"], r_["low_shown_fine"], r_["low_shown_fine_firm"]))
    print("  analyses a week           %5.1f (%.1f v + %.1f t) | %5.1f (%.1f v + %.1f t)   today %.1f" % (o["per_week"], o["videos_per_week"], o["transcripts_per_week"], r_["per_week"], r_["videos_per_week"], r_["transcripts_per_week"], today_load))
    print("  next-class risk Bad/Exc   %3.0f%% vs %3.0f%% | %3.0f%% vs %3.0f%%" % (o["risk_bad"], o["risk_excellent"], r_["risk_bad"], r_["risk_excellent"]))
    print("guard lift:", guard_lift)
    print("decide done in %.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
