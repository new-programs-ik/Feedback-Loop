"""
metabase.py — read low-rated classes for the PM's assigned courses from Metabase (§6.1).

Metabase stays the source of truth for the raw ratings; this module pulls the weekly
low-rated list out of it and normalises each row to the canonical shape the rest of the
system expects:

    {course, cohort, instructor, topic, class_date, rating, num_ratings, vimeo_link}

Auth (read from env / .env, never hardcoded — §10/§11):
  * METABASE_API_KEY            → sent as the `x-api-key` header (preferred, clean).
  * METABASE_USERNAME/PASSWORD  → POST /api/session for an X-Metabase-Session token (fallback).

Querying (you chose raw SQL → /api/dataset):
  * METABASE_DATABASE_ID + METABASE_SQL  → run a native SQL query.
  * METABASE_CARD_ID                     → or run a saved question/card instead.

Robustness (§11): every HTTP call has a timeout and retries on transient errors; the
response shape is validated; on auth/network failure we raise a clear error (n8n Slack-alerts).

Discovery: run ``python metabase.py --explore`` to authenticate and list databases + search
for ratings-related questions — used to find the right data without guessing column names.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

logger = logging.getLogger("metabase")

CANONICAL_FIELDS = ["course", "cohort", "instructor", "topic", "class_date",
                    "rating", "num_ratings", "vimeo_link"]
RETRY_STATUS = {429, 500, 502, 503, 504}


class MetabaseError(RuntimeError):
    """Any failure talking to Metabase (network, auth, bad response)."""


class MetabaseAuthError(MetabaseError):
    """Authentication failed (bad credentials, SSO-only login, expired key)."""


# ───────────────────────────────────────────────────────────────────────── config
@dataclass
class MetabaseConfig:
    base_url: str
    api_key: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    database_id: Optional[int] = None
    card_id: Optional[int] = None
    sql: Optional[str] = None
    assigned_courses: list[str] = field(default_factory=list)
    rating_threshold: float = 4.5
    lookback_days: int = 7
    timeout_s: float = 30.0
    max_retries: int = 3

    @classmethod
    def from_env(cls, env: Optional[dict] = None) -> "MetabaseConfig":
        env = env or os.environ
        base = (env.get("METABASE_URL") or "").rstrip("/")
        if not base:
            raise MetabaseError("METABASE_URL is not set")
        courses = [c.strip() for c in (env.get("ASSIGNED_COURSES") or "").split(",") if c.strip()]
        return cls(
            base_url=base,
            api_key=env.get("METABASE_API_KEY") or None,
            username=env.get("METABASE_USERNAME") or None,
            password=env.get("METABASE_PASSWORD") or None,
            database_id=_int_or_none(env.get("METABASE_DATABASE_ID")),
            card_id=_int_or_none(env.get("METABASE_CARD_ID")),
            sql=env.get("METABASE_SQL") or None,
            assigned_courses=courses,
            rating_threshold=float(env.get("METABASE_RATING_THRESHOLD") or 4.5),
            lookback_days=int(env.get("METABASE_LOOKBACK_DAYS") or 7),
        )


def _int_or_none(v: Any) -> Optional[int]:
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


# ───────────────────────────────────────────────────────────────────────── client
class MetabaseClient:
    """Thin Metabase REST client with auth, retries and timeouts.

    A custom httpx transport can be injected for tests (no live server needed).
    """

    def __init__(self, config: MetabaseConfig, transport: Optional[httpx.BaseTransport] = None):
        self.cfg = config
        self._session_token: Optional[str] = None
        self._client = httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout_s,
            transport=transport,
            headers={"Accept": "application/json"},
        )

    # -- auth ----------------------------------------------------------------
    def _auth_headers(self) -> dict:
        if self.cfg.api_key:
            return {"x-api-key": self.cfg.api_key}
        if self._session_token:
            return {"X-Metabase-Session": self._session_token}
        return {}

    def authenticate(self) -> None:
        """Establish a session token from username/password if no API key is set."""
        if self.cfg.api_key:
            return  # API key needs no session
        if not (self.cfg.username and self.cfg.password):
            raise MetabaseAuthError("no METABASE_API_KEY and no username/password to log in with")
        logger.info("authenticating to Metabase as %s", self.cfg.username)
        resp = self._request("POST", "/api/session",
                             json={"username": self.cfg.username, "password": self.cfg.password},
                             auth=False)
        token = resp.get("id")
        if not token:
            raise MetabaseAuthError("Metabase /api/session returned no token")
        self._session_token = token

    def _ensure_auth(self) -> None:
        if not self.cfg.api_key and not self._session_token:
            self.authenticate()

    # -- low-level request with retries --------------------------------------
    def _request(self, method: str, path: str, *, json: Any = None, params: Any = None,
                 auth: bool = True) -> Any:
        headers = self._auth_headers() if auth else {}
        last_err: Optional[Exception] = None
        for attempt in range(1, self.cfg.max_retries + 1):
            try:
                r = self._client.request(method, path, json=json, params=params, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_err = e
                logger.warning("metabase %s %s network error (try %d/%d): %s",
                               method, path, attempt, self.cfg.max_retries, e)
            else:
                if r.status_code in (401, 403):
                    raise MetabaseAuthError(f"{method} {path} → {r.status_code} (check credentials/SSO)")
                if r.status_code in RETRY_STATUS:
                    last_err = MetabaseError(f"{method} {path} → {r.status_code}")
                    logger.warning("metabase %s %s → %d (try %d/%d)",
                                   method, path, r.status_code, attempt, self.cfg.max_retries)
                elif r.is_success:
                    return r.json() if r.content else {}
                else:
                    raise MetabaseError(f"{method} {path} → {r.status_code}: {r.text[:300]}")
            if attempt < self.cfg.max_retries:
                time.sleep(min(2 ** attempt, 8))
        raise MetabaseError(f"{method} {path} failed after {self.cfg.max_retries} tries: {last_err}")

    # -- discovery -----------------------------------------------------------
    def list_databases(self) -> list[dict]:
        self._ensure_auth()
        data = self._request("GET", "/api/database")
        dbs = data.get("data", data) if isinstance(data, dict) else data
        return [{"id": d.get("id"), "name": d.get("name"), "engine": d.get("engine")} for d in dbs]

    def database_metadata(self, database_id: int) -> dict:
        self._ensure_auth()
        return self._request("GET", f"/api/database/{database_id}/metadata")

    def search(self, query: str, models: str = "card,dataset") -> list[dict]:
        """Search saved questions/models by name — used to find the ratings report."""
        self._ensure_auth()
        data = self._request("GET", "/api/search", params={"q": query, "models": models})
        items = data.get("data", data) if isinstance(data, dict) else data
        return [{"id": i.get("id"), "name": i.get("name"), "model": i.get("model"),
                 "database_id": i.get("database_id"), "collection": (i.get("collection") or {}).get("name")}
                for i in items]

    # -- queries -------------------------------------------------------------
    def run_native_query(self, sql: str, database_id: int, parameters: Optional[list] = None) -> list[dict]:
        self._ensure_auth()
        payload = {"database": database_id, "type": "native",
                   "native": {"query": sql}, "parameters": parameters or []}
        data = self._request("POST", "/api/dataset", json=payload)
        return self._rows_to_dicts(data)

    def run_card(self, card_id: int, parameters: Optional[list] = None) -> list[dict]:
        self._ensure_auth()
        data = self._request("POST", f"/api/card/{card_id}/query/json",
                             json={"parameters": parameters or []})
        # /query/json returns a plain list of row objects.
        if isinstance(data, list):
            return data
        return self._rows_to_dicts(data)

    @staticmethod
    def _rows_to_dicts(data: Any) -> list[dict]:
        """Turn a Metabase /api/dataset response ({data:{rows,cols}}) into list[dict]."""
        if isinstance(data, dict) and data.get("status") == "failed":
            raise MetabaseError(f"query failed: {data.get('error', 'unknown error')}")
        block = data.get("data") if isinstance(data, dict) else None
        if not block or "rows" not in block or "cols" not in block:
            raise MetabaseError("unexpected Metabase response shape (no data.rows/cols)")
        names = [c.get("name") for c in block["cols"]]
        return [dict(zip(names, row)) for row in block["rows"]]

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "MetabaseClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


# ──────────────────────────────────────────────────────── normalise + validate
def normalize_row(raw: dict, mapping: Optional[dict] = None) -> dict:
    """Map a source row to the canonical shape. ``mapping`` maps source→canonical names;
    defaults to identity (write SQL that aliases columns to the canonical names)."""
    mapping = mapping or {}
    src = {mapping.get(k, k): v for k, v in raw.items()}
    out = {f: src.get(f) for f in CANONICAL_FIELDS}
    out["class_date"] = _coerce_date(out.get("class_date"))
    out["rating"] = _coerce_float(out.get("rating"))
    out["num_ratings"] = _coerce_int(out.get("num_ratings"))
    return out


def validate_row(row: dict) -> list[str]:
    errs = []
    if not row.get("course"):
        errs.append("missing course")
    if row.get("rating") is None:
        errs.append("missing/!numeric rating")
    if row.get("class_date") is None:
        errs.append("missing/invalid class_date")
    return errs


def _coerce_date(v: Any) -> Optional[_dt.date]:
    if v is None or isinstance(v, _dt.date):
        return v if not isinstance(v, _dt.datetime) else v.date()
    try:
        return _dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _coerce_float(v: Any) -> Optional[float]:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _coerce_int(v: Any) -> Optional[int]:
    try:
        return int(float(v)) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


# ──────────────────────────────────────────────────────────────── main fetch
def fetch_low_rated(config: Optional[MetabaseConfig] = None, *,
                    client: Optional[MetabaseClient] = None,
                    mapping: Optional[dict] = None) -> list[dict]:
    """Pull the week's low-rated classes for the assigned courses and normalise them.

    Filters defensively in Python (rating < threshold, assigned courses) on top of whatever
    the SQL/card already filters, so a too-broad query still yields the right rows.
    """
    cfg = config or MetabaseConfig.from_env()
    owns_client = client is None
    client = client or MetabaseClient(cfg)
    try:
        if cfg.card_id:
            raw_rows = client.run_card(cfg.card_id)
        elif cfg.sql and cfg.database_id:
            raw_rows = client.run_native_query(cfg.sql, cfg.database_id)
        else:
            raise MetabaseError(
                "nothing to query: set METABASE_CARD_ID, or METABASE_DATABASE_ID + METABASE_SQL")
    finally:
        if owns_client:
            client.close()

    rows, skipped = [], 0
    for raw in raw_rows:
        row = normalize_row(raw, mapping)
        errs = validate_row(row)
        if errs:
            skipped += 1
            logger.warning("skipping malformed row %s: %s", {k: raw.get(k) for k in list(raw)[:3]}, errs)
            continue
        rows.append(row)
    if raw_rows and not rows:
        raise MetabaseError("query returned rows but none were valid — check the column mapping")

    threshold = cfg.rating_threshold
    rows = [r for r in rows if r["rating"] is not None and r["rating"] < threshold]
    if cfg.assigned_courses:
        allowed = {c.lower() for c in cfg.assigned_courses}
        rows = [r for r in rows if (r["course"] or "").lower() in allowed]
    logger.info("fetched %d low-rated class(es) (skipped %d malformed)", len(rows), skipped)
    return rows


# ───────────────────────────────────────────────────────────────────────── CLI
def _explore() -> int:
    """Authenticate and print databases + ratings-related questions (data discovery)."""
    cfg = MetabaseConfig.from_env()
    with MetabaseClient(cfg) as client:
        client.authenticate()
        print("✓ authenticated to", cfg.base_url)
        print("\n=== Databases ===")
        for d in client.list_databases():
            print(f"  id={d['id']:>3}  {d['name']}  ({d['engine']})")
        print("\n=== Questions matching ratings/feedback ===")
        seen = set()
        for term in ("rating", "feedback", "class", "instructor", "nps", "csat"):
            for hit in client.search(term):
                key = (hit["model"], hit["id"])
                if key in seen or hit["id"] is None:
                    continue
                seen.add(key)
                print(f"  [{hit['model']}] id={hit['id']}  {hit['name']}  "
                      f"(db={hit['database_id']}, collection={hit['collection']})")
    return 0


def main(argv=None) -> int:
    import config as _config
    _config.load_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    p = argparse.ArgumentParser(description="Metabase ingest for the ratings module.")
    p.add_argument("--explore", action="store_true", help="list databases + search ratings questions")
    a = p.parse_args(argv)
    if a.explore:
        return _explore()
    rows = fetch_low_rated()
    print(f"\n{len(rows)} low-rated class(es):")
    for r in rows:
        print(f"  {r['class_date']}  {r['course']} / {r['instructor']}  "
              f"rating={r['rating']} ({r['num_ratings']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
