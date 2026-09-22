# 🚀 Setting up the worker on Render — the complete, click-by-click guide

The **worker** runs on [Render](https://render.com). It does two jobs for the live website: it pulls
the ratings sheet three times a day and scores the classes, and it runs the AI analysis when a PM clicks
Analyze. For either to work, the worker needs a few **environment variables** (settings). The most
important one is **`DATABASE_URL`** — the address and password of the database — because the worker
saves every synced class and every finished analysis there.

Written for a non-technical reader. You do this once. Take it one step at a time.

> ✅ **You do not need to be able to find things in Supabase.** The value you need is already in a
> file on your computer. Method 1 below is the easy way — start there. Method 2 (Supabase) is only
> a backup if you cannot find the file.

---

## STEP 1 — Get the `DATABASE_URL` value

The value is one long line shaped like this (yours has real values in place of the parts in angle
brackets):

```
postgresql://postgres.<project-ref>:<your-database-password>@<host>.pooler.supabase.com:5432/postgres?sslmode=require
```

### ⭐ Method 1 — Copy it from the file on your computer (easiest)

1. Open the project folder on your computer, then the `ratings_module_build_kit` folder inside it.
2. Find the file named **`.env`** (just ".env", nothing before the dot).
   - Cannot see it? In File Explorer click **View → Show → Hidden items** (files starting with a
     dot are hidden by default). Or open the folder in **VS Code**, which shows it.
3. Open `.env` (right-click → **Open with → Notepad**, or open it in VS Code).
4. Find the line that starts with **`DATABASE_URL=`**.
5. Copy **everything after the `=` sign** — the whole `postgresql://...sslmode=require` line.
   That is your value. **Done — skip to Step 2.**

### Method 2 — Get it from the Supabase website (backup)

1. Go to **[supabase.com/dashboard](https://supabase.com/dashboard)** and sign in.
2. Click the project to open it.
3. Click the green **Connect** button in the top bar. (Older layout: **Project Settings →
   Database**.)
4. In the popup, choose the **Session pooler** tab.
5. Copy the line starting with `postgresql://postgres...` (there is a copy icon on the right).
6. Replace `[YOUR-PASSWORD]` (including the square brackets) with your **database password** — the
   one chosen when the project was created (it is the same one stored in the `.env` file).
7. Make sure the very end reads `?sslmode=require`. If it is missing, add it.

> 🔒 This value contains your database password — treat it like a password. Only paste it into
> Render's Environment box (Step 3). Never put it in a chat, an email, or the code.

---

## STEP 2 — Open the worker on Render

1. Go to **[dashboard.render.com](https://dashboard.render.com)** and sign in.
2. Click the **worker** service — the one that runs the analysis (type **Web Service**; the name is
   something like **feedback-loop-worker**).
   - Not sure? It is the service whose logs mention **uvicorn** / **service:app**, not the website.

---

## STEP 3 — Add the environment variables

1. In the worker's page, click **Environment** in the left menu.
2. Under **Environment Variables**, click **+ Add Environment Variable**.
3. Add the first one:
   - **Key**: `DATABASE_URL`
   - **Value**: the line you copied in Step 1.
4. Repeat for each row you need:

   | Key (type it exactly) | Value | Do I need it? |
   |---|---|---|
   | `DATABASE_URL` | the line from Step 1 | **Yes — required.** The worker saves synced classes and analysis results here. |
   | `ANTHROPIC_API_KEY` | your Claude key (starts with `sk-ant-`) | **Yes — required.** Runs the AI. |
   | `WORKER_API_KEY` | a long secret word of your choosing | **Yes.** Only callers that know it can ask the worker to do anything. The same value goes on the website (Vercel). The scheduled sync does not need it. |
   | `RATINGS_SHEET_ID` | the long id in the ratings sheet's URL (`docs.google.com/spreadsheets/d/THIS_PART/edit`) | **Yes, for the sync.** |
   | `GOOGLE_SA_JSON_FILE` | `/etc/secrets/google-sa.json` | **Yes, for the sync** — together with Step 4. |
   | `UI_URL` | `https://feedback-loop-ten.vercel.app` | Yes. The Slack cards link here, and the worker tells the site to refresh after each sync. |
   | `SLACK_BOT_TOKEN` | the Slack bot token (starts with `xoxb-`) | For the Slack cards and the "sync failed" alerts. |
   | `SLACK_PM_CHANNEL_ID` | the channel id (starts with `C`) | Same — the channel the cards go to. |
   | `VIMEO_ACCESS_TOKEN` | your Vimeo token | Yes, if you analyze **Vimeo links**. |
   | `VIDEO_MAX_FRAMES` | `40` | Recommended on Render's free tier — caps the video frames per class. |
   | `VIDEO_DISABLED` | `1` | Optional kill-switch: video analysis off on this deployment. |
   | `RESUME_SCHEDULED` | `0` | Optional: stops the worker picking up queued classes on its own (it does by default, a minute after it starts and every 90 seconds). |
   | `UPLEVEL_COOKIE` | a signed-in UpLevel cookie header | Optional, for fetching a class's recording link from UpLevel ([UPLEVEL_VIDEO_LINK.md](UPLEVEL_VIDEO_LINK.md)). Temporary until the platform team gives a durable token. |
   | `RATINGS_SHEET_TABS` | tab names, comma-separated | Only if the tabs are not `MLSU_Live_Class_Poll,Agentic_AI_Live_Class_Poll`. |
   | `NOTIFY_MAX_AGE_DAYS` / `NOTIFY_MAX_PER_RUN` | `10` / `25` | Optional guard rails for Slack: only classes this recent are pinged, at most this many per sync run. `0` for the second one holds every card. |
   | `GOOGLE_ACCESS_TOKEN` | a Google token | Only for **private** Google Drive materials (optional). |

   > 🎬 **About video analysis on the free tier:** it works, but the free worker is slow and can spin
   > down mid-job, so keep `VIDEO_MAX_FRAMES=40`. If video jobs get stuck, set `VIDEO_DISABLED=1`
   > (analyses continue transcript-only) or upgrade the worker to Render's Starter plan (about
   > $7/month; its real benefit is no spin-down). Enabling video for plain Vimeo links is a separate
   > one-time step: [VIMEO_VIDEO_ACCESS.md](VIMEO_VIDEO_ACCESS.md).

   *(The Claude and Vimeo values are also in the same `.env` file from Step 1 — the lines
   `ANTHROPIC_API_KEY=` and `VIMEO_ACCESS_TOKEN=`.)*
5. Do **not** click Save yet if you still have Step 4 to do; otherwise click **Save Changes**.

---

## STEP 4 — Add the Google key as a Secret File

The sync reads the ratings sheet through a "robot" Google account. Its key is a small JSON
file (created in [GOOGLE_SHEET_SYNC_SETUP.md](GOOGLE_SHEET_SYNC_SETUP.md); on your computer it is
`ratings_module_build_kit/google-sa.json`). On Render it goes in as a **Secret File**, not a
variable:

1. Still on the **Environment** page, scroll to **Secret Files** → **+ Add Secret File**.
2. **Filename**: `google-sa.json`
3. **Contents**: open your local `google-sa.json` in Notepad, select all, copy, paste.
4. Render stores it at `/etc/secrets/google-sa.json` — which is exactly the value you gave
   `GOOGLE_SA_JSON_FILE` in Step 3.
5. Click **Save Changes**. Render shows **Deploying** and restarts the worker (1–3 minutes).

---

## STEP 5 — Check it worked

1. On the worker's page, click **Logs**. Success looks like:
   ```
   INFO:     Application startup complete.
   INFO:     Uvicorn running on http://0.0.0.0:10000
   ```
2. Open `https://<your-worker>.onrender.com/health` in a browser. You want to see
   `"status":"ok"`, `"database":"ok"`, `"anthropic_key":true`, `"sheet_configured":true`,
   `"slack_configured":true` (if you set Slack), `"ffmpeg":true`, and `"scoring_config_version"`
   with a number. `"database":"unreachable"` means the worker cannot talk to Supabase right now:
   check `DATABASE_URL` (Step 3) and Supabase's status page.
3. Open the **live website**, sign in, go to **Admin › Sync** and click **Sync now**. Within a
   minute or two the table shows a run with status **ok**, rows fetched and rows scored.
4. Run a **New analysis** on one class from the queue (click **Analyze** on a row). It shows
   **Analyzing…** and then, a few minutes later, fills in the feedback on its own. 🎉

---

## STEP 6 — Check the schedule (nothing to switch on)

The database calls the worker on its own at **10:00, 12:00 and 14:00 India time**, with a retry
five minutes after each in case the free worker was asleep. No secret is needed: every run mints
a one-time token and the worker checks it against the database. The schedule is created by the
migrations (`0027` and `0031`, see [DEPLOY.md](../DEPLOY.md)).

The only thing to check is that the worker's address is right. In Supabase → **SQL Editor**:

```sql
select key, value from app_settings;
```

`worker_url` must be your worker's address (for example `https://feedback-loop-50w0.onrender.com`).
If it is not, `update app_settings set value = 'https://<your-worker>.onrender.com' where key = 'worker_url';`.
After the next slot, **Admin › Sync** shows a run with trigger **cron:Asia/Kolkata**; if the
worker did not answer, the same page counts it under "scheduled runs not picked up".

---

## If something goes wrong

| What you see | What it usually means | Fix |
|---|---|---|
| Class stuck on **"Analyzing…"** forever | `DATABASE_URL` is missing or wrong | Redo Step 1 → Step 3. Check the password and that the line ends with `?sslmode=require`. |
| Logs say **`No module named ...`** | A code file was not included in the deploy | Tell your developer (a Dockerfile fix, not a settings one). |
| Logs say **`DATABASE_URL is not set`** | The variable name is misspelled | It must be exactly `DATABASE_URL` (all caps, underscore). |
| **"password authentication failed"** | Wrong database password in the value | Get the password again (it is in the `.env` file) and re-paste the whole line. |
| Sync failed: **"no Google service-account key"** | Step 4 missed, or `GOOGLE_SA_JSON_FILE` does not match the Secret File's path | Redo Step 4; the path must be `/etc/secrets/google-sa.json`. |
| Sync failed: **"403 — the sheet is not shared…"** | The sheet is not shared with the robot account | Share it with the account's `client_email` as Viewer ([sheet setup](GOOGLE_SHEET_SYNC_SETUP.md)). |
| Sync failed: **"missing required column(s) [X]"** | Someone renamed a header in the sheet | Rename it back, or tell the dev team. |
| Sync failed: **"no active scoring config"** | No scoring version is active | Admin › Scoring → activate one (version 1 is the manager's original). |
| No runs with trigger **cron:Asia/Kolkata** ever appear | `worker_url` in `app_settings` is wrong, or the worker never answered (Admin › Sync counts these under "scheduled runs not picked up") | Do Step 6; check the worker's logs on Render around 10:00 India time. |
| Slack cards say **"No owner assigned"** | The course has nobody on it | Admin › People → add the course's people and pick a handler. |
| First analysis of the day is slow (about a minute extra) | The free worker sleeps when idle and has to wake up | Normal — nothing to fix. The scheduled sync retries five minutes later for the same reason. |

---

## Quick answers

- **Do I need Render for testing on my own laptop?** No. Locally the worker reads these settings
  from the `.env` file. Render is only for the shared **live** website.
- **I changed the database password.** Update `DATABASE_URL` in Render (Step 3) with the new
  password and click **Save Changes** — it redeploys on its own.
- **Which variables are truly required?** For analyses: `DATABASE_URL` and `ANTHROPIC_API_KEY`. For
  the sync, also `RATINGS_SHEET_ID` and the Google key (Step 4). Everything else depends on
  which features you use.
- **Where do I see whether the sync is healthy?** Admin › Sync in the app, and `/health` on the
  worker.

Related: keeping these secrets safe — [HOW_IT_WORKS.md](HOW_IT_WORKS.md), section 15.
