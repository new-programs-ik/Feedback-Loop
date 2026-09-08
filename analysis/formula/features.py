"""Step 1 - the feature table: everything measurable at scoring time from a sheet row plus
history, one row per rated class, with the targets (what "went wrong" looks like) attached.

Source: the database (class_ratings joined to cohorts, topics, instructors) so every class has
its cohort week, module identity and resolved instructor. Falls back to the workbook loader
(analysis/ratings_data.py) only when DATABASE_URL is missing - the fallback has no cohort or
module identity, and the features that need it are left empty.

Every history feature uses only classes dated STRICTLY BEFORE the class (same-day classes are
not history for each other), so every number here could be computed by the sync at scoring
time. The one exception is marked "diagnostic": module_loo_rating (leave-one-out over the whole
window) uses the future and is never fed to a deployable formula.

Ids are anonymised (I-001, M-001, C-001); no instructor name leaves this module.

Run:  python analysis/formula/features.py      -> analysis/out/formula_features.csv (+ _meta.json)
"""
from __future__ import annotations

import csv
import datetime as dt
import math
import os
import sys
import time
from bisect import bisect_left
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (OUT, LINE, BAR, VOICES, FIT_MONTHS, Anonymiser, write_json)  # noqa: E402

FEATURES_CSV = os.path.join(OUT, "formula_features.csv")
META_JSON = os.path.join(OUT, "formula_features_meta.json")
PRIOR_DAYS, PRIOR_MIN = 180, 10       # the course prior window (as the guard's prior in the study)
EWMA_HALFLIFE_DAYS = 60.0             # the recency-weighted instructor mean
LIVE_BEFORE_DAYS = 7                  # a review "of" a live class held within this many days

# One line per feature: what it means. Every deployable feature can be computed by the sync from
# the sheet row plus history; the targets need the future and exist only for the study.
FEATURE_DOCS = {
    # the row itself
    "rating": "the class's average star rating (1-5), as the sheet gives it",
    "responses": "how many learners rated the class",
    "attended": "how many learners attended",
    "reach": "responses divided by attended, capped at 1 (the share of the room that rated)",
    "yes": "voters who would have this instructor back",
    "no": "voters who would not",
    "votes": "yes + no",
    "approval": "yes divided by votes, in percent (empty when nobody voted)",
    "kind_live": "1 for a live class, 0 for a test review (the 4 'Other' rows count as live)",
    "region_ind": "1 for an India cohort, 0 for US",
    "weekday": "day of the week of the class (0 = Monday)",
    "votes_minus_responses": "votes minus responses (0 on every row today; a data-quality check)",
    "resp_gt_att": "1 when more people rated than attended (a data-entry error, kept and flagged)",
    # the cohort
    "week_no": "weeks since the cohort's first class in the data (the sync's week_no)",
    "curr_week": "weeks since the cohort's start month (its position in the curriculum)",
    "week_share": "curr_week divided by the course's typical length in weeks (0-1, capped)",
    "cohort_size": "attended at the cohort's first observed class of the same kind",
    "att_vs_first": "attended divided by cohort_size (how much of the room is still coming)",
    "att_vs_prev": "attended divided by the cohort's previous class of the same kind",
    "cohort_n_before": "how many classes the cohort has had before this one (in the data)",
    "prev_rating": "the cohort's previous class rating (any kind) - momentum",
    "prev_approval": "the cohort's previous class approval, percent",
    "prev_low": "1 when the cohort's previous class was under a human line",
    "cohort_mean_before": "the cohort's average rating over its earlier classes",
    "is_review_of_live": "1 when this is a test review and the cohort had a live class in the 7 days before",
    "live_before_rating": "that live class's rating (empty otherwise)",
    # the module (topic) and the course
    "module_prior_rating": "average rating of earlier classes on the same module in OTHER cohorts",
    "module_prior_n": "how many such classes",
    "module_prior_approval": "their pooled approval, percent",
    "rating_vs_module": "rating minus module_prior_rating (how unusual the class is for its module)",
    "module_loo_rating": "DIAGNOSTIC ONLY: the module's average over every other class in the window (uses the future)",
    "course_prior_rating": "the course's average rating over the previous 180 days (at least 10 classes; else all history)",
    "course_prior_approval": "the course's pooled approval over the same window, percent",
    "rating_vs_course": "rating minus course_prior_rating",
    # the instructor
    "track_mean": "the instructor's average rating over earlier classes (empty under 3 of them)",
    "track_n": "how many earlier classes the instructor has in the data",
    "track_ewma": "the same average with recent classes counting more (half-life 60 days)",
    "track_trend": "average of the instructor's last 3 classes minus the average of the ones before",
    "days_since_last": "days since the instructor's previous class",
    "instr_prev_rating": "the instructor's previous class rating",
    "track_approval": "the instructor's pooled approval over earlier classes, percent",
    "track_module_mean": "the instructor's average over earlier classes on THIS module",
    "track_module_n": "how many such classes",
    "rating_vs_track": "rating minus track_mean (the surprise against the instructor's record)",
}
TARGET_DOCS = {
    "t_a": "the instructor's NEXT class (5+ votes both sides) is under 4.55 or under 80% approval",
    "t_b": "the cohort's next class of the same kind loses more attendance than the median cohort at the same week",
    "t_c": "the cohort's next class is under 4.55 or under 80% approval (5+ votes)",
    "t_c_fall": "the cohort's next class is rated lower than this one (literal 'falls'; dominated by regression to the mean)",
    "t_c_below": "the cohort's next class is rated below the cohort's average so far",
    "t_d": "this class itself is under a human line (rating under 4.55, or approval under 80% with 5+ votes)",
    "t_e": "a PM decision recorded in the database (confirmed / dismissed / override)",
    "b_resid": "continuous version of t_b: log attendance ratio minus the median at the same week",
    "c_delta": "continuous version of t_c: the cohort's next class rating minus this one",
}


def low(rating, votes, approval):
    return (rating is not None and rating < LINE) or (votes is not None and votes >= VOICES and approval is not None and approval < BAR)


# ------------------------------------------------------------------ sources
def load_db_rows():
    import config
    config.load_env()
    import ratings_store as RS
    conn = RS.connect()
    cur = conn.cursor()
    cur.execute("""
        select r.id, r.class_date, co.name, r.course_id, r.cohort_id, r.cohort_text, r.topic_id, r.topic,
               r.instructor, r.instructor_id, r.session_kind, r.rating, r.num_ratings, r.attended, r.yes_votes, r.no_votes,
               r.escalated, r.week_no, ch.region, ch.start_month, ch.start_part, r.review_status, r.decision, r.decision_override,
               r.sentiment_score, r.sentiment_band, r.sentiment_action, r.sentiment_provisional
        from class_ratings r
        left join courses co on co.id = r.course_id
        left join cohorts ch on ch.id = r.cohort_id
        where r.class_date between '2026-01-01' and '2026-08-31'
        order by r.class_date, r.session_kind, r.topic""")
    rows = []
    for rec in cur.fetchall():
        (rid, date, course, course_id, cohort_id, cohort_text, topic_id, topic, instructor, instructor_id, kind, rating, num, att, yes, no,
         esc, week_no, region, start_month, start_part, review_status, decision, override, s_score, s_band, s_action, s_prov) = rec
        region = region or ("IND" if "india" in (cohort_text or "").lower() else "US")
        rows.append({
            "db_id": str(rid), "date": date if isinstance(date, dt.date) else date.date(), "course": course or "unmapped",
            "course_id": str(course_id) if course_id else None, "cohort_id": str(cohort_id) if cohort_id else ("text:" + (cohort_text or "")),
            "topic_id": str(topic_id) if topic_id else ("text:" + (topic or "").lower()), "instructor_raw": instructor or "",
            "instructor_id": str(instructor_id) if instructor_id else None,
            "kind": "live" if kind == "Live Class" else "review" if kind == "Test Review" else "other",
            "rating": float(rating), "responses": float(num or 0), "attended": float(att or 0),
            "yes": float(yes) if yes is not None else None, "no": float(no) if no is not None else None,
            "escalated": bool(esc), "week_no": week_no, "region": region, "start_month": start_month, "start_part": start_part,
            "review_status": review_status, "decision": decision, "decision_override": override,
            "v7_score": float(s_score) if s_score is not None else None, "v7_band": s_band, "v7_action": s_action, "v7_provisional": bool(s_prov),
        })
    conn.close()
    return rows, "database"


def load_workbook_rows():
    from ratings_data import load
    rows = []
    for r in load(dt.datetime(2026, 1, 1), dt.datetime(2026, 8, 31, 23, 59, 59), strict=False):
        rows.append({
            "db_id": None, "date": r["date"].date(), "course": r["course"], "course_id": r["course"],
            "cohort_id": "text:" + str(r.get("type") or ""), "topic_id": "text:" + r["topic"].lower(), "instructor_raw": r["instructor"],
            "instructor_id": None, "kind": "live" if r["kind"] == "Live Class" else "review" if r["kind"] == "Test Review" else "other",
            "rating": r["rating"], "responses": r["responses"], "attended": r["attended"], "yes": r["yes"], "no": r["no"],
            "escalated": False, "week_no": None, "region": r["region"], "start_month": None, "start_part": None,
            "review_status": None, "decision": None, "decision_override": None,
            "v7_score": None, "v7_band": None, "v7_action": None, "v7_provisional": False,
        })
    return rows, "workbook"


def load_rows():
    import config
    config.load_env()
    if os.environ.get("DATABASE_URL"):
        try:
            return load_db_rows()
        except Exception as e:  # pragma: no cover - network
            print("database unavailable (%s) - falling back to the workbook" % type(e).__name__)
    return load_workbook_rows()


def resolve_instructors(rows):
    """instructor key: the database id when resolved, else the study's alias table on the raw
    spelling (analysis/out/instructor_aliases.csv), else the raw spelling."""
    alias = {}
    path = os.path.join(OUT, "instructor_aliases.csv")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for rec in csv.DictReader(f):
                alias[rec["raw"]] = rec["canonical"]
    for r in rows:
        if r["instructor_id"]:
            r["instructor_key"] = "id:" + r["instructor_id"]
        elif r["instructor_raw"]:
            r["instructor_key"] = "name:" + alias.get(r["instructor_raw"], r["instructor_raw"]).strip().lower()
        else:
            r["instructor_key"] = None
    return rows


# ------------------------------------------------------------------ the build
def _start_date(r):
    if r["start_month"] is None:
        return None
    day = {"early": 1, "mid": 15, "end": 25}.get(r["start_part"] or "", 1)
    sm = r["start_month"]
    return dt.date(sm.year, sm.month, min(day, 28))


def build(rows):
    rows = sorted(rows, key=lambda r: (r["date"], r["kind"], r["topic_id"], r["instructor_key"] or ""))
    for i, r in enumerate(rows):
        r["id"] = i
        r["votes"] = (r["yes"] or 0) + (r["no"] or 0) if (r["yes"] is not None or r["no"] is not None) else 0
        r["approval"] = (r["yes"] / r["votes"] * 100.0) if r["votes"] else None
        r["reach"] = min(1.0, r["responses"] / r["attended"]) if r["attended"] else None
        r["resp_gt_att"] = 1 if (r["attended"] and r["responses"] > r["attended"]) else 0
        r["votes_minus_responses"] = r["votes"] - r["responses"]
        r["kind_live"] = 0 if r["kind"] == "review" else 1
        r["region_ind"] = 1 if r["region"] == "IND" else 0
        r["weekday"] = r["date"].weekday()
        r["month"] = r["date"].month
        sd = _start_date(r)
        r["curr_week"] = (1 + max(0, (r["date"] - sd).days) // 7) if sd else r["week_no"]
        r["self_low"] = 1 if low(r["rating"], r["votes"], r["approval"]) else 0

    # course length in weeks: the 90th percentile of curr_week over the course's classes (a curriculum constant)
    cw = defaultdict(list)
    for r in rows:
        if r["curr_week"] is not None:
            cw[r["course"]].append(r["curr_week"])
    course_len = {c: max(4.0, float(np.percentile(v, 90))) for c, v in cw.items()}
    for r in rows:
        r["week_share"] = min(1.0, r["curr_week"] / course_len[r["course"]]) if (r["curr_week"] is not None and r["course"] in course_len) else None

    # ---- cohort passes (time-safe: strictly earlier dates) ----------------------------------
    by_cohort = defaultdict(list)
    for r in rows:
        by_cohort[r["cohort_id"]].append(r)
    for cid, lst in by_cohort.items():
        first_kind, prev_kind = {}, {}
        earlier = []                                    # classes strictly before the current date
        pending = []                                    # same-day classes not yet history
        last_date = None
        for r in lst:                                   # already in date order
            if last_date is not None and r["date"] > last_date:
                earlier.extend(pending)
                pending = []
            k = r["kind"]
            pa = earlier[-1] if earlier else None
            ratings_before = [x["rating"] for x in earlier]
            r["cohort_n_before"] = len(earlier)
            r["prev_rating"] = pa["rating"] if pa else None
            r["prev_approval"] = pa["approval"] if pa else None
            r["prev_low"] = pa["self_low"] if pa else None
            r["cohort_mean_before"] = float(np.mean(ratings_before)) if ratings_before else None
            fk = first_kind.get(k)
            r["cohort_size"] = fk["attended"] if fk else None
            r["att_vs_first"] = (r["attended"] / fk["attended"]) if (fk and fk["attended"] and fk["date"] < r["date"]) else None
            pk = prev_kind.get(k)
            r["att_vs_prev"] = (r["attended"] / pk["attended"]) if (pk and pk["attended"] and pk["date"] < r["date"]) else None
            r["is_review_of_live"] = 0
            r["live_before_rating"] = None
            if k == "review" and pa and pa["kind"] == "live" and 0 <= (r["date"] - pa["date"]).days <= LIVE_BEFORE_DAYS:
                r["is_review_of_live"] = 1
                r["live_before_rating"] = pa["rating"]
            if k not in first_kind:
                first_kind[k] = r
            if pk is None or pk["date"] < r["date"]:
                prev_kind[k] = r
            pending.append(r)
            last_date = r["date"]
        # next classes (targets): next of any kind, next of the same kind
        for i, r in enumerate(lst):
            r["next_c"] = next((x for x in lst[i + 1:] if x["date"] > r["date"]), None)
            r["next_k"] = next((x for x in lst[i + 1:] if x["date"] > r["date"] and x["kind"] == r["kind"]), None)

    # ---- module prior (other cohorts, strictly earlier) and course prior -------------------
    by_topic = defaultdict(list)
    for r in rows:
        by_topic[r["topic_id"]].append(r)
    for tid, lst in by_topic.items():
        allr = [x["rating"] for x in lst]
        tot = sum(allr)
        for r in lst:
            hist = [x for x in lst if x["date"] < r["date"] and x["cohort_id"] != r["cohort_id"]]
            r["module_prior_n"] = len(hist)
            r["module_prior_rating"] = float(np.mean([x["rating"] for x in hist])) if hist else None
            v = sum(x["votes"] for x in hist)
            r["module_prior_approval"] = (sum(x["yes"] or 0 for x in hist) / v * 100.0) if v else None
            r["module_loo_rating"] = ((tot - r["rating"]) / (len(allr) - 1)) if len(allr) > 1 else None
    by_course = defaultdict(list)
    for r in rows:
        by_course[r["course"]].append(r)
    g_dates = [r["date"] for r in rows]
    g_cr = np.concatenate([[0.0], np.cumsum([r["rating"] for r in rows])])
    for c, lst in by_course.items():
        dates = [r["date"] for r in lst]
        cr = np.concatenate([[0.0], np.cumsum([r["rating"] for r in lst])])
        cy = np.concatenate([[0.0], np.cumsum([r["yes"] or 0 for r in lst])])
        cv = np.concatenate([[0.0], np.cumsum([r["votes"] for r in lst])])
        for r in lst:
            hi = bisect_left(dates, r["date"])
            lo = bisect_left(dates, r["date"] - dt.timedelta(days=PRIOR_DAYS))
            n = hi - lo
            if n >= PRIOR_MIN:
                r["course_prior_rating"] = float((cr[hi] - cr[lo]) / n)
                r["course_prior_approval"] = float((cy[hi] - cy[lo]) / (cv[hi] - cv[lo]) * 100.0) if (cv[hi] - cv[lo]) > 0 else None
                r["course_prior_source"] = "course-180d"
            elif hi >= 3:
                r["course_prior_rating"] = float(cr[hi] / hi)
                r["course_prior_approval"] = float(cy[hi] / cv[hi] * 100.0) if cv[hi] > 0 else None
                r["course_prior_source"] = "course-all"
            else:
                gh = bisect_left(g_dates, r["date"])
                r["course_prior_rating"] = float(g_cr[gh] / gh) if gh >= 10 else None
                r["course_prior_approval"] = None
                r["course_prior_source"] = "global" if gh >= 10 else "none"
    for r in rows:
        r["rating_vs_module"] = (r["rating"] - r["module_prior_rating"]) if r["module_prior_rating"] is not None else None
        r["rating_vs_course"] = (r["rating"] - r["course_prior_rating"]) if r["course_prior_rating"] is not None else None

    # ---- instructor passes ------------------------------------------------------------------
    by_instr = defaultdict(list)
    for r in rows:
        if r["instructor_key"]:
            by_instr[r["instructor_key"]].append(r)
    lam = math.log(2) / EWMA_HALFLIFE_DAYS
    for key, lst in by_instr.items():
        for i, r in enumerate(lst):
            hist = [x for x in lst[:i] if x["date"] < r["date"]]
            r["track_n"] = len(hist)
            hr = [x["rating"] for x in hist]
            r["track_mean"] = float(np.mean(hr)) if len(hr) >= 3 else None
            if hist:
                w = np.array([math.exp(-lam * (r["date"] - x["date"]).days) for x in hist])
                r["track_ewma"] = float(np.dot(w, hr) / w.sum()) if len(hr) >= 3 else None
                r["days_since_last"] = (r["date"] - hist[-1]["date"]).days
                r["instr_prev_rating"] = hist[-1]["rating"]
                v = sum(x["votes"] for x in hist)
                r["track_approval"] = (sum(x["yes"] or 0 for x in hist) / v * 100.0) if v else None
                r["track_trend"] = (float(np.mean(hr[-3:])) - float(np.mean(hr[:-3]))) if len(hr) >= 6 else None
            else:
                r["track_ewma"] = r["days_since_last"] = r["instr_prev_rating"] = r["track_approval"] = r["track_trend"] = None
            hm = [x["rating"] for x in hist if x["topic_id"] == r["topic_id"]]
            r["track_module_n"] = len(hm)
            r["track_module_mean"] = float(np.mean(hm)) if hm else None
            r["rating_vs_track"] = (r["rating"] - r["track_mean"]) if r["track_mean"] is not None else None
            r["next_i"] = next((x for x in lst[i + 1:] if x["date"] > r["date"]), None)
    for r in rows:
        for k in ("track_n", "track_mean", "track_ewma", "days_since_last", "instr_prev_rating", "track_approval", "track_trend",
                  "track_module_n", "track_module_mean", "rating_vs_track"):
            r.setdefault(k, 0 if k in ("track_n", "track_module_n") else None)
        r.setdefault("next_i", None)

    # ---- targets ------------------------------------------------------------------------------
    # (b) the attendance drop, against the median cohort at the same course / kind / month of the curriculum
    ratios = defaultdict(list)
    for r in rows:
        nk = r.get("next_k")
        if nk and r["attended"] and nk["attended"]:
            r["att_ratio_next"] = nk["attended"] / r["attended"]
            wk = min(int(r["curr_week"] or 1), 40)
            ratios[(r["course"], r["kind"], wk // 4)].append(math.log(r["att_ratio_next"]))
            ratios[("all", r["kind"], wk // 4)].append(math.log(r["att_ratio_next"]))
        else:
            r["att_ratio_next"] = None
    med = {k: float(np.median(v)) for k, v in ratios.items() if len(v) >= 8}
    for r in rows:
        r["t_a"] = r["t_b"] = r["t_c"] = r["t_c_fall"] = r["t_c_below"] = r["b_resid"] = r["c_delta"] = None
        ni = r.get("next_i")
        if ni and ni["votes"] >= VOICES and r["votes"] >= VOICES:
            r["t_a"] = 1 if low(ni["rating"], ni["votes"], ni["approval"]) else 0
        nc = r.get("next_c")
        if nc:
            r["t_c"] = 1 if low(nc["rating"], nc["votes"], nc["approval"]) else 0
            r["t_c_fall"] = 1 if nc["rating"] < r["rating"] else 0
            r["c_delta"] = nc["rating"] - r["rating"]
            if r["cohort_mean_before"] is not None:
                r["t_c_below"] = 1 if nc["rating"] < r["cohort_mean_before"] else 0
        if r["att_ratio_next"] is not None:
            wk = min(int(r["curr_week"] or 1), 40)
            m = med.get((r["course"], r["kind"], wk // 4), med.get(("all", r["kind"], wk // 4)))
            if m is not None:
                r["b_resid"] = math.log(r["att_ratio_next"]) - m
                r["t_b"] = 1 if r["b_resid"] < 0 else 0
        r["t_d"] = r["self_low"]
        r["t_e"] = 1 if (r["review_status"] not in (None, "new") or r["decision_override"] is not None) else 0
        r["split"] = "fit" if r["month"] in FIT_MONTHS else "holdout"

    # ---- anonymise and tabulate --------------------------------------------------------------
    an_i, an_m, an_c = Anonymiser("I"), Anonymiser("M"), Anonymiser("C")
    cols = ["id", "date", "month", "split", "course", "cohort", "module", "instructor", "kind", "region", "escalated",
            *FEATURE_DOCS.keys(), "self_low", "course_prior_source", "att_ratio_next",
            "next_i_rating", "next_i_votes", "next_i_approval", "next_c_rating", "next_c_votes", "next_c_approval", "next_k_attended",
            *TARGET_DOCS.keys(), "v7_score", "v7_band", "v7_action", "v7_provisional"]
    out = []
    for r in rows:
        ni, nc, nk = r.get("next_i"), r.get("next_c"), r.get("next_k")
        rec = {"id": r["id"], "date": r["date"].isoformat(), "month": r["month"], "split": r["split"], "course": r["course"],
               "cohort": an_c(r["cohort_id"]), "module": an_m(r["topic_id"]), "instructor": an_i(r["instructor_key"]),
               "kind": r["kind"], "region": r["region"], "escalated": int(r["escalated"]),
               "next_i_rating": ni["rating"] if ni else None, "next_i_votes": ni["votes"] if ni else None, "next_i_approval": ni["approval"] if ni else None,
               "next_c_rating": nc["rating"] if nc else None, "next_c_votes": nc["votes"] if nc else None, "next_c_approval": nc["approval"] if nc else None,
               "next_k_attended": nk["attended"] if nk else None}
        for k in cols:
            if k not in rec:
                rec[k] = r.get(k)
        out.append(rec)
    df = pd.DataFrame(out, columns=cols)
    meta = {"rows": len(df), "course_len_weeks": course_len, "instructors": len(an_i.map), "modules": len(an_m.map), "cohorts": len(an_c.map),
            "features": FEATURE_DOCS, "targets": TARGET_DOCS}
    return df, meta


def main():
    t0 = time.time()
    rows, source = load_rows()
    resolve_instructors(rows)
    df, meta = build(rows)
    meta["source"] = source
    meta["generated"] = time.strftime("%Y-%m-%d %H:%M")
    os.makedirs(OUT, exist_ok=True)
    df.to_csv(FEATURES_CSV, index=False)
    cov = {c: int(df[c].notna().sum()) for c in list(FEATURE_DOCS) + list(TARGET_DOCS)}
    meta["coverage"] = cov
    meta["target_rates"] = {t: (float(df[t].mean()) if df[t].notna().any() and t not in ("b_resid", "c_delta") else None) for t in TARGET_DOCS}
    meta["split_counts"] = {"fit": int((df["split"] == "fit").sum()), "holdout": int((df["split"] == "holdout").sum())}
    write_json(META_JSON, meta)
    print("source %s | %d rows | %d instructors, %d modules, %d cohorts | fit %d / holdout %d | %.1fs" % (
        source, len(df), meta["instructors"], meta["modules"], meta["cohorts"], meta["split_counts"]["fit"], meta["split_counts"]["holdout"], time.time() - t0))
    print("coverage:", {k: v for k, v in cov.items() if v < len(df)})
    print("target rates:", {k: (round(v, 3) if v is not None else None) for k, v in meta["target_rates"].items()})


def load_features():
    if not os.path.exists(FEATURES_CSV):
        main()
    df = pd.read_csv(FEATURES_CSV)
    df["date"] = pd.to_datetime(df["date"])
    return df


if __name__ == "__main__":
    main()
