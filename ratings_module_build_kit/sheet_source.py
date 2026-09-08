"""sheet_source.py - ratings from the team's Google Sheet, via a read-only service account.

Design notes (why it looks like this):
- google-auth is used ONLY to mint the OAuth token; the actual Sheets call is one plain httpx
  GET against the REST API (values:batchGet). That keeps the repo's httpx.MockTransport test
  pattern working and the dependency tree tiny (Render free tier).
- Columns are found BY HEADER NAME, so reordering or adding columns in the sheet is harmless.
  A RENAMED/removed required column fails the whole run loudly, with the column named - the
  schema-drift guard. (Same hygiene rules as analysis/ratings_data.py: skip non-numeric rows,
  drop responses>attended data errors, dedupe across tabs.)
- The approval vote (the "Yes" / "No" columns) is OPTIONAL: a tab without them yields None for
  both counts and the rule scores approval as no-penalty. Only REQUIRED_COLUMNS are loud.
- The CLASS NAME comes from "Class" whenever that header exists. On the Agentic tab "Topic" holds
  the session kind ("Live Class" / "Test Review Session") and "Class" the real name - reading
  "Topic" there mislabelled two thirds of all classes (found 3 Sep 2026). "Topic" is used only on
  tabs that have no "Class" column (the MLSU tab).
- `region` is 'IND' when the Type says India ("India ML Switchup Live Class"), else 'US'.
- The service-account key comes from GOOGLE_SA_JSON_FILE (a Render Secret File) or GOOGLE_SA_JSON
  (raw JSON in an env var). File wins.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import time
from typing import Callable, Optional

import httpx

import course_rules as CR

log = logging.getLogger("sheet_source")

SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
DEFAULT_TABS = "MLSU_Live_Class_Poll,Agentic_AI_Live_Class_Poll"

REQUIRED_COLUMNS = ["Session Date", "Type", "Cohorts", "Topic", "Instructor",
                    "Overall Average", "Responses", "# Students Attended"]
# "Topic" may be called "Class" on some tabs - either satisfies the requirement.
TOPIC_FALLBACK = "Class"
# The approval vote - "would you want this instructor to take the class again?" - as Yes/No
# counts per class. Optional: read when present, None when the tab has no such columns.
VOTE_COLUMNS = ("Yes", "No")


class SheetSourceError(RuntimeError):
    """Configuration or schema problem - the sync run should fail loudly with this message."""


def _default_token_provider(env: dict) -> str:
    """Mint a service-account access token. Isolated so tests can inject a fake."""
    from google.oauth2 import service_account  # deferred: not needed under test
    import google.auth.transport.requests

    sa_file = (env.get("GOOGLE_SA_JSON_FILE") or "").strip()
    sa_json = env.get("GOOGLE_SA_JSON")
    found = _resolve_key_file(sa_file) if sa_file else None
    if found:
        creds = service_account.Credentials.from_service_account_file(found, scopes=[SCOPE])
    elif sa_json:
        creds = service_account.Credentials.from_service_account_info(
            json.loads(sa_json), scopes=[SCOPE])
    elif sa_file:
        # The setting is there; the file it names is not. Saying "no key configured" sent people
        # looking for a missing setting instead of a missing file.
        raise SheetSourceError(
            f"GOOGLE_SA_JSON_FILE is set to {sa_file!r} but no such file exists. Looked in: "
            + ", ".join(_key_search_paths(sa_file)))
    else:
        raise SheetSourceError(
            "no Google service-account key: set GOOGLE_SA_JSON_FILE (path) or GOOGLE_SA_JSON (content)")
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def _key_search_paths(sa_file: str) -> list[str]:
    """Where a relative key path could reasonably live: as given, next to this module, and next to
    the project it sits in. A relative path used to depend entirely on the working directory."""
    if os.path.isabs(sa_file):
        return [sa_file]
    here = os.path.dirname(os.path.abspath(__file__))
    return [os.path.abspath(sa_file),
            os.path.join(here, sa_file),
            os.path.join(os.path.dirname(here), sa_file)]


def _resolve_key_file(sa_file: str) -> Optional[str]:
    """The first of those that actually exists, or None."""
    for p in _key_search_paths(sa_file):
        if os.path.isfile(p):
            return p
    return None


# %B is the full month name ("January"), %b the abbreviation ("Jan"). The live sheet writes the
# full name, and the list here used to carry only %b - so every month parsed as None except May,
# the one month whose abbreviation IS its full name. Seven months of classes were dropped in
# silence. Both forms are accepted now, in both orders, with and without a weekday in front.
_DATE_FORMATS = (
    "%Y-%m-%d", "%Y/%m/%d",
    "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y",
    "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y",
    "%d %B %Y", "%d %b %Y", "%d-%B-%Y", "%d-%b-%Y",
)


def _parse_date(v) -> Optional[dt.date]:
    """A class date from whatever the sheet holds: a formatted string, an ISO stamp, or the raw
    serial number a spreadsheet stores underneath."""
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        # A spreadsheet serial: days since 1899-12-30. Only sane values are accepted, so a stray
        # rating or head-count in the date column is rejected rather than becoming a date in 1970.
        if 20000 <= float(v) <= 80000:
            return (dt.date(1899, 12, 30) + dt.timedelta(days=int(float(v))))
        return None

    s = str(v).strip()
    if not s:
        return None
    if "," in s and s.split(",")[0].strip().isalpha() and len(s.split(",")) > 2:
        s = s.split(",", 1)[1].strip()          # drop a leading weekday: "Friday, January 2, 2026"
    head = s.split("T")[0].split(" ")[0]

    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(head, fmt).date()
        except ValueError:
            pass
    try:
        return dt.datetime.fromisoformat(s).date()
    except ValueError:
        return None


def _num(v) -> Optional[float]:
    try:
        f = float(str(v).replace(",", "").strip())
        return f
    except (TypeError, ValueError):
        return None


class SheetRatingsSource:
    name = "sheet"

    def __init__(self, env: dict | None = None,
                 transport: Optional[httpx.BaseTransport] = None,
                 token_provider: Optional[Callable[[dict], str]] = None):
        self.env = env if env is not None else dict(os.environ)
        self.sheet_id = (self.env.get("RATINGS_SHEET_ID") or "").strip()
        self.tabs = [t.strip() for t in
                     (self.env.get("RATINGS_SHEET_TABS") or DEFAULT_TABS).split(",") if t.strip()]
        self._transport = transport
        self._token_provider = token_provider or _default_token_provider

    # ── fetch ────────────────────────────────────────────────────────────────
    def _get_values(self) -> dict:
        if not self.sheet_id:
            raise SheetSourceError("RATINGS_SHEET_ID is not set")
        token = self._token_provider(self.env)
        params = [("ranges", tab) for tab in self.tabs]
        params += [("valueRenderOption", "UNFORMATTED_VALUE"),
                   ("dateTimeRenderOption", "FORMATTED_STRING")]
        url = f"{SHEETS_API}/{self.sheet_id}/values:batchGet"
        last_err: Exception | None = None
        with httpx.Client(transport=self._transport, timeout=60) as client:
            for attempt in range(3):
                try:
                    r = client.get(url, params=params, headers={"Authorization": f"Bearer {token}"})
                    if r.status_code in (429, 500, 502, 503, 504):
                        raise httpx.HTTPStatusError("retryable", request=r.request, response=r)
                    if r.status_code == 403:
                        raise SheetSourceError(
                            "Google returned 403 - the sheet is not shared with the service account "
                            "(share it with the client_email from the key file, as Viewer)")
                    if r.status_code == 404:
                        raise SheetSourceError(
                            f"Google returned 404 - RATINGS_SHEET_ID {self.sheet_id!r} not found "
                            "(copy the long id from the sheet's URL)")
                    r.raise_for_status()
                    return r.json()
                except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as e:
                    last_err = e
                    time.sleep(min(2 ** attempt, 6))
        raise SheetSourceError(f"could not reach the Google Sheets API: {last_err}")

    # ── parse ────────────────────────────────────────────────────────────────
    def _parse_tab(self, tab_name: str, values: list[list]) -> list[dict]:
        if not values:
            log.warning("tab %s is empty", tab_name)
            return []
        header = [str(c).strip() if c is not None else "" for c in values[0]]
        idx: dict[str, int] = {}
        for i, h in enumerate(header):
            if h and h not in idx:
                idx[h] = i

        missing = [c for c in REQUIRED_COLUMNS
                   if c not in idx and not (c == "Topic" and TOPIC_FALLBACK in idx)]
        if missing:
            raise SheetSourceError(
                f"tab {tab_name!r} is missing required column(s) {missing} - "
                "was a header renamed in the sheet?")

        # The class name: "Class" wins whenever it exists (on the Agentic tab "Topic" is the session
        # kind); "Topic" only on tabs without a "Class" column.
        topic_col = TOPIC_FALLBACK if TOPIC_FALLBACK in idx else "Topic"

        def g(row: list, col: str):
            i = idx.get(col)
            return row[i] if i is not None and len(row) > i else None

        out: list[dict] = []
        skipped: dict[str, int] = {"unreadable date": 0, "no rating": 0, "nobody attended": 0,
                                   "more rated than attended": 0}
        first_bad_date = None
        for row in values[1:]:
            date = _parse_date(g(row, "Session Date"))
            rating = _num(g(row, "Overall Average"))
            attended = _num(g(row, "# Students Attended"))
            responses = _num(g(row, "Responses"))
            yes, no = _num(g(row, VOTE_COLUMNS[0])), _num(g(row, VOTE_COLUMNS[1]))
            if date is None:
                raw = g(row, "Session Date")
                if raw not in (None, ""):
                    skipped["unreadable date"] += 1
                    if first_bad_date is None:
                        first_bad_date = repr(raw)[:40]
                continue
            if rating is None:
                skipped["no rating"] += 1
                continue                                    # "No Ratings" rows
            if not attended:
                skipped["nobody attended"] += 1
                continue
            if responses is not None and responses > attended:
                skipped["more rated than attended"] += 1
                continue                                    # data-entry error (seen in the wild)
            cohort = str(g(row, "Cohorts") or "").strip()
            type_ = str(g(row, "Type") or "").strip()
            out.append({
                "course_label": CR.course_of(cohort, type_),
                "cohort_text": cohort,
                "topic": str(g(row, topic_col) or "").strip(),
                "instructor": str(g(row, "Instructor") or "").strip(),
                "class_date": date,
                "session_kind": CR.kind_of(type_),
                "rating": round(rating, 2),
                "num_ratings": int(responses) if responses is not None else None,
                "attended": int(attended),
                "yes_votes": int(yes) if yes is not None else None,
                "no_votes": int(no) if no is not None else None,
                "region": CR.region_of(type_),
            })

        body = max(len(values) - 1, 1)
        lost = sum(skipped.values())
        if skipped["unreadable date"]:
            # This is the failure that hid seven months of classes. It must never be quiet again.
            log.error("tab %s: %d row(s) have a date this reader cannot understand (e.g. %s) - "
                      "those classes are NOT being synced", tab_name,
                      skipped["unreadable date"], first_bad_date)
        if lost > body * 0.2:
            log.error("tab %s: kept only %d of %d rows (%.0f%% dropped) - %s", tab_name, len(out),
                      body, 100.0 * lost / body,
                      ", ".join(f"{k}: {v}" for k, v in skipped.items() if v))
        elif lost:
            log.info("tab %s: kept %d of %d rows (%s)", tab_name, len(out), body,
                     ", ".join(f"{k}: {v}" for k, v in skipped.items() if v))
        self.last_skipped = dict(skipped)
        return out

    def fetch_rows(self) -> list[dict]:
        payload = self._get_values()
        ranges = payload.get("valueRanges") or []
        rows: list[dict] = []
        for tab_name, vr in zip(self.tabs, ranges):
            rows.extend(self._parse_tab(tab_name, vr.get("values") or []))
        # Cross-tab dedupe on the natural key (same convention as the DB unique constraint).
        seen: set = set()
        unique: list[dict] = []
        for r in rows:
            key = (r["class_date"], r["topic"], r["instructor"], r["session_kind"])
            if key in seen:
                continue
            seen.add(key)
            unique.append(r)
        log.info("sheet: %d rows across %d tab(s) (%d after dedupe)",
                 len(rows), len(self.tabs), len(unique))
        return unique
