"""Step 2b - trust: how many votes make a low average believable, and whether a low average from
few raters deserves less belief than a high one.

The manager's "responses" term (6 points at 10+ raters) was meant as trust, not quality: a low
average from two or three raters may be two or three biased learners. Without per-learner ratings
we cannot check the raters, but we can check the claim itself on eight months of classes:

  1. Believability by vote count. Among classes under the 4.55 line (or under the 80% bar), by
     how many voted: how often does the instructor's next class, and the cohort's next class, go
     wrong - against classes over the line with the same number of votes. If a low 3-vote class
     predicts trouble as well as a low 15-vote class, the low average is believable at 3 votes;
     if not, it needs shrinking.
  2. The shrinkage strength the data supports. Var(rating - prior | n raters) = tau^2 + sigma^2 / n:
     tau is the true spread between classes, sigma the spread between raters inside a class. The
     Bayesian weight of the prior is k = sigma^2 / tau^2 "phantom raters" - the guard's k, derived
     instead of guessed. Fitted by weighted least squares on the fit months, checked on held-out.
  3. Asymmetry. The same believability table split by whether the class sits above or below its
     prior: if few-vote lows are less predictive than many-vote lows while few-vote highs are as
     predictive as many-vote highs, the data supports trusting the two differently.

Run:  python analysis/formula/trust.py   -> analysis/out/formula_trust.json
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (OUT, LINE, BAR, FIT_MONTHS, HOLDOUT_MONTHS, auc, cluster_bootstrap, write_json)  # noqa: E402
from features import load_features  # noqa: E402

VOTE_BUCKETS = (("1-2", 1, 2), ("3-4", 3, 4), ("5-9", 5, 9), ("10-14", 10, 14), ("15+", 15, 10 ** 9))


def bucket(v):
    for name, lo, hi in VOTE_BUCKETS:
        if lo <= v <= hi:
            return name
    return "0"


def risk_table(df, cond_col, target, cluster):
    """Per vote bucket: the target rate when the condition holds vs when it does not, with a
    cluster-bootstrap interval on the difference."""
    out = {}
    for name, lo, hi in VOTE_BUCKETS:
        sub = df[(df["votes"] >= lo) & (df["votes"] <= hi) & df[target].notna()]
        a = sub[sub[cond_col] == 1]
        b = sub[sub[cond_col] == 0]
        rec = {"n_low": int(len(a)), "n_fine": int(len(b)),
               "risk_low": float(a[target].mean()) if len(a) else None, "risk_fine": float(b[target].mean()) if len(b) else None}
        if len(a) >= 8 and len(b) >= 8:
            y = sub[target].values.astype(float)
            c = sub[cond_col].values
            cl = sub[cluster].fillna("none").values

            def diff(idx):
                yy, cc = y[idx], c[idx]
                if (cc == 1).sum() == 0 or (cc == 0).sum() == 0:
                    return float("nan")
                return float(yy[cc == 1].mean() - yy[cc == 0].mean())
            est, se, lo_, hi_ = cluster_bootstrap(diff, cl, reps=300)
            rec.update({"diff": est, "diff_se": se, "diff_lo": lo_, "diff_hi": hi_})
        out[name] = rec
    return out


def variance_decomposition(df, prior_col):
    """Fit Var(rating - prior | n) = tau^2 + sigma^2 / n by weighted least squares over the
    squared deviations; returns tau, sigma and k = sigma^2 / tau^2."""
    sub = df[df[prior_col].notna() & (df["responses"] > 0)]
    d2 = (sub["rating"] - sub[prior_col]).values ** 2
    inv_n = 1.0 / sub["responses"].values
    # group by n to stabilise: mean squared deviation per n, weighted by the count
    g = pd.DataFrame({"n": sub["responses"].values, "d2": d2}).groupby("n")["d2"].agg(["mean", "size"]).reset_index()
    g = g[g["size"] >= 5]
    X = np.column_stack([np.ones(len(g)), 1.0 / g["n"].values])
    w = np.sqrt(g["size"].values)
    beta, *_ = np.linalg.lstsq(X * w[:, None], g["mean"].values * w, rcond=None)
    tau2, sigma2 = float(beta[0]), float(beta[1])
    tau2 = max(tau2, 1e-4)
    sigma2 = max(sigma2, 1e-4)
    return {"tau": tau2 ** 0.5, "sigma": sigma2 ** 0.5, "k": sigma2 / tau2, "points": len(g), "rows": int(len(sub)),
            "by_n": [(int(n), float(m), int(s)) for n, m, s in zip(g["n"], g["mean"], g["size"])][:30]}


def approval_prior(df):
    """Beta prior for the approval share by the method of moments on classes with 5+ votes:
    mean m and variance v of the share -> a + b = m(1-m)/v - 1."""
    sub = df[df["votes"] >= 5]
    p = (sub["yes"] / sub["votes"]).values
    m, v = float(p.mean()), float(p.var())
    ab = max(1.0, m * (1 - m) / v - 1) if v > 0 else 20.0
    return {"mean": m, "var": v, "a": m * ab, "b": (1 - m) * ab, "a_plus_b": ab, "rows": int(len(sub))}


def trust_for(df_train):
    """The trust parameters a family's fit needs, derived from the given months only (used per
    fold by the loop so no validation month leaks into k)."""
    return {"variance": {prior: {"fit": variance_decomposition(df_train, prior)} for prior in ("course_prior_rating", "module_prior_rating", "track_mean")},
            "approval_prior": {"fit": approval_prior(df_train)}}


def main():
    t0 = time.time()
    df = load_features()
    df["low_rating"] = (df["rating"] < LINE).astype(int)
    df["low_approval"] = ((df["approval"] < BAR) & (df["votes"] > 0)).astype(int)
    df["below_prior"] = (df["rating"] < df["course_prior_rating"]).astype(int)
    out = {"meta": {"generated": time.strftime("%Y-%m-%d %H:%M"), "buckets": [b[0] for b in VOTE_BUCKETS]}}

    # 1. believability by vote count (no parameter is fitted here; fit and held-out months shown separately)
    # t_a is only defined with 5+ votes on THIS class; for the vote-count question we need the next class's
    # outcome regardless of this class's votes: rebuild it from the raw next-class columns
    df["t_a_any"] = np.where(df["next_i_rating"].notna() & (df["next_i_votes"] >= 5),
                             ((df["next_i_rating"] < LINE) | (df["next_i_approval"] < BAR)).astype(float), np.nan)
    for scope, part in (("all", df), ("fit", df[df["month"].isin(FIT_MONTHS)]), ("holdout", df[df["month"].isin(HOLDOUT_MONTHS)])):
        out["believability_" + scope] = {
            "rating_line": {"instructor_next": risk_table(part, "low_rating", "t_a_any", "instructor"),
                            "cohort_next": risk_table(part, "low_rating", "t_c", "cohort")},
            "approval_bar": {"instructor_next": risk_table(part, "low_approval", "t_a_any", "instructor"),
                             "cohort_next": risk_table(part, "low_approval", "t_c", "cohort")},
        }
    # 3. asymmetry: above vs below the course prior, by vote bucket - how well does the rating rank the next class?
    asym = {}
    for side, cond in (("below prior", df["below_prior"] == 1), ("above prior", df["below_prior"] == 0)):
        asym[side] = {}
        for name, lo, hi in VOTE_BUCKETS:
            sub = df[cond & (df["votes"] >= lo) & (df["votes"] <= hi)]
            rec = {"n": int(len(sub))}
            for t in ("t_a_any", "t_c"):
                s2 = sub[sub[t].notna()]
                rec[t] = {"n": int(len(s2)), "rate": float(s2[t].mean()) if len(s2) else None,
                          "auc_rating": auc(-s2["rating"].values, s2[t].values) if len(s2) > 30 else None}
            asym[side][name] = rec
    out["asymmetry"] = asym
    # 2. the shrinkage strength the data supports
    out["variance"] = {}
    for prior in ("course_prior_rating", "module_prior_rating", "track_mean"):
        out["variance"][prior] = {"fit": variance_decomposition(df[df["month"].isin(FIT_MONTHS)], prior),
                                  "holdout": variance_decomposition(df[df["month"].isin(HOLDOUT_MONTHS)], prior),
                                  "all": variance_decomposition(df, prior)}
    out["approval_prior"] = {"fit": approval_prior(df[df["month"].isin(FIT_MONTHS)]), "all": approval_prior(df)}
    # how many classes are low with few votes (the population the trust machinery touches)
    lowfew = df[(df["rating"] < LINE)]
    out["low_by_votes"] = {name: int(((lowfew["votes"] >= lo) & (lowfew["votes"] <= hi)).sum()) for name, lo, hi in VOTE_BUCKETS}
    write_json(os.path.join(OUT, "formula_trust.json"), out)

    b = out["believability_all"]["rating_line"]
    print("believability of a rating under 4.55, by votes (all months): next class low, low vs fine classes")
    for name, _, _ in VOTE_BUCKETS:
        i, c = b["instructor_next"][name], b["cohort_next"][name]
        print("  %-6s instructor-next: low %s (n=%d) vs fine %s (n=%d) diff %s [%s, %s] | cohort-next: low %s vs fine %s diff %s" % (
            name, _p(i["risk_low"]), i["n_low"], _p(i["risk_fine"]), i["n_fine"], _p(i.get("diff")), _p(i.get("diff_lo")), _p(i.get("diff_hi")),
            _p(c["risk_low"]), _p(c["risk_fine"]), _p(c.get("diff"))))
    print("asymmetry (AUC of the rating for the next class, by side of the course prior and votes):")
    for side, tab in asym.items():
        print("  %s: %s" % (side, "; ".join("%s n=%d a=%s c=%s" % (k, v["n"], _f(v["t_a_any"]["auc_rating"]), _f(v["t_c"]["auc_rating"])) for k, v in tab.items())))
    for prior, v in out["variance"].items():
        print("variance vs %s: fit tau %.3f sigma %.3f k %.1f | holdout k %.1f | all k %.1f" % (prior, v["fit"]["tau"], v["fit"]["sigma"], v["fit"]["k"], v["holdout"]["k"], v["all"]["k"]))
    ap = out["approval_prior"]["fit"]
    print("approval beta prior (fit): mean %.3f a+b %.1f (a %.1f, b %.1f) | done %.0fs" % (ap["mean"], ap["a_plus_b"], ap["a"], ap["b"], time.time() - t0))


def _p(v):
    return "n/a" if v is None or v != v else "%.0f%%" % (v * 100)


def _f(v):
    return "n/a" if v is None or v != v else "%.2f" % v


if __name__ == "__main__":
    main()
