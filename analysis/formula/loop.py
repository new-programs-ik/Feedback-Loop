"""Step 5 - the loop: propose -> fit on the training months -> check the properties on the
generated cases -> judge on the selection months -> simplify -> repeat.

The rules, fixed before the first iteration:

  fitting     every weight, shape, k and band edge is fitted on the training months of each
              selection fold (Jan-Mar -> judged on Apr; Jan-Apr -> judged on May); the deployable
              settings are fitted on Jan-May. The held-out months (Jun-Aug) are scored once per
              candidate for the report and never used to choose.
  objective   the mean AUC of (100 - score) for "the instructor's next class is low" and "the
              cohort's next class is low" (targets a and c), pooled over the selection months,
              with a cluster-bootstrap standard error. Attendance loss (target b) is reported
              but not fitted against: no quality input predicts it (AUC ~0.54).
  admissible  every property passes on the case fixture, and on the selection months: false
              comfort <= 2%, false alarm <= 5%, at most 12 analyses and 5 videos a week.
  adopt       an admissible candidate replaces the best if its objective is higher by more than
              one standard error - or is within one standard error and (a) simpler (fewer moving
              parts), or (b) as simple with fewer verdict flips, or (c) one part more complex but
              cutting verdict flips at 10+ votes by more than 3 points ("stability buys one part").
              Rule (c) was added after a dry run (formula_log_dryrun.jsonl) showed the objective
              cannot separate the candidates - every difference sits inside one standard error -
              so stability and simplicity, not signal, have to decide.
  stop        the fixed exploration (families, inputs, shapes) always completes; from the
              simplification and neighbourhood phases on, three consecutive iterations with no
              adoption end the loop; 40 iterations at most.

Every iteration is appended to analysis/out/formula_log.jsonl; the full results go to
formula_results.json and the winner's settings to formula_recommended.json.

Run:  python analysis/formula/loop.py            (about 5-10 minutes)
"""
from __future__ import annotations

import copy
import math
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (OUT, FIT_MONTHS, HOLDOUT_MONTHS, SELECT_FOLDS, weeks_in, write_json, append_jsonl, read_json, LINE, BAR)  # noqa: E402
from features import load_features  # noqa: E402
from families import (Original, TodayV7, C5Guarded, Points, Logistic, Sequential, inputs_from_df, inputs_from_cases, describe,  # noqa: E402
                      fit_bands_for_workload, score_any)
from evaluate import score_three, concat_results, metrics, constraints, soft_marks  # noqa: E402
from properties import run_properties, summarise  # noqa: E402
from cases import load_cases  # noqa: E402
from trust import trust_for  # noqa: E402

LOG = os.path.join(OUT, "formula_log.jsonl")
RESULTS = os.path.join(OUT, "formula_results.json")
RECOMMENDED = os.path.join(OUT, "formula_recommended.json")
MAX_ITER = 40
PATIENCE = 3


# ------------------------------------------------------------------ specs -> families
def make(spec):
    fam = spec["family"]
    kw = dict(spec.get("kwargs", {}))
    if fam == "Original":
        return Original()
    if fam == "TodayV7":
        return TodayV7()
    if fam == "C5Guarded":
        return C5Guarded()
    if fam == "Points":
        return Points(**kw)
    if fam == "Logistic":
        return Logistic(**kw)
    if fam == "Sequential":
        return Sequential(**kw)
    raise ValueError(fam)


def moving_parts(cfg):
    """How many ideas a PM must hold: inputs with weight, the guard, the lines, the floors, the knee, the graded vote."""
    if cfg.get("model") == "logistic":
        return len(cfg["inputs"]) + 2 + (1 if cfg["caps"].get("rating_line") is not None else 0) + 1
    parts = sum(1 for k, w in cfg["weights"].items() if w and not (k == "track" and cfg["track"]["mode"] == "off")
                and not (k == "sample" and cfg["sample"]["mode"] == "off") and not (k == "reach" and cfg["reach"]["mode"] == "off"))
    parts += 1 if (cfg["guard"].get("k") or 0) > 0 else 0
    parts += 1 if cfg["guard"].get("k_low") is not None else 0
    parts += 1 if cfg["caps"].get("rating_line") is not None else 0
    parts += 1 if (cfg["min_votes"].get("band") or cfg["min_votes"].get("action")) else 0
    parts += 1 if cfg["rating"]["mode"] == "knee" else 0
    parts += 1 if cfg["approval"]["mode"] != "cliff" else 0
    return parts


# ------------------------------------------------------------------ assessment
class Assessor:
    def __init__(self, df, cases, X_cases):
        self.df = df
        self.cases, self.X_cases = cases, X_cases
        self.fit_df = df[df["month"].isin(FIT_MONTHS)].reset_index(drop=True)
        self.hold_df = df[df["month"].isin(HOLDOUT_MONTHS)].reset_index(drop=True)
        self.X_fit = inputs_from_df(self.fit_df)
        self.X_hold = inputs_from_df(self.hold_df)
        self.trust_fit = trust_for(self.fit_df)
        self.folds = []
        for tr_m, va_m in SELECT_FOLDS:
            tr = df[df["month"].isin(tr_m)].reset_index(drop=True)
            va = df[df["month"].isin(va_m)].reset_index(drop=True)
            self.folds.append({"train": tr, "X_train": inputs_from_df(tr), "trust": trust_for(tr), "val": va, "X_val": inputs_from_df(va), "weeks": weeks_in(va_m)})

    def assess(self, spec, bootstrap_sel=80, bootstrap_hold=200):
        fam = make(spec)
        # selection: fit per fold, score the fold's validation months with its own settings, pool
        parts, dfs, weeks = [], [], 0.0
        fold_cfgs = []
        for f in self.folds:
            cfg = fam.fit(f["train"], f["X_train"], f["trust"])
            fold_cfgs.append(cfg)
            parts.append(score_three(f["val"], cfg, f["X_val"]))
            dfs.append(f["val"])
            weeks += f["weeks"]
        pooled_df = pd.concat(dfs).reset_index(drop=True)
        res = [concat_results([p[i] for p in parts]) for i in range(3)]
        sel = metrics(pooled_df, res[0], res[1], res[2], weeks, bootstrap=bootstrap_sel)
        # deployable settings: fit on all training months; report on held-out and on the training months
        cfg = fam.fit(self.fit_df, self.X_fit, self.trust_fit)
        r_fit = score_three(self.fit_df, cfg, self.X_fit)
        ev_fit = metrics(self.fit_df, *r_fit, weeks_in(FIT_MONTHS), bootstrap=0)
        r_hold = score_three(self.hold_df, cfg, self.X_hold)
        ev_hold = metrics(self.hold_df, *r_hold, weeks_in(HOLDOUT_MONTHS), bootstrap=bootstrap_hold)
        props = run_properties(cfg, self.cases, self.X_cases)
        ps = summarise(props)
        fails = constraints(sel)
        shape_ok, needs = fam.contract_shape(cfg)
        return {"spec": spec, "family": fam.key, "name": fam.name, "config": cfg, "fold_configs": fold_cfgs, "sentence": fam.sentence(cfg),
                "describe": describe(cfg), "inputs": list(fam.inputs), "parts": moving_parts(cfg), "contract_as_is": shape_ok, "contract_needs": needs,
                "selection": sel, "fit": ev_fit, "holdout": ev_hold, "properties": {"summary": ps, "detail": {k: {kk: vv for kk, vv in v.items() if kk != "examples"} for k, v in props.items()},
                                                                                     "examples": {k: v["examples"] for k, v in props.items() if not v["passed"]}},
                "constraint_fails": fails, "admissible": (ps["passed"] == ps["total"]) and not fails, "soft": soft_marks(sel)}


# ------------------------------------------------------------------ the schedule
def P(**kw):
    return {"family": "Points", "kwargs": kw}


def schedule_phase_a():
    return [
        ("A0", {"family": "Original"}, "the manager's original", "the reference point everything is measured against"),
        ("A1", {"family": "TodayV7"}, "today's active version (v7)", "the incumbent: two lines + graded score, guard off, analysis from 6 votes"),
        ("A2", {"family": "C5Guarded"}, "C5 as studied (guard k=5 on the course prior)", "the earlier study's candidate, with the lines read on the guarded values"),
        ("A3", P(key="P5", name="Points + trust, analysis from 5 votes", min_action=5, workload_bands=True), "weighted points + trust machinery, analysis from 5 votes",
         "the contract's shape with the data-derived guard (k from the variance split), a module-first prior, the lines read on the raw values, weights refitted within the design box, edges lowered only if capacity demands"),
        ("A4", P(key="P6", name="Points + trust, analysis from 6 votes", min_action=6, workload_bands=True), "the same, analysis from 6 votes",
         "today's floor; the believability table says a low average is believable from 5, capacity says 6"),
        ("A5", P(key="W", name="Points + trust, Wilson vote", approval_mode="wilson", min_action=6, workload_bands=True), "the vote as a Wilson lower bound instead of a blended share",
         "the other standard way to distrust a thin vote"),
        ("A6", {"family": "Logistic", "kwargs": {"inputs": ("rating", "approval", "track")}}, "monotone logistic on rating, vote, record",
         "the probability shape: 100 minus the chance the next class goes wrong"),
        ("A7", {"family": "Sequential", "kwargs": {"key": "S", "name": "Sequential", "min_action": 6, "workload_bands": True}}, "sequential: recent record (EWMA) + shrinkage toward the instructor's own record",
         "does the instructor's series carry more than the plain record?"),
    ]


def schedule_phase_b(best_spec):
    """Inputs: add each candidate input to the best, drop the record, swap the prior."""
    base = copy.deepcopy(best_spec)
    kw = base["kwargs"]
    out = []
    for e, why in (("module_delta", "how the class compares with its module's usual rating"), ("attendance", "attendance against the cohort's previous class"),
                   ("momentum", "the cohort's previous class rating")):
        s = copy.deepcopy(base)
        s["kwargs"]["extras"] = tuple(sorted(set(kw.get("extras", ())) | {e}))
        s["kwargs"]["key"] = "P+" + e[:3]
        s["kwargs"]["name"] = "Points + trust + " + e
        out.append(("B-" + e, s, "add %s as a component" % e, why))
    s = copy.deepcopy(base)
    s["kwargs"].update(track_mode="off", key="P-track", name="Points + trust, no record")
    out.append(("B-notrack", s, "drop the instructor's record", "is the record worth its points, or is it the instructor's persistence dressed as this class?"))
    s = copy.deepcopy(base)
    s["kwargs"].update(track_mode="ewma", key="P-ewma", name="Points + trust, recent record")
    out.append(("B-ewma", s, "the record as a recency-weighted mean (half-life 60 days)", "does a recent slump matter more than an old one?"))
    s = copy.deepcopy(base)
    s["kwargs"].update(prior="course", key="P-course", name="Points + trust, course prior")
    out.append(("B-course", s, "shrink toward the course prior (as the contract does today) instead of module-first", "is the module prior worth a new input to the sync?"))
    s = copy.deepcopy(base)
    s["kwargs"].update(prior="instructor", key="P-instr", name="Points + trust, instructor prior")
    out.append(("B-instr", s, "shrink toward the instructor's own record", "the trust machinery pointed at the person rather than the module"))
    return out


def schedule_phase_c(best_spec):
    """Shapes: k, asymmetry, the lines, the knee, the cliff, the floors, the band edges, refitting."""
    base = copy.deepcopy(best_spec)
    out = []

    def var(tag, change, why, **changes):
        s = copy.deepcopy(base)
        s["kwargs"].update(changes)
        s["kwargs"]["key"] = "P:" + tag
        s["kwargs"]["name"] = "Points + trust, " + change
        out.append(("C-" + tag, s, change, why))
    var("k5", "guard k = 5 (the earlier guess)", "the study guessed 5 phantom raters; the data says about 3", k_mode="5")
    var("k0", "no shrinkage at all (floors only)", "is the guard worth having once the vote floors exist?", k_mode="0")
    var("asym", "asymmetric trust: a low average is shrunk twice as hard as a high one", "the owner's hypothesis that few-rater lows are the suspicious case", asym=True)
    var("nocaps", "no hard lines (the score alone decides)", "are the two lines doing work the score cannot?", caps=False)
    var("guardedlines", "the lines read on the guarded values (as the contract does today)", "the earlier study's finding F1, re-tested", caps_basis="guarded")
    var("linear", "rating straight (÷5) instead of the knee", "is the steeper slope below 4.55 earning anything?", rating_mode="linear")
    var("cliff", "approval as a cliff at 80% instead of graded", "the manager's original vote shape", approval_mode="cliff")
    other_floor = 5 if base["kwargs"].get("min_action", 5) == 6 else 6
    var("floor%d" % other_floor, "analysis from %d votes" % other_floor, "the vote floor is the team's workload dial; both sides of it are measured", min_action=other_floor)
    var("roundbands", "band edges held at the round numbers 90/75/60", "is the capacity-fitted edge doing anything?", workload_bands=False)
    var("fixedw", "weights held at 60/25/15 (no refit)", "is refitting the weights worth anything at all?", refit_weights=False, weights={"rating": 60, "approval": 25, "track": 15})
    return out


def schedule_phase_d(best_spec):
    """Simplify: drop each optional input of the best in turn."""
    if best_spec["family"] not in ("Points", "Sequential"):
        return []
    out = []
    kw = best_spec["kwargs"]
    for e in kw.get("extras", ()):
        s = copy.deepcopy(best_spec)
        s["kwargs"]["extras"] = tuple(x for x in kw["extras"] if x != e)
        s["kwargs"]["key"] = "P-" + e[:3]
        s["kwargs"]["name"] = "Points + trust without " + e
        out.append(("D-drop-" + e, s, "drop %s" % e, "simplify: keep it only if it earns more than one standard error"))
    if kw.get("track_mode", "on") != "off":
        s = copy.deepcopy(best_spec)
        s["kwargs"].update(track_mode="off", key="P-track", name="Points + trust, no record")
        out.append(("D-drop-track", s, "drop the instructor's record", "simplify"))
    if (kw.get("k_mode", "data") != "0"):
        s = copy.deepcopy(best_spec)
        s["kwargs"].update(k_mode="0", key="P:k0", name="Points, floors only")
        out.append(("D-drop-guard", s, "drop the guard (floors only)", "simplify"))
    return out


def schedule_phase_e(best_spec, results, seed=7):
    """Adaptive neighbourhood search around the best points spec: random small changes to the
    trust settings, floors and inputs, skipping anything already tried. Runs until the stop rule."""
    if best_spec["family"] not in ("Points", "Sequential"):
        return []
    rng = np.random.default_rng(seed)
    tried = {tuple(sorted((k, str(v)) for k, v in r["spec"].get("kwargs", {}).items() if k not in ("key", "name"))) for r in results.values()}
    moves = [("k_mode", ["data", "1.5", "4", "8"]), ("min_action", [5, 6, 7]), ("prior", ["hierarchical", "course", "module"]),
             ("extras", [(), ("module_delta",), ("momentum",), ("module_delta", "momentum")]), ("track_mode", ["on", "ewma", "off"]),
             ("workload_bands", [True, False]), ("asym", [False, True]), ("rating_mode", ["knee", "linear"])]
    out, n = [], 0
    for _ in range(200):
        s = copy.deepcopy(best_spec)
        kw = s["kwargs"]
        picks = rng.choice(len(moves), size=int(rng.integers(1, 3)), replace=False)
        desc = []
        for i in picks:
            k, opts = moves[i]
            v = opts[int(rng.integers(0, len(opts)))]
            if kw.get(k) == v:
                continue
            kw[k] = v
            desc.append("%s -> %s" % (k, v))
        sig = tuple(sorted((k, str(v)) for k, v in kw.items() if k not in ("key", "name")))
        if not desc or sig in tried:
            continue
        tried.add(sig)
        n += 1
        kw["key"] = "P~%d" % n
        kw["name"] = "Points + trust, " + ", ".join(desc)
        out.append(("E%02d" % n, s, ", ".join(desc), "neighbourhood search around the best"))
        if n >= 20:
            break
    return out


def weights_ablation(A, best_spec):
    """What the data alone would choose for the weights (no property box) on the training months,
    against the box the properties impose - and how both do on the held-out months."""
    from families import fit_weights, base_config, WEIGHT_LIMITS
    fam = make(best_spec) if best_spec["family"] in ("Points", "Sequential") else make(P(key="P6", name="Points + trust", min_action=6, workload_bands=True))
    cfg_box = fam.fit(A.fit_df, A.X_fit, A.trust_fit)
    wide = {"rating": (20, 100), "approval": (0, 60), "track": (0, 60), "module_delta": (0, 40), "attendance": (0, 40), "momentum": (0, 40)}
    keys = [k for k in ("rating", "approval", "track") if cfg_box["weights"].get(k) is not None and not (k == "track" and cfg_box["track"]["mode"] == "off")]
    cfg_free, obj_train = fit_weights(A.fit_df, A.X_fit, cfg_box, keys, limits=wide)
    from properties import run_properties, summarise
    out = {}
    for label, cfg in (("within the property box", cfg_box), ("data alone (no box)", cfg_free)):
        ev_h = metrics(A.hold_df, *score_three(A.hold_df, cfg, A.X_hold), weeks_in(HOLDOUT_MONTHS), bootstrap=100)
        ev_f = metrics(A.fit_df, *score_three(A.fit_df, cfg, A.X_fit), weeks_in(FIT_MONTHS), bootstrap=0)
        ps = summarise(run_properties(cfg, A.cases, A.X_cases))
        out[label] = {"weights": {k: v for k, v in cfg["weights"].items() if v}, "fit_objective": ev_f["objective"]["value"], "holdout": brief(ev_h),
                      "properties": ps}
    return out


# ------------------------------------------------------------------ the decision rule
def better(cand, best):
    """(adopt?, reason)."""
    if not cand["admissible"]:
        return False, "not admissible: " + "; ".join(cand["constraint_fails"] + ["fails " + p for p in cand["properties"]["summary"]["failed"]])
    if best is None:
        return True, "first admissible candidate"
    a, b = cand["selection"]["objective"], best["selection"]["objective"]
    se = max(a["se"] if a["se"] == a["se"] else 0.0, b["se"] if b["se"] == b["se"] else 0.0, 0.005)
    gain = a["value"] - b["value"]
    if gain > se:
        return True, "objective +%.3f, more than one standard error (%.3f)" % (gain, se)
    if gain >= -se:
        fl_c, fl_b = cand["soft"]["verdict_flips_10plus"], best["soft"]["verdict_flips_10plus"]
        if cand["parts"] < best["parts"] and fl_c <= fl_b + 3.0:
            return True, "within one standard error (%+.3f) and simpler (%d moving parts vs %d)" % (gain, cand["parts"], best["parts"])
        if cand["parts"] == best["parts"] and fl_c < fl_b - 1.0:
            return True, "within one standard error (%+.3f), as simple, fewer verdict flips (%.1f%% vs %.1f%%)" % (gain, fl_c, fl_b)
        if cand["parts"] == best["parts"] + 1 and fl_c < fl_b - 3.0:
            return True, "within one standard error (%+.3f); one part more, but verdict flips at 10+ votes fall by %.1f points (%.1f%% vs %.1f%%)" % (gain, fl_b - fl_c, fl_c, fl_b)
        return False, "within one standard error (%+.3f) but not simpler and not clearly more stable (flips %.1f%% vs %.1f%%)" % (gain, fl_c, fl_b)
    return False, "objective %+.3f, worse by more than one standard error (%.3f)" % (gain, se)


def brief(ev):
    s = ev["signal"]
    return {"objective": ev["objective"]["value"], "se": ev["objective"]["se"],
            "auc_a": s["t_a"]["auc"] if s.get("t_a") else None, "auc_b": s["t_b"]["auc"] if s.get("t_b") else None,
            "auc_c": s["t_c"]["auc"] if s.get("t_c") else None, "auc_d": s["t_d"]["auc"] if s.get("t_d") else None,
            "false_comfort": ev["lines"]["false_comfort"], "false_comfort_share": ev["lines"]["false_comfort_share"],
            "false_alarm": ev["lines"]["false_alarm"], "bad_rated_fine": ev["lines"]["bad_rated_fine"], "bad_total": ev["lines"]["bad_total"],
            "per_week": ev["workload"]["per_week"], "videos_per_week": ev["workload"]["videos_per_week"],
            "flip_label": ev["stability"]["flip_label"], "flip_verdict": ev["stability"]["flip_verdict"], "flip_verdict_10plus": ev["stability"]["flip_verdict_10plus"],
            "max_move_20plus": ev["stability"]["max_move_20plus"],
            "risk_bad": ev["bands"]["per_band"]["bad"]["a_share"], "risk_excellent": ev["bands"]["per_band"]["excellent"]["a_share"],
            "band_order": ev["bands"]["order_ok_a"], "fairness_gap": ev["fairness"]["max_flagged_gap"], "no_band_share": ev["bands"]["no_band_share"]}


# ------------------------------------------------------------------ main
def main():
    t0 = time.time()
    if os.path.exists(LOG):
        os.remove(LOG)
    df = load_features()
    cases, fx = load_cases(full_grid=False)
    X_cases = inputs_from_cases(cases)
    A = Assessor(df, cases, X_cases)
    print("rows %d | fit %d | holdout %d | cases %d | folds %d" % (len(df), len(A.fit_df), len(A.hold_df), len(cases), len(A.folds)))

    results, best, history = {}, None, []
    it, no_improve, stopped = 0, 0, None

    def run(phase, items, enforce_patience):
        nonlocal it, no_improve, best, stopped
        for tag, spec, change, why in items:
            if it >= MAX_ITER or stopped:
                stopped = stopped or "40 iterations reached"
                return
            it += 1
            t1 = time.time()
            r = A.assess(spec)
            adopt, reason = better(r, best)
            key = r["config"].get("name") or tag
            rec = {"iteration": it, "phase": phase, "tag": tag, "key": r["family"], "name": r["name"], "change": change, "why": why,
                   "settings": r["describe"], "sentence": r["sentence"], "parts": r["parts"], "contract_as_is": r["contract_as_is"], "contract_needs": r["contract_needs"],
                   "properties_passed": "%d/%d" % (r["properties"]["summary"]["passed"], r["properties"]["summary"]["total"]),
                   "properties_failed": r["properties"]["summary"]["failed"], "constraint_fails": r["constraint_fails"],
                   "selection": brief(r["selection"]), "holdout": brief(r["holdout"]), "fit": brief(r["fit"]),
                   "decision": "adopted" if adopt else "rejected", "reason": reason, "seconds": round(time.time() - t1, 1)}
            results[tag] = r
            if adopt:
                best = r
                best["tag"] = tag
                no_improve = 0
            else:
                no_improve += 1
            rec["best_after"] = best["tag"] if best else None
            history.append(rec)
            append_jsonl(LOG, rec)
            sb = rec["selection"]
            print("[%2d %s] %-46s sel %.3f±%.3f (a %.3f c %.3f) fc %d fa %d /wk %.1f | hold %.3f | props %s | %s | %s (%.0fs)" % (
                it, tag, (r["name"] or "")[:46], sb["objective"], sb["se"], sb["auc_a"] or 0, sb["auc_c"] or 0, sb["false_comfort"], sb["false_alarm"], sb["per_week"],
                rec["holdout"]["objective"], rec["properties_passed"], rec["decision"], reason[:90], rec["seconds"]))
            if enforce_patience and no_improve >= PATIENCE:
                stopped = "three consecutive iterations improved nothing (phase %s)" % phase
                return

    run("A families", schedule_phase_a(), enforce_patience=False)

    def points_base():
        """The base for the input/shape phases: the best if it is a points family, else the best
        admissible points candidate so far, else the 6-vote points candidate."""
        if best and best["spec"]["family"] in ("Points", "Sequential"):
            return best["spec"]
        pool = [r for r in results.values() if r["spec"]["family"] in ("Points", "Sequential") and r["admissible"]]
        if pool:
            return max(pool, key=lambda r: r["selection"]["objective"]["value"])["spec"]
        return results["A4"]["spec"] if "A4" in results else P(key="P6", name="Points + trust, analysis from 6 votes", min_action=6, workload_bands=True)
    run("B inputs", schedule_phase_b(points_base()), enforce_patience=False)
    run("C shapes", schedule_phase_c(points_base()), enforce_patience=False)
    no_improve = 0
    if best is not None:
        run("D simplify", schedule_phase_d(points_base()), enforce_patience=True)
    if not stopped:
        run("E neighbourhood", schedule_phase_e(points_base(), results), enforce_patience=True)
    stopped = stopped or "schedule exhausted"

    # ---- outputs -------------------------------------------------------------------------------
    ablation = weights_ablation(A, results["A4"]["spec"] if "A4" in results else points_base())
    out = {"ablations": {"weights": ablation}, "meta": {"generated": time.strftime("%Y-%m-%d %H:%M"), "iterations": it, "stopped": stopped, "seconds": round(time.time() - t0),
                    "rows": len(df), "fit_rows": len(A.fit_df), "holdout_rows": len(A.hold_df), "cases": len(cases),
                    "selection_folds": [{"train": tr, "validate": va} for tr, va in SELECT_FOLDS], "fit_months": list(FIT_MONTHS), "holdout_months": list(HOLDOUT_MONTHS),
                    "rules": {"objective": "mean AUC of (100 - score) for targets a and c on the selection months", "adopt": "gain > 1 SE, or within 1 SE and simpler",
                              "admissible": "all properties pass; false comfort <= 2%, false alarm <= 5%, <= 12 analyses and <= 5 videos a week on the selection months",
                              "stop": "the fixed exploration (A-C) completes; from phase D on, three consecutive iterations without adoption; 40 at most"}},
           "history": history, "best": best["tag"] if best else None,
           "candidates": {tag: {k: v for k, v in r.items() if k not in ("fold_configs",)} for tag, r in results.items()}}
    write_json(RESULTS, out)
    if best:
        write_recommended(best, results)
    print("loop done: %d iterations, %s, best %s (%s) in %.0fs" % (it, stopped, best["tag"] if best else None, best["name"] if best else "-", time.time() - t0))


RATER_RELIABILITY_SPEC = {
    "name": "rater_reliability",
    "status": "designed, not built - needs per-learner ratings, which the sheet does not carry",
    "what_it_needs": "one row per learner per class: learner id, class id, date, the learner's star rating, and their yes/no vote",
    "how_it_plugs_in": [
        "Each learner gets a reliability weight w in [0.25, 1]: 1 by default; lowered when the learner's past ratings sit consistently far below "
        "the class averages they rated (a persistent negative bias), measured as the mean of (learner rating - class average) over their previous "
        "ratings, needing at least 5 of them; a learner with fewer than 5 earlier ratings keeps w = 1.",
        "The class's trusted rating = sum(w_i * r_i) / sum(w_i); the trusted vote = sum(w_i * yes_i) / sum(w_i).",
        "The effective number of raters n_eff = (sum w_i)^2 / sum(w_i^2) replaces the raw count in the guard and the vote floors, so a class carried "
        "by a few down-weighted raters is treated as thinner, not as lower.",
        "No other part of the formula changes: the trusted rating and vote enter exactly where the raw ones do.",
    ],
    "guard_rails": ["a weight never rises above 1 (enthusiasm is not down-weighted; only a persistent negative bias is)", "weights are recomputed monthly, never per class",
                    "a learner's weight is never shown to instructors", "the raw and the trusted rating are both stored; the flag 'rater_reliability_applied' explains any gap"],
    "how_to_validate": "re-run this study with the trusted rating in place of the raw one; keep it only if the held-out objective improves by more than one standard error",
}


def _entry(r):
    cfg = copy.deepcopy(r["config"])
    cfg.pop("note", None)
    return {"name": cfg.get("name"), "family": r["family"], "tag": r.get("tag"), "sentence": r["sentence"], "settings": cfg,
            "fits_current_contract": r["contract_as_is"], "contract_needs": r["contract_needs"], "new_components": component_specs(cfg),
            "measured": {"selection_months": brief(r["selection"]), "holdout_months": brief(r["holdout"])},
            "properties": r["properties"]["summary"], "inputs": r["inputs"], "moving_parts": r["parts"]}


def write_recommended(best, results):
    rec = {"recommended": _entry(best),
           "rater_reliability": RATER_RELIABILITY_SPEC,
           "note": "Chosen by the loop on the selection months (Mar-May, each judged after fitting on the months before); the held-out numbers "
                   "(Jun-Aug) were never used to choose. The refinement is the best admissible candidate that is not the incumbent: within one "
                   "standard error on signal, the same verdicts, a steadier displayed number - kept in the drawer until the contract change it needs lands."}
    # the refinement: the incumbent's own inputs (rating, vote, record) with the trust guard on - the simplest
    # admissible points candidate within one standard error of the best points candidate
    def plain(r):
        kw = r["spec"].get("kwargs", {})
        return (r["spec"]["family"] == "Points" and r["admissible"] and not kw.get("extras") and kw.get("track_mode", "on") == "on"
                and kw.get("rating_mode", "knee") == "knee" and kw.get("approval_mode", "graded") == "graded" and kw.get("caps", True)
                and kw.get("caps_basis", "raw") == "raw" and not kw.get("asym") and kw.get("k_mode", "data") == "data")
    pool = [r for tag, r in results.items() if plain(r) and tag != best.get("tag")]
    if pool:
        top = max(r["selection"]["objective"]["value"] for r in pool)
        se = max(r["selection"]["objective"]["se"] for r in pool)
        near = [r for r in pool if r["selection"]["objective"]["value"] >= top - se]
        ref = min(near, key=lambda r: (r["parts"], r["selection"]["workload"]["per_week"], -r["selection"]["objective"]["value"]))
        ref["tag"] = next(tag for tag, r in results.items() if r is ref)
        rec["refinement"] = _entry(ref)
    write_json(RECOMMENDED, rec)


def component_specs(cfg):
    """The exact spec of every input the current contract lacks."""
    specs = []
    g = cfg.get("guard", {})
    if g.get("prior", "course") in ("module", "hierarchical"):
        specs.append({"name": "module prior", "inputs": ["topic_id", "cohort_id", "class_date"], "shape": "mean rating and pooled yes/votes over earlier classes on the same topic in OTHER cohorts (strictly before the class date)",
                      "used_as": "the value the guard shrinks toward when the module has at least %d earlier classes; else the course prior" % int(g.get("prior_min_n", 3)),
                      "missing_value_rule": "fall back to the course prior; with no prior at all, no shrinkage (raw values)",
                      "sync_must_compute": "module_prior_rating, module_prior_n, module_prior_approval per class at scoring time (a window function over class_ratings by topic_id, excluding the class's own cohort)"})
    if g.get("k_approval") is not None and float(g["k_approval"]) != float(g.get("k") or 0):
        specs.append({"name": "guard.k_approval", "inputs": ["yes_votes", "no_votes", "prior_approval"], "shape": "approval blended with k_approval phantom votes at the prior's approval",
                      "weight": None, "missing_value_rule": "no vote: approval stays missing (neutral)", "sync_must_compute": "nothing new; a config key the scorer reads"})
    if cfg.get("caps", {}).get("basis", "guarded") == "raw":
        specs.append({"name": "caps.basis = raw", "inputs": ["rating", "approval"], "shape": "the two hard lines are read on the raw rating and vote, the guard shapes the score only",
                      "missing_value_rule": "no vote: only the rating line applies", "sync_must_compute": "nothing new; a config key the scorer reads (the earlier study's finding F1)"})
    if cfg.get("track", {}).get("mode") == "ewma":
        specs.append({"name": "track.mode = ewma", "inputs": ["instructor_id", "class_date"], "shape": "recency-weighted mean of the instructor's earlier ratings, half-life 60 days, at least 3 earlier classes",
                      "missing_value_rule": "under 3 earlier classes: neutral (excluded)", "sync_must_compute": "track_ewma per class"})
    for name, spec in (cfg.get("extras") or {}).items():
        w = cfg["weights"].get(name, 0)
        if not w:
            continue
        specs.append({"name": name, "inputs": {"module_delta": ["rating", "module_prior_rating", "module_prior_n"], "attendance": ["attended", "previous same-kind class attended (same cohort)"],
                                              "momentum": ["previous class rating (same cohort)"]}[name],
                      "shape": "0 at %g, 100 at %g, straight in between" % (spec["floor"], spec["ceiling"]), "weight": w,
                      "missing_value_rule": "neutral (excluded, weights re-scaled)", "sync_must_compute": name + " per class at scoring time"})
    return specs


if __name__ == "__main__":
    main()
