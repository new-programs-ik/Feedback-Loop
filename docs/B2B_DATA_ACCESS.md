# Getting Feedback Loop's class analyses into your knowledge base

For: engineers on the B2B team.

Feedback Loop is the New Programs team's system that scores every live class from the ratings
sheet and, for the weak ones, writes an AI analysis of the recording. You are getting **read-only
access** to the results, straight from the database, so you can pull them into your own knowledge
base whenever you like.

You do **not** need a Supabase account, an API key, or any access to the Feedback Loop website.
You need two things, both from Bishal Roy (New Programs): this document, and one password.

---

## 1. What you are getting

A database login called `kb_reader` that can read three tables (technically "views") and nothing
else. It cannot change anything, and it cannot see class transcripts, learner records, user
accounts or settings.

| Table | One row per | What it holds |
|---|---|---|
| `class_analyses` | AI analysis of a class | which class (course, cohort, instructor, topic, date, type, rating), the overall verdict, every finding with its timestamp and quote, the summary written for the instructor, the feedback note the PM approved, and whether the class should be re-taught |
| `class_scores` | rated class on the ratings sheet | course, cohort, topic, instructor, date, session type, rating, how many rated, how many attended, yes/no votes, the score out of 100, the band, and what the band asks for |
| `scoring_versions` | version of the scoring formula | its name, whether it is the one in use, and its settings |

Today that is about **3,100 scored classes** and a smaller number of AI analyses (one is written
only when a PM runs it). The scores refresh from the sheet three times a day (10:00, 12:00 and
14:00 India time).

---

## 2. Step by step

### Step 1. Get the password

Ask Bishal for the `kb_reader` password. He will give it to you in person or through a password
manager, never over chat or email. Keep it out of code and out of git: put it in an environment
variable (the examples below call it `FEEDBACK_LOOP_DSN`).

### Step 2. Note the connection details

| Setting | Value |
|---|---|
| Host | `aws-1-ap-southeast-1.pooler.supabase.com` |
| Port | `5432` |
| Database | `postgres` |
| Username | `kb_reader.hedtphkfatmpqhuyndwk` |
| Password | from Bishal |
| SSL | required |

All of that as one connection string (replace `PASSWORD`):

```
postgresql://kb_reader.hedtphkfatmpqhuyndwk:PASSWORD@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require
```

The username really does contain a dot and that code after it; that is how this host routes
connections. Use it exactly.

### Step 3. Check that it works

Any Postgres tool will do. Three options, pick one:

**Option A, a desktop tool** (DBeaver, TablePlus, pgAdmin): create a new PostgreSQL connection,
fill in the five values from Step 2, tick "use SSL", connect. You should see a schema called `kb`
with the three tables. Open `class_scores` and rows should appear.

**Option B, the `psql` command line:**

```
psql "postgresql://kb_reader.hedtphkfatmpqhuyndwk:PASSWORD@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require" -c "select count(*) from class_scores"
```

You should get a number in the thousands.

**Option C, Python:**

```python
import os, psycopg2
conn = psycopg2.connect(os.environ["FEEDBACK_LOOP_DSN"])
cur = conn.cursor()
cur.execute("select count(*) from class_scores")
print(cur.fetchone())   # (3099,) or similar
conn.close()
```

If you get "password authentication failed", the password is wrong or was never set; ask Bishal.
If you get "too many connections", you have more than 5 open at once; close some.

### Step 4. Pull everything once

```python
import os
import pandas as pd
import psycopg2

conn = psycopg2.connect(os.environ["FEEDBACK_LOOP_DSN"])
analyses = pd.read_sql("select * from class_analyses order by analysed_at", conn)
scores   = pd.read_sql("select * from class_scores   order by class_date",  conn)
versions = pd.read_sql("select * from scoring_versions order by version",   conn)
conn.close()

analyses.to_csv("class_analyses.csv", index=False)
scores.to_csv("class_scores.csv", index=False)
```

Or, without Python, a one-line export with `psql`:

```
psql "postgresql://...same as above..." -c "\copy (select * from class_analyses) to 'class_analyses.csv' csv header"
```

### Step 5. Keep it fresh without re-pulling everything

Remember the time of your last pull, and ask only for what changed since:

```sql
select * from class_analyses where analysed_at > '2026-09-21 00:00+00' order by analysed_at;
select * from class_scores   where synced_at   > '2026-09-21 00:00+00' order by synced_at;
```

`synced_at` on a score row changes only when the sheet changed that class, so this is cheap.
Once a day is plenty; the data itself refreshes three times a day at most.

### Step 6. Read the columns right

In `class_scores`:

- `sentiment_score`: 0 to 100. `sentiment_band`: `excellent`, `good`, `average`, `bad`, or empty when fewer than 6 learners answered (too few to judge).
- `sentiment_action`: what the band asks for. `video` = someone watches the recording, `transcript` = someone reads the transcript, `none` = nothing needed, `watch` = too few responses, kept an eye on.
- `sentiment_flags`: short codes explaining the band, for example `under_rating_line` (rated below 4.3) or `thin_low_rating_read` (too few responses, but rated low enough to read anyway).
- `yes_votes` / `no_votes`: answers to "would you want this instructor again?". `approval_pct` is yes as a share of answers.
- `num_ratings` = learners who rated; `attended` = learners who attended.

In `class_analyses`:

- `overall`: the one-paragraph verdict.
- `flags`: the findings, as JSON. Each has `flag` (what kind: `pace`, `clarity`, `correctness`, `coverage`, `doubt_handling`, ...), `severity` (`minor`, `moderate`, `major`), `confidence`, and `evidence` (a list of `{timestamp, quote}` from the transcript).
- `instructor_summary`: the short summary written for the instructor. `feedback_text`: the full note. `feedback_status`: `draft` (not yet reviewed by a PM), `approved`, or `sent`. For a knowledge base, prefer rows where `feedback_status` is `approved` or `sent`.
- `reclass`: `yes`, `no` or `maybe`: whether the class should be taught again. `reclass_reason` says why.
- `video_used`: whether frames from the recording were part of the analysis.

---

## 3. Rules of the road

- **Read-only.** Any write is refused by the database, not by convention.
- **At most 5 open connections and 60 seconds per query.** Pull with one query, not one per row.
- **Don't poll more than a few times a day.** Scores change when the sheet is pulled (10:00, 12:00 and 14:00 India time); analyses arrive when a PM approves one.
- **Not included, by design:** transcripts (confidential, deleted after 20 days anyway), learner-level data, user accounts, Slack settings.
- **Treat the content as internal.** It names instructors and quotes their classes.

## 4. What we promise

The three tables are the contract. We may **add** columns; we will not rename or remove one, or
change what a column means, without telling you first. Everything underneath can change freely.

## 5. Questions

Bishal Roy, New Programs team. Need a column that isn't here? Ask; adding one to a view is a small
change.
