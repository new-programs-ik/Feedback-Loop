"""cohort_parse.py - the sheet's "Cohorts" text -> structured cohorts. Pure: no I/O, no DB.

A class row's cohort cell glues one or more cohort labels together, separated by "," or ";", and
often carries junk (a placeholder, a template, a deprecated label). Each real label looks like

    <Program> - [IND ][2nd ]<Early|Mid|End>-<Month> <Year>[ : Cohort <n> | (<n>)]

e.g. "Applied Agentic AI for SWEs - 2nd Mid-February 2026 : Cohort 2". From it we read the course
(via course_rules.course_of on the SEGMENT, since one cell can name cohorts of different courses),
the region (IND when the segment or the class type says India, else US), the intake window
(start month + early/mid/end), the ordinal ("2nd" intake of that window), the cohort number and
the audience (swe / tech / pm / em, from the program name).

Unparseable non-junk segments are returned for counting - they never fail a sync. Validated on
the Jan-Aug 2026 workbook: 100% of the 497 distinct cohort strings yield at least one cohort.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Callable, Optional, Union

SEGMENT_SPLIT = re.compile(r"[,;]")

# Any segment matching one of these is dropped before parsing (word-bounded, case-insensitive).
JUNK_MARKERS = ("placeholder", "place holder", "template", "deprecated", "dnu", "do not use",
                "events and session requests", "test cohort", "only for ops")
_JUNK = re.compile(r"\b(" + "|".join(re.escape(m) for m in JUNK_MARKERS) + r")\b", re.IGNORECASE)
# Ops codes glued to letters ("DNUtpm", "p2dnu", "Dnuadgen") and bare short codes ("DBUAB", "-").
_JUNK_CODE = re.compile(r"(\bdnu|dnu\b)", re.IGNORECASE)
_BARE_CODE = re.compile(r"^[A-Za-z0-9]{1,8}$|^[-_.\s]*$")

PATTERN = re.compile(
    r"^(?P<program>.+?)\s*-\s*(?P<ind>IND\s+)?(?P<ord>2nd\s+)?(?P<part>Early|Mid|End)[-\s]+"
    r"(?P<month>[A-Za-z]+)\s+(?P<year>20\d{2})(?:\s*:\s*Cohort\s*(?P<n>\d+)|\s*\((?P<n2>\d+)\))?\s*$",
    re.IGNORECASE)

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]
_MONTH_BY_PREFIX = {m[:3].lower(): i for i, m in enumerate(MONTHS, 1)}

# Audience, read from the program name. Order matters: the first match wins.
AUDIENCE_RULES = (
    ("swe", re.compile(r"\bswe'?s?\b", re.IGNORECASE)),
    ("tech", re.compile(r"\btech\b", re.IGNORECASE)),
    ("pm", re.compile(r"\bt?pm\b", re.IGNORECASE)),
    ("em", re.compile(r"\bem'?s?\b", re.IGNORECASE)),
)
AUDIENCE_LABELS = {"swe": "for SWEs", "tech": "for Tech Professionals", "pm": "for PM/TPM", "em": "for EMs"}


def month_number(word: str) -> Optional[int]:
    """'February' / 'Feb' / 'Sept' -> 2 / 2 / 9; None for anything that is not a month."""
    return _MONTH_BY_PREFIX.get((word or "")[:3].lower())


def slugify(label: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", (label or "").lower())).strip("-")


def is_junk(segment: str) -> bool:
    seg = (segment or "").strip()
    return bool(_JUNK.search(seg) or _JUNK_CODE.search(seg) or _BARE_CODE.match(seg))


def audience_of(program: str) -> Optional[str]:
    for key, rx in AUDIENCE_RULES:
        if rx.search(program or ""):
            return key
    return None


@dataclass(frozen=True)
class ParsedCohort:
    course_label: str          # course_rules label for this segment (the PM-facing name)
    program: str               # the program text before " - ", as written
    region: str                # 'US' | 'IND'
    year: int
    month: int                 # 1-12
    part: str                  # 'early' | 'mid' | 'end'
    intake_ordinal: int        # 1, or 2 for a "2nd" intake of the same window
    cohort_no: Optional[int]   # the ": Cohort n" suffix when present
    audience: Optional[str]    # 'swe' | 'tech' | 'pm' | 'em' | None
    raw_label: str             # the segment as it appeared in the sheet (stripped)

    @property
    def start_month(self) -> dt.date:
        return dt.date(self.year, self.month, 1)

    @property
    def key_suffix(self) -> str:
        """Everything in the key except the course: region-year-month-part-ordinal-cohort[-audience]."""
        s = f"{self.region}-{self.year}-{self.month:02d}-{self.part}-{self.intake_ordinal}-{self.cohort_no or 1}"
        return s + (f"-{self.audience}" if self.audience else "")

    def key_for(self, course_slug: str) -> str:
        return f"{course_slug}-{self.key_suffix}"

    @property
    def cohort_key(self) -> str:
        """Pure default: keyed on the slugified course label. The store re-keys on courses.slug."""
        return self.key_for(slugify(self.course_label))

    def name_for(self, course_name: str) -> str:
        """Display name: '<Course> · Mid-Feb 2026 (2nd) · IND' (audience and cohort no. when present)."""
        who = f" {AUDIENCE_LABELS[self.audience]}" if self.audience else ""
        ordinal = " (2nd)" if self.intake_ordinal == 2 else ""
        cohort = f" · Cohort {self.cohort_no}" if self.cohort_no and self.cohort_no > 1 else ""
        region = " · IND" if self.region == "IND" else ""
        return f"{course_name}{who} · {self.part.capitalize()}-{MONTHS[self.month - 1][:3]} {self.year}{ordinal}{cohort}{region}"

    @property
    def name(self) -> str:
        return self.name_for(self.course_label)


@dataclass(frozen=True)
class ParseReport:
    cohorts: tuple            # ParsedCohort, in the order they appeared, de-duplicated by key
    unparsed: tuple           # non-junk segments the pattern did not match (count these, never fail)
    junk: tuple               # segments dropped as placeholder / template / deprecated / ...


CourseOf = Union[Callable[[str, str], str], str]


def split_segments(cohort_text: str) -> list[str]:
    return [s.strip() for s in SEGMENT_SPLIT.split(cohort_text or "") if s and s.strip()]


def parse_segment(segment: str, course_of: CourseOf, region: Optional[str] = None,
                  type_: str = "") -> Optional[ParsedCohort]:
    """One label -> ParsedCohort, or None when it does not fit the pattern."""
    m = PATTERN.match(segment.strip())
    if not m:
        return None
    month = month_number(m.group("month"))
    if month is None:
        return None
    program = m.group("program").strip()
    label = course_of if isinstance(course_of, str) else course_of(segment, type_)
    ind = bool(m.group("ind")) or (region or "").upper() == "IND" or "india" in (type_ or "").lower()
    n = m.group("n") or m.group("n2")
    return ParsedCohort(
        course_label=label, program=program, region="IND" if ind else "US",
        year=int(m.group("year")), month=month, part=m.group("part").lower(),
        intake_ordinal=2 if m.group("ord") else 1, cohort_no=int(n) if n else None,
        audience=audience_of(program), raw_label=segment.strip())


def parse_cohorts_report(cohort_text: str, course_of: CourseOf, region: Optional[str] = None,
                         type_: str = "") -> ParseReport:
    cohorts: list[ParsedCohort] = []
    seen: set[str] = set()
    unparsed: list[str] = []
    junk: list[str] = []
    for seg in split_segments(cohort_text):
        if is_junk(seg):
            junk.append(seg)
            continue
        parsed = parse_segment(seg, course_of, region, type_)
        if parsed is None:
            unparsed.append(seg)
            continue
        if parsed.cohort_key in seen:
            continue
        seen.add(parsed.cohort_key)
        cohorts.append(parsed)
    return ParseReport(tuple(cohorts), tuple(unparsed), tuple(junk))


def parse_cohorts(cohort_text: str, course_of: CourseOf, region: Optional[str] = None,
                  type_: str = "") -> list[ParsedCohort]:
    """The cohorts named in one cell. `course_of` is course_rules.course_of (called per segment)
    or a fixed label; `region` is the row's region hint ('IND' forces IND); `type_` is the raw
    class type when the caller has it (an 'India ...' type also forces IND)."""
    return list(parse_cohorts_report(cohort_text, course_of, region, type_).cohorts)


def week_number(class_date: dt.date, window_start: dt.date) -> int:
    """1 + whole weeks since the cohort's first class (never below 1)."""
    return 1 + max(0, (class_date - window_start).days) // 7
