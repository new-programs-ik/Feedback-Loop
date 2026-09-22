# Run the Feedback Loop on your own computer

You can run the whole system locally — the **website** and the **worker** both run on your machine
and talk to the same live database. That is how changes are reviewed before they go live.

---

## ✅ The easy way (one click) — Windows

Double-click **`start-local.bat`** in the project folder.

It opens two small black windows (the **Worker** and the **Website**), waits about ten seconds, then
opens your browser at **http://localhost:3000/login**. The first run after a code update builds the
website once (about a minute); after that it starts at once.

**Log in with your IK email and password** (Google sign-in only works on the live site unless you
enable it for localhost — see below). No login yet? Ask the NP team, or create one (First-time
setup, step 5).

**To stop:** close the two black windows.

---

## 🛠️ The manual way (two terminals)

**Terminal 1 — the worker:**
```bash
cd ratings_module_build_kit
./.venv/Scripts/python -m uvicorn service:app --port 8000
```
Check it: open http://localhost:8000/health → `"status":"ok"` plus the model, the build, which keys
are present, and `scoring_config_version` (the scoring version the sync uses).

**Terminal 2 — the website:**
```bash
cd web
npm run dev
```
Then open http://localhost:3000.

---

## 🧰 First-time setup (only on a fresh computer)

1. **Node.js** (v20 or newer) and **Python** (3.12 or newer).
2. Worker dependencies:
   ```bash
   cd ratings_module_build_kit
   py -3 -m venv .venv
   ./.venv/Scripts/python -m pip install -r requirements.txt
   ```
3. Website dependencies:
   ```bash
   cd web
   npm install
   ```
4. **Secrets.** Two files, both gitignored, never committed. Copy the examples and fill them in;
   the names are listed here, the values come from the person who runs the project.
   - `ratings_module_build_kit/.env` (start from `.env.example`):
     `ANTHROPIC_API_KEY`, `DATABASE_URL`, `VIMEO_ACCESS_TOKEN`, `WORKER_API_KEY`,
     `UI_URL=http://localhost:3000`; for the live-sheet sync also `RATINGS_SHEET_ID` and
     `GOOGLE_SA_JSON_FILE=./google-sa.json` ([sheet setup](GOOGLE_SHEET_SYNC_SETUP.md)).
     Leave `SLACK_BOT_TOKEN` empty locally unless you are testing Slack on a test channel.
   - `web/.env.local` (start from `.env.local.example`):
     `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`,
     `ANALYSIS_WORKER_URL=http://localhost:8000`, and `WORKER_API_KEY` (the same value as the
     worker's).
5. **A local login** (email + password, so you do not depend on Google locally):
   ```bash
   cd web
   node scripts/bootstrap-admin.mjs you@interviewkickstart.com <a-password> admin
   ```

---

## 📥 Getting the ratings data in

Two ways, depending on whether the Google service-account key is on this machine.

**With the key** (`ratings_module_build_kit/google-sa.json` present and the sheet shared with the
account): open the app → **Needs analysis** → **Sync now** (or Admin › Sync). The banner and the
Admin › Sync table show the run within a minute.

**Without the key** — push the local workbook copy through the worker's own sync path (the same
parser, cohort parsing, instructor resolution and scoring; Slack switched off; a full backup taken
first):
```bash
# from the repo root, with the worker's Python
./ratings_module_build_kit/.venv/Scripts/python analysis/resync_from_workbook.py --check   # compare, write nothing
./ratings_module_build_kit/.venv/Scripts/python analysis/resync_from_workbook.py --run     # backup, then sync
```
The workbook is confidential; it lives in the project root and is never committed. `--ui-url`
changes which site gets the "fresh data" ping (default `http://localhost:3000`); `--tabs` narrows
the tabs.

A sync needs an active scoring version. If the worker says *no active scoring config*, open
**Admin › Scoring** and activate one (version 1 is the manager's original).

---

## 🧪 Tests and checks

```bash
cd ratings_module_build_kit && ./.venv/Scripts/python -m unittest            # 285 tests, fully offline
cd web && npm test                                                           # 107 tests: the score mirror against supabase/fixtures/scoring_cases.json, and the report window
cd web && npx tsc --noEmit                                                   # type-check
./ratings_module_build_kit/.venv/Scripts/python supabase/test_scoring_sql.py # the database's scoring function against the same fixtures (needs DATABASE_URL)
./ratings_module_build_kit/.venv/Scripts/python supabase/test_worker_sql.py  # the worker's SQL against the real database, rolled back (needs DATABASE_URL)
./ratings_module_build_kit/.venv/Scripts/python -m unittest analysis.test_sentiment_score   # the 44 edge cases, from the repo root
```

**Screenshots of every page, light and dark** (for a design review; needs a local Chrome):
```bash
cd web
SHOT_EMAIL=you@interviewkickstart.com SHOT_PASSWORD=... node scripts/shots.mjs [baseUrl] [outDir] [path ...]
```
`SHOT_WIDTH` (default 1440; use 375 for the phone pass) and `SHOT_THEMES` (default `light,dark`)
narrow a run; `CHROME` points at a different Chrome. Screenshots contain real class data — keep
them out of the repo.

**A full backup of the database** (one JSON-lines file per table, to `_archive/backups/<timestamp>/`):
```bash
./ratings_module_build_kit/.venv/Scripts/python analysis/db_backup.py
```
Take one before anything that rewrites many rows — a scoring activation, a full re-sync, a migration.

**The validation study** (local only; the outputs carry instructor names and are gitignored):
```bash
./ratings_module_build_kit/.venv/Scripts/python analysis/sentiment_run_all.py            # everything, about 20 minutes
./ratings_module_build_kit/.venv/Scripts/python analysis/sentiment_run_all.py --no-sweep # reuse the last sweep, about a minute
```
It writes `analysis/out/*` and the two PDFs (`Sentiment-Score-Validation.pdf`,
`Sentiment-Score-One-Pager.pdf`) in the project root, using a local Chrome to print them.

---

## ℹ️ Good to know

- **It uses the LIVE database.** A class you dismiss, a scoring version you activate, an instructor
  you merge — all of it shows up in the real app, and the other way round. Migrations are
  additive, so applying them locally does not break the live site, but treat activations, merges
  and re-syncs as real.
- **Google login locally:** by default only the live site is allowed. To use Google on localhost,
  add `http://localhost:3000/**` under **Supabase → Authentication → URL Configuration → Redirect
  URLs**. Otherwise use the email + password login.
- **The first visit to a page is slower** in `npm run dev` (Next.js builds it on demand). The
  launcher uses the production build, which does not have this.
- **Where you land:** the last workspace you used (a cookie), else your first course membership,
  else `/team` for an admin or your first course.

## ❓ Troubleshooting

- **"Port 3000 (or 8000) is already in use"** → something is already running on it. Close old
  windows, or change the port (`--port 8001` for the worker and set `ANALYSIS_WORKER_URL` to match).
- **"Could not reach the analysis service"** when you click Analyze → the worker window is not
  running. Start it (Terminal 1), then try again.
- **"Could not reach the sync service — it may be waking up"** → same cause locally: start the
  worker. On the live site it means Render's free tier is waking up; try again in a minute.
- **A sync fails with "no active scoring config"** → Admin › Scoring → activate a version.
- **A sync fails with "missing required column(s)"** → someone renamed a header in the sheet; see
  the column table in [GOOGLE_SHEET_SYNC_SETUP.md](GOOGLE_SHEET_SYNC_SETUP.md).
- **Website will not start / module errors** → run `npm install` in `web/` once.
- **Pages say a table "is not available yet"** → a migration has not been applied to this database
  yet; see [DEPLOY.md](../DEPLOY.md), step 1.
