"""Shared pieces for the formula study: paths, the two human lines, the time split, AUC and
bootstrap helpers, anonymised ids, small file helpers.

Nothing here touches production code. Everything written goes under analysis/out/ (gitignored).
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYSIS = os.path.dirname(HERE)
ROOT = os.path.dirname(ANALYSIS)
OUT = os.path.join(ANALYSIS, "out")
KIT = os.path.join(ROOT, "ratings_module_build_kit")
for p in (ANALYSIS, KIT):
    if p not in sys.path:
        sys.path.insert(0, p)

LINE, BAR, VOICES = 4.55, 80.0, 5           # the two agreed human lines and the voice floor
CAPACITY = {"per_week": 12.0, "videos": 5.0}  # the team's capacity (analyses a week)
COST = {"video": 0.70, "transcript": 0.51, "none": 0.0, "watch": 0.0}
BANDS = ("excellent", "good", "average", "bad")
BAND_RANK = {b: i for i, b in enumerate(BANDS)}
BAND_LABEL = {"excellent": "Excellent", "good": "Good", "average": "Average", "bad": "Bad", None: "no band"}
ACTIONS = {"bad": "video", "average": "transcript", "good": "none", "excellent": "none", "no_data": "watch"}
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug")

# The time split, fixed before anything was run:
#   FIT      Jan-May: every weight, shape, band edge and vote floor is chosen here
#   SELECT   inside FIT, rolling: fit on Jan-Feb -> judge on Mar; Jan-Mar -> Apr; Jan-Apr -> May
#   HOLDOUT  Jun-Aug: reported for every candidate, never used to choose anything
FIT_MONTHS = (1, 2, 3, 4, 5)
SELECT_FOLDS = (((1, 2), (3,)), ((1, 2, 3), (4,)), ((1, 2, 3, 4), (5,)))
HOLDOUT_MONTHS = (6, 7, 8)
ROLLING_FOLDS = (((1, 2, 3, 4, 5), (6,)), ((1, 2, 3, 4, 5, 6), (7,)), ((1, 2, 3, 4, 5, 6, 7), (8,)))


def weeks_in(months, year=2026):
    import calendar
    return sum(calendar.monthrange(year, m)[1] for m in months) / 7.0


# ------------------------------------------------------------------ statistics
def auc(score, y):
    """Area under the ROC curve of `score` against binary `y` (higher score = more positive).
    Rank-based, ties averaged. Returns nan when one class is empty."""
    s = np.asarray(score, dtype=float)
    yy = np.asarray(y, dtype=float)
    ok = ~np.isnan(s) & ~np.isnan(yy)
    s, yy = s[ok], yy[ok]
    n1 = int(yy.sum())
    n0 = len(yy) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    from scipy.stats import rankdata
    r = rankdata(s)
    return float((r[yy == 1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def spearman(a, b):
    from scipy.stats import spearmanr
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    ok = ~np.isnan(a) & ~np.isnan(b)
    if ok.sum() < 5 or np.std(a[ok]) == 0 or np.std(b[ok]) == 0:
        return float("nan")
    return float(spearmanr(a[ok], b[ok]).statistic)


def cluster_bootstrap(fn, clusters, reps=200, seed=7):
    """Bootstrap the statistic `fn(idx)` by resampling whole clusters (instructors, cohorts).
    Returns (estimate, standard error, lower 2.5%, upper 97.5%)."""
    clusters = np.asarray(clusters)
    uniq, inv = np.unique(clusters, return_inverse=True)
    members = [np.flatnonzero(inv == k) for k in range(len(uniq))]
    rng = np.random.default_rng(seed)
    est = fn(np.arange(len(clusters)))
    vals = []
    for _ in range(reps):
        pick = rng.integers(0, len(uniq), len(uniq))
        idx = np.concatenate([members[k] for k in pick]) if len(pick) else np.arange(0)
        v = fn(idx)
        if v == v:
            vals.append(v)
    if not vals:
        return est, float("nan"), float("nan"), float("nan")
    vals = np.array(vals)
    return est, float(vals.std(ddof=1)) if len(vals) > 1 else float("nan"), float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def wilson_lower(yes, n, z=1.0):
    """Wilson score interval lower bound for a share (z = 1 -> one standard error)."""
    if n <= 0:
        return None
    p = yes / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - m) / d


# ------------------------------------------------------------------ files
def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, default=_json_default)


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_csv(path, header, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def append_jsonl(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, default=_json_default) + "\n")


def _json_default(o):
    if isinstance(o, (dt.datetime, dt.date)):
        return o.isoformat()
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        v = float(o)
        return None if (v != v or v in (float("inf"), float("-inf"))) else v
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, float) and (o != o or o in (float("inf"), float("-inf"))):
        return None
    if isinstance(o, set):
        return sorted(o)
    if hasattr(o, "item"):
        return o.item()
    raise TypeError(str(type(o)))


def fnum(v, d=1):
    return "n/a" if v is None or (isinstance(v, float) and v != v) else ("%%.%df" % d) % v


class Anonymiser:
    """Stable anonymous ids (I-001, M-001, C-001) in order of first appearance."""

    def __init__(self, prefix):
        self.prefix = prefix
        self.map = {}

    def __call__(self, key):
        if key is None or key == "":
            return None
        if key not in self.map:
            self.map[key] = "%s-%03d" % (self.prefix, len(self.map) + 1)
        return self.map[key]
