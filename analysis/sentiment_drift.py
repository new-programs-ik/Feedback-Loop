"""Drift: re-derive the weights (the approval_weights next-class method) on Jan-Apr and May-Aug,
and separate "the classes changed" (ratings really fell) from "the model is wrong" (the derived
weights move by more than 10 points). Also the band mix per half under C0 and C5.

The derivation is approval_weights.compute()'s lens 2, re-implemented here with the date window
as a parameter (approval_weights itself is not modified): track record over >= 3 earlier classes
inside the window, the next class inside the window, logistic regression on standardised
rating / approval / track scores, predictive shares averaged over the two kinds of trouble,
rounded to the nearest five.

Outputs analysis/out/drift.json and drift.csv.
"""
import datetime as dt
import os
import statistics as st
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sentiment_common import Study, Engine, OUT, LINE, BAR, VOICES, TRACK_MIN, MONTHS, BAND_LABEL, BANDS, write_csv, write_json  # noqa: E402
from sentiment_score import CONFIGS  # noqa: E402
from approval_weights import score_rating, score_approval, score_track, logistic, zs  # noqa: E402

HALVES = {"Jan-Apr": (dt.datetime(2026, 1, 1), dt.datetime(2026, 4, 30, 23, 59, 59)),
          "May-Aug": (dt.datetime(2026, 5, 1), dt.datetime(2026, 8, 31, 23, 59, 59)),
          "Jan-Aug": (dt.datetime(2026, 1, 1), dt.datetime(2026, 8, 31, 23, 59, 59))}


def derive(rows, lo, hi, key):
    """approval_weights lens 2 on the rows inside [lo, hi], instructors identified by `key`."""
    sub = sorted([dict(r) for r in rows if lo <= r["date"] <= hi and r["approval"] is not None and r[key]],
                 key=lambda r: (r["date"], r[key], r["topic"]))
    hist = defaultdict(list)
    for r in sub:
        prev = hist[r[key]]
        r["track"] = st.mean(prev) if len(prev) >= TRACK_MIN else None
        prev.append(r["rating"])
    nxt = {}
    for r in reversed(sub):
        r["next"] = nxt.get(r[key])
        nxt[r[key]] = r
    for r in sub:
        r["R"], r["A"], r["T"] = score_rating(r["rating"]), score_approval(r["approval"]), score_track(r["track"])
    fit = [r for r in sub if r["responses"] >= VOICES and r["next"] is not None and r["next"]["responses"] >= VOICES]
    Z = {k: zs([r[k] for r in fit]) for k in ("R", "A", "T")}
    X = [[1.0, Z["R"][i], Z["A"][i], Z["T"][i]] for i in range(len(fit))]
    outcomes = {"next rated low": [1.0 if r["next"]["rating"] < LINE else 0.0 for r in fit],
                "next approval low": [1.0 if r["next"]["approval"] < BAR else 0.0 for r in fit]}
    shares, betas, base = {}, {}, {}
    for name, y in outcomes.items():
        w = logistic(X, y)
        tot = sum(abs(v) for v in w[1:]) or 1.0
        shares[name] = {k: abs(w[j + 1]) / tot * 100 for j, k in enumerate(("R", "A", "T"))}
        betas[name] = {k: w[j + 1] for j, k in enumerate(("R", "A", "T"))}
        base[name] = sum(y) / len(y) * 100 if y else 0.0
    avg = {k: (shares["next rated low"][k] + shares["next approval low"][k]) / 2 for k in ("R", "A", "T")}
    derived = {k: round(avg[k] / 5) * 5 for k in ("R", "A", "T")}
    return {"classes": len(sub), "pairs": len(fit), "with_track": sum(1 for r in sub if r["track"] is not None),
            "shares": shares, "betas": betas, "base_rates": base, "average_share": avg, "derived_weights": derived}


def class_drift(rows, lo, hi):
    g = [r for r in rows if lo <= r["date"] <= hi]
    v = [r for r in g if r["votes"] >= VOICES]
    return {"classes": len(g), "avg_rating": st.mean(r["rating"] for r in g), "share_under_line": sum(1 for r in g if r["rating"] < LINE) / len(g) * 100,
            "share_under_bar_5plus": sum(1 for r in v if r["approval"] < BAR) / len(v) * 100 if v else 0.0,
            "avg_attended": st.mean(r["attended"] for r in g), "avg_responses": st.mean(r["responses"] for r in g),
            "pooled_approval": sum(r["yes"] for r in g) / sum(r["votes"] for r in g) * 100}


def main():
    t0 = time.time()
    S = Study()
    E = Engine(S)
    out = {"halves": {}, "weights": {}, "band_mix": {}, "monthly": []}
    csv_rows = []
    for half, (lo, hi) in HALVES.items():
        out["halves"][half] = class_drift(S.rows, lo, hi)
        for naming, key in (("resolved", "instructor_resolved"), ("raw", "instructor_raw")):
            d = derive(S.rows, lo, hi, key)
            out["weights"]["%s|%s" % (half, naming)] = d
            csv_rows.append([half, naming, d["classes"], d["pairs"], round(d["average_share"]["R"], 1), round(d["average_share"]["A"], 1),
                             round(d["average_share"]["T"], 1), d["derived_weights"]["R"], d["derived_weights"]["A"], d["derived_weights"]["T"],
                             round(d["base_rates"]["next rated low"], 1), round(d["base_rates"]["next approval low"], 1)])
    # model drift = the largest move of a derived weight between the halves (resolved names)
    a, b = out["weights"]["Jan-Apr|resolved"]["average_share"], out["weights"]["May-Aug|resolved"]["average_share"]
    out["model_drift"] = {"max_shift_points": max(abs(a[k] - b[k]) for k in ("R", "A", "T")), "shift": {k: b[k] - a[k] for k in ("R", "A", "T")},
                          "flag": max(abs(a[k] - b[k]) for k in ("R", "A", "T")) > 10.0}
    ha, hb = out["halves"]["Jan-Apr"], out["halves"]["May-Aug"]
    out["class_drift"] = {"avg_rating_shift": hb["avg_rating"] - ha["avg_rating"], "under_line_shift_points": hb["share_under_line"] - ha["share_under_line"],
                          "under_bar_shift_points": hb["share_under_bar_5plus"] - ha["share_under_bar_5plus"], "attended_shift": hb["avg_attended"] - ha["avg_attended"]}
    # band mix per half under C0 and C5
    for key in ("C0", "C5"):
        res = E.base.run(CONFIGS[key])
        out["band_mix"][key] = {}
        for half, (lo, hi) in HALVES.items():
            c = Counter(x["band"] for r, x in zip(S.rows, res) if lo <= r["date"] <= hi)
            banded = sum(v for k, v in c.items() if k is not None)
            out["band_mix"][key][half] = {BAND_LABEL[b]: c[b] / banded * 100 for b in BANDS}
            out["band_mix"][key][half]["no band"] = c[None] / sum(c.values()) * 100
        # month by month
        for m in range(1, 9):
            c = Counter(x["band"] for r, x in zip(S.rows, res) if r["month"] == m)
            banded = sum(v for k, v in c.items() if k is not None)
            out["monthly"].append({"config": key, "month": MONTHS[m - 1], **{BAND_LABEL[b]: c[b] / banded * 100 for b in BANDS}})
    for m in range(1, 9):
        g = [r for r in S.rows if r["month"] == m]
        out["monthly"].append({"config": "data", "month": MONTHS[m - 1], "avg_rating": st.mean(r["rating"] for r in g),
                               "under_line": sum(1 for r in g if r["rating"] < LINE) / len(g) * 100, "attended": st.mean(r["attended"] for r in g)})
    write_csv(os.path.join(OUT, "drift.csv"), ["window", "naming", "classes", "pairs", "share_R", "share_A", "share_T", "w_R", "w_A", "w_T",
                                               "base_next_rated_low", "base_next_approval_low"], csv_rows)
    write_json(os.path.join(OUT, "drift.json"), out)
    for half in HALVES:
        d = out["weights"][half + "|resolved"]
        print("%-8s classes %4d pairs %4d | shares R %.0f A %.0f T %.0f -> %d/%d/%d | base rates: rated low %.0f%%, approval low %.0f%%" % (
            half, d["classes"], d["pairs"], d["average_share"]["R"], d["average_share"]["A"], d["average_share"]["T"], d["derived_weights"]["R"],
            d["derived_weights"]["A"], d["derived_weights"]["T"], d["base_rates"]["next rated low"], d["base_rates"]["next approval low"]))
    print("model drift: max shift %.1f points (%s) | class drift: rating %+.2f, under-line %+.1f pts, under-bar %+.1f pts, room size %+.1f" % (
        out["model_drift"]["max_shift_points"], "FLAG" if out["model_drift"]["flag"] else "fine", out["class_drift"]["avg_rating_shift"],
        out["class_drift"]["under_line_shift_points"], out["class_drift"]["under_bar_shift_points"], out["class_drift"]["attended_shift"]))
    for key in ("C0", "C5"):
        print("%s band mix: %s" % (key, {h: {b: round(v, 1) for b, v in mix.items()} for h, mix in out["band_mix"][key].items() if h != "Jan-Aug"}))
    print("drift done in %.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
