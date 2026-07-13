# Run the Feedback Loop on your own computer

You can run the whole system locally — the **Website** and the **AI Brain** both run on your machine,
and they talk to the same live database. Great for testing changes before they go live.

---

## ✅ The easy way (one click) — Windows

Just **double-click `start-local.bat`** in the project folder.

It opens two small black windows (the **Worker** and the **Website**), waits ~15 seconds, then opens
your browser at **http://localhost:3000/login**.

**Log in with your IK email + password** (Google sign-in only works on the live site by default — see
the note further down to enable it on localhost). If you don't have an email/password login yet, ask
the NP team.

**To stop:** close the two black windows.

That's it. 🎉

---

## 🛠️ The manual way (two terminals)

If you prefer to run them yourself, open **two** terminals:

**Terminal 1 — the AI Brain (Worker):**
```bash
cd ratings_module_build_kit
./.venv/Scripts/python -m uvicorn service:app --port 8000
```
Check it's up: open http://localhost:8000/health → you should see `{"status":"ok", ...}`.

**Terminal 2 — the Website:**
```bash
cd web
npm run dev
```
Then open http://localhost:3000.

---

## 🧰 First-time setup (only if something's missing)

Everything below is already done on the current machine — you only need this on a **fresh** computer.

1. **Node.js** (v20+) and **Python** (3.12+) installed.
2. Python worker deps:
   ```bash
   cd ratings_module_build_kit
   py -3 -m venv .venv
   ./.venv/Scripts/python -m pip install -r requirements.txt
   ```
3. Website deps:
   ```bash
   cd web
   npm install
   ```
4. Secrets (these already exist here, gitignored):
   - `ratings_module_build_kit/.env` → `ANTHROPIC_API_KEY`, `VIMEO_ACCESS_TOKEN`, `DATABASE_URL`
   - `web/.env.local` → the Supabase keys + `ANALYSIS_WORKER_URL=http://localhost:8000`

---

## ℹ️ Good to know

- **It uses the LIVE database.** Anything you create/delete locally shows up in the real app (and vice
  versa). That's usually what you want for testing — just be mindful. (We can set up a separate test
  database later if you'd like isolation.)
- **Google login locally:** by default only the live site is allowed. To use Google on localhost too,
  add `http://localhost:3000/**` under **Supabase → Auth → URL Configuration → Redirect URLs**.
  Otherwise, just use the email/password login above.
- **First analysis is slower to compile** the first time you open a page (Next.js builds on demand) —
  normal, it's quick after that.

## ❓ Troubleshooting

- **"Port 3000 (or 8000) is already in use"** → something's already running on it. Close old windows,
  or change the port (e.g. `--port 8001` for the worker + set `ANALYSIS_WORKER_URL` to match).
- **"Could not reach the analysis service"** when you click Analyze → the **Worker** window isn't
  running. Start it (Terminal 1 above), then try again.
- **Website won't start / module errors** → run `npm install` in `web/` once.
