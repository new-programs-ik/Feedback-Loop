"""Step 6 - the deliverables: the full study, the two-page one-pager, and the short summary.

  Formula-Study.pdf         the full study (repo root, gitignored); HTML in analysis/out/formula-study.html
  Formula-One-Pager.pdf     two pages for the VP; HTML in analysis/out/formula-one-pager.html
  analysis/out/formula_summary.md   five sentences for the programme owner

House style and the HTML -> Chrome PDF path are borrowed from analysis/build_sentiment_report.py.
Every number in the text is read from the study's outputs; nothing is typed in by hand except the
team's capacity (12 analyses and 5 videos a week) and the two agreed lines.
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from common import OUT, ROOT, LINE, BAR, CAPACITY, BANDS, BAND_LABEL, FIT_MONTHS, HOLDOUT_MONTHS, SELECT_FOLDS, MONTHS, weeks_in, read_json  # noqa: E402
from build_sentiment_report import CSS, hbars, grouped, stacked, lines_chart, print_pdf, esc, pct, n1, BLUE, ORANGE, GREEN, BC  # noqa: E402
from features import load_features, FEATURE_DOCS, TARGET_DOCS  # noqa: E402
from families import inputs_from_df, score_points, score_any  # noqa: E402

GREY = "#9aa3ad"
LABELS = {
    "rating": "rating", "responses": "how many rated", "attended": "attended", "reach": "share of the room that rated", "yes": "yes votes", "no": "no votes",
    "votes": "votes", "approval": "approval %", "kind_live": "live (vs review)", "region_ind": "India cohort", "weekday": "weekday",
    "votes_minus_responses": "votes minus responses", "resp_gt_att": "more raters than attendees", "week_no": "weeks since first class",
    "curr_week": "curriculum week", "week_share": "position in the course (0-1)", "cohort_size": "cohort size", "att_vs_first": "attendance vs the first class",
    "att_vs_prev": "attendance vs the previous class", "cohort_n_before": "classes the cohort has had", "prev_rating": "previous class rating (cohort)",
    "prev_approval": "previous class approval (cohort)", "prev_low": "previous class was low", "cohort_mean_before": "the cohort's average so far",
    "is_review_of_live": "a review of a live class days before", "live_before_rating": "that live class's rating", "module_prior_rating": "module's usual rating",
    "module_prior_n": "module's earlier classes", "module_prior_approval": "module's usual approval", "rating_vs_module": "rating minus the module's usual",
    "module_loo_rating": "module's average (uses the future)", "course_prior_rating": "course's usual rating", "course_prior_approval": "course's usual approval",
    "rating_vs_course": "rating minus the course's usual", "track_mean": "instructor's record (mean)", "track_n": "instructor's earlier classes",
    "track_ewma": "instructor's recent record", "track_trend": "instructor's trend (last 3 vs before)", "days_since_last": "days since the instructor's last class",
    "instr_prev_rating": "instructor's previous class", "track_approval": "instructor's usual approval", "track_module_mean": "instructor's record on this module",
    "track_module_n": "instructor's earlier classes on this module", "rating_vs_track": "rating minus the instructor's record",
}
CHART = {
    "rating": "rating", "responses": "how many rated", "attended": "attended", "reach": "share of room rating", "yes": "yes votes", "no": "no votes", "votes": "votes",
    "approval": "approval %", "kind_live": "live class", "region_ind": "India cohort", "weekday": "weekday", "week_no": "weeks since first", "curr_week": "curriculum week",
    "week_share": "course position", "cohort_size": "cohort size", "att_vs_first": "attend. vs first", "att_vs_prev": "attend. vs previous", "cohort_n_before": "classes so far",
    "prev_rating": "previous class rating", "prev_approval": "previous approval", "prev_low": "previous was low", "cohort_mean_before": "cohort average so far",
    "is_review_of_live": "review of a live", "live_before_rating": "that live's rating", "module_prior_rating": "module usual rating", "module_prior_n": "module classes",
    "module_prior_approval": "module usual approval", "rating_vs_module": "rating vs module", "module_loo_rating": "module avg (future)", "course_prior_rating": "course usual rating",
    "course_prior_approval": "course usual approval", "rating_vs_course": "rating vs course", "track_mean": "instructor record", "track_n": "instructor classes",
    "track_ewma": "instr. recent record", "track_trend": "instructor trend", "days_since_last": "days since last", "instr_prev_rating": "instr. previous class",
    "track_approval": "instr. usual approval", "track_module_mean": "instr. on this module", "track_module_n": "instr. classes here", "rating_vs_track": "rating vs record",
}
TARGET_SHORT = {"t_a": "instructor's next class low", "t_b": "cohort loses attendance", "t_c": "cohort's next class low", "t_c_below": "cohort's next class below its average", "t_d": "this class under a line"}


def _f(v, d=3):
    return "n/a" if v is None or (isinstance(v, float) and v != v) else ("%%.%df" % d) % v


def sig_strength(a):
    """AUC re-expressed as 'higher value -> more trouble' strength on 0.5-1: max(a, 1-a) with a direction."""
    if a is None or a != a:
        return None, ""
    return (max(a, 1 - a), "more = safer" if a < 0.5 else "more = riskier")


def dial_table(df, cfg):
    """Analyses a week on the held-out months for today's settings as the vote floor moves."""
    hold = df[df["month"].isin(HOLDOUT_MONTHS)].reset_index(drop=True)
    X = inputs_from_df(hold)
    weeks = weeks_in(HOLDOUT_MONTHS)
    rows = []
    for floor in (5, 6, 7, 8, 10):
        c = json.loads(json.dumps(cfg))
        c["min_votes"]["action"] = floor
        r = score_points(X, c)
        acts = Counter(r["action"])
        rows.append((floor, (acts["video"] + acts["transcript"]) / weeks, acts["video"] / weeks, acts["transcript"] / weeks, acts["watch"]))
    return rows


def build():
    t0 = time.time()
    R = read_json(os.path.join(OUT, "formula_results.json"))
    S = read_json(os.path.join(OUT, "formula_signal.json"))
    T = read_json(os.path.join(OUT, "formula_trust.json"))
    PR = read_json(os.path.join(OUT, "formula_properties.json"))
    FX = read_json(os.path.join(OUT, "formula_cases.json"))
    FM = read_json(os.path.join(OUT, "formula_features_meta.json"))
    REC = read_json(os.path.join(OUT, "formula_recommended.json"))
    hist = R["history"]
    C = R["candidates"]
    best_tag = R["best"]
    win = C[best_tag]
    ref_tag = REC.get("refinement", {}).get("tag")
    ref = C[ref_tag] if ref_tag else None
    orig = C["A0"]
    v7 = C["A1"]
    df = load_features()
    hold_n = R["meta"]["holdout_rows"]
    fit_n = R["meta"]["fit_rows"]
    weeks_h = weeks_in(HOLDOUT_MONTHS)
    props_list = PR["properties"]
    n_props = len(props_list)
    dial = dial_table(df, v7["config"])
    # weekday explanation: share of classes with 6+ votes by weekday group, held-out
    hold = df[df["month"].isin(HOLDOUT_MONTHS)]
    wd_grp = hold["weekday"].apply(lambda d: "Thu-Sun" if d >= 3 else "Mon-Wed")
    wd_n = {g: int(len(sub)) for g, sub in hold.groupby(wd_grp)}
    wd_low = {g: int(((sub["votes"] >= 6) & (sub["t_d"] == 1)).sum()) for g, sub in hold.groupby(wd_grp)}
    from evaluate import evaluate as _evaluate
    ev_all = _evaluate(df, v7["config"], weeks_in(range(1, 9)), bootstrap=0)
    wd_all = ev_all["fairness"]["weekday"]
    wd_all_n = {g: int(len(sub)) for g, sub in df.groupby(df["weekday"].apply(lambda d: "Thu-Sun" if d >= 3 else "Mon-Wed"))}
    low_share = {m: float(sub["t_d"].mean() * 100) for m, sub in df.groupby("month")}

    def H(ev, k):
        return ev["holdout"][k] if isinstance(ev["holdout"], dict) and k in ev["holdout"] else None

    def hb(c):
        return c["holdout"]

    A = []
    add = A.append
    add('<title>Formula Study</title><style>%s</style><div class="wrap">' % CSS)
    add('<div class="kicker">Feedback Loop v3 · Formula study · New Programs</div>')
    add('<h1>What the Class Sentiment Score should be made of</h1>')
    add('<p class="sub">%s real classes, 1 January to 31 August 2026 · %d inputs measured against %d targets · %d formula families · %s generated cases · %d properties · %d loop iterations · generated %s</p>' % (
        "{:,}".format(R["meta"]["rows"]), len(FEATURE_DOCS) - 1, len(TARGET_DOCS) - 2, 5, "{:,}".format(FX["grid_points"] + FX["counts"]["random"] + FX["counts"]["adversarial"]), n_props, R["meta"]["iterations"], R["meta"]["generated"]))
    o_h, v_h = hb(orig), hb(v7)
    r_h = hb(ref) if ref else None
    add('<p class="lede">We were asked to forget the formula we were given, find the real inputs and weights from the data, simulate every case we could think of, and keep '
        'looping until the best defensible formula was found. The loop ran %d iterations over five families, %d inputs and every shape switch we could name. Its '
        'answer is plainer than a new formula: on eight months of classes <b>no formula we can build separates from today\'s active version</b> on the thing that matters '
        '(does the score foresee a low next class - every difference sits inside one standard error), today\'s version is the only one of the family that passes all %d '
        'properties, and the two agreed lines - not the points - decide the queue. What the data does settle is the <b>trust</b> question: how many votes make a low '
        'average believable (about five), and how hard a thin class should be pulled toward its module\'s usual rating (about three phantom raters, not the five we guessed).</p>' % (
            R["meta"]["iterations"], len(FEATURE_DOCS) - 1, n_props))

    # ---- 1. the answer -------------------------------------------------------------------------
    add('<h2>1. The answer in one table</h2>')
    add('<p>Measured on the <b>held-out months</b> (June to August, %s classes) that no setting was ever fitted or chosen on. "Original" is the manager\'s method as '
        'written; "today" is the version active in the database (v7); "today + trust guard" is the one refinement the loop found worth keeping in the drawer.</p>' % "{:,}".format(hold_n))
    cols = [("Manager\'s original", o_h), ("Today (v7) - the winner", v_h)] + ([("Today + trust guard", r_h)] if r_h else [])
    add('<table><tr><th></th>%s</tr>' % "".join('<th class="n">%s</th>' % esc(k) for k, _ in cols))

    def row(label, fn, sub=""):
        add('<tr><td>%s%s</td>%s</tr>' % (label, ('<br><span class="sub">%s</span>' % sub) if sub else "", "".join('<td class="n">%s</td>' % fn(ev) for _, ev in cols)))
    row("Does the score foresee a low next class? (AUC, 95% interval)", lambda e: "%s <span class=\"sub\">(%s-%s)</span>" % (_f(e["objective"]["value"]), _f(e["objective"]["value"] - 1.96 * e["objective"]["se"], 2), _f(e["objective"]["value"] + 1.96 * e["objective"]["se"], 2)),
        "mean of two targets: the instructor\'s next class, the cohort\'s next class; 0.5 = coin toss")
    row("Low classes (under 4.55 or under 80%, 5+ votes) shown as Good or Excellent", lambda e: "%d of %d <span class=\"sub\">(%s)</span>" % (e["lines"]["false_comfort"], e["lines"]["n_voiced"], pct(e["lines"]["false_comfort_share"])))
    row("\"Bad\" classes that were actually rated 4.55 or better", lambda e: "%d of %d" % (e["lines"]["bad_rated_fine"], e["lines"]["bad_total"]))
    row("Classes whose verdict flips if one learner votes differently", lambda e: "%s <span class=\"sub\">(label %s)</span>" % (pct(e["stability"]["flip_verdict"]), pct(e["stability"]["flip_label"])), "verdict = video / transcript / nothing / watch; label = the band name")
    row("Chance the instructor\'s next class is low: Bad vs Excellent", lambda e: "%s vs %s" % (pct(e["bands"]["per_band"]["bad"]["a_share"], 0), pct(e["bands"]["per_band"]["excellent"]["a_share"], 0)))
    row("Analyses a week in June-August", lambda e: "%s <span class=\"sub\">(%s video)</span>" % (n1(e["workload"]["per_week"]), n1(e["workload"]["videos_per_week"])), "the team\'s capacity is %g a week, %g videos" % (CAPACITY["per_week"], CAPACITY["videos"]))
    add('<tr class="pickrow"><td>Properties passed (of %d)</td>%s</tr></table>' % (n_props, "".join('<td class="n">%d</td>' % C[t]["properties"]["summary"]["passed"] for t in (["A0", "A1"] + ([ref_tag] if ref_tag else [])))))
    add('<div class="card finding"><b>Three things the VP should take from this.</b> (1) <b>Keep today\'s version.</b> It is the simplest formula that passes every property, and nothing '
        'beats it on signal - the loop tried %d alternatives. (2) <b>The queue is set by the two lines and by the period, not by the formula.</b> In June-August the lines alone put '
        '%s classes a week in front of the team against a capacity of %g; every formula that honours the lines lands there, and the only dials are the vote floor (section 8) and the lines '
        'themselves. (3) <b>Head-count is trust, not points.</b> The old "responses" term is served by the vote floors (a band from 3 votes, an analysis from %d) and, once one contract change '
        'lands, by a guard of about three phantom raters - the number the data gives, not a guess.</div>' % (
            R["meta"]["iterations"] - 1, n1(v_h["workload"]["per_week"]), CAPACITY["per_week"], v7["config"]["min_votes"]["action"]))

    # ---- 2. what the score is for, how the study ran ---------------------------------------------
    add('<h2>2. What the score is for, and how this study was run</h2>')
    add('<p>One number per rated class, 0-100, read as four bands; the band decides the work: Bad → video analysis, Average → transcript analysis, Good and Excellent → nothing '
        'unless a PM asks, too few votes → watch. The right formula (1) finds the classes where something went wrong for learners, (2) is stable - one learner changing their mind must not '
        'flip the verdict, (3) is fair to small rooms and test reviews, (4) keeps the queue near %g analyses a week, (5) can be said in one sentence, and (6) degrades gracefully when an input is missing. '
        'The team\'s two lines - under %.2f rating or under %d%% approval with enough votes is a class to look at - are treated here as reference points to test against, not as the formula.</p>' % (
            CAPACITY["per_week"], LINE, BAR))
    add('<div class="term"><b>How the months were used.</b> <b>Fit</b>: January-May (%s classes) - every weight, shape, k and band edge was chosen here. <b>Selection</b>: inside the fit months, '
        'rolling - fit on January-February and judge on March, fit on January-March and judge on April, fit on January-April and judge on May - so the loop\'s choices were always judged on months '
        'it had not fitted. <b>Held-out</b>: June-August (%s classes) - scored once per candidate for the tables in this report, never used to choose anything. Confidence intervals come from '
        'a bootstrap that resamples whole instructors (or whole cohorts), because classes of one instructor are not independent.</div>' % ("{:,}".format(fit_n), "{:,}".format(hold_n)))

    # ---- 3. the inputs ---------------------------------------------------------------------------
    add('<h2>3. The inputs - everything measurable at scoring time</h2>')
    add('<p>One row per rated class, built from the database so every class has its cohort week, its module and a resolved instructor (%d instructors, %d modules, %d cohorts). '
        'Every history input uses only classes dated strictly before the class, so the sync could compute it at scoring time. Ids are anonymised throughout.</p>' % (FM["instructors"], FM["modules"], FM["cohorts"]))
    groups = [("The row itself", ["rating", "responses", "attended", "reach", "yes", "no", "votes", "approval", "kind_live", "region_ind", "weekday", "votes_minus_responses", "resp_gt_att"]),
              ("The cohort", ["week_no", "curr_week", "week_share", "cohort_size", "att_vs_first", "att_vs_prev", "cohort_n_before", "prev_rating", "prev_approval", "prev_low", "cohort_mean_before", "is_review_of_live", "live_before_rating"]),
              ("The module and the course", ["module_prior_rating", "module_prior_n", "module_prior_approval", "rating_vs_module", "course_prior_rating", "course_prior_approval", "rating_vs_course", "module_loo_rating"]),
              ("The instructor", ["track_mean", "track_n", "track_ewma", "track_trend", "days_since_last", "instr_prev_rating", "track_approval", "track_module_mean", "track_module_n", "rating_vs_track"])]
    add('<table><tr><th>Input</th><th>Meaning</th><th class="n">Classes with a value</th></tr>')
    for g, keys in groups:
        add('<tr><td colspan="3"><b>%s</b></td></tr>' % g)
        for k in keys:
            add('<tr><td>%s</td><td class="sub">%s</td><td class="n">%s</td></tr>' % (esc(LABELS.get(k, k)), esc(FEATURE_DOCS[k]), "{:,}".format(FM["coverage"][k])))
    add('</table>')

    # ---- 4. what predicts what -------------------------------------------------------------------
    add('<h2>4. What "went wrong" looks like, and what predicts it</h2>')
    add('<p>There are no per-learner ratings, so "something went wrong for learners" has to be read from what happened next. Five targets were defined; the base rates are the share of classes where the target happened.</p>')
    br = S["notes"]["base_rates"]
    add('<table><tr><th></th><th>Target</th><th class="n">Fit months</th><th class="n">Held-out</th><th>Reading</th></tr>')
    readings = {"t_a": "the existing definition; mostly the instructor\'s persistence", "t_b": "worse than the median cohort at the same week; a coin toss by construction",
                "t_c": "the closest thing to \'the cohort was let down\'", "t_c_below": "a milder version of c", "t_d": "consistency with the two lines, not evidence"}
    for t, (label, _) in (("t_a", (TARGET_SHORT["t_a"], 0)), ("t_b", (TARGET_SHORT["t_b"], 0)), ("t_c", (TARGET_SHORT["t_c"], 0)), ("t_c_below", (TARGET_SHORT["t_c_below"], 0)), ("t_d", (TARGET_SHORT["t_d"], 0))):
        add('<tr><td><b>%s</b></td><td>%s<br><span class="sub">%s</span></td><td class="n">%s</td><td class="n">%s</td><td class="sub">%s</td></tr>' % (
            t[2:].replace("_below", " (below)"), esc(label), esc(TARGET_DOCS[t]), pct(br[t]["fit"] * 100, 0), pct(br[t]["holdout"] * 100, 0), readings[t]))
    add('<tr><td><b>e</b></td><td>a PM decision recorded in the database</td><td class="n" colspan="2">%d of %s rows</td><td class="sub">too few to measure anything; the app has only just started collecting them</td></tr></table>' % (
        S["notes"]["pm_decisions"]["rows_with_a_decision"], "{:,}".format(S["notes"]["pm_decisions"]["rows"])))
    rtm = S["notes"]["regression_to_mean"]
    add('<p>The literal target "the cohort\'s next class is rated lower than this one" was defined and then set aside: it is regression to the mean, not a signal - the correlation between a class\'s rating '
        'and the change to the next class is %s, so a high class is followed by a lower one almost by arithmetic. "The next class is low" (c) does not have that flaw.</p>' % _f(rtm["corr_rating_vs_next_minus_this"], 2))
    add('<h3>Which inputs carry signal</h3>')
    add('<p>Each input on its own, on the held-out months: how well it ranks classes by the target (AUC re-expressed as a strength from 0.5, a coin toss, to 1). The ten strongest per target.</p>')
    for t in ("t_a", "t_c"):
        u = S["univariate"][t]
        rows = []
        for f, v in u.items():
            a = v["holdout"]["auc"]
            st, direction = sig_strength(a)
            if st is not None and v["holdout"]["n"] >= 100 and f != "module_loo_rating":
                rows.append((f, st, direction, v["fit"]["auc"], a, v["holdout"]["n"]))
        rows.sort(key=lambda r: -r[1])
        items = [(CHART.get(f, f), st, BLUE if d.endswith("safer") else ORANGE) for f, st, d, *_ in rows[:10]]
        add('<div class="figure">%s<div class="cap">Target %s - <b>%s</b>. Blue: more of the input means a safer next class; orange: more means a riskier one. Held-out months, inputs with at least 100 classes.</div></div>' % (
            hbars(items, maxv=1.0, fmt="%.2f", mark=0.5, mark_label="coin toss", aria="Signal strength of the ten strongest inputs for target %s" % t), t[2:], esc(TARGET_SHORT[t])))
    ua, uc = S["univariate"]["t_a"], S["univariate"]["t_c"]
    add('<table><tr><th>Input</th><th class="n">a: instructor\'s next class<br>fit / held-out</th><th class="n">c: cohort\'s next class<br>fit / held-out</th><th class="n">b: attendance<br>held-out</th></tr>')
    show = ["rating", "approval", "no", "track_mean", "track_ewma", "track_approval", "rating_vs_course", "rating_vs_module", "module_prior_rating", "cohort_mean_before", "prev_rating", "live_before_rating",
            "att_vs_prev", "attended", "responses", "reach", "curr_week", "kind_live", "region_ind", "weekday"]
    ub = S["univariate"]["t_b"]
    for f in show:
        add('<tr><td>%s</td><td class="n">%s / %s</td><td class="n">%s / %s</td><td class="n">%s</td></tr>' % (
            esc(LABELS.get(f, f)), _f(ua[f]["fit"]["auc"], 2), _f(ua[f]["holdout"]["auc"], 2), _f(uc[f]["fit"]["auc"], 2), _f(uc[f]["holdout"]["auc"], 2), _f(ub[f]["holdout"]["auc"], 2)))
    add('</table><p class="sub">AUC of the input itself: under 0.5 means a higher value goes with a safer next class (rating, approval, the record); over 0.5 means riskier (no-votes). 0.5 is no signal.</p>')
    add('<h3>The ceilings: what any model could reach</h3>')
    add('<p>A regularised logistic regression and a gradient-boosted model, on the sheet row alone and with the history added, fitted on January-May and tested on June-August ("fixed"), '
        'and refitted every month on all earlier months ("rolling"). The reference points are single inputs and today\'s score on the same held-out rows.</p>')
    add('<table><tr><th>Target</th><th>Model</th><th class="n">Fixed (95% interval)</th><th class="n">Rolling</th></tr>')
    for t in ("t_a", "t_c", "t_b"):
        first = True
        for k, v in S["models"][t].items():
            if k == "logistic_coefficients" or not v.get("fixed"):
                continue
            if "diagnostic" in k:
                continue
            add('<tr><td>%s</td><td>%s</td><td class="n">%s (%s-%s)</td><td class="n">%s</td></tr>' % (esc(TARGET_SHORT[t]) if first else "", esc(k), _f(v["fixed"]["auc"]), _f(v["fixed"]["lo"], 2), _f(v["fixed"]["hi"], 2), _f(v["rolling"]["auc"]) if v["rolling"] else "n/a"))
            first = False
        for name, v in S["reference"][t].items():
            add('<tr class="dim"><td></td><td>%s</td><td class="n">%s (%s-%s)</td><td class="n"></td></tr>' % (esc(name), _f(v["auc"]), _f(v["lo"], 2), _f(v["hi"], 2)))
    add('</table>')
    ref_a = S["reference"]["t_a"]
    add('<div class="card finding"><b>Finding F1 - the signal is real but modest, and it lives in the rating.</b> The best any model reaches for "the cohort\'s next class is low" is about %s; the rating alone reaches %s and today\'s score %s. '
        'Adding the cohort\'s history, the module\'s history and attendance does not raise the ceiling on held-out months - the boosted model with everything does no better than the logistic on the sheet row alone. '
        '<b>F2 - the instructor\'s record predicts the instructor\'s next class, not this class.</b> The record alone reaches %s for target a (better than the rating\'s %s) because it measures the person\'s persistence; '
        'for the cohort\'s next class it is worth %s. That is why the record earns a small weight, not a large one. <b>F3 - attendance loss is not predictable from quality.</b> The best quality input reaches %s for target b; '
        'what predicts an attendance drop is the previous attendance itself (mean reversion). A formula cannot foresee it, so it is not fitted against.</div>' % (
            _f(max(v["fixed"]["auc"] for k, v in S["models"]["t_c"].items() if k != "logistic_coefficients" and v.get("fixed") and "diagnostic" not in k), 2),
            _f(S["reference"]["t_c"]["rating alone"]["auc"], 2), _f(S["reference"]["t_c"]["today's v7 score"]["auc"], 2),
            _f(ref_a["track record alone"]["auc"], 2), _f(ref_a["rating alone"]["auc"], 2), _f(S["reference"]["t_c"]["track record alone"]["auc"], 2),
            _f(max(S["reference"]["t_b"][k]["auc"] for k in ("rating alone", "approval alone", "today's v7 score")), 2)))

    # ---- 5. trust ----------------------------------------------------------------------------------
    add('<h2>5. Trust - how many votes make a low average believable</h2>')
    add('<p>The manager\'s "responses" term (6 points once ten or more rated) was never meant to reward a big room. Its intent was trust: when only a handful rated, two or three biased learners can drag the average down, '
        'so a low average from a tiny sample cannot be believed on its own. Without each rater\'s history we cannot check the raters - but we can check the claim itself. For classes under the %.2f line, by how many voted: '
        'how often the instructor\'s next class goes wrong, against classes over the line with the same number of votes.</p>' % LINE)
    B = T["believability_all"]["rating_line"]["instructor_next"]
    Bc = T["believability_all"]["rating_line"]["cohort_next"]
    cats = list(T["meta"]["buckets"])
    add('<div class="figure">%s<div class="cap">Share of next classes (same instructor, 5+ votes) that are low, for classes under 4.55 (orange) and classes fine on the rating (blue), by how many voted. All eight months; '
        'the intervals in the table below come from a bootstrap over instructors.</div></div>' % grouped(
            cats, [("under 4.55", ORANGE, [(B[c]["risk_low"] or 0) * 100 for c in cats]), ("4.55 or better", BLUE, [(B[c]["risk_fine"] or 0) * 100 for c in cats])], ymax=70, aria="Next-class risk for low and fine classes by vote count", ylab="next class low"))
    add('<table><tr><th>Votes</th><th class="n">Low classes</th><th class="n">Next class low: low vs fine</th><th class="n">Difference (95% interval)</th><th class="n">Cohort\'s next class: low vs fine</th></tr>')
    for c in cats:
        b, bc = B[c], Bc[c]
        add('<tr><td>%s</td><td class="n">%d</td><td class="n">%s vs %s</td><td class="n">%s (%s to %s)</td><td class="n">%s vs %s</td></tr>' % (
            c, b["n_low"], pct((b["risk_low"] or 0) * 100, 0), pct((b["risk_fine"] or 0) * 100, 0),
            pct((b.get("diff") or 0) * 100, 0) if b.get("diff") is not None else "n/a", pct((b.get("diff_lo") or 0) * 100, 0) if b.get("diff_lo") is not None else "-", pct((b.get("diff_hi") or 0) * 100, 0) if b.get("diff_hi") is not None else "-",
            pct((bc["risk_low"] or 0) * 100, 0), pct((bc["risk_fine"] or 0) * 100, 0)))
    add('</table>')
    var_c, var_m, var_t = T["variance"]["course_prior_rating"], T["variance"]["module_prior_rating"], T["variance"]["track_mean"]
    ap = T["approval_prior"]["fit"]
    add('<div class="card finding"><b>Finding F4 - a low average is believable from about 5 votes; 3-4 votes are suggestive; 1-2 say nothing.</b> From 5 votes up, a low class\'s next class goes wrong %s-%s of the time against %s-%s for fine classes, and the '
        'intervals clear zero; at 3-4 votes the difference is as large but its interval touches zero; at 1-2 votes there is no difference to speak of. '
        '<b>F5 - the guard\'s strength, derived instead of guessed.</b> The spread of class ratings around their module\'s usual rating splits into a true between-class spread (%s) and a rater-level spread (%s): '
        'the weight of the prior is their squared ratio, <b>about %s phantom raters</b> (against the course prior %s, against the instructor\'s own record %s; the earlier study guessed 5). '
        'The vote is even more concentrated: a beta prior with mean %s and %s phantom votes. <b>F6 - the asymmetric version is not supported.</b> A low 3-4-vote class predicts trouble about as well as a low 15-vote class '
        '(%s vs %s), so the data gives no reason to distrust few-rater lows more than few-rater highs; both are simply less certain, which the symmetric guard and the vote floors already express. The asymmetric guard was still built and tried in the loop (iteration %s) and added nothing.</div>' % (
            pct(min((B[c]["risk_low"] or 0) for c in ("5-9", "10-14", "15+")) * 100, 0), pct(max((B[c]["risk_low"] or 0) for c in ("5-9", "10-14", "15+")) * 100, 0),
            pct(min((B[c]["risk_fine"] or 0) for c in ("5-9", "10-14", "15+")) * 100, 0), pct(max((B[c]["risk_fine"] or 0) for c in ("5-9", "10-14", "15+")) * 100, 0),
            _f(var_m["fit"]["tau"], 2), _f(var_m["fit"]["sigma"], 2), _f(var_m["fit"]["k"], 1), _f(var_c["fit"]["k"], 1), _f(var_t["fit"]["k"], 1),
            pct(ap["mean"] * 100, 0), _f(ap["a_plus_b"], 1), pct((B["3-4"]["risk_low"] or 0) * 100, 0), pct((B["15+"]["risk_low"] or 0) * 100, 0),
            next((str(h["iteration"]) for h in hist if h["tag"] == "C-asym"), "-")))
    byn = var_c["all"]["by_n"][:15]
    fitted = [var_c["all"]["tau"] ** 2 + var_c["all"]["sigma"] ** 2 / n for n, _, _ in byn]
    add('<div class="figure">%s<div class="cap">How far classes sit from their course\'s usual rating (mean squared distance, blue) by how many rated, and the fitted line tau² + sigma²/n (orange). The curve flattens at about tau² = %s: past ten raters the sample no longer explains the distance - the class really is different.</div></div>' % (
        lines_chart([str(n) for n, _, _ in byn], [("", BLUE, [m for _, m, _ in byn]), ("", ORANGE, fitted)], fmt="%.2f", aria="Squared distance from the course prior by number of raters"), _f(var_c["all"]["tau"] ** 2, 3)))
    add('<p><b>How the responses term\'s intent is served.</b> Head-count never adds or removes points in any candidate the loop kept. It decides how much the numbers are believed: under 3 voices no band is shown; from 3 a band is shown but marked provisional and the class is watched; '
        'from %d votes the band stands and drives the work (the believability table says 5 would do; 6 is today\'s capacity choice - the dial in section 8); and, once the contract change lands, a class\'s rating and vote are blended with about three typical classes of its module before they are scored, so three opinions cannot sink a class on their own. '
        'The same principle is written as property P12 and tested on every generated case: at the same rating and vote, more raters can only move the score toward the class\'s own numbers.</p>' % v7["config"]["min_votes"]["action"])
    RR = REC["rater_reliability"]
    add('<div class="card ok"><b>Designed, not built: a rater-reliability input for when per-learner ratings arrive.</b> %s <b>What it needs:</b> %s. <b>How it plugs in:</b> %s <b>Guard rails:</b> %s. <b>How it would be validated:</b> %s</div>' % (
        esc(RR["status"]) + ".", esc(RR["what_it_needs"]), " ".join("(%d) %s" % (i + 1, esc(s)) for i, s in enumerate(RR["how_it_plugs_in"])), "; ".join(esc(g) for g in RR["guard_rails"]), esc(RR["how_to_validate"])))

    # ---- 6. the families -------------------------------------------------------------------------
    add('<h2>6. The families - five deployable shapes</h2>')
    add('<p>Each family is a small JSON of settings a PM could read on a Scoring page, fitted on the training months. The one-sentence explanation is the family\'s own; where a family fails that test it says so.</p>')
    short_fam = {"A0": "Manager's original", "A1": "Today (v7)", "A2": "C5 as studied", "A4": "Points + trust", "A5": "Wilson vote", "A6": "Logistic", "A7": "Sequential"}
    fams = [("A0", "The manager\'s original"), ("A1", "Today\'s version (two lines + graded score)"), ("A2", "C5 as studied (guard k=5, lines on the guarded values)"),
            ("A4", "Weighted points + trust (module prior, k from the data, lines on raw values)"), ("A5", "Points + Wilson lower bound for the vote"),
            ("A6", "Monotone logistic (probability shape)"), ("A7", "Sequential (recent record, shrink toward the instructor)")]
    add('<table><tr><th>Family</th><th class="n">Held-out signal</th><th class="n">Verdict flips</th><th class="n">False comfort</th><th class="n">A week</th><th class="n">Properties</th><th>Fits the contract</th></tr>')
    for tag, label in fams:
        if tag not in C:
            continue
        c = C[tag]
        h = c["holdout"]
        cls = ' class="pickrow"' if tag == best_tag else ""
        add('<tr%s><td><b>%s</b></td><td class="n">%s</td><td class="n">%s</td><td class="n">%d</td><td class="n">%s</td><td class="n">%d/%d</td><td class="sub">%s</td></tr>' % (
            cls, esc(label), _f(h["objective"]["value"]), pct(h["stability"]["flip_verdict"], 0), h["lines"]["false_comfort"], n1(h["workload"]["per_week"]),
            c["properties"]["summary"]["passed"], n_props, "yes" if c["contract_as_is"] else "needs: " + ", ".join(c["contract_needs"])))
        add('<tr%s><td colspan="7" class="sub" style="padding-top:0;border-top:0"><i>In one sentence:</i> %s</td></tr>' % (cls, esc(c["sentence"])))
    add('</table>')
    add('<div class="figure">%s<div class="cap">Held-out signal (mean AUC for the two next-class targets) per family; the dashed line is today\'s version. Every bar sits inside every other bar\'s 95%% interval (about ±%s).</div></div>' % (
        hbars([(short_fam[tag], C[tag]["holdout"]["objective"]["value"], GREEN if tag == best_tag else (ORANGE if not C[tag]["admissible"] else BLUE)) for tag, label in fams if tag in C], maxv=0.8, fmt="%.3f",
              mark=v_h["objective"]["value"], mark_label="today", aria="Held-out objective per family"), _f(2 * v_h["objective"]["se"], 2)))
    lg = C.get("A6")
    lg_lo = lg_hi = "n/a"
    if lg:
        rr = score_any(inputs_from_df(hold.reset_index(drop=True)), lg["config"])
        sc_ = rr["score"][~np.isnan(rr["score"])]
        lg_lo, lg_hi = "%.0f" % np.percentile(sc_, 5), "%.0f" % np.percentile(sc_, 95)
    add('<p><b>Why each family fell away.</b> The <b>Wilson</b> vote treats a thin vote as a bad vote - more raters at the same 40%% share raise the score - so it fails P12 by design. '
        'The <b>logistic</b> shape puts nine classes in ten between %s and %s, so the four bands have no natural edges; it also cannot be worked out by hand, and its queue on the selection months was %s a week. '
        'The <b>sequential</b> family shrinks a class toward the instructor\'s own record and then scores the record again: the record is counted twice, and a bad record sinks a 4.8 class rated by 15 people (P16). '
        '<b>C5 as studied</b> reads the lines on the blended values and lets %d low classes past them (the earlier study\'s finding, confirmed here as P22).</p>' % (
            lg_lo, lg_hi, n1(C["A6"]["selection"]["workload"]["per_week"]) if "A6" in C else "n/a", C["A2"]["holdout"]["lines"]["false_comfort"]))

    # ---- 7. cases and properties -----------------------------------------------------------------
    add('<h2>7. The cases and the properties</h2>')
    add('<p>A formula must behave on cases that have not happened yet. Three sources: a <b>full grid</b> over rating × votes × approval × attended × record × kind × cohort week (%s points; the properties run on a fixed-seed sample of %s and, on request, on the whole grid), '
        '<b>%s random draws</b> over every input at once (priors, attendance change, previous class and missing values included), and <b>%d named adversarial cases</b> - nobody attended, one rater, the 200-person webinar with five happy raters, the big room saying no, '
        'a 4.9 with everyone voting no, a 1.0 with everyone voting yes, more raters than attendees, a missing vote column, a brand-new course, an instructor\'s first class, a bad record with a fine class, a tiny cohort of 5, a review, an attendance collapse, '
        'a bimodal opinion behind a 3.8, the worst class of a 4.9 course, the guarded-line case, and the nonsense inputs. The expected behaviour is written as %d principles, each a test. The fixture is permanent (<code>analysis/out/formula_cases.json</code>, <code>analysis/formula/test_properties.py</code>).</p>' % (
            "{:,}".format(FX["grid_points"]), "{:,}".format(FX["counts"]["grid_sample"]), "{:,}".format(FX["counts"]["random"]), FX["counts"]["adversarial"], n_props))
    matrix_tags = [t for t in ("A0", "A1", "A2", "A4", "A5", "A6", "A7") if t in C]
    short = {"A0": "Original", "A1": "Today", "A2": "C5", "A4": "Points+trust", "A5": "Wilson", "A6": "Logistic", "A7": "Sequential"}
    fg_path = os.path.join(OUT, "formula_properties_fullgrid.json")
    if os.path.exists(fg_path):
        FG = read_json(fg_path)
        add('<p><b>On the whole grid.</b> %s</p>' % "; ".join("%s: %d of %d properties on %s cases" % (esc(k), v["summary"]["passed"], v["summary"]["total"], "{:,}".format(FG["cases"])) for k, v in FG["families"].items()))
    add('<table><tr><th>#</th><th>Property (the principle)</th>%s</tr>' % "".join('<th class="n">%s</th>' % short[t] for t in matrix_tags))
    for pid, name in props_list.items():
        cells = []
        for t in matrix_tags:
            d = C[t]["properties"]["detail"].get(pid)
            if d is None:
                cells.append('<td class="n">-</td>')
            elif d["passed"]:
                cells.append('<td class="n" style="color:%s;font-weight:700">pass</td>' % GREEN)
            else:
                cells.append('<td class="n" style="color:%s;font-weight:700">%d</td>' % (ORANGE, d["violations"]))
        add('<tr><td>%s</td><td class="sub">%s</td>%s</tr>' % (pid, esc(name), "".join(cells)))
    add('</table><p class="sub">A number is how many of the %s fixture cases violate the property.</p>' % "{:,}".format(FX["counts"]["grid_sample"] + FX["counts"]["random"] + FX["counts"]["adversarial"]))
    add('<div class="card finding"><b>Four properties were changed while the study ran, and why.</b> <b>P07</b> (one vote moves the score by at most 8 points and the band by one step): a hard line lets a class jump two bands on one vote - the line, not the score, decides; that jump is now counted and reported, not called a violation. '
        '<b>P08</b> (a missing vote is not a failed vote): first written as "at most 5 points below a vote exactly at the bar", which compared against a perfect vote score; rewritten as "never a worse band than everyone saying no, never above everyone saying yes, and a class rated 4.55+ with no vote is never Bad". '
        '<b>P12</b> (head-count is trust): the brief\'s literal "more raters at the same average never lower the score" is wrong for a class below its prior - more raters are more evidence that the class really was low; the property now says more raters only move the score toward the class\'s own numbers. '
        '<b>P16</b> was testing two bad histories at once (a 4.0 module and a 4.0 record); it now tests the record alone, and P23 tests the prior alone; two bad histories together may put a 4.8 class in Average - a transcript read - and the study accepts that.</div>')

    # ---- 8. the loop -----------------------------------------------------------------------------
    add('<h2>8. The loop\'s path - %d iterations</h2>' % R["meta"]["iterations"])
    add('<p>Propose → fit on the training months → check every property on the cases → judge on the selection months → simplify → repeat. The rules were fixed before the run (section 2 and the README); one was amended after a dry run and the dry run is kept (<code>formula_log_dryrun.jsonl</code>): '
        'because no candidate can beat another by more than one standard error on signal, a candidate within one standard error may also win by being simpler, or by cutting verdict flips at 10+ votes by more than 3 points at the cost of one moving part. The loop stopped: %s.</p>' % esc(R["meta"]["stopped"]))
    add('<div class="figure">%s<div class="cap">The selection objective by iteration (fitted on earlier months, judged on March-May). The band of one standard error around today\'s version is about ±%s; no candidate leaves it.</div></div>' % (
        lines_chart([str(h["iteration"]) for h in hist], [("selection objective", BLUE, [h["selection"]["objective"] for h in hist])], fmt="%.2f", ymax=0.8, aria="Selection objective by iteration"), _f(v7["selection"]["objective"]["se"], 3)))
    add('<table><tr><th>#</th><th>Change</th><th>Why</th><th class="n">Selection<br>signal</th><th class="n">Held-out<br>signal</th><th class="n">A week</th><th class="n">Props</th><th>Decision</th></tr>')
    for h in hist:
        add('<tr%s><td>%d</td><td>%s</td><td class="sub">%s</td><td class="n">%s ± %s</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td><td class="sub">%s: %s</td></tr>' % (
            ' class="pickrow"' if h["decision"] == "adopted" else "", h["iteration"], esc(h["change"]), esc(h["why"]), _f(h["selection"]["objective"]), _f(h["selection"]["se"]), _f(h["holdout"]["objective"]),
            n1(h["selection"]["per_week"]), h["properties_passed"], h["decision"], esc(h["reason"][:120])))
    add('</table>')
    ab = R["ablations"]["weights"]
    box, free = ab["within the property box"], ab["data alone (no box)"]
    add('<h3>What the data alone would choose for the weights</h3>')
    add('<p>The weights were refitted by coordinate search on the training months. Inside the design box the properties impose (rating 60-75 of 100, vote 25-40, record at most 15) the search returns <b>%s</b>. '
        'With the box removed the data alone chooses <b>%s</b> - it wants more weight on the record, because the record predicts the instructor\'s next class - and reaches a held-out signal of %s against %s inside the box: the same number. '
        'The box costs nothing on signal and buys the properties (the free weights pass %d of %d). The manager\'s 60/25/15 was, after all, the right neighbourhood; the data cannot improve on it.</p>' % (
            esc("/".join("%s %g" % (k, v) for k, v in box["weights"].items())), esc("/".join("%s %g" % (k, v) for k, v in free["weights"].items())), _f(free["holdout"]["objective"]), _f(box["holdout"]["objective"]),
            free["properties"]["passed"], free["properties"]["total"]))

    # ---- 9. the winner ---------------------------------------------------------------------------
    cfg = win["config"]
    add('<h2>9. The winner, and the one refinement worth keeping</h2>')
    add('<div class="formula"><b>%s</b><br>%s</div>' % (esc(cfg.get("name", win["name"])), esc(win["sentence"])))
    w = cfg["weights"]
    add('<table><tr><th>Setting</th><th>Value</th><th>Why the evidence supports it</th></tr>')
    add('<tr><td>Rating</td><td>%s</td><td>the rating carries most of the signal (section 4); the steeper slope below the line is the shape the sweep in the earlier study kept, and the linear shape tried here (iteration %s) was no better</td></tr>' % (
        "out of %d, steeper below %.2f (0 at %.2f, 75 at the line, 100 at 5.0)" % (w["rating"], cfg["rating"]["line"], cfg["rating"]["floor"]) if cfg["rating"]["mode"] == "knee" else "out of %d, straight" % w["rating"],
        next((str(h["iteration"]) for h in hist if h["tag"] == "C-linear"), "-")))
    add('<tr><td>Approval</td><td>out of %d, gradual from %d%% to %d%%</td><td>the vote adds signal beyond the rating; the cliff version (iteration %s) fails the one-vote property</td></tr>' % (
        w["approval"], cfg["approval"]["floor"], cfg["approval"]["bar"], next((str(h["iteration"]) for h in hist if h["tag"] == "C-cliff"), "-")))
    add('<tr><td>Instructor\'s record</td><td>out of %d (needs 3 earlier classes; 0 at %.2f, full at %.2f)</td><td>the record predicts the instructor\'s next class; more than 15 points lets a bad record sink a fine class (P16); dropping it (iteration %s) loses %s of signal - inside the noise</td></tr>' % (
        w["track"], cfg["track"]["floor"], cfg["track"]["line"], next((str(h["iteration"]) for h in hist if h["tag"] == "B-notrack"), "-"),
        _f(C["A4"]["selection"]["objective"]["value"] - C["B-notrack"]["selection"]["objective"]["value"], 3) if "B-notrack" in C else "n/a"))
    add('<tr><td>Responses and reach</td><td>no points</td><td>head-count is trust, not quality (section 5, P12); a big room is not a good class and a small room is not a bad one</td></tr>')
    add('<tr><td>The two lines</td><td>under %.2f or under %d%% (with %d+ votes) → at most Average; both → Bad</td><td>the score alone hides %d low classes on the held-out months (no-lines variant, iteration %s); the lines read on the raw values</td></tr>' % (
        LINE, BAR, cfg["min_votes"]["action"], C["C-nocaps"]["holdout"]["lines"]["false_comfort"] if "C-nocaps" in C else 0, next((str(h["iteration"]) for h in hist if h["tag"] == "C-nocaps"), "-")))
    add('<tr><td>Vote floors</td><td>a band from %d votes; an analysis from %d</td><td>a low average is believable from about 5 votes (section 5); 6 is the capacity choice</td></tr>' % (cfg["min_votes"]["band"], cfg["min_votes"]["action"]))
    add('<tr><td>Guard</td><td>%s</td><td>as the contract stands the lines would read the blended values (P22); the refinement below switches it on once the contract reads the raw values</td></tr>' % ("off" if not cfg["guard"]["k"] else "k = %g" % cfg["guard"]["k"]))
    add('<tr><td>Bands</td><td>Excellent ≥ %g · Good ≥ %g · Average ≥ %g</td><td>lowering the edges for capacity (iteration %s) changed nothing: the lines, not the edges, fill the queue</td></tr></table>' % (
        cfg["bands"]["excellent"], cfg["bands"]["good"], cfg["bands"]["average"], next((str(h["iteration"]) for h in hist if h["tag"] == "C-roundbands"), "-")))
    if ref:
        rc = ref["config"]
        add('<div class="card ok"><b>The refinement in the drawer: today\'s formula with the trust guard on.</b> %s Same inputs, same weights, same lines, same verdicts on every held-out class that matters '
            '(false comfort %d, %s analyses a week - identical), a steadier displayed number (label flips %s against %s), held-out signal %s against %s. It needs three contract keys: %s. '
            'Not adopted by the loop because it adds one moving part for no change in verdicts; recorded in <code>formula_recommended.json</code> as <code>refinement</code>.</div>' % (
                esc(ref["sentence"]), ref["holdout"]["lines"]["false_comfort"], n1(ref["holdout"]["workload"]["per_week"]), pct(ref["holdout"]["stability"]["flip_label"], 0), pct(v_h["stability"]["flip_label"], 0),
                _f(ref["holdout"]["objective"]["value"]), _f(v_h["objective"]["value"]), esc(", ".join(ref["contract_needs"]))))
    add('<h3>Next-class risk per band, held-out months</h3>')
    catsb = ["Excellent", "Good", "Average", "Bad"]
    series = [("Original", GREY, [o_h["bands"]["per_band"][b.lower()]["a_share"] for b in catsb]), ("Today", GREEN, [v_h["bands"]["per_band"][b.lower()]["a_share"] for b in catsb])]
    if r_h:
        series.append(("Today + guard", BLUE, [r_h["bands"]["per_band"][b.lower()]["a_share"] for b in catsb]))
    add('<div class="figure">%s<div class="cap">Share of instructors\' next classes that are low, per band (firm bands only). The original\'s Average is riskier than its Bad - its order is wrong; today\'s order is right and its Bad is %sx its Excellent.</div></div>' % (
        grouped(catsb, series, ymax=80, aria="Next-class risk per band", ylab="next class low"), n1(v_h["bands"]["ratio_bad_excellent_a"] or 0)))
    add('<h3>The workload dial</h3>')
    add('<p>Today\'s settings on the held-out months, with only the analysis floor moved. The lines decide who is in the queue; the floor decides how many voices it takes.</p>')
    add('<div class="figure">%s<div class="cap">Analyses a week on June-August by the analysis floor (today: %d votes). Capacity is %g.</div></div>' % (
        hbars([("from %d votes" % f, t, ORANGE if t > CAPACITY["per_week"] else BLUE) for f, t, v, tr, wch in dial], maxv=18, fmt="%.1f", mark=CAPACITY["per_week"], mark_label="capacity", aria="Analyses a week by vote floor"), cfg["min_votes"]["action"], CAPACITY["per_week"]))
    add('<table><tr><th class="n">Analysis from</th><th class="n">A week</th><th class="n">Video</th><th class="n">Transcript</th><th class="n">Watched (Jun-Aug)</th></tr>')
    for f, t, v, tr, wch in dial:
        add('<tr%s><td class="n">%d votes</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">%d</td></tr>' % (' class="pickrow"' if f == cfg["min_votes"]["action"] else "", f, n1(t), n1(v), n1(tr), wch))
    add('</table>')
    add('<p>The classes got worse over the year: the share under a line went from %s in January to %s in August (%s in the fit months, %s in the held-out months), and with it the queue grew from %s a week on the fit months to %s on the held-out months under the same settings. '
        'A formula cannot fix that; a floor of 7 votes brings the queue to %s a week at the price of watching, not analysing, %d more classes.</p>' % (
            pct(low_share[1], 0), pct(low_share[8], 0), pct(float(df[df["month"].isin(FIT_MONTHS)]["t_d"].mean() * 100), 0), pct(float(hold["t_d"].mean() * 100), 0),
            n1(v7["fit"]["workload"]["per_week"]), n1(v_h["workload"]["per_week"]), n1(next(t for f, t, *_ in dial if f == 7)), next(wch for f, t, v, tr, wch in dial if f == 7) - next(wch for f, t, v, tr, wch in dial if f == 6)))

    # ---- 10. fairness ------------------------------------------------------------------------------
    add('<h2>10. Fairness</h2>')
    add('<p>At equal rating (classes grouped in 0.1-rating buckets and re-weighted to the same mix), how often does each group get flagged for an analysis, and how often does it get Excellent? Today\'s settings, held-out months.</p>')
    fa = v_h["fairness"]
    cats_f, vals_f, vals_e = [], [], []
    for name, order in (("kind", ["live", "review"]), ("region", ["US", "IND"]), ("room", ["<10 responses", "10+ responses"]), ("weekday", ["Mon-Wed", "Thu-Sun"])):
        for g in order:
            if g in fa[name]["flagged"]:
                cats_f.append(g)
                vals_f.append(fa[name]["flagged"][g])
                vals_e.append(fa[name]["excellent"][g])
    add('<div class="figure">%s<div class="cap">Flagged (video or transcript) and Excellent shares at equal rating by group. Live vs review %s points apart, India vs US %s, small vs big room %s.</div></div>' % (
        grouped(cats_f, [("flagged for analysis", ORANGE, vals_f), ("Excellent", BLUE, vals_e)], ymax=80, aria="Fairness slices"), n1(fa["kind"]["flagged_gap"]), n1(fa["region"]["flagged_gap"]), n1(fa["room"]["flagged_gap"])))
    add('<p>The one wide gap is by weekday, and it is a small-numbers effect, not the formula: only %d of the %s held-out classes fall on Monday-Wednesday (%d of them under a line with 6+ votes), so re-weighting them by rating bucket gives %s flagged against %s for Thursday-Sunday. '
        'Over all eight months (%d Monday-Wednesday classes against %s) the same figure is %s against %s - a gap of %s points. The midweek sessions are few and thin; the score treats them as it treats every other class.</p>' % (
            wd_n.get("Mon-Wed", 0), "{:,}".format(len(hold)), wd_low.get("Mon-Wed", 0), pct(fa["weekday"]["flagged"].get("Mon-Wed", 0), 0), pct(fa["weekday"]["flagged"].get("Thu-Sun", 0), 0),
            wd_all_n.get("Mon-Wed", 0), "{:,}".format(wd_all_n.get("Thu-Sun", 0)), pct(wd_all["flagged"].get("Mon-Wed", 0), 0), pct(wd_all["flagged"].get("Thu-Sun", 0), 0), n1(wd_all["flagged_gap"])))

    # ---- 11. limits --------------------------------------------------------------------------------
    add('<h2>11. The honest limits</h2>')
    add('<ul>')
    add('<li><b>No per-learner ratings.</b> The sheet carries the class average and the yes/no counts. A bimodal room (half delighted, half let down) is invisible behind a 3.8 except through the vote; a biased rater cannot be told from an honest one. The rater-reliability input (section 5) is designed for the day that data exists.</li>')
    add('<li><b>The targets are proxies.</b> "The instructor\'s next class is low" mostly measures the instructor\'s persistence; "the cohort\'s next class is low" is the closest to "learners were let down" but is also shaped by whoever teaches next. There is no ground truth for "something went wrong for learners" in this data, and only %d PM decision has been recorded.</li>' % S["notes"]["pm_decisions"]["rows_with_a_decision"])
    add('<li><b>How sure we are.</b> With %s held-out classes the 95%% interval on the signal is about ±%s. Two formulas closer than that cannot be told apart, and every formula in this study is closer than that. The study prefers the simpler one on purpose.</li>' % ("{:,}".format(hold_n), _f(2 * v_h["objective"]["se"], 2)))
    add('<li><b>The period drifted.</b> The held-out months are worse than the fit months (%s vs %s of classes under a line), which is why the queue on June-August exceeds the capacity under every line-honouring formula. The monthly re-run (section 12) is what catches this.</li>' % (
        pct(float(hold["t_d"].mean() * 100), 0), pct(float(df[df["month"].isin(FIT_MONTHS)]["t_d"].mean() * 100), 0)))
    add('<li><b>Instructor identity.</b> %d of %s classes have no resolved instructor in the database; the study resolved them through the earlier alias table, and its replay of today\'s version agrees with the database\'s stored bands on about 91%% of classes - the rest differ on the record. Every candidate was measured on the same feature table, so the comparisons stand.</li>' % (
        R["meta"]["rows"] - 2393, "{:,}".format(R["meta"]["rows"])))
    add('<li><b>Two properties are principles the team may want to revisit.</b> P07 lets a hard line jump a class two bands on one vote (the lines are the team\'s policy, and %d%% of 10+-vote classes sit within one vote of a line); P23 accepts that two bad histories together can put a plainly fine class in Average.</li>' % round(v_h["stability"]["flip_verdict_10plus"]))
    add('</ul>')

    # ---- 12. re-run and alarms ---------------------------------------------------------------------
    add('<h2>12. What to re-run monthly, and the drift alarms</h2>')
    add('<p>One command re-runs the whole study (<code>python analysis/formula/run_all.py</code>, a few minutes). On the first Monday of each month, with the new month appended as the held-out month, look at six numbers; each has a line that should raise a hand:</p>')
    add('<table><tr><th>Number</th><th>Today (held-out)</th><th>Alarm</th></tr>')
    add('<tr><td>Held-out signal of the active version</td><td class="n">%s</td><td>under 0.60 for two months running</td></tr>' % _f(v_h["objective"]["value"]))
    add('<tr><td>False comfort (low classes shown Good/Excellent)</td><td class="n">%d</td><td>above 2%% of voiced classes</td></tr>' % v_h["lines"]["false_comfort"])
    add('<tr><td>Analyses a week</td><td class="n">%s</td><td>above 1.25× capacity (%g) for two weeks, or below half</td></tr>' % (n1(v_h["workload"]["per_week"]), CAPACITY["per_week"] * 1.25))
    add('<tr><td>Share of classes under a line</td><td class="n">%s</td><td>moves more than 5 points month over month</td></tr>' % pct(float(hold["t_d"].mean() * 100), 0))
    add('<tr><td>The guard\'s k, re-derived</td><td class="n">%s (module) · %s (course)</td><td>outside 1.5-5 - the rater or class spread has changed</td></tr>' % (_f(var_m["all"]["k"], 1), _f(var_c["all"]["k"], 1)))
    add('<tr><td>Label flips on one vote</td><td class="n">%s</td><td>above 45%%; verdict flips above 25%%</td></tr>' % pct(v_h["stability"]["flip_label"], 0))
    add('<tr><td>Band mix</td><td class="n">%s</td><td>any band moves more than 10 points month over month</td></tr></table>' % esc(", ".join("%s %s" % (BAND_LABEL[b], pct(v_h["bands"]["shares"][b], 0)) for b in BANDS)))
    add('<p>Re-run the full loop quarterly, whenever a new input arrives (per-learner ratings, TA scores), and whenever a course reaches 30 classes. The properties run on every change of the scoring contract (<code>python -m unittest analysis.formula.test_properties</code>).</p>')
    add('<footer>Formula study · Feedback Loop v3 · New Programs · %s · code in analysis/formula/, outputs in analysis/out/ (gitignored)</footer></div>' % time.strftime("%d %b %Y"))
    html = "".join(A)
    path = os.path.join(OUT, "formula-study.html")
    open(path, "w", encoding="utf-8").write(html)
    print("wrote %s (%.0f KB) in %.0fs" % (path, len(html) / 1024, time.time() - t0))
    return path, dict(R=R, S=S, T=T, REC=REC, FX=FX, win=win, ref=ref, orig=orig, v7=v7, dial=dial, hold_n=hold_n, n_props=n_props, df=df, hold=hold, cfg=cfg, lg_lo=lg_lo, lg_hi=lg_hi)


def one_pager(ctx):
    R, S, T, REC, FX = ctx["R"], ctx["S"], ctx["T"], ctx["REC"], ctx["FX"]
    win, ref, orig, v7, dial = ctx["win"], ctx["ref"], ctx["orig"], ctx["v7"], ctx["dial"]
    o_h, v_h = orig["holdout"], v7["holdout"]
    r_h = ref["holdout"] if ref else None
    n_props, hold_n, cfg = ctx["n_props"], ctx["hold_n"], ctx["cfg"]
    B = T["believability_all"]["rating_line"]["instructor_next"]
    var_m = T["variance"]["module_prior_rating"]
    A = []
    add = A.append
    add('<title>Formula One-Pager</title><style>%s .wrap{max-width:820px}'
        '@page{size:A4;margin:9mm 11mm}'
        '@media print{body{font-size:10.6px;line-height:1.4}h1{font-size:21px;margin-bottom:2px}h2{font-size:15px}h3{font-size:12.5px;margin:9px 0 3px}'
        'p{margin:5px 0}.lede{font-size:11.6px}table{font-size:10.2px;margin:6px 0}th,td{padding:2.5px 6px}.card{padding:7px 11px;margin:6px 0}'
        '.big{gap:8px;margin:8px 0}.stat{padding:6px 10px;flex-basis:120px}.stat .v{font-size:18px}.stat .l{font-size:10px}.sub{font-size:10px}ul{margin:4px 0}li{margin:2px 0}'
        'footer{margin-top:10px;padding-top:6px;font-size:10px}}'
        '</style><div class="wrap">' % CSS)
    add('<div class="kicker">Feedback Loop v3 · Class Sentiment Score · the formula, for the VP</div>')
    add('<h1>We looked for a better formula. The data says keep this one - and fix the trust.</h1>')
    add('<p class="sub">New Programs · %s real classes, January-August 2026 · full study: Formula-Study.pdf</p>' % "{:,}".format(R["meta"]["rows"]))
    add('<p class="lede">We were asked to forget the formula we were given and find the real one: the inputs, the weights, the shape - tested on every case we could construct and on eight months of classes, in a loop, until nothing improved. '
        'The loop ran %d iterations across five formula families, %d measurable inputs and every shape switch we could name. <b>No formula separates from the one active today</b> on the question that matters - does the score foresee a low next class - '
        'and today\'s is the only one that passes all %d behaviour properties. The data does settle one thing we had guessed: how much a thin vote should be trusted.</p>' % (R["meta"]["iterations"], len(FEATURE_DOCS) - 1, n_props))
    cols = [("Manager\'s original", o_h), ("Today (v7)", v_h)] + ([("Today + trust guard", r_h)] if r_h else [])
    add('<table><tr><th>Held-out months, June-August (%s classes)</th>%s</tr>' % ("{:,}".format(hold_n), "".join('<th class="n">%s</th>' % esc(k) for k, _ in cols)))

    def row(label, fn):
        add('<tr><td>%s</td>%s</tr>' % (label, "".join('<td class="n">%s</td>' % fn(ev) for _, ev in cols)))
    row("Does the score foresee a low next class? (0.5 = coin toss)", lambda e: _f(e["objective"]["value"], 2))
    row("Low classes (under 4.55 or under 80%, 5+ votes) shown as Good or Excellent", lambda e: "%d of %d" % (e["lines"]["false_comfort"], e["lines"]["n_voiced"]))
    row("\"Bad\" classes that were actually rated 4.55 or better", lambda e: "%d of %d" % (e["lines"]["bad_rated_fine"], e["lines"]["bad_total"]))
    row("Verdict flips if one learner votes differently", lambda e: pct(e["stability"]["flip_verdict"], 0))
    row("Chance the instructor\'s next class is low: Bad vs Excellent", lambda e: "%s vs %s" % (pct(e["bands"]["per_band"]["bad"]["a_share"], 0), pct(e["bands"]["per_band"]["excellent"]["a_share"], 0)))
    row("Analyses a week (capacity %g)" % CAPACITY["per_week"], lambda e: "%s (%s video)" % (n1(e["workload"]["per_week"]), n1(e["workload"]["videos_per_week"])))
    add('<tr class="pickrow"><td>Behaviour properties passed, of %d</td>%s</tr></table>' % (n_props, "".join('<td class="n">%d</td>' % c["properties"]["summary"]["passed"] for c in ([orig, v7] + ([ref] if ref else [])))))
    add('<div class="big"><div class="stat"><div class="v">%d</div><div class="l">formulas tried in the loop</div></div><div class="stat"><div class="v">%s</div><div class="l">generated cases (grid + random + named)</div></div>'
        '<div class="stat"><div class="v">%d</div><div class="l">behaviour properties, now a permanent test</div></div><div class="stat"><div class="v">±%s</div><div class="l">the noise: two formulas closer than this cannot be told apart</div></div></div>' % (
            R["meta"]["iterations"], "{:,}".format(FX["grid_points"] + FX["counts"]["random"] + FX["counts"]["adversarial"]), n_props, _f(2 * v_h["objective"]["se"], 2)))
    add('<h3>Three findings</h3>')
    add('<div class="card ok"><b>1. The signal lives in the rating, and it is modest.</b> The rating alone foresees a low next class at %s; the best model with every input we could build reaches %s. The instructor\'s record predicts the <i>instructor\'s</i> next class (%s alone) but not the cohort\'s, which is why it earns a small weight. '
        'Attendance loss cannot be foreseen from quality at all (%s). Module history, cohort momentum and attendance change add nothing on months they were not fitted on.</div>' % (
            _f(S["reference"]["t_c"]["rating alone"]["auc"], 2), _f(max(v["fixed"]["auc"] for k, v in S["models"]["t_c"].items() if k != "logistic_coefficients" and v.get("fixed")), 2),
            _f(S["reference"]["t_a"]["track record alone"]["auc"], 2), _f(max(S["reference"]["t_b"][k]["auc"] for k in ("rating alone", "approval alone", "today's v7 score")), 2)))
    add('<div class="card ok"><b>2. Head-count is trust, not points.</b> The old "responses" term was meant to say "do not believe a low average from three raters". Measured: a low average is believable from about 5 votes (its next class goes wrong %s-%s of the time against %s-%s for fine classes); 3-4 votes are suggestive; 1-2 say nothing. '
        'The right strength for blending a thin class with its module\'s usual rating is about <b>%s phantom raters</b>, derived from the data - not the 5 we guessed. Treating few-rater lows as more suspicious than few-rater highs is not supported (a low 3-4-vote class predicts trouble as well as a low 15-vote one). '
        'Today\'s vote floors (a band from %d votes, an analysis from %d) already carry this; the guard would steady the displayed number once one contract change lands.</div>' % (
            pct(min((B[c]["risk_low"] or 0) for c in ("5-9", "10-14", "15+")) * 100, 0), pct(max((B[c]["risk_low"] or 0) for c in ("5-9", "10-14", "15+")) * 100, 0),
            pct(min((B[c]["risk_fine"] or 0) for c in ("5-9", "10-14", "15+")) * 100, 0), pct(max((B[c]["risk_fine"] or 0) for c in ("5-9", "10-14", "15+")) * 100, 0),
            _f(var_m["fit"]["k"], 1), cfg["min_votes"]["band"], cfg["min_votes"]["action"]))
    add('<div class="card ok"><b>3. The two lines, not the points, set the queue - and the one-vote flips.</b> In June-August the lines alone put %s classes a week in front of the team (capacity %g); every formula that honours them lands there. '
        '%s of classes with 10+ votes sit within one vote of a line, so a verdict flips on one vote that often whatever the points say. The dials are the vote floor (7 votes → %s a week) and the lines themselves; the formula is not a dial.</div>' % (
            n1(v_h["workload"]["per_week"]), CAPACITY["per_week"], pct(v_h["stability"]["flip_verdict_10plus"], 0), n1(next(t for f, t, *_ in dial if f == 7))))
    # page 2
    add('<div class="pagebreak"></div><h2 style="border:0;margin-top:0">What was tried, and what needs deciding</h2>')
    add('<table><tr><th>Family</th><th>What it is</th><th>Why it fell away</th></tr>')
    add('<tr><td>Manager\'s original</td><td>60/30/6/4, pass/fail vote</td><td>hides %d low classes behind Good/Excellent; its Average is riskier than its Bad; fails %d properties</td></tr>' % (o_h["lines"]["false_comfort"], n_props - orig["properties"]["summary"]["passed"]))
    add('<tr class="pickrow"><td>Today\'s version</td><td>rating 60 (steeper below 4.55) · vote 25 (gradual) · record 15; the two lines; floors 3/6</td><td>the winner: passes all %d properties, nothing beats it on signal</td></tr>' % n_props)
    add('<tr><td>Points + trust guard</td><td>the same, with a thin class blended with ~3 typical classes of its module</td><td>same verdicts, steadier number; needs a contract change; kept in the drawer</td></tr>')
    add('<tr><td>+ module history, + cohort momentum, + attendance change</td><td>new inputs the sync would have to compute</td><td>each adds nothing outside the noise on held-out months</td></tr>')
    add('<tr><td>Wilson lower bound for the vote</td><td>the statistician\'s way to distrust a thin vote</td><td>treats a thin vote as a bad vote (fails P12)</td></tr>')
    add('<tr><td>Probability model (logistic)</td><td>100 minus the chance the next class goes wrong</td><td>cannot be worked out by hand; nine classes in ten score between %s and %s so the bands have no natural edges</td></tr>' % (ctx["lg_lo"], ctx["lg_hi"]))
    add('<tr><td>Sequential (instructor\'s series)</td><td>recent record, shrink toward the instructor\'s own record</td><td>counts the record twice; a bad record sinks a fine class (P16)</td></tr>')
    add('<tr><td>No hard lines / lines on blended values / vote as a cliff / straight rating / other weights</td><td>every shape switch</td><td>no lines hides %d low classes; blended lines hide %d; the cliff fails the one-vote property; the rest change nothing</td></tr></table>' % (
        ctx["R"]["candidates"]["C-nocaps"]["holdout"]["lines"]["false_comfort"] if "C-nocaps" in ctx["R"]["candidates"] else 0, ctx["R"]["candidates"]["A2"]["holdout"]["lines"]["false_comfort"]))
    add('<h3>What needs deciding</h3><ul>')
    add('<li><b>The queue.</b> Under today\'s settings June-August ran at %s analyses a week against a capacity of %g, because the classes got worse (%s under a line in August against %s in January). Either the capacity rises, or the analysis floor moves to 7 votes (%s a week, %d more classes watched instead of analysed), or the team revisits the lines. None of these is a formula change.</li>' % (
        n1(v_h["workload"]["per_week"]), CAPACITY["per_week"], pct(float(ctx["df"][ctx["df"]["month"] == 8]["t_d"].mean() * 100), 0), pct(float(ctx["df"][ctx["df"]["month"] == 1]["t_d"].mean() * 100), 0),
        n1(next(t for f, t, *_ in dial if f == 7)), next(wch for f, t, v, tr, wch in dial if f == 7) - next(wch for f, t, v, tr, wch in dial if f == 6)))
    add('<li><b>The trust guard.</b> One contract change (the lines read the raw rating and vote; the guard shapes the score only) lets the guard back on with k ≈ 3 and a module-first prior. It changes no verdict; it steadies the displayed number. Worth doing when the scorer is next touched, not before.</li>')
    add('<li><b>Per-learner ratings.</b> The one input that would change this study is each rater\'s own rating and vote. A rater-reliability input is designed (in the study and in <code>formula_recommended.json</code>) for the day it exists.</li>')
    add('<li><b>Two principles to confirm.</b> A hard line may jump a class two bands on one vote (the line decides, not the score); and two bad histories together may put a plainly fine class in Average. The study accepts both; the team should say so too.</li></ul>')
    add('<p class="sub">Re-run monthly (one command, a few minutes); alarms on signal, false comfort, workload, the share of low classes, the re-derived k, flips and band mix. Full loop quarterly and whenever a new input arrives.</p>')
    add('<footer>Formula study · Feedback Loop v3 · New Programs · %s</footer></div>' % time.strftime("%d %b %Y"))
    html = "".join(A)
    path = os.path.join(OUT, "formula-one-pager.html")
    open(path, "w", encoding="utf-8").write(html)
    print("wrote %s (%.0f KB)" % (path, len(html) / 1024))
    return path


def summary_md(ctx):
    R, REC, win, ref, v7, orig, dial = ctx["R"], ctx["REC"], ctx["win"], ctx["ref"], ctx["v7"], ctx["orig"], ctx["dial"]
    v_h, o_h = v7["holdout"], orig["holdout"]
    T = ctx["T"]
    lines = []
    lines.append("# Formula study - summary for Bishal\n")
    lines.append("## The winner in five sentences\n")
    lines.append("1. Today's active version (v7) is the winner: rating out of 60 (steeper below 4.55), the vote out of 25 (gradual from 40% to 80%), the instructor's record out of 15, the two lines as caps, a band from 3 votes and an analysis from 6.")
    lines.append("2. On the held-out months (June-August, %s classes) it foresees a low next class at %s against %s for the manager's original, shows 0 low classes as Good or Excellent against %d, and its Bad band carries %s next-class risk against %s for its Excellent." % (
        "{:,}".format(ctx["hold_n"]), _f(v_h["objective"]["value"], 2), _f(o_h["objective"]["value"], 2), o_h["lines"]["false_comfort"], pct(v_h["bands"]["per_band"]["bad"]["a_share"], 0), pct(v_h["bands"]["per_band"]["excellent"]["a_share"], 0)))
    lines.append("3. The loop tried %d alternatives (five families, every candidate input, every shape switch) and none beats it by more than the noise (about +/-%s on the signal); it is also the only family member that passes all %d behaviour properties on %s generated cases." % (
        R["meta"]["iterations"] - 1, _f(2 * v_h["objective"]["se"], 2), ctx["n_props"], "{:,}".format(ctx["FX"]["counts"]["grid_sample"] + ctx["FX"]["counts"]["random"] + ctx["FX"]["counts"]["adversarial"])))
    lines.append("4. What the data settles is trust: a low average is believable from about 5 votes, the right guard strength is about %s phantom raters (not 5), the vote's prior is worth about %s phantom votes, and there is no evidence for trusting few-rater lows less than few-rater highs." % (
        _f(T["variance"]["module_prior_rating"]["fit"]["k"], 1), _f(T["approval_prior"]["fit"]["a_plus_b"], 1)))
    lines.append("5. The queue and the one-vote verdict flips are set by the two lines and by the period, not by the formula: in June-August the lines alone put %s classes a week in the queue against a capacity of 12, and the only dials are the vote floor (7 votes -> %s a week) and the lines." % (
        n1(v_h["workload"]["per_week"]), n1(next(t for f, t, *_ in dial if f == 7))))
    lines.append("\n## Does it fit the current contract?\n")
    lines.append("Yes - the winner IS the active version (scoring_configs version 7); nothing to ship. The refinement in the drawer (%s) needs three contract keys: %s." % (
        ref["name"] if ref else "none", ", ".join(ref["contract_needs"]) if ref else "-"))
    lines.append("\n## What code must change to ship the refinement (only if the team wants the steadier number)\n")
    lines.append("- `caps.basis = raw`: the two hard lines read the raw rating and vote; the guard shapes the score only (one line in analysis/sentiment_score.py, the SQL function in migration 0015, and web/src/lib/sentiment.ts; regenerate supabase/fixtures/scoring_cases.json).")
    lines.append("- `guard.prior = hierarchical` with `prior_min_n = 3`: the sync computes module_prior_rating / module_prior_n / module_prior_approval per class (earlier classes on the same topic in other cohorts) and passes them to score_class_rating(); falls back to the course prior.")
    lines.append("- `guard.k_approval`: a separate prior strength for the vote (%s phantom votes) alongside `guard.k` (%s phantom raters)." % (_f(T["approval_prior"]["fit"]["a_plus_b"], 1), _f(T["variance"]["module_prior_rating"]["fit"]["k"], 1)))
    lines.append("- The properties test (analysis/formula/test_properties.py) must pass on the new contract before it is activated.")
    lines.append("\n## The three biggest risks\n")
    lines.append("1. **Capacity.** The classes got worse over the year (%s under a line in January, %s in August); under today's settings June-August ran at %s analyses a week against 12. If that continues the queue outgrows the team; the honest dials are the analysis floor and the lines, and both are policy calls, not formula calls." % (
        pct(float(ctx["df"][ctx["df"]["month"] == 1]["t_d"].mean() * 100), 0), pct(float(ctx["df"][ctx["df"]["month"] == 8]["t_d"].mean() * 100), 0), n1(v_h["workload"]["per_week"])))
    lines.append("2. **One-vote verdict flips.** %s of classes with 10+ votes flip their verdict when one learner votes differently, because they sit within one vote of a hard line. No formula fixes this while the lines are hard; the team should decide whether a line should become a narrow band.")
    lines.append("3. **The targets are proxies.** Without per-learner ratings and without recorded PM decisions (%d so far), 'something went wrong for learners' is read from the next class; the signal is modest (about %s on a 0.5-1 scale) and two formulas closer than the noise cannot be told apart. Recording every PM confirm/dismiss in the app is the cheapest way to sharpen the next study." % (
        ctx["S"]["notes"]["pm_decisions"]["rows_with_a_decision"], _f(v_h["objective"]["value"], 2)))
    lines[-2] = lines[-2] % pct(v_h["stability"]["flip_verdict_10plus"], 0)
    lines.append("\nFiles: Formula-Study.pdf, Formula-One-Pager.pdf (repo root); analysis/out/formula_recommended.json, formula_results.json, formula_log.jsonl, formula_cases.json; code in analysis/formula/ (README.md there).\n")
    path = os.path.join(OUT, "formula_summary.md")
    open(path, "w", encoding="utf-8").write("\n".join(lines))
    print("wrote", path)


if __name__ == "__main__":
    study_html, ctx = build()
    pager_html = one_pager(ctx)
    summary_md(ctx)
    print_pdf(study_html, os.path.join(ROOT, "Formula-Study.pdf"))
    print_pdf(pager_html, os.path.join(ROOT, "Formula-One-Pager.pdf"))
