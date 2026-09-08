"""learner_source.py - the learner-level ingestion contract: one row per learner per rated class.

There is no learner-level data anywhere yet (0 emails in the whole ratings workbook, Sep 2026),
so this module is the seam the future export plugs into - a Protocol, the canonical row, and a
factory that says "not configured" until LEARNER_SOURCE names an implementation. The worker's
POST /sync-learners answers 501 with the same message. The tables it will feed (learners,
learner_ratings, learner_import_runs) are created empty by migration 0020, with the contract in
that file's header; the class layer is untouched when this arrives.

Canonical learner row (plain dict), keyed to the class row we already have:
    learner_email    str          - the IK login email, lower-cased (the learner's identity)
    learner_name     str | None
    course_label     str          - as course_rules.course_of names it
    cohort_text      str          - the cohort label(s); parsed by cohort_parse like class rows
    topic            str          - the CLASS NAME (matches class_ratings.topic)
    instructor       str          - as recorded; resolved through aliases like class rows
    class_date       datetime.date
    session_kind     str          - "Live Class" | "Test Review" | "Other"
    rating           float | None - this learner's rating of the class (1-5)
    would_have_back  bool | None  - this learner's approval vote; None = did not vote
    attended         bool | None
    comment          str | None   - free text, if the export carries it
"""
from __future__ import annotations

import os
from typing import Protocol, TypedDict, Optional
import datetime as dt


class LearnerRow(TypedDict, total=False):
    learner_email: str
    learner_name: Optional[str]
    course_label: str
    cohort_text: str
    topic: str
    instructor: str
    class_date: dt.date
    session_kind: str
    rating: Optional[float]
    would_have_back: Optional[bool]
    attended: Optional[bool]
    comment: Optional[str]


CANONICAL_FIELDS = ["learner_email", "learner_name", "course_label", "cohort_text", "topic",
                    "instructor", "class_date", "session_kind", "rating", "would_have_back",
                    "attended", "comment"]

NOT_CONFIGURED = ("learner sync is not configured: there is no learner-level data source yet "
                  "(the ratings sheet has no per-learner rows). When an export exists, implement "
                  "learner_source.LearnerSource for it and set LEARNER_SOURCE.")


class LearnerSourceNotConfigured(RuntimeError):
    """Raised by build_learner_source() until LEARNER_SOURCE names a real implementation."""


class LearnerSource(Protocol):
    name: str

    def fetch_rows(self) -> list[LearnerRow]:
        """Every learner x rated-class row the source knows about (not just low ratings)."""
        ...


def build_learner_source(env: dict | None = None) -> LearnerSource:
    env = env if env is not None else dict(os.environ)
    kind = (env.get("LEARNER_SOURCE") or "").strip().lower()
    if not kind:
        raise LearnerSourceNotConfigured(NOT_CONFIGURED)
    raise LearnerSourceNotConfigured(
        f"LEARNER_SOURCE={kind!r} names no implementation - none exists yet. " + NOT_CONFIGURED)
