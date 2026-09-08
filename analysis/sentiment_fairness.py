"""Y5 - fair to small classes and test reviews. For every candidate: band shares by live vs
review, India vs US, class-size bucket, course and weekday; and at EQUAL rating (0.1-rating
buckets, standardised to the pooled rating mix) the Excellent and Bad shares for <10 vs 10+
responses and live vs review. Plus the classes with <= 3 votes that get a firm Bad or Excellent.

Outputs analysis/out/fairness.csv (long) and fairness.json.
"""
import os
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sentiment_common import (Study, Engine, OUT, BANDS, BAND_LABEL, WEEKDAYS, SIZE_BUCKETS, standardised_share,  # noqa: E402
                              write_csv, write_json)
from sentiment_score import CONFIGS  # noqa: E402

SLICES = {
    "kind": lambda r: r["kind"],
    "region": lambda r: r["region"],
    "size": lambda r: r["size_bucket"],
    "responses": lambda r: "<10" if r["responses"] < 10 else "10+",
    "course": lambda r: r["course"],
    "weekday": lambda r: r["weekday"],
}
ORDER = {"size": [b[0] for b in SIZE_BUCKETS], "weekday": list(WEEKDAYS), "responses": ["<10", "10+"], "kind": ["Live Class", "Test Review", "Other"],
         "region": ["US", "IND"]}


def band_shares(rows, res, keyfn):
    acc = defaultdict(Counter)
    for r, x in zip(rows, res):
        k = keyfn(r)
        acc[k]["classes"] += 1
        acc[k][x["band"]] += 1
        acc[k]["provisional"] += 1 if x["provisional"] else 0
    out = {}
    for k, c in acc.items():
        banded = sum(c[b] for b in BANDS)
        out[k] = {"classes": c["classes"], "no_band_pct": c[None] / c["classes"] * 100, "provisional_pct": c["provisional"] / c["classes"] * 100,
                  "avg_rating": 0.0, **{BAND_LABEL[b]: (c[b] / banded * 100 if banded else 0.0) for b in BANDS}}
    return out


def main():
    t0 = time.time()
    S = Study()
    E = Engine(S)
    rows = S.rows
    ratings = defaultdict(list)
    for r in rows:
        for name, fn in SLICES.items():
            ratings[(name, fn(r))].append(r["rating"])
    csv_rows, out = [], {"configs": {}}
    for key, cfg in CONFIGS.items():
        res = E.base.run(cfg)
        entry = {"name": cfg["name"], "slices": {}, "at_equal_rating": {}}
        for name, fn in SLICES.items():
            t = band_shares(rows, res, fn)
            for k, v in t.items():
                v["avg_rating"] = sum(ratings[(name, k)]) / len(ratings[(name, k)])
            order = ORDER.get(name)
            keys = sorted(t, key=lambda k: (order.index(k) if order and k in order else 99, -t[k]["classes"]))
            entry["slices"][name] = {k: t[k] for k in keys}
            for k in keys:
                v = t[k]
                csv_rows.append([key, name, k, v["classes"], round(v["avg_rating"], 3), round(v["Excellent"], 1), round(v["Good"], 1),
                                 round(v["Average"], 1), round(v["Bad"], 1), round(v["no_band_pct"], 1), round(v["provisional_pct"], 1)])
        for name in ("responses", "kind", "region", "size"):
            ex = standardised_share(rows, res, SLICES[name], ("excellent",))
            bd = standardised_share(rows, res, SLICES[name], ("bad",))
            entry["at_equal_rating"][name] = {"excellent": ex, "bad": bd}
        thin = [(r, x) for r, x in zip(rows, res) if r["votes"] <= 3 and x["band"] in ("bad", "excellent") and not x["provisional"]]
        entry["thin_firm"] = {"total": len(thin), "bad": sum(1 for r, x in thin if x["band"] == "bad"), "excellent": sum(1 for r, x in thin if x["band"] == "excellent")}
        m = E.metrics(cfg)["Y5"]
        entry["size_gap"], entry["kind_gap"] = m["size_gap"], m["kind_gap"]
        entry["pass_gaps"], entry["pass_thin"] = (m["size_gap"] < 10 and m["kind_gap"] < 10), m["thin_firm"] == 0
        out["configs"][key] = entry
        er = entry["at_equal_rating"]
        print("%s at equal rating - Excellent: <10 resp %.0f%% vs 10+ %.0f%% (gap %.1f) | live %.0f%% vs review %.0f%% (gap %.1f) | US %.0f%% vs IND %.0f%% | thin firm Bad/Excellent %d" % (
            key, er["responses"]["excellent"].get("<10", 0), er["responses"]["excellent"].get("10+", 0), entry["size_gap"],
            er["kind"]["excellent"].get("Live Class", 0), er["kind"]["excellent"].get("Test Review", 0), entry["kind_gap"],
            er["region"]["excellent"].get("US", 0), er["region"]["excellent"].get("IND", 0), entry["thin_firm"]["total"]))
    write_csv(os.path.join(OUT, "fairness.csv"), ["config", "slice", "group", "classes", "avg_rating", "excellent_pct", "good_pct", "average_pct", "bad_pct",
                                                  "no_band_pct", "provisional_pct"], csv_rows)
    write_json(os.path.join(OUT, "fairness.json"), out)
    print("fairness done in %.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
