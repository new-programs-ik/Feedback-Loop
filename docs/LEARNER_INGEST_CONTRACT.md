# Learner-level ratings — the ingestion contract

> Status: **designed, not fed.** The tables exist (migration `0020_learner_contract.sql`) and are
> empty. No learner-level export exists yet — the ratings workbook holds not a single email. When
> an export arrives, it plugs into these tables without touching the class layer.

## 1. What the layer is for

Today every number we have is per **class** (one row per session in `class_ratings`: the average
rating, how many responded, the Yes/No vote). The learner layer adds **one row per learner per
rated class**, keyed to the class row we already have. It answers questions the class layer
cannot:

- Who is consistently below the room? (learner × week heatmap vs the cohort median)
- Who is about to churn? (attendance falling + rating falling + "no" votes)
- Is the class bad, or is one person unhappy? (rater-bias panel: "this learner rates everything 3")
- Are the no-votes the same three people every week?

## 2. The tables

| Table | One row per | Key |
|---|---|---|
| `learners` | person | `learner_key` (unique) |
| `learner_ratings` | learner × rated class | `(source, external_id)` (unique) |
| `learner_import_runs` | import | `id` |

### `learners`

| Column | Type | Rule |
|---|---|---|
| `learner_key` | text, unique | **Stable and source-independent.** The SHA-256 (hex, lower-case) of the lower-cased, trimmed email, or the LMS learner id when the source has one. The raw email is **never** stored in this table. |
| `user_id` | uuid, null | Linked to `auth.users` if the learner ever signs in (matched on the same key derivation at sign-in time). |
| `display_name` | text, null | Optional. First name or initials are enough for the PM views. |

### `learner_ratings`

| Column | Type | Rule |
|---|---|---|
| `source` | text | Where the row came from: `lms`, `sheet`, `metabase`, … |
| `external_id` | text | The source's own row id. `(source, external_id)` is the **idempotency key** — a re-import updates the row in place, never duplicates it. If the source has no id, use `sha256(learner_key ‖ class_date ‖ topic ‖ instructor)`. |
| `learner_id` | uuid | → `learners.id` (created on first sight). |
| `class_rating_id` | uuid, null | → `class_ratings.id`. **The link to the class layer** (section 3). Null when no class row matched; kept, never dropped. |
| `cohort_id` | uuid, null | → `cohorts.id`, resolved from the source's cohort label through the same cohort parser the sync uses. |
| `class_date` | date | The session date. |
| `topic` | text | The class name as the source spells it. |
| `topic_id` | uuid, null | → `topics.id` via `topic_aliases` (per course). |
| `instructor_id` | uuid, null | → `instructors.id` via `instructor_aliases`. |
| `rating` | numeric(3,2), null | 0–5, two decimals. Out of range → the row is **rejected** (counted, sampled, not stored). |
| `approve` | boolean, null | "Would you want this instructor to take the class again?" yes → true, no → false, not asked → null. |
| `comment` | text, null | Free text, verbatim. |
| `submitted_at` | timestamptz, null | When the learner answered. |
| `ingested_at` | timestamptz | When we stored it. |
| `raw` | jsonb | The source record verbatim (audit; lets a later parser fix re-derive columns). |

### `learner_import_runs` (mirrors `sync_runs`)

`source`, `trigger` (`manual` / `cron` / `api`), `status` (`running` / `ok` / `failed`),
`rows_fetched`, `rows_upserted`, `rows_matched`, `rows_unmatched`, `learners_created`,
`unmatched_samples` (up to 50 `{external_id, class_date, topic, instructor}`), `error`,
`started_at`, `finished_at`, `duration_ms`.

## 3. Matching a learner row to the class row

The class layer's natural key is `(class_date, topic, instructor, session_kind)` on
`class_ratings`. The import resolves, in order:

1. **Instructor** — `normalize_person_name(instructor)` → `instructor_aliases.alias_norm` →
   `instructor_id` (exact normalised match only; unknown spellings stay unresolved and are
   reported, never guessed).
2. **Topic** — `normalize_topic_name(topic)` → `topic_aliases.alias_norm` (per course) →
   `topic_id`.
3. **Class row** — first by the natural key (`class_date`, `topic`, `instructor`, `session_kind`,
   after alias resolution both sides); then, if that misses, by `(course_id, class_date, topic_id)`
   when exactly one class row matches. Two same-day sessions of the same topic are left unmatched
   rather than guessed.

Unmatched rows are stored with `class_rating_id = null`, counted in `rows_unmatched`, and sampled
into `unmatched_samples` so a human can add the missing alias and re-import (idempotent).

## 4. What the import must and must not do

- **Must** be idempotent: re-running the same export changes nothing; a corrected export updates
  rows in place.
- **Must** create `learners` rows on first sight (`learners_created`), never delete them.
- **Must** reject nonsense: rating outside 0–5, dates outside the course window by more than a
  year, a missing `learner_key`. Rejections are counted and sampled, never silently dropped.
- **Must not** write to `class_ratings`. The class row's `rating`, `num_ratings`, `yes_votes`,
  `no_votes` remain the source's own figures. When learner-level totals disagree with the class
  row (e.g. 12 learner rows but `num_ratings = 10`), the run **reports** it (in
  `unmatched_samples` with `reason: "count_mismatch"`), the Sentiment Score is not affected.
- **Must not** store the raw email anywhere in these tables. `raw` may hold the source record but
  the importer strips `email` / `phone` fields before storing it.

## 5. The worker endpoint (to build when the export arrives)

`POST /import-learner-ratings` on the worker (bearer `WORKER_API_KEY`), body:

```json
{
  "source": "lms",
  "trigger": "manual",
  "rows": [
    {
      "external_id": "lms-rating-88213",
      "learner_key": "3a7bd3e2360a3d29eea436fcfb7e44c735d117c42d1c1835420b6b9942dd4f1b",
      "display_name": "A. Sharma",
      "class_date": "2026-08-14",
      "topic": "RAG Powered Knowledge Agents",
      "instructor": "Kalpesh Singh",
      "session_kind": "Live Class",
      "cohort_label": "Applied Agentic AI - 2nd Mid-March 2026 : Cohort 2",
      "rating": 4.0,
      "approve": false,
      "comment": "Too fast in the second hour.",
      "submitted_at": "2026-08-14T21:12:00Z"
    }
  ]
}
```

Response: the `learner_import_runs` row (`rows_fetched`, `rows_upserted`, `rows_matched`,
`rows_unmatched`, `learners_created`, `unmatched_samples`).

A CSV export with the same columns is accepted by the same endpoint (`multipart/form-data`,
field `file`), with `learner_key` derived by the worker from an `email` column that is hashed
in memory and discarded.

## 6. Access

| Who | `learners` | `learner_ratings` | `learner_import_runs` |
|---|---|---|---|
| admin / pm (staff) | read all | read all | read all |
| learner (signed in) | own row | own rows | — |
| anon | — | — | — |
| worker (service role) | write | write | write |

No client writes: the three tables have select policies only; the worker writes through
`DATABASE_URL` / the service role.

## 7. Views that will sit on top (v1.1, once data exists)

- `v_learner_week` — learner × cohort week: rating, approve, vs the cohort median that week.
- `v_learner_risk` — the at-risk list: three consecutive weeks below the median, a falling trend,
  or two "no" votes in a row.
- `v_rater_bias` — per learner: mean, spread, share of "no", vs the room.
- `v_no_voters` — per class: who said no, and how often each of them says no elsewhere.

All are plain aggregations over `learner_ratings` joined to `class_ratings` on `class_rating_id`;
none of them changes the class layer.

## 8. Checklist for the day the export arrives

1. Confirm the export has a per-row id and a stable learner identifier (email or LMS id).
2. Agree the hashing rule (section 2) with whoever owns the data — write it once, in the worker.
3. Run one import against a copy; read `unmatched_samples`; add aliases; re-run.
4. Compare learner-level totals with the class rows for one week; investigate mismatches above 5%.
5. Only then schedule it.
