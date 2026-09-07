"""Instructor identity for the validation study - one person, many spellings.

276 raw name strings cover about 180 people ("Kalpesh" / "Kalpesh Singh" / "kalpesh"). Every
instructor figure (track record, next-class risk) is wrong until the spellings are resolved, so
this module proposes aliases from the data alone and separates the SAFE merges from the ones that
need a human.

Rules that merge automatically (written to analysis/out/instructor_aliases.csv):
  case_variant           the same letters, different case            ("kalpesh" -> "Kalpesh")
  punctuation_variant    the same letters once punctuation is gone   ("Aniket -" -> "Aniket")
  repeated_token         a name repeated ("Devdatt Devdatt" -> "Devdatt"), then resolved further
  initial                "Shreyansh K" -> "Shreyansh Khanna" (last token is one letter that starts
                         the only candidate's last name, same programme family)
  first_token_same_family a one-word name that matches exactly ONE full name by first token inside
                         the same programme family

Rules that only PROPOSE (written to analysis/out/instructor_needs_review.csv, never merged):
  edit_distance          two different names one letter apart, or two letters apart on full
                         names (Zoya / Zoyan, Ravi / Ravin / Rabi, Keshav / Kesshav,
                         Pranav Singhal / Pranav Singh)
  first_token_multi      a one-word name with two or more full-name candidates (Pranav, Rohit)
  first_token_other_family the only candidate teaches a different programme family
  (same-day overlap between two spellings is recorded as a note, not a block: one person
   routinely teaches a live class and a test review on the same day)
  junk_label             not a person's name ("Arjun + AMA with PWC Team")

A name that sits in ANY edit-distance pair is kept out of the automatic rules, so a typo of one
person can never be silently merged into a namesake.
"""
from __future__ import annotations

import csv
import os
import re
import unicodedata
from collections import Counter, defaultdict

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")

# Course -> programme family. Instructors move freely between the ML Program and the Advanced ML
# Program (same people, same syllabus depth), so "same course" is judged at family level.
FAMILY = {
    "ML Program": "ML", "Advanced ML Program": "ML", "ML Flagship (IND)": "ML",
    "AI Data Science SwitchUp": "ML", "ML SwitchUp (unmapped cohort)": "ML",
    "Applied Agentic AI": "Agentic", "FDE (Forward Deployed Engineering)": "Agentic",
    "PwC x IK Agentic AI Accelerator": "Agentic",
    "Transformative GenAI": "GenAI",
}
JUNK_MARKERS = (" with ", "+", " ama", "team", "session", "class")


def normalize(name: str) -> str:
    """lower-case, ASCII only, letters/digits/spaces, single spaces."""
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-z0-9 ]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _near(a: str, b: str) -> bool:
    """Edit distance small enough to be a typo: one letter always; two letters only on full names
    (10+ characters, e.g. "pranav singh" / "pranav singhal"). Short names two letters apart
    (Rohan / Rohit, Vivaan / Shajan) are different people far more often than typos.
    An initial added to a name ("shreyansh" / "shreyansh k") is never a typo pair."""
    if a == b:
        return False
    if b.startswith(a + " ") and len(b) == len(a) + 2 or a.startswith(b + " ") and len(a) == len(b) + 2:
        return False
    limit = 2 if min(len(a), len(b)) >= 10 else 1
    return edit_distance(a, b) <= limit


def propose_aliases(rows, write=True, out_dir=OUT_DIR):
    """Return {raw name -> canonical raw name} for the automatic rules; write both CSVs."""
    count = Counter(r["instructor"] for r in rows if r["instructor"])
    families = defaultdict(set)
    days = defaultdict(set)
    for r in rows:
        if r["instructor"]:
            families[r["instructor"]].add(FAMILY.get(r["course"], "Other"))
            days[r["instructor"]].add(r["date"].date())

    alias, rule_of, review = {}, {}, []
    note_of = {}

    # ---- pass 1: case / punctuation / repeated-token variants -> the most common spelling ------
    groups = defaultdict(list)
    for raw in count:
        toks = normalize(raw).split()
        key = " ".join(toks)
        if toks and len(set(toks)) == 1 and len(toks) > 1:
            key = toks[0]                                   # "Devdatt Devdatt" -> "devdatt"
        groups[key].append(raw)
    canon_of_key = {}
    for key, raws in groups.items():
        if not key:
            continue
        if any(m in " " + key + " " for m in JUNK_MARKERS) and len(key.split()) >= 3:
            for raw in raws:
                review.append((raw, "", "junk_label", count[raw], "not a person's name"))
            continue
        best = max(raws, key=lambda x: (count[x], len(x)))
        canon_of_key[key] = best
        for raw in raws:
            if raw == best:
                continue
            if raw.lower() == best.lower():
                rule = "case_variant"
            elif len(set(normalize(raw).split())) == 1 and len(normalize(raw).split()) > 1:
                rule = "repeated_token"
            else:
                rule = "punctuation_variant"
            alias[raw], rule_of[raw] = best, rule

    # working set: one representative per normalised key
    keys = sorted(canon_of_key)
    key_classes = {k: sum(count[x] for x in groups[k]) for k in keys}
    key_fam = {k: set().union(*(families[x] for x in groups[k])) for k in keys}
    key_days = {k: set().union(*(days[x] for x in groups[k])) for k in keys}

    # ---- pass 2: edit-distance pairs -> review only, and the names involved are frozen ----------
    frozen = set()
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if _near(a, b):
                frozen.add(a)
                frozen.add(b)
                review.append((canon_of_key[a], canon_of_key[b], "edit_distance", key_classes[a],
                               "%d letters apart; %s has %d classes" % (edit_distance(a, b), canon_of_key[b], key_classes[b])))

    single = [k for k in keys if len(k.split()) == 1]
    multi = [k for k in keys if len(k.split()) > 1]
    resolved_key = {}          # key -> key it now points at (after pass 3)

    # ---- pass 3: initials ("shreyansh k" -> "shreyansh khanna") --------------------------------
    for k in multi:
        toks = k.split()
        if len(toks[-1]) != 1 or k in frozen:
            continue
        cands = [m for m in multi if m != k and m.split()[0] == toks[0] and len(m.split()[-1]) > 1
                 and m.split()[-1][0] == toks[-1] and m not in frozen]
        fam_c = [m for m in cands if key_fam[m] & key_fam[k]]
        if len(fam_c) == 1:
            alias[canon_of_key[k]], rule_of[canon_of_key[k]] = canon_of_key[fam_c[0]], "initial"
            resolved_key[k] = fam_c[0]
            for raw in groups[k]:
                if raw != canon_of_key[k]:
                    alias[raw] = canon_of_key[fam_c[0]]
        elif fam_c:
            review.append((canon_of_key[k], " | ".join(canon_of_key[m] for m in fam_c), "first_token_multi", key_classes[k], "initial"))

    # ---- pass 4: one-word names -> exactly one full name in the same family ---------------------
    for k in single:
        if k in frozen:
            cands = [m for m in multi if m.split()[0] == k]
            review.append((canon_of_key[k], " | ".join(canon_of_key[resolved_key.get(m, m)] for m in cands),
                           "edit_distance", key_classes[k], "frozen: a one- or two-letter neighbour exists"))
            continue
        cands = sorted({resolved_key.get(m, m) for m in multi if m.split()[0] == k})
        if not cands:
            continue
        fam_c = [m for m in cands if key_fam[m] & key_fam[k]]
        other = [m for m in cands if m not in fam_c]
        target = canon_of_key[fam_c[0]] if len(fam_c) == 1 else None
        if len(fam_c) == 1:
            alias[canon_of_key[k]], rule_of[canon_of_key[k]] = target, "first_token_same_family"
            notes = []
            if other:
                notes.append("namesake in another family: " + ", ".join(canon_of_key[m] for m in other))
            clash = key_days[k] & key_days[fam_c[0]]
            if clash:
                notes.append("both spellings taught on %d of the same days (two sessions a day is common)" % len(clash))
            note_of[canon_of_key[k]] = "; ".join(notes)
            for raw in groups[k]:
                if raw != canon_of_key[k]:
                    alias[raw] = target
        elif len(fam_c) > 1:
            review.append((canon_of_key[k], " | ".join(canon_of_key[m] for m in fam_c), "first_token_multi", key_classes[k], ""))
        else:
            review.append((canon_of_key[k], " | ".join(canon_of_key[m] for m in other), "first_token_other_family", key_classes[k], ""))

    # chase chains (raw -> "Shreyansh K" -> "Shreyansh Khanna")
    def final(x):
        seen = set()
        while x in alias and x not in seen:
            seen.add(x)
            x = alias[x]
        return x
    alias = {raw: final(raw) for raw in alias}
    alias = {raw: c for raw, c in alias.items() if raw != c}

    if write:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "instructor_aliases.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["raw", "canonical", "rule", "classes", "note"])
            for raw in sorted(alias, key=lambda x: (alias[x].lower(), -count[x])):
                w.writerow([raw, alias[raw], rule_of.get(raw, "chained"), count[raw], note_of.get(raw, "")])
        with open(os.path.join(out_dir, "instructor_needs_review.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["raw", "candidates", "rule", "classes", "note"])
            seen = set()
            for row in sorted(review, key=lambda x: (x[2], x[0].lower())):
                if row[:3] in seen:
                    continue
                seen.add(row[:3])
                w.writerow(row)
    return alias


def summary(rows, alias):
    raw = {r["instructor"] for r in rows if r["instructor"]}
    resolved = {alias.get(r["instructor"], r["instructor"]) for r in rows if r["instructor"]}
    moved = sum(1 for r in rows if r["instructor"] in alias)
    return {"raw_names": len(raw), "resolved_names": len(resolved), "aliases": len(alias), "classes_re-labelled": moved}


if __name__ == "__main__":
    import datetime as dt
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ratings_data import load
    rows = load(dt.datetime(2026, 1, 1), dt.datetime(2026, 8, 31, 23, 59, 59), strict=False)
    alias = propose_aliases(rows)
    print(summary(rows, alias))
    rules = Counter()
    with open(os.path.join(OUT_DIR, "instructor_aliases.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rules[row["rule"]] += 1
    print("alias rules:", dict(rules))
    with open(os.path.join(OUT_DIR, "instructor_needs_review.csv"), encoding="utf-8") as f:
        rev = list(csv.DictReader(f))
    print("needs review:", len(rev), dict(Counter(r["rule"] for r in rev)))
