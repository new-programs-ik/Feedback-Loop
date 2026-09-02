"""ratings_source.py - the swappable "where do ratings come from" seam.

Today the source is the team's Google Sheet; soon it may be Metabase. Everything downstream
(store, decision rule, notifications, the web UI) consumes only CANONICAL rows, so switching
source is the RATINGS_SOURCE env var and nothing else.

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
"""
from __future__ import annotations

import os
from typing import Protocol


CANONICAL_FIELDS = ["course_label", "cohort_text", "topic", "instructor", "class_date",
                    "session_kind", "rating", "num_ratings", "attended"]


class RatingsSource(Protocol):
    name: str

    def fetch_rows(self) -> list[dict]:
        """All class sessions the source knows about (NOT just low-rated ones)."""
        ...


def build_source(env: dict | None = None) -> "RatingsSource":
    env = env if env is not None else dict(os.environ)
    kind = (env.get("RATINGS_SOURCE") or "sheet").strip().lower()
    if kind == "metabase":
        from metabase_source import MetabaseRatingsSource
        return MetabaseRatingsSource(env)
    if kind == "sheet":
        from sheet_source import SheetRatingsSource
        return SheetRatingsSource(env)
    raise ValueError(f"unknown RATINGS_SOURCE {kind!r} (use 'sheet' or 'metabase')")
