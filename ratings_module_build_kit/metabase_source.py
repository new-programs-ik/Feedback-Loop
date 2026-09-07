"""metabase_source.py - ratings straight from Metabase, wrapping the existing metabase.py client.

The forward path: when the team switches the source of truth from the sheet to Metabase, set
RATINGS_SOURCE=metabase (plus the METABASE_* env vars that metabase.py already reads) and the
rest of the pipeline is unchanged.

Deliberately does NOT reuse metabase.fetch_low_rated(): that filters to rating < threshold,
and the dashboard needs EVERY class - good ones included - so trends and shares are honest.

Column mapping: metabase.py normalises to course/cohort/instructor/topic/class_date/rating/
num_ratings. Attendance isn't in its canonical set, so we read `attended` (or a name given in
METABASE_RATINGS_MAPPING, a JSON object of canonical->source column names). The approval vote
(`yes_votes` / `no_votes`) is emitted only when the mapping names its source columns - there is
no default column, so an unmapped card yields None for both (no penalty in the rule).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

import httpx

import course_rules as CR
import metabase as MB

log = logging.getLogger("metabase_source")


class MetabaseRatingsSource:
    name = "metabase"

    def __init__(self, env: dict | None = None, transport: Optional[httpx.BaseTransport] = None):
        self.env = env if env is not None else dict(os.environ)
        self.cfg = MB.MetabaseConfig.from_env(self.env)
        self._transport = transport
        try:
            self.mapping: dict = json.loads(self.env.get("METABASE_RATINGS_MAPPING") or "{}")
        except json.JSONDecodeError:
            log.warning("METABASE_RATINGS_MAPPING is not valid JSON - ignoring it")
            self.mapping = {}

    def fetch_rows(self) -> list[dict]:
        with MB.MetabaseClient(self.cfg, transport=self._transport) as client:
            if self.cfg.card_id:
                raw = client.run_card(self.cfg.card_id)
            elif self.cfg.sql and self.cfg.database_id:
                raw = client.run_native_query(self.cfg.sql, self.cfg.database_id)
            else:
                raise MB.MetabaseError(
                    "set METABASE_CARD_ID, or METABASE_SQL + METABASE_DATABASE_ID")

        att_col = self.mapping.get("attended", "attended")
        kind_col = self.mapping.get("session_kind", "type")
        yes_col, no_col = self.mapping.get("yes_votes"), self.mapping.get("no_votes")
        out: list[dict] = []
        for r in raw:
            row = MB.normalize_row(r, self.mapping or None)
            errs = MB.validate_row(row)
            if errs:
                log.warning("skipping metabase row (%s): %r", "; ".join(errs), r)
                continue
            cohort = str(row.get("cohort") or "")
            type_ = str(r.get(kind_col) or "")
            att = r.get(att_col)
            yes = r.get(yes_col) if yes_col else None
            no = r.get(no_col) if no_col else None
            out.append({
                "course_label": CR.course_of(cohort or str(row.get("course") or ""), type_),
                "cohort_text": cohort,
                "topic": str(row.get("topic") or "").strip(),
                "instructor": str(row.get("instructor") or "").strip(),
                "class_date": row["class_date"],
                "session_kind": CR.kind_of(type_),
                "rating": round(float(row["rating"]), 2),
                "num_ratings": row.get("num_ratings"),
                "attended": int(att) if att not in (None, "") else None,
                "yes_votes": int(yes) if yes not in (None, "") else None,
                "no_votes": int(no) if no not in (None, "") else None,
                "region": CR.region_of(type_),
            })
        log.info("metabase: %d canonical rows", len(out))
        return out
