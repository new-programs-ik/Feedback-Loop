"""ratings_source.py - the swappable "where do ratings come from" seam.

The source is the team's Google Sheet. Everything downstream (store, decision rule,
notifications, the web UI) consumes only CANONICAL rows, so another source only has to produce
the same rows.

Canonical row (plain dict):
    course_label  str   - from course_rules.course_of (the PM-facing label, aliased to courses.id later)
    cohort_text   str
    topic         str
    instructor    str
    class_date    datetime.date
    session_kind  str   - "Live Class" | "Test Review" | "Other"
    rating        float
    num_ratings   int | None   - learners who rated
    attended      int | None   - learners who attended
    yes_votes     int | None   - "would you have this instructor back?" Yes count; None = no vote data
    no_votes      int | None   - the No count; None = no vote data (never a penalty in the rule)
    region        str   - "IND" when the class type says India, else "US" (course_rules.region_of)

`topic` is the CLASS NAME. On tabs that carry both a "Topic" and a "Class" header (the Agentic
tab), "Topic" holds the session kind and "Class" the real name - the source must read "Class".
"""
from __future__ import annotations

import os
from typing import Protocol


CANONICAL_FIELDS = ["course_label", "cohort_text", "topic", "instructor", "class_date",
                    "session_kind", "rating", "num_ratings", "attended", "yes_votes", "no_votes",
                    "region"]


class RatingsSource(Protocol):
    name: str

    def fetch_rows(self) -> list[dict]:
        """All class sessions the source knows about (NOT just low-rated ones)."""
        ...


def build_source(env: dict | None = None) -> "RatingsSource":
    env = env if env is not None else dict(os.environ)
    kind = (env.get("RATINGS_SOURCE") or "sheet").strip().lower()
    if kind != "sheet":
        raise ValueError(f"unknown RATINGS_SOURCE {kind!r}: only 'sheet' exists")
    from sheet_source import SheetRatingsSource
    return SheetRatingsSource(env)
