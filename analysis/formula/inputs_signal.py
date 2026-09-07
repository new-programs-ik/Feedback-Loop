"""Step 2 - which inputs carry signal, for which targets.

For every target (a-d) and every deployable input: the input's own AUC and rank correlation,
measured on the fit months (Jan-May) and confirmed on the held-out months (Jun-Aug). Then the
ceilings: a regularised logistic regression and a gradient-boosted model on three feature sets
(the sheet row only; the row plus history; everything), fitted on Jan-May and tested on Jun-Aug,
plus a rolling refit (fit up to month m, test month m+1, pooled over Jun-Aug). Cluster bootstrap
(by instructor for target a, by cohort for b and c) gives the confidence intervals.

Also: how much of the "next class falls" target is regression to the mean, and how many PM
decisions exist (target e).

Run:  python analysis/formula/inputs_signal.py   -> analysis/out/formula_signal.json, formula_signal.csv
"""
from __future__ import annotations

import os
import sys
import time
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (OUT, FIT_MONTHS, HOLDOUT_MONTHS, ROLLING_FOLDS, auc, spearman, cluster_bootstrap, write_json, write_csv)  # noqa: E402
from features import load_features, FEATURE_DOCS  # noqa: E402

warnings.filterwarnings("ignore")

TARGETS = {
    "t_a": ("instructor's next class low", "instructor"),
    "t_b": ("cohort's next class loses attendance (vs the median cohort at that week)", "cohort"),
    "t_c": ("cohort's next class low", "cohort"),
    "t_c_below": ("cohort's next class below the cohort's average so far", "cohort"),
    "t_d": ("this class under a human line (consistency)", "id"),
}
CONTINUOUS = {"b_resid": "attendance residual (log ratio minus the median at that week)", "c_delta": "next class rating minus this one"}

ROW_ONLY = ["rating", "responses", "attended", "reach", "approval", "votes", "no", "kind_live", "region_ind", "weekday"]
HISTORY = ["curr_week", "week_share", "cohort_size", "att_vs_first", "att_vs_prev", "cohort_n_before", "prev_rating", "prev_approval", "prev_low",
           "cohort_mean_before", "is_review_of_live", "live_before_rating", "module_prior_rating", "module_prior_n", "module_prior_approval",
           "rating_vs_module", "course_prior_rating", "course_prior_approval", "rating_vs_course", "track_mean", "track_n", "track_ewma",
           "track_trend", "days_since_last", "instr_prev_rating", "track_approval", "track_module_mean", "track_module_n", "rating_vs_track"]
DEPLOYABLE = ROW_ONLY + HISTORY
SETS = {"row only": ROW_ONLY, "row + history": DEPLOYABLE, "everything (incl. diagnostic)": DEPLOYABLE + ["module_loo_rating"]}


def _design(df, cols, medians=None):
    """Numeric matrix with median imputation and a missing flag per column that has gaps."""
    X = df[cols].astype(float)
    if medians is None:
        medians = X.median()
    flags = {}
    for c in cols:
        if X[c].isna().any():
            flags[c + "__missing"] = X[c].isna().astype(float)
    X = X.fillna(medians)
    for k, v in flags.items():
        X[k] = v
    return X, medians


def fit_predict(train, test, cols, target, model):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.ensemble import HistGradientBoostingClassifier
    tr = train[train[target].notna()]
    te = test[test[target].notna()]
    if len(tr) < 50 or len(te) < 20 or tr[target].nunique() < 2:
        return None, te
    ytr = tr[target].astype(int).values
    if model == "logistic":
        Xtr, med = _design(tr, cols)
        Xte, _ = _design(te, cols, med)
        Xte = Xte.reindex(columns=Xtr.columns, fill_value=0.0)
        sc = StandardScaler().fit(Xtr)
        clf = LogisticRegression(C=0.5, max_iter=2000).fit(sc.transform(Xtr), ytr)
        return clf.predict_proba(sc.transform(Xte))[:, 1], te
    clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=8, min_samples_leaf=30, l2_regularization=1.0,
                                         random_state=7).fit(tr[cols].astype(float).values, ytr)
    return clf.predict_proba(te[cols].astype(float).values)[:, 1], te


def auc_ci(p, te, target, cluster):
    y = te[target].astype(int).values
    cl = te[cluster].fillna("none").values if cluster != "id" else np.arange(len(te))
    est, se, lo, hi = cluster_bootstrap(lambda idx: auc(p[idx], y[idx]), cl, reps=200)
    return {"auc": est, "se": se, "lo": lo, "hi": hi, "n": int(len(y)), "positives": int(y.sum())}


def main():
    t0 = time.time()
    df = load_features()
    fit = df[df["month"].isin(FIT_MONTHS)]
    hold = df[df["month"].isin(HOLDOUT_MONTHS)]
    out = {"meta": {"rows": len(df), "fit_rows": len(fit), "holdout_rows": len(hold), "targets": {k: v[0] for k, v in TARGETS.items()},
                    "continuous": CONTINUOUS, "generated": time.strftime("%Y-%m-%d %H:%M")},
           "univariate": {}, "models": {}, "importance": {}, "notes": {}}
    csv_rows = []

    # ---- univariate ------------------------------------------------------------------------------
    for t, (label, cluster) in TARGETS.items():
        out["univariate"][t] = {}
        for f in DEPLOYABLE + ["module_loo_rating"]:
            rec = {}
            for name, part in (("fit", fit), ("holdout", hold)):
                sub = part[part[t].notna() & part[f].notna()]
                rec[name] = {"auc": auc(sub[f].values, sub[t].values) if len(sub) > 30 else float("nan"),
                             "rho": spearman(sub[f].values, sub[t].values) if len(sub) > 30 else float("nan"), "n": int(len(sub))}
            out["univariate"][t][f] = rec
            csv_rows.append([t, f, round(rec["fit"]["auc"], 3), round(rec["fit"]["rho"], 3), rec["fit"]["n"],
                             round(rec["holdout"]["auc"], 3), round(rec["holdout"]["rho"], 3), rec["holdout"]["n"]])
    for c, label in CONTINUOUS.items():
        out["univariate"][c] = {}
        for f in DEPLOYABLE:
            rec = {}
            for name, part in (("fit", fit), ("holdout", hold)):
                sub = part[part[c].notna() & part[f].notna()]
                rec[name] = {"rho": spearman(sub[f].values, sub[c].values) if len(sub) > 30 else float("nan"), "n": int(len(sub))}
            out["univariate"][c][f] = rec

    # ---- the reference points: rating alone, approval alone, today's v7 score -------------------
    out["reference"] = {}
    for t, (label, cluster) in TARGETS.items():
        h = hold[hold[t].notna()]
        ref = {}
        for name, col, sign in (("rating alone", "rating", -1), ("approval alone", "approval", -1), ("today's v7 score", "v7_score", -1), ("track record alone", "track_mean", -1)):
            sub = h[h[col].notna()]
            if len(sub) > 30:
                p = sign * sub[col].values.astype(float)
                ref[name] = auc_ci(p, sub, t, cluster)
        out["reference"][t] = ref

    # ---- multivariable ceilings ---------------------------------------------------------------
    for t, (label, cluster) in TARGETS.items():
        out["models"][t] = {}
        for set_name, cols in SETS.items():
            for model in ("logistic", "boosting"):
                p, te = fit_predict(fit, hold, cols, t, model)
                fixed = auc_ci(p, te, t, cluster) if p is not None else None
                # rolling: refit monthly, pool the predictions
                preds, tes = [], []
                for tr_m, te_m in ROLLING_FOLDS:
                    p2, te2 = fit_predict(df[df["month"].isin(tr_m)], df[df["month"].isin(te_m)], cols, t, model)
                    if p2 is not None:
                        preds.append(p2)
                        tes.append(te2)
                rolling = auc_ci(np.concatenate(preds), pd.concat(tes), t, cluster) if preds else None
                out["models"][t]["%s | %s" % (set_name, model)] = {"fixed": fixed, "rolling": rolling}
        # coefficients of the logistic on "row + history" (standardised), for the report
        tr = fit[fit[t].notna()]
        if len(tr) > 50 and tr[t].nunique() > 1:
            from sklearn.linear_model import LogisticRegression
            from sklearn.preprocessing import StandardScaler
            Xtr, _ = _design(tr, DEPLOYABLE)
            sc = StandardScaler().fit(Xtr)
            clf = LogisticRegression(C=0.5, max_iter=2000).fit(sc.transform(Xtr), tr[t].astype(int).values)
            coefs = sorted(zip(Xtr.columns, clf.coef_[0]), key=lambda kv: -abs(kv[1]))
            out["models"][t]["logistic_coefficients"] = [(k, float(v)) for k, v in coefs]

    # ---- importance on held-out: drop one input from the boosting model (row + history) -------
    from sklearn.ensemble import HistGradientBoostingClassifier
    for t, (label, cluster) in TARGETS.items():
        tr = fit[fit[t].notna()]
        te = hold[hold[t].notna()]
        if len(tr) < 50 or tr[t].nunique() < 2:
            continue
        ytr, yte = tr[t].astype(int).values, te[t].astype(int).values
        base_clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=8, min_samples_leaf=30, l2_regularization=1.0, random_state=7)
        base_clf.fit(tr[DEPLOYABLE].astype(float).values, ytr)
        Xte = te[DEPLOYABLE].astype(float).values
        base = auc(base_clf.predict_proba(Xte)[:, 1], yte)
        rng = np.random.default_rng(7)
        imp = {}
        for j, f in enumerate(DEPLOYABLE):
            drops = []
            for _ in range(5):
                Xp = Xte.copy()
                Xp[:, j] = rng.permutation(Xp[:, j])
                drops.append(base - auc(base_clf.predict_proba(Xp)[:, 1], yte))
            imp[f] = float(np.mean(drops))
        out["importance"][t] = {"base_auc": base, "permutation_drop": dict(sorted(imp.items(), key=lambda kv: -kv[1]))}

    # ---- notes: regression to the mean, PM decisions ------------------------------------------
    sub = df[df["c_delta"].notna()]
    out["notes"]["regression_to_mean"] = {"corr_rating_vs_next_minus_this": float(sub["rating"].corr(sub["c_delta"])),
                                          "auc_rating_for_t_c_fall": auc(-sub["rating"].values, sub["t_c_fall"].values),
                                          "auc_rating_for_t_c": auc(-sub["rating"].values, sub["t_c"].values)}
    out["notes"]["pm_decisions"] = {"rows_with_a_decision": int(df["t_e"].sum()), "rows": len(df)}
    out["notes"]["base_rates"] = {t: {"fit": float(fit[t].mean()), "holdout": float(hold[t].mean())} for t in TARGETS}

    write_json(os.path.join(OUT, "formula_signal.json"), out)
    write_csv(os.path.join(OUT, "formula_signal.csv"), ["target", "input", "auc_fit", "rho_fit", "n_fit", "auc_holdout", "rho_holdout", "n_holdout"], csv_rows)

    # ---- console summary ------------------------------------------------------------------------
    for t in TARGETS:
        u = out["univariate"][t]
        top = sorted(((f, v["holdout"]["auc"]) for f, v in u.items() if v["holdout"]["auc"] == v["holdout"]["auc"]), key=lambda kv: -abs(kv[1] - 0.5))[:8]
        print("%s (%s): top held-out inputs: %s" % (t, TARGETS[t][0], ", ".join("%s %.2f" % (f, a) for f, a in top)))
        for k, v in out["models"][t].items():
            if k == "logistic_coefficients" or not v["fixed"]:
                continue
            print("   %-42s fixed %.3f (%.3f-%.3f)  rolling %.3f" % (k, v["fixed"]["auc"], v["fixed"]["lo"], v["fixed"]["hi"], v["rolling"]["auc"] if v["rolling"] else float("nan")))
        print("   reference: %s" % ", ".join("%s %.3f" % (k, v["auc"]) for k, v in out["reference"][t].items()))
    print("regression to the mean:", {k: round(v, 3) for k, v in out["notes"]["regression_to_mean"].items()})
    print("PM decisions recorded: %d of %d rows | %.0fs" % (out["notes"]["pm_decisions"]["rows_with_a_decision"], len(df), time.time() - t0))


if __name__ == "__main__":
    main()
