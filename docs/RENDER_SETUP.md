# 🚀 Setting up the Worker on Render — step by step (simple English)

The **worker** ("AI brain") runs on [Render](https://render.com). For the live website's analysis to
work, the worker needs a few **environment variables** (settings) — most importantly the
**`DATABASE_URL`**, which lets it save the finished analysis back to the database.

This guide is written for a non-technical reader. You only need to do this **once** (and again only if
you change a password).

---

## Part 1 — What is `DATABASE_URL` and where do I get it?

`DATABASE_URL` is the **address + password of your database** (Supabase), in one line. It looks like:

```
postgresql://postgres.hedtphkfatmpqhuyndwk:YOUR_DB_PASSWORD@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require
```

You have two easy ways to get the exact value:

### Option A — copy it from Supabase (most reliable)
1. Go to **[supabase.com/dashboard](https://supabase.com/dashboard)** and open your project
   (**hedtphkfatmpqhuyndwk**).
2. Click the **⚙️ Project Settings** (bottom-left) → **Database**.
3. Find the **"Connection string"** section → choose the **"Session pooler"** tab (or "Connection
   pooling"). Copy the **URI** shown. It starts with `postgresql://postgres...`.
4. That string has a placeholder like `[YOUR-PASSWORD]`. Replace it with your **database password**
   (the one you set when creating the project — the same one in your local `.env` file).
5. Make sure the end has `?sslmode=require` (add it if it's missing).

### Option B — it's already in your project
Open the file `ratings_module_build_kit/.env` on your computer. The line that starts with
`DATABASE_URL=` is exactly the value you need. Copy everything **after** the `=`.

> 🔒 This value contains your database password. Treat it like a password — paste it only into
> Render's secure Environment settings (below), never into public places or the code.

---

## Part 2 — Add it to Render (and the other settings)

1. Go to **[dashboard.render.com](https://dashboard.render.com)** and sign in.
2. Click your worker service (the one that runs the analysis — its name is something like
   **feedback-loop-worker**).
3. In the left menu, click **Environment**.
4. Under **Environment Variables**, click **Add Environment Variable** and add each of these
   (Key on the left, Value on the right):

   | Key | Value | Needed for |
   |---|---|---|
   | `DATABASE_URL` | the string from Part 1 | **Required** — saving the analysis (background jobs) |
   | `ANTHROPIC_API_KEY` | your Claude API key (starts with `sk-ant-…`) | **Required** — running the AI |
   | `VIMEO_ACCESS_TOKEN` | your Vimeo token | Fetching transcripts from Vimeo links |
   | `WORKER_API_KEY` | a shared secret (only if your website sends one) | Optional security |
   | `GOOGLE_ACCESS_TOKEN` | a Google OAuth token | Optional — only for **private** Drive materials |

5. Click **Save Changes**. Render will **automatically redeploy** the worker (takes ~1–3 minutes).
6. Watch the **Logs** tab. Success looks like:
   ```
   Application startup complete.
   Uvicorn running on http://0.0.0.0:10000
   ```
   If you instead see `No module named ...` or a crash, tell your developer — it usually means a file
   wasn't included in the deploy.

---

## Part 3 — Check it actually works

1. Open the **live website** and run a **New analysis** on a class.
2. It should show **"Analyzing…"** and then, about a minute later, fill in the feedback on its own.
3. If it stays stuck on "Analyzing…" forever, the most common cause is a **missing or wrong
   `DATABASE_URL`** — re-check Part 1 (especially the password and the `?sslmode=require` at the end).

---

## Quick FAQ

- **Do I need Render for local testing?** No. On your own computer the worker already has these
  settings from `ratings_module_build_kit/.env`. Render is only for the shared live website.
- **The worker "sleeps"?** On Render's free tier the worker sleeps when idle, so the *first* analysis
  after a quiet period takes ~1 extra minute to wake up. That's normal.
- **I changed my database password.** Update `DATABASE_URL` in Render (Part 2) with the new password
  and Save — Render redeploys automatically.

Related: the connection string and keys are secrets — see the confidentiality notes in
[HOW_IT_WORKS.md](HOW_IT_WORKS.md) §7.
