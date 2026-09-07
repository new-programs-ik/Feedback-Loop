"""Seed the instructor-identity review from the name study (analysis/out/instructor_aliases.csv and
instructor_needs_review.csv, written by analysis/instructor_names.py).

What it does, in the order the plan allows:
1. Every spelling the study treats as a person's own name gets an instructor record, and the
   classes recorded under exactly that spelling link to it (the "exact spellings link
   automatically" rule). Nothing is merged.
2. Every "this spelling is that person" pair becomes a PENDING suggestion on Admin > Identity,
   with a confidence taken from the study's rule, for a human to accept or reject.
3. Spellings the study could not settle become low-confidence suggestions against each candidate.
4. Every other spelling still unresolved gets its own record too - it is nobody's duplicate.

    python analysis/seed_identity.py --dry-run
    python analysis/seed_identity.py --apply

Safe to re-run: records are matched by normalised name, suggestions upsert on
(raw_norm, candidate). Local use; the study files carry instructor names and stay gitignored.
"""
import argparse
import csv
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "ratings_module_build_kit"))
import config  # noqa: E402

config.load_env()
import instructor_match as IM  # noqa: E402
import ratings_store as ST  # noqa: E402

ALIASES = os.path.join(HERE, "out", "instructor_aliases.csv")
REVIEW = os.path.join(HERE, "out", "instructor_needs_review.csv")
SOURCE = "name study, 7 Sep 2026"

# confidence per study rule - the UI's "accept everything above" button works on this number
SCORE = {
    "case_variant": 0.98, "punctuation_variant": 0.97, "repeated_token": 0.95, "initial": 0.90,
    "first_token_same_family": 0.85, "edit_distance": 0.60, "first_token_multi": 0.45,
    "first_token_other_family": 0.40,
}
JUNK = re.compile(r"^(tbd|tba|na|n/a|none|null|unknown|test|instructor|-+|\.+|\?+)$", re.I)


def is_junk(name: str) -> bool:
    return len(re.sub(r"[^a-z]", "", name.lower())) < 2 or bool(JUNK.match(name.strip()))


class Identity:
    """Everything the script needs to know about who exists, resolved by normalised name."""

    def __init__(self, cur):
        self.cur = cur
        cur.execute("select id, name, normalized_name, merged_into from instructors")
        self.by_id = {}
        self.by_norm = {}
        for iid, name, norm, merged in cur.fetchall():
            self.by_id[iid] = (name, merged)
            if merged is None:
                self.by_norm[norm or IM.normalize(name)] = iid
        cur.execute("select alias_norm, instructor_id from instructor_aliases")
        for norm, iid in cur.fetchall():
            self.by_norm.setdefault(norm, self.survivor(iid))
        cur.execute("""select instructor, normalize_person_name(instructor), count(*)
                         from class_ratings where instructor_id is null and instructor <> ''
                        group by 1, 2 order by 3 desc""")
        self.unresolved = {}          # norm -> (most common raw spelling, classes)
        for raw, norm, n in cur.fetchall():
            if norm not in self.unresolved:
                self.unresolved[norm] = (raw, n)
        self.created = []
        self.suggested = []
        self.skipped = []

    def survivor(self, iid):
        seen = set()
        while iid in self.by_id and self.by_id[iid][1] and iid not in seen:
            seen.add(iid)
            iid = self.by_id[iid][1]
        return iid

    def resolve(self, name: str):
        return self.by_norm.get(IM.normalize(name))

    def ensure(self, name: str, why: str, apply: bool):
        """An instructor record for this spelling (existing or new) + its exact-spelling rows linked."""
        norm = IM.normalize(name)
        iid = self.by_norm.get(norm)
        if iid:
            return iid
        if is_junk(name):
            self.skipped.append((name, "junk"))
            return None
        raw = self.unresolved.get(norm, (name, 0))[0]
        if apply:
            self.cur.execute("insert into instructors (name) values (%s) returning id", (raw,))
            iid = self.cur.fetchone()[0]
            self.cur.execute("select link_class_ratings_to_instructor(%s, %s::uuid)", (norm, iid))
            linked = self.cur.fetchone()[0]
        else:
            iid, linked = f"new:{norm}", self.unresolved.get(norm, (None, 0))[1]
        self.by_id[iid] = (raw, None)
        self.by_norm[norm] = iid
        self.created.append((raw, linked, why))
        return iid

    def suggest(self, raw: str, target, rule: str, note: str, classes, apply: bool):
        norm = IM.normalize(raw)
        if not norm or target is None:
            return
        current = self.by_norm.get(norm)
        if current == target:
            self.skipped.append((raw, "already that person"))
            return
        own_record = current is not None and IM.normalize(self.by_id[current][0]) == norm
        if current is not None and not own_record:
            # an alias somebody chose points elsewhere - never overrule a human decision
            self.skipped.append((raw, f"already resolved to a different record ({self.by_id[current][0]})"))
            return
        score = SCORE.get(rule, 0.5)
        evidence = json.dumps({"rule": rule, "note": note, "classes": classes, "source": SOURCE,
                               "has_own_record": own_record})
        if apply:
            self.cur.execute("""insert into instructor_match_suggestions
                                  (raw_name, raw_norm, candidate_instructor_id, score, method, evidence)
                                values (%s, %s, %s::uuid, %s, %s, %s::jsonb)
                                on conflict (raw_norm, candidate_instructor_id) do update
                                  set score = greatest(instructor_match_suggestions.score, excluded.score),
                                      method = case when instructor_match_suggestions.status = 'pending'
                                                    then excluded.method else instructor_match_suggestions.method end,
                                      evidence = excluded.evidence, last_seen_at = now()""",
                             (raw, norm, target, score, f"study:{rule}", evidence))
        self.suggested.append((raw, self.by_id[target][0], score, rule + (" (merges its own record)" if own_record else "")))


def run(apply: bool) -> None:
    conn = ST.connect()
    conn.autocommit = False
    cur = conn.cursor()
    idn = Identity(cur)
    print(f"today: {len(idn.by_id)} instructor records · {len(idn.unresolved)} unresolved spellings "
          f"({sum(n for _, n in idn.unresolved.values())} classes)")

    aliases = list(csv.DictReader(open(ALIASES, encoding="utf-8")))
    review = list(csv.DictReader(open(REVIEW, encoding="utf-8")))
    raws_in_study = {IM.normalize(r["raw"]) for r in aliases} | {IM.normalize(r["raw"]) for r in review}

    # 1 + 2: the study's confident pairs
    for r in aliases:
        target = idn.ensure(r["canonical"], "canonical name in the study", apply)
        idn.suggest(r["raw"], target, r["rule"], r.get("note", ""), r.get("classes"), apply)

    # 3: the ambiguous ones - one low-confidence suggestion per candidate
    for r in review:
        if r["rule"] == "junk_label":
            idn.skipped.append((r["raw"], "junk label per the study"))
            continue
        for cand in [c.strip() for c in r["candidates"].split("|") if c.strip()]:
            target = idn.ensure(cand, "candidate in the study's review list", apply)
            idn.suggest(r["raw"], target, r["rule"], r.get("note", ""), r.get("classes"), apply)

    # 4: everything else that is still unresolved is nobody's duplicate - its own record
    for norm, (raw, n) in list(idn.unresolved.items()):
        if norm in raws_in_study or norm in idn.by_norm:
            continue
        idn.ensure(raw, "unique spelling", apply)

    if apply:
        conn.commit()
        idn2 = Identity(cur)
        print(f"after: {len(idn2.by_id)} instructor records · {len(idn2.unresolved)} unresolved spellings")
        cur.execute("select status, count(*) from instructor_match_suggestions group by 1")
        print("suggestions:", dict(cur.fetchall()))
        cur.execute("select count(*), count(instructor_id) from class_ratings")
        print("class rows linked to an instructor:", cur.fetchone())
    else:
        conn.rollback()
    conn.close()

    print(f"\nrecords {'created' if apply else 'to create'}: {len(idn.created)}")
    reasons = Counter(w for _, _, w in idn.created)
    print("   ", dict(reasons))
    for raw, linked, why in idn.created[:12]:
        print(f"    {raw!r:<34} {linked:>4} classes · {why}")
    print(f"suggestions {'written' if apply else 'to write'}: {len(idn.suggested)}")
    for raw, cand, score, rule in idn.suggested[:12]:
        print(f"    {raw!r:<28} -> {cand!r:<30} {score:.2f} {rule}")
    print(f"skipped: {len(idn.skipped)}")
    for raw, why in idn.skipped[:20]:
        print(f"    {raw!r:<34} {why}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    run(apply=args.apply)


if __name__ == "__main__":
    main()
