# 🔌 Connecting the live ratings sheet — one-time setup (10 minutes)

The app reads the team's **main ratings sheet** through a *service account* — a robot Google
account that can only **view** the one sheet you share with it. No public links, revocable any
time, nothing else in your Drive visible to it.

Written for a non-technical reader. You do this once.

---

## Step 1 — Create the service account (Google Cloud)

1. Open https://console.cloud.google.com and sign in with your IK Google account.
2. Top bar → project picker → **New project** → name it `feedback-loop-sync` → Create → select it.
3. Left menu → **APIs & Services → Library** → search **Google Sheets API** → open it → **Enable**.
4. Left menu → **IAM & Admin → Service Accounts** → **+ Create service account**.
   - Name: `feedback-loop-reader` → Create and continue.
   - Roles: **skip** (it needs no project roles) → Done.
5. Click the account you just created → **Keys** tab → **Add key → Create new key → JSON → Create**.
   A file like `feedback-loop-sync-xxxx.json` downloads. **Treat it like a password — never email
   it, never paste it into a chat.**

## Step 2 — Put the key where the app looks

Move/copy the downloaded file to:

```
C:\Users\DELL\Documents\NP team automation\ratings_module_build_kit\google-sa.json
```

(That exact name. It is gitignored — it can never end up in the repository.)

## Step 3 — Share the sheet with the robot

1. Open the downloaded JSON in Notepad and copy the **`client_email`** value
   (looks like `feedback-loop-reader@feedback-loop-sync-xxxx.iam.gserviceaccount.com`).
2. Open the **main ratings sheet** → **Share** → paste that email → role **Viewer** →
   untick "Notify people" → Share.

## Step 4 — Tell the app which sheet

In `ratings_module_build_kit/.env`, fill in the two lines the setup added:

```
RATINGS_SHEET_ID=   <- the long id from the sheet's URL: docs.google.com/spreadsheets/d/THIS_PART/edit
GOOGLE_SA_JSON_FILE=google-sa.json
```

(If the tab names differ from `MLSU_Live_Class_Poll,Agentic_AI_Live_Class_Poll`, also set
`RATINGS_SHEET_TABS=` with the correct comma-separated names.)

## Step 5 — Verify

Open the app → **Needs analysis** → **Sync now**. Within a minute the banner should read
"Last synced just now · N rows".

## Which columns it reads

Columns are found **by their header name**, so reordering or adding columns is harmless. Renaming
one of the required ones stops the sync with the column named.

| Header in the sheet | Required? | Used for |
|---|---|---|
| `Session Date` | yes | the class date |
| `Type` | yes | Live Class vs Test Review, and the course fallback |
| `Cohorts` | yes | the course (mapped by the cohort text) |
| `Class` (or `Topic` on tabs without a `Class` column) | yes | the class name — on the Agentic tab `Topic` holds the session kind, so `Class` always wins when both exist |
| `Instructor` | yes | the instructor, and their track record |
| `Overall Average` | yes | the rating |
| `Responses` | yes | how many rated |
| `# Students Attended` | yes | how many attended (participation %) |
| `Yes` / `No` | **optional** | the approval vote — "would you want this instructor to take the class again?" |

A tab without the `Yes` / `No` columns still syncs; those classes simply carry no vote, which is
never a penalty in the score (see `docs/HOW_IT_WORKS.md`, the Class Sentiment Score section).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Sync failed: "403 — the sheet is not shared…" | Step 3 missed or wrong email | Re-share with the exact `client_email` |
| Sync failed: "404 — sheet id not found" | Wrong `RATINGS_SHEET_ID` | Copy the id from the sheet URL again |
| Sync failed: "missing required column(s) [X]" | Someone renamed a header in the sheet | Rename it back, or tell the dev team |
| Classes show "no vote recorded" | The `Yes` / `No` headers are missing or renamed on that tab | Optional — add or rename them back and the next sync fills the vote in |
| Banner never updates | Worker not running | Locally: start the worker; in production: check Render |

## At deploy time (later, not now)

The same two settings go into Render: the JSON as a **Secret File** at
`/etc/secrets/google-sa.json` (and `GOOGLE_SA_JSON_FILE=/etc/secrets/google-sa.json`), plus
`RATINGS_SHEET_ID`. The hourly schedule is switched on with migration `0013_ratings_cron.sql`.
