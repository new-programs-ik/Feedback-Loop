"""ratings_store.py - persistence for the ratings sync (psycopg2, DATABASE_URL, same as store.py).

All statements are idempotent upserts on a natural key. A PM's manual state is sacred: rows with
a decision_override, or already dismissed / analysis_started, keep their decision when the sheet
re-syncs - the sync updates their numbers but never re-opens a closed call.

v3 (Sep 2026): the verdict is the Class Sentiment Score, computed INSIDE THE DATABASE by
score_class_rating() in the very statement that saves the row, with the active scoring_configs
row and the course's priors (course_priors). This module passes the nine inputs - rating,
responses, attended, yes, no, escalated, the instructor's track record, and the two course
priors - and reads score / band / action / provisional / flags back from RETURNING. `decision`
follows sentiment_action unless a PM froze it (override, dismissed, analysis started; an
escalation is always 'video'). The legacy rule-v2 read-out (decision.py: approval_pct, track_avg,
health_score, health_band, flag_reasons) is still written for one release.

Identity: a raw instructor name links to an instructor only through an EXACT normalised spelling
(instructors.normalized_name or instructor_aliases.alias_norm; merged rows point at their
survivor). Everything looser is a suggestion (instructor_match_suggestions) a human accepts.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Optional

import psycopg2
import psycopg2.errors

import cohort_parse as CP
import decision as D
import instructor_match as IM

log = logging.getLogger("ratings_store")

RULE_VERSION = "v3"          # what /health reports; decision.RULE_VERSION ("v2") is the legacy read-out

# Topic (class-name) normalisation - the twin of SQL normalize_topic_name(): lower, ASCII-fold, every
# run of non-[a-z0-9] becomes one space, trim. Person names use instructor_match.normalize instead.
TOPIC_JUNK = frozenset({"live class", "test review session", "test review", "live session",
                        "other", "class", "session", "live"})   # kind codes, never a topic (0017's list)


def normalize_topic_name(name) -> str:
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _url() -> str:
    return os.environ.get("DATABASE_URL", "").replace("postgresql+psycopg2://", "postgresql://")


def connect():
    url = _url()
    if not url:
        raise RuntimeError("DATABASE_URL is not set - the ratings sync cannot run")
    return psycopg2.connect(url, connect_timeout=15)


# ── reference data ───────────────────────────────────────────────────────────

def load_aliases(cur) -> dict[str, str]:
    """Sheet course label -> courses.id (course_aliases)."""
    cur.execute("select alias, course_id from course_aliases")
    return {alias: str(cid) for alias, cid in cur.fetchall()}


def load_courses(cur) -> dict[str, dict]:
    """courses.id -> {id, name, slug} (the slug keys cohorts and builds the Slack links)."""
    cur.execute("select id, name, slug from courses")
    return {str(i): {"id": str(i), "name": n, "slug": s} for i, n, s in cur.fetchall()}


def active_scoring_config(cur) -> Optional[dict]:
    """The active scoring_configs row as {id, version, key, name, status, config}; None if nothing is active."""
    cur.execute("select id, version, key, name, status, config from active_scoring_config()")
    r = cur.fetchone()
    if not r:
        return None
    cfg = r[5]
    if isinstance(cfg, (str, bytes)):
        cfg = json.loads(cfg)
    return {"id": str(r[0]), "version": r[1], "key": r[2], "name": r[3], "status": r[4], "config": cfg or {}}


_cfg_cache: dict = {"at": 0.0, "version": None, "ttl": 600.0}


def remember_config_version(version) -> None:
    """The sync tells /health which version it just scored with (saves /health a DB round trip)."""
    _cfg_cache.update(at=time.monotonic(), version=version)


def cached_config_version(now: Optional[float] = None) -> Optional[int]:
    """For /health: the active scoring-config version, cached for ten minutes; None when there is
    no DATABASE_URL, no active config, or the database cannot be reached (never raises)."""
    now = time.monotonic() if now is None else now
    if _cfg_cache["version"] is not None and now - _cfg_cache["at"] < _cfg_cache["ttl"]:
        return _cfg_cache["version"]
    if now - _cfg_cache["at"] < 60.0 and _cfg_cache["at"] > 0:
        return _cfg_cache["version"]                     # a recent miss: do not hammer the DB
    version = None
    if _url():
        conn = None
        try:
            conn = psycopg2.connect(_url(), connect_timeout=5)
            cur = conn.cursor()
            cfg = active_scoring_config(cur)
            version = cfg["version"] if cfg else None
        except Exception:                                # pragma: no cover - network / missing function
            log.warning("scoring config version lookup failed", exc_info=True)
        finally:
            if conn is not None:
                try:
                    conn.rollback()
                    conn.close()
                except Exception:
                    pass
    _cfg_cache.update(at=now, version=version)
    return version


# ── instructors ──────────────────────────────────────────────────────────────

class InstructorResolver:
    """normalised spelling -> (instructor id, canonical name); exact spellings only."""

    def __init__(self, by_norm: dict[str, tuple[str, str]], candidates: dict[str, IM.Candidate]):
        self.by_norm = by_norm
        self._candidates = candidates

    def __call__(self, raw_name) -> tuple[Optional[str], Optional[str]]:
        hit = self.by_norm.get(IM.normalize(raw_name))
        return (hit[0], hit[1]) if hit else (None, None)

    def candidates(self) -> list[IM.Candidate]:
        """The people a stray spelling could be: canonical (unmerged) instructors + their spellings."""
        return list(self._candidates.values())

    def __len__(self) -> int:
        return len(self.by_norm)


def load_instructor_resolver(cur) -> InstructorResolver:
    """Map alias_norm / normalized_name -> (id, canonical) from instructors not merged, plus aliases.
    A merged instructor's own name resolves to its survivor; chains are followed."""
    cur.execute("select id, name, coalesce(normalized_name, normalize_person_name(name)), merged_into "
                "from instructors")
    rows = [(str(i), n, norm, str(m) if m else None) for i, n, norm, m in cur.fetchall()]
    by_id = {i: (n, norm, m) for i, n, norm, m in rows}

    def survivor(iid: str) -> str:
        seen = set()
        while by_id.get(iid, (None, None, None))[2] and iid not in seen:
            seen.add(iid)
            iid = by_id[iid][2]
        return iid

    by_norm: dict[str, tuple[str, str]] = {}
    spellings: dict[str, set] = {}
    for iid, name, norm, _merged in rows:
        sid = survivor(iid)
        canonical = by_id[sid][0]
        if norm:
            by_norm.setdefault(norm, (sid, canonical))
        spellings.setdefault(sid, set()).add(name)
    cur.execute("select a.alias, a.alias_norm, a.instructor_id from instructor_aliases a")
    for alias, alias_norm, iid in cur.fetchall():
        sid = survivor(str(iid))
        if sid not in by_id:
            continue
        by_norm.setdefault(alias_norm or IM.normalize(alias), (sid, by_id[sid][0]))
        spellings.setdefault(sid, set()).add(alias)
    candidates = {sid: IM.Candidate(sid, by_id[sid][0], tuple(sorted(s - {by_id[sid][0]})))
                  for sid, s in spellings.items() if by_id[sid][2] is None}
    return InstructorResolver(by_norm, candidates)


def write_suggestions(cur, suggestions) -> int:
    """Upsert instructor_match_suggestions; a pending one refreshes, an accepted / rejected one is
    left alone ("not the same person" is never asked again). Returns how many are new."""
    created = 0
    for s in suggestions:
        cur.execute(
            """
            insert into instructor_match_suggestions
              (raw_name, raw_norm, candidate_instructor_id, score, method, evidence, status,
               first_seen_at, last_seen_at)
            values (%s, %s, %s::uuid, least(%s, 0.99), %s, %s::jsonb, 'pending', now(), now())
            on conflict (raw_norm, candidate_instructor_id) do update set
              raw_name = excluded.raw_name, score = excluded.score, method = excluded.method,
              evidence = excluded.evidence, last_seen_at = now()
              where instructor_match_suggestions.status = 'pending'
            returning (xmax = 0) as created
            """,
            (s.raw_name, s.raw_norm, s.candidate_id, s.score, s.method, json.dumps(s.evidence)))
        r = cur.fetchone()
        if r and r[0]:
            created += 1
    return created


# ── cohorts and topics ───────────────────────────────────────────────────────

def upsert_cohorts(cur, parsed, course_id: Optional[str], *, aliases: Optional[dict] = None,
                   courses: Optional[dict] = None, cache: Optional[dict] = None,
                   stats: Optional[Counter] = None, source: str = "sheet") -> list[Optional[str]]:
    """One cohorts.id per ParsedCohort (None when its course is unknown), creating rows that are
    new. Each segment's own course wins (a cell can name cohorts of two courses); `course_id` is
    the row's course, the fallback. Keys use courses.slug, names courses.name. `cache`
    (cohort_key -> id) spans a run; `stats['cohorts_created']` counts inserts."""
    ids: list[Optional[str]] = []
    for p in parsed:
        cid = (aliases or {}).get(p.course_label) or course_id
        if not cid:
            ids.append(None)
            continue
        course = (courses or {}).get(str(cid)) or {"name": p.course_label, "slug": CP.slugify(p.course_label)}
        key, name = p.key_for(course["slug"]), p.name_for(course["name"])
        if cache is not None and key in cache:
            ids.append(cache[key])
            continue
        params = {"course_id": cid, "name": name, "region": p.region, "start_month": p.start_month,
                  "part": p.part, "ordinal": p.intake_ordinal, "cohort_no": p.cohort_no,
                  "audience": p.audience, "key": key, "source": source, "raw_labels": [p.raw_label]}
        cur.execute("savepoint cohort_upsert")
        try:
            cur.execute(
                """
                insert into cohorts (course_id, name, region, start_month, start_part, intake_ordinal,
                                     cohort_no, audience, cohort_key, source, raw_labels)
                values (%(course_id)s::uuid, %(name)s, %(region)s, %(start_month)s, %(part)s, %(ordinal)s,
                        %(cohort_no)s, %(audience)s, %(key)s, %(source)s, %(raw_labels)s::text[])
                on conflict (cohort_key) do update set
                  name = excluded.name, region = excluded.region, start_month = excluded.start_month,
                  start_part = excluded.start_part, intake_ordinal = excluded.intake_ordinal,
                  cohort_no = coalesce(excluded.cohort_no, cohorts.cohort_no),
                  audience = coalesce(excluded.audience, cohorts.audience),
                  raw_labels = (select array_agg(distinct x) from unnest(coalesce(cohorts.raw_labels, '{}'::text[])
                                                                         || excluded.raw_labels) x)
                returning id, (xmax = 0) as created
                """, params)
            rid, created = cur.fetchone()
            cur.execute("release savepoint cohort_upsert")
        except psycopg2.errors.UniqueViolation:
            # A pre-v3 cohort row with this (course_id, name) and no cohort_key: adopt it.
            cur.execute("rollback to savepoint cohort_upsert")
            cur.execute(
                "update cohorts set cohort_key = %(key)s, region = %(region)s, start_month = %(start_month)s, "
                "start_part = %(part)s, intake_ordinal = %(ordinal)s, cohort_no = %(cohort_no)s, "
                "audience = %(audience)s, raw_labels = %(raw_labels)s::text[] "
                "where course_id = %(course_id)s::uuid and name = %(name)s returning id", params)
            r = cur.fetchone()
            rid, created = (r[0], False) if r else (None, False)
            cur.execute("release savepoint cohort_upsert")    # a rolled-back savepoint still exists
        rid = str(rid) if rid else None
        if created and stats is not None:
            stats["cohorts_created"] += 1
        if cache is not None and rid:
            cache[key] = rid
        ids.append(rid)
    return ids


def resolve_topic(cur, course_id: Optional[str], topic: str, *, cache: Optional[dict] = None,
                  unmapped: Optional[Counter] = None) -> Optional[str]:
    """topics.id for a class name via topics.name_norm or topic_aliases.alias_norm (per course,
    cached per run). Unknown names are counted in `unmapped[(course_id, topic)]`; ensure_topics()
    creates them after the loop."""
    if not course_id or not (topic or "").strip():
        return None
    cache = cache if cache is not None else {}
    if course_id not in cache:
        cur.execute("select name_norm, id from topics where course_id = %s::uuid", (course_id,))
        m = {n: str(i) for n, i in cur.fetchall()}
        cur.execute("select alias_norm, topic_id from topic_aliases where course_id = %s::uuid", (course_id,))
        for n, i in cur.fetchall():
            m.setdefault(n, str(i))
        cache[course_id] = m
    norm = normalize_topic_name(topic)
    if not norm or norm in TOPIC_JUNK:
        return None                                  # a kind code is not a class name
    tid = cache[course_id].get(norm)
    if tid is None and unmapped is not None:
        unmapped[(course_id, topic.strip())] += 1
    return tid


def ensure_topics(cur, unmapped: Counter) -> dict:
    """Create the topics the sync could not map, with the seed's rule (0017): per (course,
    normalised name) the most frequent spelling becomes the topic's name and its alias; kind codes
    never become topics. Then point every class row still without a topic at them. Additive."""
    groups: dict[tuple, Counter] = {}
    for (course_id, topic), n in unmapped.items():
        norm = normalize_topic_name(topic)
        if not course_id or not norm or norm in TOPIC_JUNK:
            continue
        groups.setdefault((course_id, norm), Counter())[topic.strip()] += n
    out = {"topics_created": 0, "aliases_created": 0, "rows_backfilled": 0}
    for (course_id, norm), spellings in groups.items():
        name = spellings.most_common(1)[0][0]
        cur.execute(
            "insert into topics (course_id, name, name_norm) values (%s::uuid, %s, %s) "
            "on conflict (course_id, name_norm) do update set name = topics.name "
            "returning id, (xmax = 0) as created", (course_id, name, norm))
        tid, created = cur.fetchone()
        out["topics_created"] += 1 if created else 0
        cur.execute(
            "insert into topic_aliases (course_id, alias, alias_norm, topic_id) values (%s::uuid, %s, %s, %s::uuid) "
            "on conflict (course_id, alias_norm) do nothing returning id", (course_id, name, norm, tid))
        if cur.fetchone():
            out["aliases_created"] += 1
    if groups:
        cur.execute(
            "update class_ratings r set topic_id = a.topic_id from topic_aliases a "
            "where r.topic_id is null and a.course_id = r.course_id "
            "and a.alias_norm = normalize_topic_name(r.topic)")
        out["rows_backfilled"] = max(0, getattr(cur, "rowcount", 0) or 0)
    return out


# ── sync runs ────────────────────────────────────────────────────────────────

def start_run(cur, source: str, trigger: str) -> str:
    cur.execute(
        "insert into sync_runs(source, trigger, status) values (%s,%s,'running') returning id",
        (source, trigger))
    return str(cur.fetchone()[0])


def finish_run(cur, run_id: str, *, status: str, rows_fetched: int = 0, rows_upserted: int = 0,
               rows_flagged: int = 0, notifications_sent: int = 0,
               unmapped_labels: Optional[list[str]] = None, error: str = "",
               rows_scored: Optional[int] = None, scoring_config_version=None,
               band_counts: Optional[dict] = None, cohorts_created: Optional[int] = None,
               cohorts_unparsed: Optional[int] = None, instructors_unresolved: Optional[int] = None,
               suggestions_created: Optional[int] = None, topics_unmapped: Optional[int] = None,
               duration_ms: Optional[int] = None, rows_unchanged: Optional[int] = None) -> None:
    cur.execute(
        """
        update sync_runs set status=%s, rows_fetched=%s, rows_upserted=%s, rows_flagged=%s,
          notifications_sent=%s, unmapped_labels=%s, error=nullif(%s,''), finished_at=now(),
          rows_scored=%s, scoring_config_version=%s, band_counts=%s::jsonb, cohorts_created=%s,
          cohorts_unparsed=%s, instructors_unresolved=%s, suggestions_created=%s, topics_unmapped=%s,
          duration_ms=%s, rows_unchanged=%s
        where id=%s
        """,
        (status, rows_fetched, rows_upserted, rows_flagged, notifications_sent,
         sorted(set(unmapped_labels or [])) or None, error,
         rows_scored, scoring_config_version,
         json.dumps(band_counts) if band_counts is not None else None,
         cohorts_created, cohorts_unparsed, instructors_unresolved, suggestions_created,
         topics_unmapped, duration_ms, rows_unchanged, run_id))


def recompute_week_numbers(cur) -> int:
    """Week numbers count from the cohort's first class. A class added later with an earlier date
    moves that start, and rows the sync skips would keep a number that is now one too low. One
    statement per run puts every cohort right."""
    cur.execute(
        "with m as (select cohort_id, min(class_date) as first from class_ratings "
        "            where cohort_id is not null group by cohort_id) "
        "update class_ratings r set week_no = 1 + (r.class_date - m.first) / 7 from m "
        " where r.cohort_id = m.cohort_id "
        "   and r.week_no is distinct from 1 + (r.class_date - m.first) / 7")
    return cur.rowcount


def heartbeat_run(run_id: str) -> None:
    """Say "still here" from inside a long run. On its own connection, because the run's own
    transaction is not visible to anyone until it commits. Best-effort."""
    conn = None
    try:
        conn = connect()
        cur = conn.cursor()
        cur.execute("update sync_runs set heartbeat_at = now() where id = %s", (run_id,))
        conn.commit()
    except Exception:
        log.warning("heartbeat failed for run %s", run_id, exc_info=True)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def mark_stale_runs(cur, older_than_minutes: int = 10) -> int:
    """A sync lives inside the worker process; a restart or redeploy mid-run leaves its row on
    "running" forever, and the page shows a run that is not there. Mark such rows failed."""
    cur.execute(
        "update sync_runs set status='failed', finished_at=now(), error=%s "
        " where status='running' "
        "   and coalesce(heartbeat_at, started_at) < now() - make_interval(mins => %s) returning id",
        (f"no result after {older_than_minutes} minutes - the worker was probably restarted mid-sync",
         older_than_minutes))
    return len(cur.fetchall())


RETIRE_MAX_SHARE = 0.05     # never remove more than this share of a run's candidates...
RETIRE_MAX_ABS = 50         # ...nor more than this many rows, in one run


def retire_rows_missing_from_sheet(cur, seen_keys: set, source: str = "sheet",
                                   seen_labels: set | None = None) -> int:
    """Rows this source wrote that the sheet no longer has, and nobody touched, are removed.

    A corrected instructor spelling on the sheet makes a new row (the spelling is part of the key)
    and used to leave the old one behind forever: the same class twice, one instructor under two
    names, on every page and in every report (123 such rows by 21 Sep 2026). Rows a person has
    acted on - reviewed, linked to an analysis, overridden, escalated - are never touched.

    Two guards, because a delete is the one step that cannot be undone by the next run: only rows
    whose course label appeared in this run are candidates (a tab that parsed to nothing must not
    take its history with it), and a run that would remove more than a small share refuses and
    logs instead - that is a sheet problem for a person to look at, not a clean-up.
    """
    cur.execute("select id, class_date, topic, instructor, session_kind, course_label from class_ratings "
                " where source = %s and review_status = 'new' and class_id is null "
                "   and decision_override is null and not coalesce(escalated, false)", (source,))
    candidates = cur.fetchall()
    gone = [str(rid) for rid, d, t, i, k, label in candidates
            if (seen_labels is None or label in seen_labels) and (d, t, i or "", k) not in seen_keys]
    if not gone:
        return 0
    limit = max(RETIRE_MAX_ABS, int(len(candidates) * RETIRE_MAX_SHARE))
    if len(gone) > limit:
        log.error("refusing to remove %d rows the sheet no longer has (limit %d this run): "
                  "check the sheet before anything is deleted", len(gone), limit)
        return 0
    cur.execute("delete from class_ratings where id = any(%s::uuid[])", (gone,))
    cur.execute("insert into audit_log(actor_label, action, detail) values ('worker', 'stale_rows_removed', %s)",
                (json.dumps({"count": len(gone), "reason": "no longer on the sheet; untouched"}),))
    return len(gone)


def running_run_exists(cur, max_age_minutes: int = 10) -> bool:
    """Concurrent-run guard: a 'running' row younger than the cutoff means skip this trigger."""
    cur.execute(
        "select 1 from sync_runs where status='running' "
        "and coalesce(heartbeat_at, started_at) > now() - make_interval(mins => %s) limit 1",
        (max_age_minutes,))
    return cur.fetchone() is not None


# ── the scored upsert ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class UpsertResult:
    id: str
    decision: str
    review_status: str
    score: Optional[float] = None
    band: Optional[str] = None
    action: Optional[str] = None
    provisional: bool = False
    flags: tuple = ()

    def __iter__(self):
        """Backwards-compatible unpacking: id, decision, review_status."""
        return iter((self.id, self.decision, self.review_status))


def prior_state(cur, row: dict, instructor_id: Optional[str] = None,
                min_classes: int = D.T_MIN_CLASSES) -> tuple[bool, Optional[float]]:
    """What the table already knows that the verdict needs, in one round trip:
    - the PM's escalation toggle on this row (false for a row never seen), and
    - the instructor's track record: their average rating over classes dated strictly before this
      one, None until there are `min_classes` of them. Counted by instructor_id when the name
      resolved (every spelling of the person counts), by the raw name string otherwise. A blank
      name with no id gets no track record (it would pool every nameless row into one phantom)."""
    cur.execute(
        """
        select coalesce((select escalated from class_ratings
                          where class_date=%(class_date)s and topic=%(topic)s
                            and instructor=%(instructor)s and session_kind=%(session_kind)s), false),
               t.avg_rating, t.n
        from (select avg(rating) as avg_rating, count(*) as n
                from class_ratings
               where class_date < %(class_date)s
                 and case when %(instructor_id)s::uuid is not null
                          then instructor_id = %(instructor_id)s::uuid
                          else instructor = %(instructor)s end) t
        """,
        {"class_date": row["class_date"], "topic": row["topic"], "instructor": row.get("instructor") or "",
         "session_kind": row["session_kind"], "instructor_id": instructor_id})
    escalated, avg, n = cur.fetchone()
    has_identity = bool(instructor_id) or bool(row.get("instructor"))
    track = round(float(avg), 2) if has_identity and avg is not None and n >= min_classes else None
    return bool(escalated), track


# ---- what the sheet says about a row, as one short string -------------------------------------
FINGERPRINT_VERSION = "fp1"      # bump to push every row through the next sync (logic changes)
FINGERPRINT_FIELDS = ("course_label", "cohort_text", "topic", "instructor", "class_date",
                      "session_kind", "rating", "num_ratings", "attended", "yes_votes", "no_votes",
                      "region")


def row_fingerprint(row: dict) -> str:
    """Same sheet values -> same fingerprint. Stored on the class row; a match means the sync has
    nothing to do for that class. Fields the app writes (review status, escalation, overrides) are
    deliberately not in it: they do not come from the sheet."""
    parts = [FINGERPRINT_VERSION]
    for key in FINGERPRINT_FIELDS:
        v = row.get(key)
        parts.append("" if v is None else str(v))
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()


def row_key(row: dict) -> tuple:
    """The upsert's conflict target, so a sheet row finds its stored class."""
    return (row["class_date"], row["topic"], row.get("instructor") or "", row["session_kind"])


def load_row_state(cur) -> dict:
    """Every stored class -> (fingerprint, band, action, scored?, course mapped?), in one round
    trip, so the loop can skip unchanged rows and still report whole-sheet totals. An unmapped row
    is never skipped: the alias that maps it may have arrived since."""
    cur.execute("select class_date, topic, instructor, session_kind, row_hash, sentiment_band, "
                "sentiment_action, sentiment_score is not null, course_id is not null from class_ratings")
    return {(d, t, i or "", k): (h, b, a, bool(s), bool(m)) for d, t, i, k, h, b, a, s, m in cur.fetchall()}


# The nine score inputs go to score_class_rating() inside the statement; the config comes from
# active_scoring_config(), the priors from course_priors(). Nothing is inserted when no config is
# active (the CTE is empty) - upsert_rating turns that into a loud error.
UPSERT_SQL = """
with cfg as (select id as config_id, config from active_scoring_config()),
     pri as (select prior_rating, prior_approval from course_priors(%(course_id)s::uuid)),
     s as (
       select cfg.config_id, sc.score, sc.band, sc.action, sc.provisional, sc.flags, sc.components
       from cfg
       cross join lateral score_class_rating(
            %(rating)s::numeric, %(num_ratings)s::int, %(attended)s::int,
            %(yes_votes)s::int, %(no_votes)s::int, %(escalated)s::boolean, %(track_avg)s::numeric,
            (select prior_rating from pri), (select prior_approval from pri), cfg.config) sc
     )
insert into class_ratings
  (source, course_label, course_id, cohort_text, topic, instructor, instructor_id, instructor_canonical,
   class_date, session_kind, rating, num_ratings, attended, participation_pct,
   yes_votes, no_votes, approval_pct, track_avg, health_score, health_band, flag_reasons,
   cohort_id, cohort_ids, topic_id, week_no,
   sentiment_score, sentiment_band, sentiment_action, sentiment_provisional, sentiment_flags,
   score_config_id, score_components, scored_at, decision_v2, decision, row_hash)
select %(source)s, %(course_label)s, %(course_id)s::uuid, %(cohort_text)s, %(topic)s, %(instructor)s,
       %(instructor_id)s::uuid, %(instructor_canonical)s, %(class_date)s::date, %(session_kind)s,
       %(rating)s, %(num_ratings)s, %(attended)s, %(pct)s,
       %(yes_votes)s, %(no_votes)s, %(approval_pct)s, %(track_avg)s, %(health_score)s, %(health_band)s,
       %(flag_reasons)s::text[],
       %(cohort_id)s::uuid, %(cohort_ids)s::uuid[], %(topic_id)s::uuid,
       case when %(cohort_id)s::uuid is null then null
            else 1 + (%(class_date)s::date
                      - least(%(class_date)s::date,
                              coalesce((select min(x.class_date) from class_ratings x
                                         where x.cohort_id = %(cohort_id)s::uuid), %(class_date)s::date))) / 7
       end,
       s.score, s.band, s.action, s.provisional, s.flags, s.config_id, s.components, now(),
       %(decision_v2)s::rating_decision,
       (case when %(escalated)s::boolean then 'video' else coalesce(s.action, 'watch') end)::rating_decision,
       %(row_hash)s
from s
on conflict (class_date, topic, instructor, session_kind) do update set
  source               = excluded.source,
  course_label         = excluded.course_label,
  course_id            = coalesce(excluded.course_id, class_ratings.course_id),
  cohort_text          = excluded.cohort_text,
  instructor_id        = coalesce(excluded.instructor_id, class_ratings.instructor_id),
  instructor_canonical = coalesce(excluded.instructor_canonical, class_ratings.instructor_canonical),
  rating               = excluded.rating,
  num_ratings          = excluded.num_ratings,
  attended             = excluded.attended,
  participation_pct    = excluded.participation_pct,
  -- the vote, the legacy read-out and the score always follow the latest numbers:
  yes_votes            = excluded.yes_votes,
  no_votes             = excluded.no_votes,
  approval_pct         = excluded.approval_pct,
  track_avg            = excluded.track_avg,
  health_score         = excluded.health_score,
  health_band          = excluded.health_band,
  flag_reasons         = excluded.flag_reasons,
  cohort_id            = coalesce(excluded.cohort_id, class_ratings.cohort_id),
  cohort_ids           = coalesce(nullif(excluded.cohort_ids, '{}'::uuid[]), class_ratings.cohort_ids),
  topic_id             = coalesce(excluded.topic_id, class_ratings.topic_id),
  week_no              = coalesce(excluded.week_no, class_ratings.week_no),
  sentiment_score      = excluded.sentiment_score,
  sentiment_band       = excluded.sentiment_band,
  sentiment_action     = excluded.sentiment_action,
  sentiment_provisional = excluded.sentiment_provisional,
  sentiment_flags      = excluded.sentiment_flags,
  score_config_id      = excluded.score_config_id,
  score_components     = excluded.score_components,
  scored_at            = excluded.scored_at,
  decision_v2          = coalesce(class_ratings.decision_v2, excluded.decision_v2),   -- one-time snapshot
  -- the sync's verdict applies only while the row is untouched by a human:
  decision = case
    when class_ratings.decision_override is not null then class_ratings.decision
    when class_ratings.review_status in ('dismissed','analysis_started') then class_ratings.decision
    when class_ratings.escalated then 'video'::rating_decision
    else excluded.decision
  end,
  row_hash = excluded.row_hash,
  synced_at = now(), updated_at = now()
returning id, decision, review_status, sentiment_score, sentiment_band, sentiment_action,
          sentiment_provisional, sentiment_flags
"""


def upsert_rating(cur, row: dict, course_id: Optional[str], instructor_id: Optional[str], *,
                  instructor_canonical: Optional[str] = None, cohort_ids: Optional[list] = None,
                  topic_id: Optional[str] = None,
                  min_track_classes: int = D.T_MIN_CLASSES) -> UpsertResult:
    """Insert or refresh one class_ratings row, scored by the database in the same statement.
    `cohort_ids[0]` is the primary cohort (week numbers count from its first class seen)."""
    pct = (round(row["num_ratings"] / row["attended"] * 100, 1)
           if row.get("num_ratings") is not None and row.get("attended") else None)
    approval = D.approval_pct(row.get("yes_votes"), row.get("no_votes"))
    escalated, track = prior_state(cur, row, instructor_id, min_track_classes)
    legacy = D.decide_v2(row["rating"], row.get("num_ratings"), row.get("attended"),
                         escalated=escalated, approval_pct=approval, track_avg=track)
    cohort_ids = [c for c in (cohort_ids or []) if c]
    cur.execute(UPSERT_SQL, {
        **row, "source": row.get("source", "sheet"), "course_id": course_id,
        "instructor_id": instructor_id, "instructor_canonical": instructor_canonical,
        "pct": pct, "yes_votes": row.get("yes_votes"), "no_votes": row.get("no_votes"),
        "approval_pct": approval, "track_avg": track, "escalated": escalated,
        "health_score": legacy.health_score, "health_band": legacy.health_band,
        "flag_reasons": list(legacy.flag_reasons), "decision_v2": legacy.decision,
        "cohort_id": cohort_ids[0] if cohort_ids else None, "cohort_ids": cohort_ids,
        "topic_id": topic_id, "row_hash": row_fingerprint(row),
    })
    r = cur.fetchone()
    if r is None:
        raise RuntimeError("no active scoring config - activate a scoring version (Admin > Scoring) "
                           "before syncing; nothing was written for this row")
    rid, dec, status, score, band, action, provisional, flags = r
    return UpsertResult(str(rid), dec, status,
                        float(score) if score is not None else None, band, action,
                        bool(provisional), tuple(flags or ()))


# ── notifications ────────────────────────────────────────────────────────────

def rows_needing_notification(cur, max_age_days: Optional[int] = None,
                              limit: Optional[int] = None) -> list[dict]:
    """Flagged (video / transcript), still 'new', mapped to a course, never pinged - newest first.
    Each row carries `recipients`: the course's members with Slack on (course-level, or scoped to
    one of the class's cohorts), handlers first; when the course has no members at all, the legacy
    course_handlers row; otherwise an empty list (the card then says "no owner assigned")."""
    cur.execute(
        """
        select cr.id, cr.topic, cr.instructor, cr.instructor_canonical, cr.class_date, cr.session_kind,
               cr.rating, cr.num_ratings, cr.attended, cr.participation_pct, cr.decision,
               cr.yes_votes, cr.no_votes, cr.approval_pct, cr.health_score, cr.health_band, cr.flag_reasons,
               cr.sentiment_score, cr.sentiment_band, cr.sentiment_action, cr.sentiment_provisional,
               cr.sentiment_flags, cr.cohort_id, cr.course_id,
               c.name as course_name, c.slug as course_slug,
               h.handler_name, h.handler_email, h.slack_user_id, h.id as handler_id,
               coalesce((select json_agg(json_build_object(
                             'id', m.id, 'name', m.display_name, 'email', m.email,
                             'slack_user_id', m.slack_user_id, 'is_handler', m.is_handler, 'role', m.role)
                                         order by m.is_handler desc nulls last, m.display_name)
                           from course_members m
                          where m.course_id = cr.course_id
                            and coalesce(m.notify_slack, true)
                            and (m.cohort_id is null or m.cohort_id = cr.cohort_id
                                 or m.cohort_id = any(coalesce(cr.cohort_ids, '{}'::uuid[])))),
                        '[]'::json) as members,
               (select count(*) from course_members m2 where m2.course_id = cr.course_id) as members_total
        from class_ratings cr
        join courses c on c.id = cr.course_id
        left join course_handlers h on h.course_id = cr.course_id
        left join rating_notifications n
               on n.class_rating_id = cr.id and n.channel = 'slack'
              and n.status is distinct from 'failed'
              -- A claim ('sending') that never turned into 'sent' or 'failed' is a run that died
              -- between the claim and the answer; after a while it counts as failed.
              and not (n.status = 'sending' and n.sent_at < now() - interval '15 minutes')
        where cr.decision in ('video','transcript')
          and cr.review_status = 'new'
          -- A row that says the send FAILED is not a record that the class was handled; it is a
          -- record that it was not. Excluding every row regardless of status meant one rate-limit
          -- reply from Slack buried a flagged class permanently, with nobody told.
          and n.id is null
          and (%(max_age_days)s::int is null or cr.class_date >= current_date - %(max_age_days)s::int)
        order by cr.class_date desc, cr.sentiment_score asc nulls last
        limit %(limit)s
        """, {"max_age_days": max_age_days, "limit": limit})
    cols = [d[0] for d in cur.description]
    out = []
    for r in cur.fetchall():
        row = dict(zip(cols, r))
        row["id"] = str(row["id"])
        members = row.pop("members", None) or []
        if isinstance(members, (str, bytes)):
            members = json.loads(members)
        recipients = [{"id": str(m.get("id")), "name": m.get("name"), "email": m.get("email"),
                       "slack_user_id": m.get("slack_user_id"), "is_handler": bool(m.get("is_handler")),
                       "source": "member"} for m in members]
        if not recipients and not (row.pop("members_total", 0) or 0) and row.get("handler_email"):
            recipients = [{"id": str(row["handler_id"]), "name": row.get("handler_name"),
                           "email": row.get("handler_email"), "slack_user_id": row.get("slack_user_id"),
                           "is_handler": True, "source": "handler"}]
        row.pop("members_total", None)
        row["recipients"] = recipients
        out.append(row)
    return out


STALE_CLAIM_MINUTES = 15


def record_notification(cur, class_rating_id: str, *, channel: str = "slack",
                        recipient: str = "", status: str = "sending",
                        slack_ts: str = "", error: str = "") -> bool:
    """The dedupe gate: only the caller whose INSERT wins may actually send. Returns won.

    The row is written as a claim ('sending') and the caller commits it BEFORE talking to Slack,
    then records the answer with `finish_notification`. Ordered that way, a worker that dies
    mid-send leaves a claim, not a second card: the claim blocks the next run for a while and
    then counts as failed, so the class is still told about, once.

    A row left over from a FAILED send, or a claim older than STALE_CLAIM_MINUTES, is claimed
    rather than blocking: the class still needs telling somebody.
    """
    cur.execute(
        "insert into rating_notifications(class_rating_id, channel, recipient, status, slack_ts, error, sent_at) "
        "values (%s,%s,%s,%s,nullif(%s,''),nullif(%s,''),now()) "
        "on conflict (class_rating_id, channel) do update "
        "   set status = excluded.status, recipient = excluded.recipient, "
        "       slack_ts = excluded.slack_ts, error = excluded.error, sent_at = now() "
        " where rating_notifications.status = 'failed' "
        "    or (rating_notifications.status = 'sending' "
        "        and rating_notifications.sent_at < now() - make_interval(mins => %s)) "
        "returning id",
        (class_rating_id, channel, recipient, status, slack_ts, error, STALE_CLAIM_MINUTES))
    return cur.fetchone() is not None


def finish_notification(cur, class_rating_id: str, *, ok: bool, slack_ts: str = "",
                        error: str = "", channel: str = "slack") -> None:
    """Turn the claim into the answer: 'sent' with Slack's message id, or 'failed' with the reason."""
    cur.execute(
        "update rating_notifications set status=%s, slack_ts=nullif(%s,''), error=nullif(%s,''), sent_at=now() "
        "where class_rating_id=%s and channel=%s",
        ("sent" if ok else "failed", slack_ts, (error or "")[:400], class_rating_id, channel))


def reset_stuck_analyses(cur, older_than_minutes: int = 90, scheduled_minutes: int = 15) -> int:
    """Classes whose analysis never finished, or never started, released so a PM can retry them.

    Two ways a class gets stuck. A job lives inside the worker process: if that process is
    restarted, redeployed or killed for memory, no exception is raised and the class sits on
    "analyzing" forever. And the website marks a class "scheduled" before asking the worker; if the
    worker was unreachable or refused, nobody moves it on. Both are swept here - at the start of
    every sync and before every new job - so Retry always has something it can claim.
    """
    cur.execute(
        "with old as ("
        "  select id, status from classes"
        "  where (status='analyzing' and updated_at < now() - make_interval(mins => %s))"
        "     or (status='scheduled' and updated_at < now() - make_interval(mins => %s)))"
        " update classes c set status='failed', updated_at=now() from old"
        " where c.id = old.id returning c.id, old.status",
        (older_than_minutes, scheduled_minutes))
    stuck = cur.fetchall()
    for class_id, was in stuck:
        if was == "scheduled":
            message = (f"the analysis was never picked up within {scheduled_minutes} minutes - the "
                       "worker was unreachable or refused it; released for retry")
        else:
            message = (f"no result after {older_than_minutes} minutes - the worker was probably "
                       "restarted mid-analysis; released for retry")
        cur.execute(
            "insert into audit_log(class_id, actor_label, action, detail) "
            "values (%s,'worker','error',%s)",
            (class_id, json.dumps({"where": "analyze", "message": message})))
    return len(stuck)


def mark_notified(cur, class_rating_id: str) -> None:
    cur.execute(
        "update class_ratings set review_status='notified', updated_at=now() "
        "where id=%s and review_status='new'", (class_rating_id,))


def cache_slack_user(cur, handler_id: str, slack_user_id: str) -> None:
    cur.execute("update course_handlers set slack_user_id=%s, updated_at=now() where id=%s",
                (slack_user_id, handler_id))


def cache_member_slack_user(cur, member_id: str, slack_user_id: str) -> None:
    cur.execute("update course_members set slack_user_id=%s where id=%s", (slack_user_id, member_id))
