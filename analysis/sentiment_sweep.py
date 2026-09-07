"""The staged grid: (a) shapes at fixed weights, (b) weights x approval bar x response target x
minimum votes on the best shapes, (c) band edges over the stored scores. Every setting records
all six yardsticks and the scorecard. Runs on the verified fast scorer (sentiment_common), and
every top setting that the contract can express is re-checked against the contract itself.

Two tracks are ranked side by side:
  contract-as-is   the hard lines read the GUARDED values (sentiment_score.py today)
  raw-lines        the hard lines read the RAW rating / approval (a proposed contract change,
                   flagged "needs_contract_change" wherever it appears)

Outputs analysis/out/sweep.csv, sweep_top15.csv, frontier.json, sweep_stages.json.
"""
import itertools
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sentiment_common import (Study, Engine, OUT, BANDS, make_cfg, cfg_signature, describe_cfg, needs_contract_change,  # noqa: E402
                              moving_parts, write_csv, write_json)
from sentiment_score import CONFIGS  # noqa: E402

TOPN = 15
MAX_STAGE_B = 12000            # settings; above this the weight grid is thinned evenly (and reported)

HEADER = ["stage", "signature", "needs_contract_change", "total", "vetoed", "vetoes", "parts", "Y1", "Y2", "Y3", "Y4", "Y5", "Y6",
          "flip_all", "flip_10plus", "verdict_all", "false_comfort_pct", "false_alarm_pct", "bad_rated_fine", "y3_bad", "y3_average", "y3_good",
          "y3_excellent", "y3_order", "y3_ratio", "y3_min_n", "excellent_pct", "good_pct", "average_pct", "bad_pct", "no_band_pct", "per_week",
          "videos_per_week", "cost_per_week", "size_gap", "kind_gap", "thin_firm", "description"]


def record(stage, cfg, m):
    sc, y1, y2, y3, y4, y5 = m["scorecard"], m["Y1"], m["Y2"], m["Y3"], m["Y4"], m["Y5"]
    return {"stage": stage, "signature": cfg_signature(cfg), "needs_contract_change": needs_contract_change(cfg), "total": sc["total"],
            "vetoed": bool(sc["vetoes"]), "vetoes": "; ".join(sc["vetoes"]), "parts": m["parts"],
            "Y1": sc["points"]["Y1"], "Y2": sc["points"]["Y2"], "Y3": sc["points"]["Y3"], "Y4": sc["points"]["Y4"], "Y5": sc["points"]["Y5"], "Y6": sc["points"]["Y6"],
            "flip_all": round(y1["flip_all"], 2), "flip_10plus": round(y1["flip_10plus"], 2), "verdict_all": round(y1["verdict_all"], 2),
            "false_comfort_pct": round(y2["false_comfort_share"], 2), "false_alarm_pct": round(y2["false_alarm_share"], 2), "bad_rated_fine": y2["bad_rated_fine"],
            "y3_bad": round(y3["bad"]["share"], 1), "y3_average": round(y3["average"]["share"], 1), "y3_good": round(y3["good"]["share"], 1),
            "y3_excellent": round(y3["excellent"]["share"], 1), "y3_order": y3["order_ok"],
            "y3_ratio": round(y3["ratio_bad_excellent"], 2) if y3["ratio_bad_excellent"] != float("inf") else None, "y3_min_n": y3["min_band_n"],
            "excellent_pct": round(y4["band_shares"]["excellent"], 1), "good_pct": round(y4["band_shares"]["good"], 1),
            "average_pct": round(y4["band_shares"]["average"], 1), "bad_pct": round(y4["band_shares"]["bad"], 1), "no_band_pct": round(y4["no_band_share"], 1),
            "per_week": round(y4["per_week"], 2), "videos_per_week": round(y4["videos_per_week"], 2), "cost_per_week": round(y4["cost_per_week"], 2),
            "size_gap": round(y5["size_gap"], 1), "kind_gap": round(y5["kind_gap"], 1), "thin_firm": y5["thin_firm"], "description": describe_cfg(cfg),
            "config": cfg}


def rank_key(rec):
    """Vetoed last; then the scorecard; then the simpler setting; then closest to C5's numbers."""
    w = rec["config"]["weights"]
    dist = abs(w["rating"] - 60) + abs(w["approval"] - 25) + abs(w["track"] - 15) + abs(rec["config"]["approval"]["bar"] - 80) * 2 + abs((rec["config"]["guard"]["k"] or 0) - 5) * 3
    return (rec["vetoed"], -rec["total"], rec["parts"], dist)


def shape_grid():
    for rating_mode in ("linear", "knee"):
        for rfloor in ((3.55,) if rating_mode == "linear" else (3.3, 3.55, 3.8)):
            for amode in ("cliff", "graded"):
                for afloor in ((40,) if amode == "cliff" else (30, 40, 50)):
                    for k in (0, 3, 5, 10):
                        for smode in ("off", "cliff", "graded"):
                            for reach in ("off", "graded"):
                                for track in ("off", "on"):
                                    for caps, basis in (("off", "guarded"), ("on", "guarded"), ("on", "raw")):
                                        for mb, ma in ((0, 0), (3, 5)):
                                            weights = {"rating": 60, "approval": 25 if track == "on" else 30, "track": 15 if track == "on" else 0,
                                                       "sample": 6 if smode != "off" else 0, "reach": 4 if reach != "off" else 0}
                                            yield make_cfg(name="shape", rating_mode=rating_mode, rating_floor=rfloor, approval_mode=amode,
                                                           approval_floor=afloor, approval_bar=80, sample_mode=smode, sample_target=10, reach_mode=reach,
                                                           track_mode=track, guard_k=k, min_band=mb, min_action=ma, caps=(caps == "on"), caps_basis=basis,
                                                           weights=weights)


def weight_grid():
    combos = []
    for r in range(40, 81, 5):
        for a in range(10, 46, 5):
            for t in range(0, 26, 5):
                for s in (0, 5, 10):
                    for re_ in (0, 5, 10):
                        if r + a + t + s + re_ == 100:
                            combos.append({"rating": r, "approval": a, "track": t, "sample": s, "reach": re_})
    return combos


def shape_of(cfg):
    return dict(rating_mode=cfg["rating"]["mode"], rating_floor=cfg["rating"]["floor"], approval_mode=cfg["approval"]["mode"],
                approval_floor=cfg["approval"]["floor"], reach_mode=cfg["reach"]["mode"], guard_k=cfg["guard"]["k"],
                caps=cfg["caps"]["rating_line"] is not None, caps_basis=cfg["caps"].get("basis", "guarded"))


def main():
    t0 = time.time()
    S = Study()
    E = Engine(S)
    records, stages = [], {}

    # ---- stage (a): shapes ------------------------------------------------------------------------
    t1 = time.time()
    n = 0
    for cfg in shape_grid():
        records.append(record("a-shape", cfg, E.metrics(cfg)))
        n += 1
    stages["a"] = {"settings": n, "seconds": round(time.time() - t1, 1)}
    a_ok = sorted([r for r in records if r["stage"] == "a-shape"], key=rank_key)
    best_asis = next(r for r in a_ok if not r["needs_contract_change"])
    best_raw = next(r for r in a_ok if r["needs_contract_change"])
    print("stage a: %d shapes in %.0fs | best as-is %.1f %s | best raw-lines %.1f %s" % (n, stages["a"]["seconds"], best_asis["total"], best_asis["signature"],
                                                                                        best_raw["total"], best_raw["signature"]))

    # ---- stage (b): weights x bar x target x min votes on the best shapes + C5's shape -----------
    t1 = time.time()
    shapes = {"best-as-is": shape_of(best_asis["config"]), "best-raw-lines": shape_of(best_raw["config"]), "C5-shape": shape_of(CONFIGS["C5"])}
    seen = set()
    combos = weight_grid()
    bars = [70, 72.5, 75, 77.5, 80, 82.5, 85, 87.5, 90]
    targets = [5, 8, 10, 12, 15]
    mvs = [(3, 5), (5, 5)]
    planned = []
    for sname, sh in shapes.items():
        for w in combos:
            tmodes = ["on"] if w["track"] > 0 else ["off"]
            smodes = ["off"] if w["sample"] == 0 else ["graded"]
            for bar in bars:
                for tgt in (targets if w["sample"] > 0 else [10]):
                    for mb, ma in mvs:
                        planned.append((sname, sh, w, bar, tgt, mb, ma, tmodes[0], smodes[0]))
    step = 1
    if len(planned) > MAX_STAGE_B:
        step = -(-len(planned) // MAX_STAGE_B)
        planned = planned[::step]
    n = 0
    for sname, sh, w, bar, tgt, mb, ma, tm, sm in planned:
        cfg = make_cfg(name="b:" + sname, approval_bar=bar, sample_mode=sm, sample_target=tgt, track_mode=tm, min_band=mb, min_action=ma, weights=w, **sh)
        sig = cfg_signature(cfg)
        if sig in seen:
            continue
        seen.add(sig)
        records.append(record("b-weights:" + sname, cfg, E.metrics(cfg)))
        n += 1
    stages["b"] = {"settings": n, "planned": len(planned), "thinning_step": step, "weight_combos": len(combos), "seconds": round(time.time() - t1, 1),
                   "shapes": {k: {kk: (vv if not isinstance(vv, float) else round(vv, 2)) for kk, vv in v.items()} for k, v in shapes.items()}}
    b_ok = sorted([r for r in records if r["stage"].startswith("b-")], key=rank_key)
    print("stage b: %d settings (%d planned, thinning step %d) in %.0fs | best %.1f %s" % (n, len(planned), step, stages["b"]["seconds"], b_ok[0]["total"], b_ok[0]["signature"]))

    # ---- stage (c): band edges over the stored scores of the top settings + C5 ------------------
    t1 = time.time()
    seeds = [r["config"] for r in b_ok[:5]] + [CONFIGS["C5"], CONFIGS["C4"]]
    n = 0
    for base in seeds:
        for ex, gd, av in itertools.product([85, 87.5, 90, 92.5, 95], [70, 72.5, 75, 77.5, 80], [55, 57.5, 60, 62.5, 65]):
            cfg = {**base, "bands": {"excellent": ex, "good": gd, "average": av}, "name": "c:" + base.get("name", "seed")}
            sig = cfg_signature(cfg)
            if sig in seen:
                continue
            seen.add(sig)
            records.append(record("c-bands", cfg, E.metrics(cfg)))
            n += 1
    stages["c"] = {"settings": n, "seconds": round(time.time() - t1, 1)}
    print("stage c: %d band-edge settings in %.0fs" % (n, stages["c"]["seconds"]))

    # ---- the candidates themselves, for reference --------------------------------------------------
    for key, cfg in CONFIGS.items():
        rec = record("candidate:" + key, cfg, E.metrics(cfg))
        records.append(rec)

    # ---- ranking, verification, outputs ------------------------------------------------------------
    ranked = sorted(records, key=rank_key)
    top_asis = [r for r in ranked if not r["needs_contract_change"]][:TOPN]
    top_raw = [r for r in ranked if r["needs_contract_change"]][:TOPN]
    t1 = time.time()
    for r in top_asis:
        r["verified_against_contract"] = E.verify(r["config"]) == 0
    for r in top_raw:
        r["verified_against_contract"] = None
    stages["verify"] = {"seconds": round(time.time() - t1, 1), "top_asis_all_verified": all(r["verified_against_contract"] for r in top_asis)}
    print("top-%d as-is verified against the contract: %s (%.0fs)" % (TOPN, stages["verify"]["top_asis_all_verified"], stages["verify"]["seconds"]))
    write_csv(os.path.join(OUT, "sweep.csv"), HEADER, [[r[h] for h in HEADER] for r in ranked])
    top_rows = []
    for track, lst in (("contract-as-is", top_asis), ("raw-lines (needs contract change)", top_raw)):
        for i, r in enumerate(lst, 1):
            top_rows.append([track, i, r["verified_against_contract"]] + [r[h] for h in HEADER])
    write_csv(os.path.join(OUT, "sweep_top15.csv"), ["track", "rank", "verified"] + HEADER, top_rows)
    # frontier: flip share vs workload (and vs false comfort), all points thinned to <= 3000
    pts = [{"signature": r["signature"], "stage": r["stage"], "flip_all": r["flip_all"], "verdict_all": r["verdict_all"], "per_week": r["per_week"],
            "false_comfort_pct": r["false_comfort_pct"], "total": r["total"], "vetoed": r["vetoed"], "needs_contract_change": r["needs_contract_change"]}
           for r in ranked]
    def pareto(points, fx, fy):
        best, front = None, []
        for p in sorted(points, key=lambda p: (p[fx], p[fy])):
            if best is None or p[fy] < best:
                front.append(p)
                best = p[fy]
        return front
    frontier = {"all": pts[::max(1, len(pts) // 3000)], "flip_vs_workload": pareto(pts, "flip_all", "per_week"),
                "flip_vs_false_comfort": pareto(pts, "flip_all", "false_comfort_pct"),
                "candidates": {r["stage"].split(":")[1]: {k: r[k] for k in ("flip_all", "verdict_all", "per_week", "false_comfort_pct", "total")}
                               for r in records if r["stage"].startswith("candidate:")}}
    write_json(os.path.join(OUT, "frontier.json"), frontier)
    stages["total_settings"] = len(records)
    stages["seconds"] = round(time.time() - t0, 1)
    write_json(os.path.join(OUT, "sweep_stages.json"), {"stages": stages, "top_asis": [{k: v for k, v in r.items() if k != "config"} | {"config": r["config"]} for r in top_asis],
                                                        "top_raw": [{k: v for k, v in r.items() if k != "config"} | {"config": r["config"]} for r in top_raw]})
    print("\nTOP (contract as-is):")
    for i, r in enumerate(top_asis[:8], 1):
        print("  %2d %.1f%s parts %d | flips %.1f%% (10+: %.1f%%) fc %.1f%% fa %.1f%% | Y3 %s/%s/%s/%s | %.1f/wk | %s" % (
            i, r["total"], " VETO" if r["vetoed"] else "", r["parts"], r["flip_all"], r["flip_10plus"], r["false_comfort_pct"], r["false_alarm_pct"],
            r["y3_bad"], r["y3_average"], r["y3_good"], r["y3_excellent"], r["per_week"], r["signature"]))
    print("TOP (raw lines - needs the contract change):")
    for i, r in enumerate(top_raw[:8], 1):
        print("  %2d %.1f%s parts %d | flips %.1f%% (10+: %.1f%%) fc %.1f%% fa %.1f%% | Y3 %s/%s/%s/%s | %.1f/wk | %s" % (
            i, r["total"], " VETO" if r["vetoed"] else "", r["parts"], r["flip_all"], r["flip_10plus"], r["false_comfort_pct"], r["false_alarm_pct"],
            r["y3_bad"], r["y3_average"], r["y3_good"], r["y3_excellent"], r["per_week"], r["signature"]))
    print("sweep: %d settings in %.0fs" % (len(records), time.time() - t0))


if __name__ == "__main__":
    main()
