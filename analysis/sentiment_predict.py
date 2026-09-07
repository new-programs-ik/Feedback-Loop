"""Y3 - does the band predict the instructor's next class?

For every class with 5+ votes whose instructor's NEXT class also has 5+ votes: per band, the share
of next classes that go wrong (rated under 4.55 or approval under 80%). Run on raw names and on
resolved names (analysis/out/instructor_aliases.csv). Pass: Bad worst, then Average, Good,
Excellent; Bad at least twice Excellent; every band holds 100+ classes.

Outputs analysis/out/predict.csv and predict.json.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sentiment_common import Study, Engine, OUT, LINE, BAR, BANDS, BAND_LABEL, write_csv, write_json  # noqa: E402
from sentiment_score import CONFIGS  # noqa: E402


def per_band(rows, res, pairs):
    acc = {b: [0, 0, 0, 0] for b in BANDS}          # n, low either, low rating, low approval
    for i, j in pairs:
        x = res[i]
        if x["band"] is None or x["provisional"]:
            continue
        nx = rows[j]
        lr = nx["rating"] < LINE
        la = nx["approval"] is not None and nx["approval"] < BAR
        a = acc[x["band"]]
        a[0] += 1
        a[1] += 1 if (lr or la) else 0
        a[2] += 1 if lr else 0
        a[3] += 1 if la else 0
    out = {}
    for b, a in acc.items():
        out[b] = {"n": a[0], "low": a[1], "share": (a[1] / a[0] * 100) if a[0] else 0.0,
                  "share_rating": (a[2] / a[0] * 100) if a[0] else 0.0, "share_approval": (a[3] / a[0] * 100) if a[0] else 0.0}
    shares = [out[b]["share"] for b in BANDS]
    out["order_ok"] = sum(1 for k in range(3) if shares[3 - k] > shares[2 - k])
    out["ratio_bad_excellent"] = (out["bad"]["share"] / out["excellent"]["share"]) if out["excellent"]["share"] else None
    out["min_band_n"] = min(out[b]["n"] for b in BANDS)
    out["pass_order"] = out["order_ok"] == 3 and (out["ratio_bad_excellent"] or 0) >= 2.0
    out["pass_100"] = out["min_band_n"] >= 100
    return out


def two_lines(rows, pairs):
    """The two agreed lines on their own (the shipped rule's four boxes), for context."""
    grp = {"fine on both": [], "rated low, approval fine": [], "rated fine, approval low": [], "fails both": []}
    for i, j in pairs:
        r = rows[i]
        b, l = r["rating"] < LINE, r["approval"] < BAR
        k = "fails both" if (b and l) else "rated low, approval fine" if b else "rated fine, approval low" if l else "fine on both"
        grp[k].append(rows[j])
    return {k: {"n": len(v), "share": (sum(1 for n in v if n["rating"] < LINE or n["approval"] < BAR) / len(v) * 100) if v else 0.0}
            for k, v in grp.items()}


def main():
    t0 = time.time()
    S = Study()
    E = Engine(S)
    csv_rows, out = [], {"meta": {"pairs_resolved": len(S.pairs["resolved"]), "pairs_raw": len(S.pairs["raw"]),
                                  "outcome": "next class rated under %.2f or approval under %d%% (5+ votes both sides)" % (LINE, BAR)},
                         "two_lines": {}, "configs": {}}
    for naming in ("resolved", "raw"):
        pairs = S.pairs[naming]
        base = sum(1 for i, j in pairs if S.rows[j]["rating"] < LINE or S.rows[j]["approval"] < BAR) / len(pairs) * 100
        out["two_lines"][naming] = {"base_rate": base, "groups": two_lines(S.rows, pairs)}
    for key, cfg in CONFIGS.items():
        res = E.base.run(cfg)
        out["configs"][key] = {"name": cfg["name"]}
        for naming in ("resolved", "raw"):
            pb = per_band(S.rows, res, S.pairs[naming])
            out["configs"][key][naming] = pb
            for b in BANDS:
                csv_rows.append([key, naming, BAND_LABEL[b], pb[b]["n"], pb[b]["low"], round(pb[b]["share"], 1),
                                 round(pb[b]["share_rating"], 1), round(pb[b]["share_approval"], 1)])
        pr = out["configs"][key]["resolved"]
        print("%s (resolved names): %s | order %d/3 | Bad/Excellent %s | min band n %d | pass %s/%s" % (
            key, "  ".join("%s %.0f%% (n=%d)" % (BAND_LABEL[b], pr[b]["share"], pr[b]["n"]) for b in BANDS), pr["order_ok"],
            ("%.1fx" % pr["ratio_bad_excellent"]) if pr["ratio_bad_excellent"] else "n/a", pr["min_band_n"], pr["pass_order"], pr["pass_100"]))
    write_csv(os.path.join(OUT, "predict.csv"), ["config", "naming", "band", "pairs", "next_low", "next_low_pct", "next_rated_low_pct", "next_approval_low_pct"], csv_rows)
    write_json(os.path.join(OUT, "predict.json"), out)
    print("base rate resolved %.1f%% raw %.1f%% | done in %.1fs" % (out["two_lines"]["resolved"]["base_rate"], out["two_lines"]["raw"]["base_rate"], time.time() - t0))


if __name__ == "__main__":
    main()
