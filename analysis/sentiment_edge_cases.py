"""The 44 synthetic edge cases the data lacks (plan 4e), each with the outcome the plan expects
under C5 and the switch that controls it. Scored under every candidate; for C5 the plan's
expectation is compared with what the contract actually does, and every difference is a finding.

Outputs analysis/out/edge_cases.csv (case x candidate) and edge_cases.json. The permanent unit
test lives in analysis/test_sentiment_score.py and asserts the CONTRACT's behaviour as it is.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sentiment_score import CONFIGS, score, reason  # noqa: E402
from sentiment_common import OUT, BAND_LABEL, write_csv, write_json  # noqa: E402

P = {"prior_rating": 4.7, "prior_approval": 93}          # a typical course prior (the guard's anchor)


def case(cid, label, inputs, switch, band, action, provisional=False, note="", flags=()):
    """band/action/provisional = what the PLAN expects under C5 (band None = no band)."""
    inp = {"rating": None, "num_ratings": None, "attended": None, "yes_votes": None, "no_votes": None, "escalated": False,
           "track_avg": None, **P}
    inp.update(inputs)
    return {"id": cid, "label": label, "inputs": inp, "switch": switch,
            "plan": {"band": band, "action": action, "provisional": provisional, "flags": list(flags)}, "note": note}


CASES = [
    # --- empty rooms, single voices ------------------------------------------------------------
    case("E01", "nobody attended", {"rating": 4.5, "num_ratings": 0, "attended": 0, "yes_votes": 0, "no_votes": 0},
         "min_votes.band", None, "watch", note="no voices at all: no band, watch", flags=("zero_responses", "no_attendance", "no_vote")),
    case("E02", "one attendee, rated 5.0", {"rating": 5.0, "num_ratings": 1, "attended": 1, "yes_votes": 1, "no_votes": 0},
         "min_votes.band", None, "watch", note="one voice is not a verdict"),
    case("E03", "one attendee, rated 1.0, said no", {"rating": 1.0, "num_ratings": 1, "attended": 1, "yes_votes": 0, "no_votes": 1},
         "min_votes.band", None, "watch", note="one furious voice still gets no band; a PM can escalate"),
    case("E04", "200-person webinar, 5 happy raters", {"rating": 4.9, "num_ratings": 5, "attended": 200, "yes_votes": 5, "no_votes": 0},
         "reach.mode=off", "excellent", "none", note="reach is off: thin turnout is not a penalty"),
    case("E05", "big room says no: 40 of 100 yes", {"rating": 4.6, "num_ratings": 100, "attended": 200, "yes_votes": 40, "no_votes": 60},
         "approval graded + caps", "bad", "video", note="approval 40% with 100 votes: the guard cannot help; score under 60 -> Bad",
         flags=("under_approval_bar",)),
    # --- missing or contradictory votes ---------------------------------------------------------
    case("E06", "ratings but no vote at all", {"rating": 4.2, "num_ratings": 10, "attended": 20},
         "missing.approval=neutral + caps.rating_line", "average", "transcript", note="no vote is neutral; the rating line still applies",
         flags=("no_vote", "under_rating_line")),
    case("E07", "everyone says no, high rating", {"rating": 4.9, "num_ratings": 10, "attended": 10, "yes_votes": 0, "no_votes": 10},
         "caps.approval_bar", "average", "transcript", note="flagged: rating and vote disagree; one line missed -> Average",
         flags=("rating_vote_disagree", "under_approval_bar")),
    case("E08", "more raters than attendees", {"rating": 4.6, "num_ratings": 25, "attended": 20, "yes_votes": 25, "no_votes": 0},
         "reach clamp", "good", "none", note="kept and flagged, not dropped", flags=("reach_clamped",)),
    case("E09", "rated 1.0 but loved (10 of 10)", {"rating": 1.0, "num_ratings": 10, "attended": 10, "yes_votes": 10, "no_votes": 0},
         "caps.rating_line + rating knee", "bad", "video", note="a 1.0 can never hide behind approval", flags=("under_rating_line",)),
    case("E10", "rated 5.0 but rejected (0 of 10)", {"rating": 5.0, "num_ratings": 10, "attended": 10, "yes_votes": 0, "no_votes": 10},
         "caps.approval_bar", "average", "transcript", note="one line missed -> Average (transcript), flagged",
         flags=("rating_vote_disagree", "under_approval_bar")),
    # --- missing inputs, nonsense --------------------------------------------------------------
    case("E11", "rating missing", {"num_ratings": 5, "attended": 10, "yes_votes": 5, "no_votes": 0},
         "reject: no_rating", None, "watch", note="no score, watch", flags=("no_rating",)),
    case("E12", "attendance missing", {"rating": 4.7, "num_ratings": 12, "attended": None, "yes_votes": 12, "no_votes": 0},
         "missing.reach=neutral", "good", "none", note="attendance missing is neutral (4.7 with no track record = 88.2, Good)", flags=("no_attendance",)),
    case("E13", "negative responses", {"rating": 4.6, "num_ratings": -3, "attended": 20, "yes_votes": 0, "no_votes": 0},
         "reject: invalid", None, "watch", note="rejected outright", flags=("invalid_num_ratings",)),
    case("E14", "rating above the scale (7)", {"rating": 7, "num_ratings": 5, "attended": 5, "yes_votes": 5, "no_votes": 0},
         "reject: invalid", None, "watch", note="rejected outright", flags=("invalid_rating",)),
    case("E15", "blank instructor (no track record)", {"rating": 4.7, "num_ratings": 12, "attended": 20, "yes_votes": 11, "no_votes": 1},
         "missing.track=neutral", "good", "none", note="no track record is neutral, never a penalty", flags=("no_track",)),
    case("E16", "duplicate session row (same inputs twice)", {"rating": 4.7, "num_ratings": 12, "attended": 20, "yes_votes": 11, "no_votes": 1},
         "determinism", "good", "none", note="the scorer is deterministic; duplicates are removed by the loader"),
    # --- cohorts of three, the approval bar -----------------------------------------------------
    case("E17", "cohort of 3, all yes", {"rating": 4.9, "num_ratings": 3, "attended": 3, "yes_votes": 3, "no_votes": 0},
         "min_votes.action", "excellent", "watch", True, note="a band is shown, marked provisional; no analysis"),
    case("E18", "cohort of 3, one no (the famous 4.87)", {"rating": 4.87, "num_ratings": 3, "attended": 20, "yes_votes": 2, "no_votes": 1},
         "guard.k + min_votes.action", "excellent", "watch", True, note="was Bad -> video under C0; guarded, provisional Excellent, watch"),
    case("E19", "approval exactly 80.00: 4 of 5", {"rating": 4.7, "num_ratings": 5, "attended": 10, "yes_votes": 4, "no_votes": 1},
         "approval.bar inclusive", "good", "none", note="80.00 clears the bar"),
    case("E20", "approval exactly 80.00: 8 of 10", {"rating": 4.7, "num_ratings": 10, "attended": 10, "yes_votes": 8, "no_votes": 2},
         "approval.bar inclusive", "good", "none"),
    case("E21", "approval exactly 80.00: 12 of 15", {"rating": 4.7, "num_ratings": 15, "attended": 15, "yes_votes": 12, "no_votes": 3},
         "approval.bar inclusive", "good", "none"),
    case("E22", "approval 79.99 with a huge sample", {"rating": 4.7, "num_ratings": 10000, "attended": 10000, "yes_votes": 7999, "no_votes": 2001},
         "caps.approval_bar", "average", "transcript", note="the guard cannot lift a big sample; one line missed", flags=("under_approval_bar",)),
    case("E23", "3 of 4 yes (guard passes, but only 4 voices)", {"rating": 4.7, "num_ratings": 4, "attended": 10, "yes_votes": 3, "no_votes": 1},
         "guard.k + min_votes.action", "good", "watch", True, note="guarded approval 85%: passes; provisional because 4 < 5"),
    case("E24", "7 of 9 yes (guard passes)", {"rating": 4.7, "num_ratings": 9, "attended": 12, "yes_votes": 7, "no_votes": 2},
         "guard.k", "good", "none", note="raw 77.8%, guarded 83.2%: passes the bar"),
    case("E25", "15 of 20 yes (guard does not pass)", {"rating": 4.7, "num_ratings": 20, "attended": 25, "yes_votes": 15, "no_votes": 5},
         "guard.k + caps.approval_bar", "average", "transcript", note="raw 75%, guarded 78.6%: still under the bar", flags=("under_approval_bar",)),
    # --- band edges (priors set equal to the class so the guard is neutral) ---------------------
    case("E26", "score exactly 90.00 -> Excellent", {"rating": 4.7, "num_ratings": 10, "attended": 20, "yes_votes": 10, "no_votes": 0,
                                                     "track_avg": 4.55, "prior_rating": 4.7, "prior_approval": 100},
         "bands.excellent", "excellent", "none", note="rating 4.70 -> 83.33 x 0.6 + 25 + 15 = 90.00"),
    case("E27", "just under 90 -> Good", {"rating": 4.69, "num_ratings": 10, "attended": 20, "yes_votes": 10, "no_votes": 0,
                                          "track_avg": 4.55, "prior_rating": 4.69, "prior_approval": 100},
         "bands.excellent", "good", "none"),
    case("E28", "score exactly 75.00 -> Good", {"rating": 4.7, "num_ratings": 10, "attended": 20, "yes_votes": 10, "no_votes": 0,
                                                "track_avg": 4.05, "prior_rating": 4.7, "prior_approval": 100},
         "bands.good", "good", "none", note="a track record at its floor (4.05) gives 0 of 15"),
    case("E29", "just under 75 -> Average", {"rating": 4.69, "num_ratings": 10, "attended": 20, "yes_votes": 10, "no_votes": 0,
                                             "track_avg": 4.05, "prior_rating": 4.69, "prior_approval": 100},
         "bands.good", "average", "transcript", note="Average by score alone, both lines cleared"),
    case("E30", "score exactly 60.00 -> Average", {"rating": 4.327777777777778, "num_ratings": 10, "attended": 20, "yes_votes": 10, "no_votes": 0,
                                                   "track_avg": 4.05, "prior_rating": 4.327777777777778, "prior_approval": 100},
         "bands.average", "average", "transcript", note="under the line too, so capped at Average either way", flags=("under_rating_line",)),
    case("E31", "just under 60 -> Bad", {"rating": 4.32, "num_ratings": 10, "attended": 20, "yes_votes": 10, "no_votes": 0,
                                         "track_avg": 4.05, "prior_rating": 4.32, "prior_approval": 100},
         "bands.average", "bad", "video", flags=("under_rating_line",)),
    # --- targets, history, escalation, kinds ---------------------------------------------------
    case("E32", "responses exactly at the target (10)", {"rating": 4.7, "num_ratings": 10, "attended": 20, "yes_votes": 10, "no_votes": 0},
         "sample.target (off under C5)", "good", "none", note="under C0 the cliff is met at 10; under C5 responses are not scored (4.7, no track = 88.2, Good)"),
    case("E33", "an instructor's first class", {"rating": 4.7, "num_ratings": 12, "attended": 20, "yes_votes": 11, "no_votes": 1, "track_avg": None},
         "missing.track=neutral", "good", "none", flags=("no_track",)),
    case("E34", "bad track record, fine class", {"rating": 4.7, "num_ratings": 12, "attended": 20, "yes_votes": 11, "no_votes": 1, "track_avg": 4.0},
         "track.mode", "good", "none", note="Good, not Excellent: the history costs 15 points"),
    case("E35", "PM escalation on a fine class", {"rating": 4.9, "num_ratings": 10, "attended": 10, "yes_votes": 10, "no_votes": 0, "escalated": True},
         "escalated", "excellent", "video", note="video whatever the band", flags=("escalated",)),
    case("E36", "test review, 8 of 15 rated", {"rating": 4.8, "num_ratings": 8, "attended": 15, "yes_votes": 8, "no_votes": 0},
         "sample.mode=off + reach.mode=off", "excellent", "none", note="not penalised for the smaller room"),
    case("E37", "two same-day sessions, second one weak", {"rating": 4.3, "num_ratings": 12, "attended": 20, "yes_votes": 12, "no_votes": 0},
         "independent rows", "average", "transcript", note="each session is scored on its own", flags=("under_rating_line",)),
    case("E38", "votes do not add up to responses (9 votes, 12 ratings)", {"rating": 4.7, "num_ratings": 12, "attended": 20, "yes_votes": 5, "no_votes": 4},
         "votes_ne_responses + caps", "average", "transcript", note="flagged; the votes decide approval (55.6%)", flags=("votes_ne_responses", "under_approval_bar")),
    case("E39", "brand-new course (no prior)", {"rating": 4.87, "num_ratings": 3, "attended": 20, "yes_votes": 2, "no_votes": 1, "prior_rating": None, "prior_approval": None},
         "guard.prior missing", "good", "watch", True, note="no prior -> no guard, raw values, still provisional"),
    case("E40", "a source with no vote column, fine rating", {"rating": 4.8, "num_ratings": 10, "attended": 20},
         "missing.approval=neutral", "good", "none", note="scored on the rating alone; flagged no_vote", flags=("no_vote",)),
    case("E41", "10,000 attended, nobody rated", {"num_ratings": 0, "attended": 10000, "yes_votes": 0, "no_votes": 0},
         "reject: no_rating", None, "watch", flags=("no_rating",)),
    case("E42", "rating 0", {"rating": 0, "num_ratings": 5, "attended": 5, "yes_votes": 5, "no_votes": 0},
         "reject: rating_zero", None, "watch", flags=("rating_zero",)),
    case("E43", "exactly on both lines (4.55, 8 of 10)", {"rating": 4.55, "num_ratings": 10, "attended": 20, "yes_votes": 8, "no_votes": 2,
                                                          "track_avg": 4.6, "prior_rating": 4.55, "prior_approval": 80},
         "caps inclusive", "good", "none", note="on the line is fine"),
    case("E44", "4.54 with 10 votes, everyone approves", {"rating": 4.54, "num_ratings": 10, "attended": 20, "yes_votes": 10, "no_votes": 0, "track_avg": 4.6},
         "caps.rating_line vs guard.k", "average", "transcript",
         note="PLAN: under 4.55 with 5+ votes can never sit above Average. CONTRACT: the line is checked on the GUARDED rating "
              "(4.54 with 10 votes in a 4.70 course -> 4.59), so the class clears it and is shown as Good.", flags=("under_rating_line",)),
]
assert len(CASES) == 44 and len({c["id"] for c in CASES}) == 44


def run():
    rows, out = [], {"cases": []}
    for c in CASES:
        entry = {"id": c["id"], "label": c["label"], "switch": c["switch"], "plan": c["plan"], "note": c["note"], "inputs": c["inputs"], "by_config": {}}
        for key, cfg in CONFIGS.items():
            x = score(c["inputs"], cfg)
            entry["by_config"][key] = {"score": x["score"], "band": x["band"], "action": x["action"], "provisional": x["provisional"],
                                       "flags": x["flags"], "adjusted": x["adjusted"], "reason": reason(c["inputs"], x, cfg)}
            rows.append([c["id"], c["label"], key, x["score"], BAND_LABEL[x["band"]], x["action"], int(x["provisional"]), " ".join(x["flags"]),
                         x["adjusted"]["rating"], x["adjusted"]["approval"]])
        x5 = entry["by_config"]["C5"]
        p = c["plan"]
        match = (x5["band"] == p["band"] and x5["action"] == p["action"] and x5["provisional"] == p["provisional"]
                 and all(f in x5["flags"] for f in p["flags"]))
        entry["plan_match_C5"] = match
        out["cases"].append(entry)
    out["summary"] = {"cases": len(CASES), "plan_matches_C5": sum(1 for e in out["cases"] if e["plan_match_C5"]),
                      "differences": [{"id": e["id"], "label": e["label"], "plan": e["plan"],
                                       "contract": {k: e["by_config"]["C5"][k] for k in ("band", "action", "provisional", "flags", "score")},
                                       "note": e["note"]} for e in out["cases"] if not e["plan_match_C5"]]}
    write_csv(os.path.join(OUT, "edge_cases.csv"), ["case", "label", "config", "score", "band", "action", "provisional", "flags", "adj_rating", "adj_approval"], rows)
    write_json(os.path.join(OUT, "edge_cases.json"), out)
    return out


if __name__ == "__main__":
    o = run()
    print("44 cases | plan expectation met under C5: %d | differences: %d" % (o["summary"]["plan_matches_C5"], len(o["summary"]["differences"])))
    for d in o["summary"]["differences"]:
        print("  %s %-45s plan %s/%s%s | contract %s/%s%s score %s flags %s" % (
            d["id"], d["label"][:45], d["plan"]["band"], d["plan"]["action"], " (prov)" if d["plan"]["provisional"] else "",
            d["contract"]["band"], d["contract"]["action"], " (prov)" if d["contract"]["provisional"] else "", d["contract"]["score"], d["contract"]["flags"]))
    for e in o["cases"]:
        x = e["by_config"]["C5"]
        print("  %s %-48s C5 %-6s %-9s %-10s %s %s" % (e["id"], e["label"][:48], x["score"], x["band"], x["action"], "prov" if x["provisional"] else "    ", " ".join(x["flags"])))
