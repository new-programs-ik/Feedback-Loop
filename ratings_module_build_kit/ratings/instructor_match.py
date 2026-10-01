"""instructor_match.py - instructor name normalisation and duplicate-name suggestions. Pure.

The sheet spells the same person several ways ("Kalpesh Singh" / "Kalpesh", "Devdatt" /
"Devdatt Mahajan" / "Devdatt Devdatt", "Nikhil Bhatnagar" / "Nikhil Bhattnagar"). The sync links a
raw name to an instructor ONLY through exact normalised spelling (instructors.normalized_name or
instructor_aliases.alias_norm); everything else becomes a SUGGESTION a human accepts or rejects
in Admin > Identity. Nothing here ever merges anything.

normalize()  - the exact twin of SQL normalize_person_name(): lower, ASCII-fold, keep [a-z0-9 ],
               collapse spaces, strip (leading "- " / trailing " -" go too). Used for every key.
match_form() - the suggester's looser view: normalize() minus honorifics, repeated tokens collapsed.
suggest()    - scores every (unresolved raw name, candidate instructor) pair:
    identical once honorifics / doubled tokens are removed ("Dr. Kalpesh Singh")          0.90
    first token equal, one side single-token   0.80 if that first name belongs to exactly one
                                               instructor, else 0.45
    one multi-token name a prefix of the other 0.80
    initials match ("J Jacob" / "JJ")         0.70
    typo: Damerau-Levenshtein within a length-scaled budget, or Jaro-Winkler >= 0.92 on names of
          8+ characters with the same token count                                          0.75
    +0.15 when the candidate taught the same course within +/-120 days with an overlapping topic
    -0.30 when both names appear on the same class date in different sessions (two people)
    kept when the total is >= 0.60.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Optional, Union

HONORIFICS = frozenset({"dr", "mr", "ms", "mrs", "prof", "professor"})

CLEANUP_EQUAL = 0.90          # identical once honorifics / doubled tokens are removed
FIRST_NAME_UNIQUE = 0.80
FIRST_NAME_SHARED = 0.45
PREFIX = 0.80
INITIALS = 0.70
TYPO = 0.75
COURSE_BONUS = 0.15
SAME_DAY_PENALTY = 0.30
KEEP = 0.60
COURSE_WINDOW_DAYS = 120
JW_MIN = 0.92
JW_MIN_LEN = 8


def normalize(name) -> str:
    """Twin of SQL normalize_person_name(). Keep this and the SQL identical."""
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode("ascii")
    s = s.lower().strip()
    if s.startswith("- "):
        s = s[2:]
    if s.endswith(" -"):
        s = s[:-2]
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def match_form(name) -> str:
    """normalize() minus honorifics, with repeated tokens collapsed ('Devdatt Devdatt' -> 'devdatt')."""
    out: list[str] = []
    for tok in normalize(name).split():
        if tok in HONORIFICS:
            continue
        if not out or out[-1] != tok:
            out.append(tok)
    return " ".join(out)


# ── string distances ─────────────────────────────────────────────────────────

def damerau_levenshtein(a: str, b: str) -> int:
    """Optimal-string-alignment distance: insert / delete / substitute / adjacent transposition."""
    la, lb = len(a), len(b)
    d = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = i
    for j in range(lb + 1):
        d[0][j] = j
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[la][lb]


def jaro_winkler(a: str, b: str) -> float:
    if a == b:
        return 1.0
    la, lb = len(a), len(b)
    if not la or not lb:
        return 0.0
    window = max(0, max(la, lb) // 2 - 1)
    am, bm = [False] * la, [False] * lb
    m = 0
    for i in range(la):
        for j in range(max(0, i - window), min(lb, i + window + 1)):
            if not bm[j] and a[i] == b[j]:
                am[i] = bm[j] = True
                m += 1
                break
    if m == 0:
        return 0.0
    t = k = 0
    for i in range(la):
        if am[i]:
            while not bm[k]:
                k += 1
            if a[i] != b[k]:
                t += 1
            k += 1
    jaro = (m / la + m / lb + (m - t // 2) / m) / 3
    prefix = 0
    for x, y in zip(a, b):
        if x != y or prefix == 4:
            break
        prefix += 1
    return jaro + prefix * 0.1 * (1 - jaro)


# ── inputs and outputs ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class ClassRef:
    """One class a name taught - the evidence for the course bonus and the same-day penalty."""
    course_id: Optional[str]
    class_date: dt.date
    topic: str = ""
    session_kind: str = ""


@dataclass(frozen=True)
class Candidate:
    id: str
    name: str                                   # canonical spelling
    spellings: tuple = ()                       # other known spellings (aliases), raw


@dataclass(frozen=True)
class Suggestion:
    raw_name: str
    raw_norm: str                               # normalize(raw_name): the DB key
    candidate_id: str
    candidate_name: str
    score: float
    method: str                                 # e.g. 'first_name+course', 'typo-same_day'
    evidence: dict = field(default_factory=dict)


Context = dict  # key: normalize(spelling) or a candidate id -> list[ClassRef]


def _initials(toks: list[str]) -> str:
    return "".join(t[0] for t in toks)


def _initials_match(r: list[str], c: list[str]) -> bool:
    """'JJ' vs 'Jayant Jacob', or 'J Jacob' vs 'Jayant Jacob' (the spelt-out tokens must agree)."""
    for short, full in ((r, c), (c, r)):
        if len(short) == 1 and len(full) >= 2 and 2 <= len(short[0]) <= 3 and short[0] == _initials(full):
            return True
    if len(r) == len(c) >= 2 and _initials(r) == _initials(c):
        if any(len(t) == 1 for t in r + c):
            return all(x == y for x, y in zip(r, c) if len(x) > 1 and len(y) > 1)
    return False


def _typo_match(rf: str, cf: str) -> Optional[dict]:
    n = min(len(rf), len(cf))
    budget = min(2, n // 6)                     # < 6 chars: exact only; 6-11: one edit; 12+: two
    dl = damerau_levenshtein(rf, cf)
    if 0 < dl <= budget:
        return {"dl": dl}
    if n >= JW_MIN_LEN and len(rf.split()) == len(cf.split()):
        jw = jaro_winkler(rf, cf)
        if jw >= JW_MIN:
            return {"jw": round(jw, 3)}
    return None


def _topic_norm(t: str) -> str:
    return normalize(t)


def _course_overlap(rc: list, cc: list) -> Optional[dict]:
    for r in rc:
        if not r.course_id:
            continue
        rt = _topic_norm(r.topic)
        for c in cc:
            if c.course_id == r.course_id and rt and rt == _topic_norm(c.topic) \
                    and abs((r.class_date - c.class_date).days) <= COURSE_WINDOW_DAYS:
                return {"course_id": r.course_id, "topic": r.topic, "dates": [str(r.class_date), str(c.class_date)]}
    return None


def _same_day_clash(rc: list, cc: list) -> Optional[dict]:
    for r in rc:
        for c in cc:
            if r.class_date == c.class_date and \
                    (_topic_norm(r.topic), r.session_kind) != (_topic_norm(c.topic), c.session_kind):
                return {"date": str(r.class_date), "sessions": [r.topic, c.topic]}
    return None


def _as_candidate(x) -> Candidate:
    if isinstance(x, Candidate):
        return x
    if isinstance(x, dict):
        return Candidate(str(x["id"]), str(x["name"]), tuple(x.get("spellings") or ()))
    cid, name = x[0], x[1]
    return Candidate(str(cid), str(name), tuple(x[2]) if len(x) > 2 and x[2] else ())


def suggest(raw_names: Iterable[str], instructors: Iterable[Union[Candidate, tuple, dict]],
            context: Optional[Context] = None) -> list[Suggestion]:
    """Score every unresolved raw name against every candidate; keep pairs >= KEEP, best first."""
    cands = [_as_candidate(c) for c in instructors]
    context = context or {}
    # how many instructors own each first name (the 0.80 vs 0.45 switch)
    owners = Counter()
    for c in cands:
        toks = match_form(c.name).split()
        if toks:
            owners[toks[0]] += 1
    forms_of = {c.id: sorted({f for f in (match_form(s) for s in (c.name,) + c.spellings) if f}) for c in cands}
    # exact normalised spellings are linked by the sync itself - never echoed as suggestions
    exact = {normalize(s) for c in cands for s in (c.name,) + c.spellings}

    def classes_of(c: Candidate) -> list:
        out: list = list(context.get(c.id, []))
        for s in (c.name,) + c.spellings:
            out.extend(context.get(normalize(s), []))
        return out

    out: list[Suggestion] = []
    for raw in dict.fromkeys(raw_names):            # unique, order kept
        rf = match_form(raw)
        rn = normalize(raw)
        if not rf or rn in exact:
            continue
        rtoks = rf.split()
        raw_classes = list(context.get(rn, [])) + (list(context.get(rf, [])) if rf != rn else [])
        for c in cands:
            best: Optional[tuple] = None
            for cf in forms_of[c.id]:
                ctoks = cf.split()
                found: list[tuple] = []
                if cf == rf:
                    # Same person once honorifics / doubled tokens go ("Dr. Kalpesh Singh"). The sync
                    # links only exact normalize() spellings, so this still needs a human's click.
                    found.append((CLEANUP_EQUAL, "cleanup_equal", {}))
                elif rtoks[0] == ctoks[0] and (len(rtoks) == 1 or len(ctoks) == 1):
                    unique = owners[rtoks[0]] == 1
                    found.append((FIRST_NAME_UNIQUE if unique else FIRST_NAME_SHARED, "first_name",
                                  {"first_name": rtoks[0], "unique": unique}))
                elif len(rtoks) >= 2 and len(ctoks) >= 2 and \
                        (rtoks == ctoks[:len(rtoks)] or ctoks == rtoks[:len(ctoks)]):
                    found.append((PREFIX, "prefix", {"prefix": min(rf, cf, key=len)}))
                if _initials_match(rtoks, ctoks):
                    found.append((INITIALS, "initials", {"initials": _initials(ctoks)}))
                typo = _typo_match(rf, cf)
                if typo:
                    found.append((TYPO, "typo", typo))
                for score, method, ev in found:
                    if best is None or score > best[0]:
                        best = (score, method, {**ev, "matched_spelling": cf})
            if best is None:
                continue
            score, method, ev = best
            cand_classes = classes_of(c)
            overlap = _course_overlap(raw_classes, cand_classes)
            if overlap:
                score += COURSE_BONUS
                method += "+course"
                ev["course_overlap"] = overlap
            clash = _same_day_clash(raw_classes, cand_classes)
            if clash:
                score -= SAME_DAY_PENALTY
                method += "-same_day"
                ev["same_day"] = clash
            score = round(score, 2)
            if score >= KEEP:
                out.append(Suggestion(raw, rn, c.id, c.name, score, method, ev))
    out.sort(key=lambda s: (s.raw_name.lower(), -s.score, s.candidate_name))
    return out
