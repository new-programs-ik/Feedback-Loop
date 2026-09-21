# Reading Feedback Loop's class analyses from Supabase

For: engineers on the B2B team who want the B2C class analyses in their own knowledge base.

Feedback Loop keeps one Postgres database on Supabase. You get a **read-only** view of it: a schema
called `kb` with three views, and a database user that can read those views and nothing else.
Nothing you do through this user can change data, and it cannot see transcripts, learner records
or anything under authentication.

## What you can read

| View | One row per | What it holds |
|---|---|---|
| `kb.class_analyses` | AI analysis of a class | the class (course, cohort, instructor, topic, date, type, rating), when it was analysed, the overall verdict, the findings as JSON (`flags`), the summary for the instructor, the feedback note the PM approved or is drafting (`feedback_text`, `feedback_status`), the re-teach recommendation (`reclass`, `reclass_reason`), whether the recording was sampled (`video_used`) |
| `kb.class_scores` | rated class from the ratings sheet | course, cohort, topic, instructor, date, session kind, rating, responses, attended, yes/no votes, approval %, the Class Sentiment Score and band, the action the band asks for, review status, the scoring version used |
| `kb.scoring_versions` | scoring formula version | name, status (`active` is the one in use), the full configuration as JSON, notes |

How to read a band and an action in `kb.class_scores`:

- `sentiment_band`: `excellent`, `good`, `average`, `bad`, or `NULL` = too few responses to judge (fewer than 6).
- `sentiment_action`: `video` (someone watches the recording), `transcript` (someone reads the transcript), `none` (nothing needed), `watch` (too few responses; kept an eye on).
- `sentiment_flags`: short codes explaining the band, for example `under_rating_line` (rated below 4.3) or `thin_low_rating_read`.

In `kb.class_analyses`, `flags` is a JSON array of findings; each has `flag` (the parameter, e.g. `pace`, `correctness`), `severity` (`minor`/`moderate`/`major`), `confidence`, and `evidence` (timestamps and quotes from the transcript). `reclass` is `yes`/`no`/`maybe`: whether the class should be taught again.

## Connecting

Ask Bishal for the password. It is never sent over chat or email in the clear.

| Setting | Value |
|---|---|
| Host | `aws-1-ap-southeast-1.pooler.supabase.com` |
| Port | `5432` |
| Database | `postgres` |
| User | `kb_reader.hedtphkfatmpqhuyndwk` |
| SSL | required |

As one connection string:

```
postgresql://kb_reader.hedtphkfatmpqhuyndwk:<password>@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require
```

The user's default schema is `kb`, so `select * from class_scores` works without a prefix.

## Pulling the data

Python, with `psycopg2` and `pandas`:

```python
import os
import pandas as pd
import psycopg2

conn = psycopg2.connect(os.environ["FEEDBACK_LOOP_DSN"])   # the connection string above
analyses = pd.read_sql("select * from kb.class_analyses order by analysed_at", conn)
scores   = pd.read_sql("select * from kb.class_scores   order by class_date",  conn)
conn.close()
```

Incremental refresh, so you only fetch what changed since your last pull:

```sql
select * from kb.class_analyses where analysed_at > %(since)s order by analysed_at;
select * from kb.class_scores   where synced_at   > %(since)s order by synced_at;
```

A one-off CSV from the command line (`psql` installed):

```
psql "<connection string>" -c "\copy (select * from kb.class_analyses) to 'class_analyses.csv' csv header"
```

## Limits, on purpose

- Read-only. Any write is refused.
- At most 5 open connections and 60 seconds per statement. Pull in one query rather than row by row.
- The ratings data refreshes from the sheet once an hour; analyses appear when a PM runs one. Polling more often than hourly finds nothing new.
- Not included: transcripts (confidential, and deleted after 20 days anyway), learner-level data, user accounts, Slack settings.

## What we promise about the shape

The three views are the contract. We may **add** columns; we will not rename or remove one, or
change a column's meaning, without telling you first. Everything under the views (tables, formula
versions) can change freely.

## Questions

Bishal Roy, New Programs team. If you need a column that is not here, ask; adding one to a view is
a small change.
