"""uplevel.py — find a class's recording (its Vimeo link) on IK's UpLevel.

This is the manual search a PM does, turned into code. On UpLevel's Videos page every recording is
one row with its Vimeo link, the class name, the instructor and the date. We read that same table
(`GET /get_videos/`), search by the instructor, and pick the row whose class name, date and
category match the class we are about to analyse. Nothing is guessed: a match is only returned
when the date lines up and the instructor and topic agree, and the caller still confirms it before
it is used.

Authentication. UpLevel is a Django app behind AWS Cognito. There is no service token yet, so the
worker borrows a signed-in session: an admin pastes one "Copy as cURL" on Admin › UpLevel, the
website keeps only the `sessionid` and `csrftoken` cookies, and they are stored in
`integration_credentials` (migration 0032), which nobody can read through the website's API. The
`UPLEVEL_COOKIE` environment variable and the gitignored `uplevel-cookies.txt` still work as
fallbacks. What matters is Django's `sessionid` (tested 22 Sep 2026: the fetch kept working after
the Cognito token inside the cookie had expired); it lasts about two weeks, or until that person
logs out, so a fresh paste is needed that often. Swapping it for a real token later is one
function, `_session()`, not a rewrite. A failure to reach UpLevel is "could not look it up", never
"no recording exists".

Nothing here is imported by the worker's request path automatically; it is called only when a PM
asks to fetch a link, so a missing or stale session never affects scoring or the analysis engine.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable, Optional

log = logging.getLogger("uplevel")

BASE = "https://uplevel.interviewkickstart.com"
GET_VIDEOS = "/get_videos/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/128.0 Safari/537.36")
HERE = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(HERE, "uplevel-cookies.txt")

# The categories a class name can carry, mapped to our own class kinds. Our sheet marks a class
# "Live Class" or "Test Review"; UpLevel writes "Live Class", "Assignment Review Class" or
# "Technical Coaching Class" into the recording's name. A live class must not be matched to an
# assignment review of the same topic, so the category has to agree.
CATEGORY_PATTERNS = {
    "live_class": ("live class",),
    "ars": ("assignment review", "review class", "review session"),
    "coaching": ("technical coaching", "coaching class", "office hour", "office hours"),
}
KIND_TO_CATEGORY = {"live_class": "live_class", "ars": "ars"}   # our two kinds → the category we require

_MONTHS = ("january february march april may june july august september october november december").split()
_DATE_RE = re.compile(
    r"(?:mon|tues|wednes|thurs|fri|satur|sun)day,?\s+"
    r"(" + "|".join(_MONTHS) + r")\s+(\d{1,2}),?\s+(\d{4})", re.I)
_VIMEO_RE = re.compile(r"vimeo\.com/(\d+)")


class UplevelError(RuntimeError):
    """UpLevel could not be reached or refused the session. The caller must not read this as
    'the class has no recording'."""


class UplevelAuthError(UplevelError):
    """The session is missing, malformed or no longer accepted (UpLevel served its login page)."""


@dataclass
class Video:
    vimeo_id: str
    vimeo_link: str
    topic: str                     # UpLevel's clean class name (topic__name)
    category: Optional[str]        # 'live_class' | 'ars' | 'coaching' | None
    class_date: Optional[dt.date]  # parsed from the recording's name
    name: str                      # the full descriptive name, for a person to eyeball
    duration_s: Optional[int]


@dataclass
class Match:
    video: Video
    score: float                   # 0..1
    reasons: list[str]             # why, in words, for the confirm step


# ─────────────────────────── parsing (pure, tested offline) ───────────────────────────
def parse_category(name: str) -> Optional[str]:
    low = name.lower()
    for cat, needles in CATEGORY_PATTERNS.items():
        if any(n in low for n in needles):
            return cat
    return None


def parse_date(name: str) -> Optional[dt.date]:
    m = _DATE_RE.search(name or "")
    if not m:
        return None
    month = _MONTHS.index(m.group(1).lower()) + 1
    try:
        return dt.date(int(m.group(3)), month, int(m.group(2)))
    except ValueError:
        return None


def video_from_row(row: dict) -> Optional[Video]:
    link = row.get("vimeo_link") or row.get("link") or ""
    vm = _VIMEO_RE.search(str(link))
    if not vm:
        return None
    name = row.get("name") or ""
    return Video(
        vimeo_id=vm.group(1),
        vimeo_link=f"https://vimeo.com/{vm.group(1)}",
        topic=(row.get("topic__name") or "").strip(),
        category=parse_category(name),
        class_date=parse_date(name),
        name=name.strip(),
        duration_s=row.get("duration_in_sec"),
    )


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def topic_similarity(a: str, b: str) -> float:
    """0..1 on the two class names, blending token overlap with a character ratio so that
    'MLOps - Model Training 1' and 'MLOps Model Training Live Class' still read as close."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    ta, tb = set(na.split()), set(nb.split())
    jac = len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0
    return max(jac, SequenceMatcher(None, na, nb).ratio())


def instructor_in(name: str, instructor: str) -> bool:
    """Does any real part of the instructor's name appear in the recording's name?"""
    parts = [p for p in _norm(instructor).split() if len(p) > 2]
    low = " " + _norm(name) + " "
    return any(f" {p} " in low for p in parts)


# ─────────────────────────── matching (pure, tested offline) ───────────────────────────
def score_match(video: Video, *, topic: str, instructor: str, class_date: Optional[dt.date],
                kind: Optional[str]) -> Optional[Match]:
    """How well one recording fits the class we mean to analyse, in words a person can check.

    The date is the backbone: a recording on a different day is a different class, so a date that
    is present on both sides and does not match rules the row out. Everything else adds confidence.
    """
    want_cat = KIND_TO_CATEGORY.get(kind or "")
    reasons: list[str] = []
    score = 0.0

    if class_date and video.class_date:
        delta = abs((video.class_date - class_date).days)
        if delta == 0:
            score += 0.5; reasons.append("same date")
        elif delta <= 1:
            score += 0.2; reasons.append("date within a day")
        else:
            return None                                   # a different day is a different class
    elif video.class_date:
        reasons.append(f"recording dated {video.class_date:%d %b %Y} (our class has no date)")

    if instructor and instructor_in(video.name, instructor):
        score += 0.3; reasons.append("instructor matches")
    elif instructor and _norm(instructor) not in ("", "unspecified"):
        score -= 0.1; reasons.append("instructor not found in the recording name")

    sim = topic_similarity(topic, video.topic or video.name)
    if sim >= 0.6:
        score += 0.25; reasons.append(f"class name matches ({sim:.0%})")
    elif sim >= 0.35:
        score += 0.1; reasons.append(f"class name close ({sim:.0%})")
    else:
        reasons.append(f"class name differs ({sim:.0%})")

    if want_cat and video.category:
        if video.category == want_cat:
            score += 0.15; reasons.append(f"{video.category.replace('_', ' ')} matches")
        else:
            score -= 0.35
            reasons.append(f"category is {video.category.replace('_', ' ')}, expected {want_cat.replace('_', ' ')}")

    return Match(video=video, score=round(max(0.0, min(1.0, score)), 3), reasons=reasons)


def rank_matches(rows: Iterable[dict], *, topic: str, instructor: str,
                 class_date: Optional[dt.date], kind: Optional[str]) -> list[Match]:
    seen: set[str] = set()
    out: list[Match] = []
    for row in rows:
        v = video_from_row(row)
        if not v or v.vimeo_id in seen:
            continue
        seen.add(v.vimeo_id)
        m = score_match(v, topic=topic, instructor=instructor, class_date=class_date, kind=kind)
        if m:
            out.append(m)
    out.sort(key=lambda m: m.score, reverse=True)
    return out


# ─────────────────────────── the session (the one seam to swap for a token) ───────────────────────────
class UplevelNotConnected(UplevelAuthError):
    """No session is stored anywhere: nobody has connected UpLevel yet."""


def _stored_secret() -> str:
    """The session an admin saved on Admin › UpLevel (migration 0032), or '' when none is stored
    or the database cannot be asked (then the env var or local file may still answer)."""
    try:
        import store as ST
        return ST.get_integration_secret("uplevel") or ""
    except Exception:                                    # noqa: BLE001 - fall through to env / file
        log.warning("could not read the stored UpLevel session; trying the environment", exc_info=True)
        return ""


def _read_cookie_header() -> str:
    """Where the session comes from, first hit wins: what an admin saved in the app, then the
    UPLEVEL_COOKIE environment variable, then (local work only) uplevel-cookies.txt."""
    raw = _stored_secret().strip() or os.environ.get("UPLEVEL_COOKIE", "").strip()
    if not raw and os.path.exists(COOKIE_FILE):
        raw = open(COOKIE_FILE, encoding="utf-8", errors="replace").read()
    if not raw:
        raise UplevelNotConnected(
            "UpLevel is not connected. An admin connects it once on Admin › UpLevel (paste a "
            "signed-in session). Until then, paste the recording link by hand.")
    m = re.search(r"(?:-b|--cookie)\s+(['\"])(.*?)\1", raw, re.S) or \
        re.search(r"-H\s+(['\"])cookie:\s*(.*?)\1", raw, re.I | re.S)
    if m:
        return m.group(m.lastindex).strip()
    if "\n" in raw.strip() and "cookie:" in raw.lower():
        for line in raw.splitlines():
            if line.lower().startswith("cookie:"):
                return line.split(":", 1)[1].strip()
    return raw.strip()


def _session():
    """A requests.Session carrying the UpLevel cookies. The only place auth lives; a token-based
    flow replaces the body of this function and nothing else changes."""
    import requests
    header = _read_cookie_header()
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "X-Requested-With": "XMLHttpRequest",
                      "Accept": "application/json", "Referer": BASE + "/videos/"})
    for part in header.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            s.cookies.set(k.strip(), v.strip(), domain="uplevel.interviewkickstart.com")
    if "sessionid" not in {c.name for c in s.cookies}:
        raise UplevelAuthError("The UpLevel cookie has no sessionid; it is not a signed-in session.")
    return s


SESSION_COOKIES = ("sessionid", "csrftoken")


def cookie_header_of(session) -> str:
    """The minimal cookie header a session needs to keep working (what we store)."""
    parts = []
    for name in SESSION_COOKIES:
        value = session.cookies.get(name, domain="uplevel.interviewkickstart.com") or session.cookies.get(name)
        if value:
            parts.append(f"{name}={value}")
    return "; ".join(parts)


def search_rows(query: str, *, limit: int = 50, session=None) -> list[dict]:
    """Rows from UpLevel's Videos table for a one-word search (the search is a plain substring, so
    a single distinctive word — usually the instructor's first name — works; a phrase does not)."""
    s = session or _session()
    params = {"draw": 1, "start": 0, "length": limit, "search[value]": query, "search[regex]": "false",
              "topic": "all", "presenter": "all", "added_on_date": ""}
    try:
        r = s.get(BASE + GET_VIDEOS, params=params, timeout=40, allow_redirects=False)
    except Exception as e:                                 # noqa: BLE001
        raise UplevelError(f"could not reach UpLevel: {type(e).__name__}") from e
    if r.status_code in (301, 302, 303, 307, 308) or "json" not in r.headers.get("content-type", ""):
        raise UplevelAuthError("UpLevel did not return data — the session has expired or is not accepted.")
    try:
        return r.json().get("data", [])
    except ValueError as e:
        raise UplevelError("UpLevel returned something that was not the expected table.") from e


def _search_terms(instructor: str, topic: str) -> list[str]:
    terms: list[str] = []
    for p in _norm(instructor).split():
        if len(p) > 2 and p not in ("unspecified",):
            terms.append(p)
    for p in _norm(topic).split():
        if len(p) > 3 and p not in terms:
            terms.append(p)
    if not terms and _norm(topic):
        terms = [_norm(topic).split()[0]]
    return terms[:3]


def find_recording(*, topic: str, instructor: str, class_date: Optional[dt.date],
                   kind: Optional[str] = None, session=None, limit_per_term: int = 100) -> list[Match]:
    """The one call a caller makes: the ranked recordings that could be this class, best first.
    An empty list means none was found (search terms tried, nothing matched); an UplevelError
    means we could not look — the two must never be confused. The caller shows the top match and
    lets a person confirm before it is used."""
    s = session or _session()
    rows: dict[int, dict] = {}
    for term in _search_terms(instructor, topic):
        for row in search_rows(term, limit=limit_per_term, session=s):
            rid = row.get("id")
            if rid is not None:
                rows[rid] = row
    return rank_matches(rows.values(), topic=topic, instructor=instructor,
                        class_date=class_date, kind=kind)
