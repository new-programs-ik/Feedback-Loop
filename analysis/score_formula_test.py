"""Score the two-sided formula test against the rules written down before the analysis was run.

The rules are in docs/FORMULA_TEST_RULES.md. Nothing here decides anything the rules did not decide
in advance; this only counts.

    python analysis/score_formula_test.py

Reads Formula-Test-Results.csv (env RESULTS_CSV to point elsewhere) and prints the scoreboard, the
classes that go each way, and the classes that do not count yet and why.
"""
import collections
import csv
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IN = os.environ.get("RESULTS_CSV") or os.path.join(ROOT, "Formula-Test-Results.csv")

# The four flags the engine itself treats as deciding a re-teach, so the definition is not invented
# for this test. `coverage` is live-class only; the other two are test-review only.
CONTENT_FLAGS = {"coverage", "correctness", "problem_coverage", "solution_walkthrough"}
SERIOUS = ("moderate", "major")


def findings(row):
    """[(flag, severity)] as recorded, ignoring anything malformed."""
    out = []
    for item in (row.get("all_findings") or "").split("; "):
        if ":" in item:
            flag, sev = item.rsplit(":", 1)
            out.append((flag.strip(), sev.strip()))
    return out


def content_problems(row):
    return [f for f, s in findings(row) if f in CONTENT_FLAGS and s in SERIOUS]


def other_problems(row):
    return [f for f, s in findings(row) if f not in CONTENT_FLAGS and s in SERIOUS]


def counts(row):
    """What this class found, in the terms the rules use."""
    if row.get("reclass") == "yes":
        return "re-teach asked for"
    if content_problems(row):
        return "content problem found"
    if other_problems(row):
        return "presentation notes only"
    return "nothing serious found"


# rules table: outcome -> who it supports, per test group
SUPPORTS = {
    "A": {"re-teach asked for": "new", "content problem found": "new",
          "presentation notes only": "old", "nothing serious found": "old"},
    "B": {"re-teach asked for": "old", "content problem found": "old",
          "presentation notes only": "new", "nothing serious found": "new"},
}
LABEL = {"new": "the new formula", "old": "Karthika's formula"}


def usable(row):
    """A result only counts if the self-check actually ran and no part of the class was lost."""
    why = []
    if row.get("verified") and not str(row["verified"]).lower().startswith("yes"):
        why.append("the self-check did not run")
    if row.get("error"):
        why.append("the analysis failed")
    if not row.get("analysed_at"):
        why.append("not analysed")
    return (not why), "; ".join(why)


def main():
    with io.open(IN, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))

    good, skipped = [], []
    for r in rows:
        ok, why = usable(r)
        (good if ok else skipped).append((r, why))

    print(f"Scored against docs/FORMULA_TEST_RULES.md, written before the analysis was run.")
    print(f"{len(rows)} classes analysed, {len(good)} count, {len(skipped)} do not.\n")

    for test, title in (("A", "TEST A — the new formula said watch the recording, "
                              "Karthika's said nobody needs to look"),
                        ("B", "TEST B — Karthika's formula said spend a video, "
                              "the new one said it is not needed")):
        group = [(r, w) for r, w in good if r.get("test") == test]
        if not group:
            continue
        print(title)
        print(f"  {'rated':>6}  {'class':<30}{'who':<15}{'what the recording showed':<26}{'supports'}")
        print("  " + "-" * 92)
        for r, _ in sorted(group, key=lambda x: float(x[0].get("rating") or 0)):
            outcome = counts(r)
            who = LABEL[SUPPORTS[test][outcome]]
            print(f"  {r.get('rating',''):>6}  {r.get('class','')[:29]:<30}"
                  f"{r.get('instructor','')[:14]:<15}{outcome:<26}{who}")
            cp = content_problems(r)
            if cp:
                print(f"          content problems: {', '.join(sorted(set(cp)))}")
        tally = collections.Counter(SUPPORTS[test][counts(r)] for r, _ in group)
        print(f"  -> new formula {tally['new']} · Karthika's formula {tally['old']}"
              f"   (of {len(group)} classes)\n")

    total = collections.Counter()
    for r, _ in good:
        t = r.get("test")
        if t in SUPPORTS:
            total[SUPPORTS[t][counts(r)]] += 1
    print("BOTH TESTS TOGETHER")
    print(f"  the new formula was right on   {total['new']} of {sum(total.values())} classes")
    print(f"  Karthika's formula was right on {total['old']} of {sum(total.values())} classes")
    if total["new"] == total["old"]:
        print("  level — and the rules say a tie goes to the simpler formula, which is Karthika's.")

    if skipped:
        print("\nDO NOT COUNT YET — re-run these before drawing any conclusion")
        for r, why in skipped:
            print(f"  {r.get('test','?')}  {r.get('class','')[:34]:<36}{r.get('instructor','')[:14]:<15}{why}")

    print("\nThe honest limit: this rests on "
          f"{len(good)} classes, and the analysis is not perfectly repeatable.")


if __name__ == "__main__":
    main()
