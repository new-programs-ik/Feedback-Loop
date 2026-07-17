# 🚀 Setting up the Worker on Render — the complete, click-by-click guide

The **worker** ("AI brain") runs on [Render](https://render.com). For the **live website's** analysis
to work, the worker needs a few **environment variables** (settings). The most important one is
**`DATABASE_URL`** — the address + password of your database — because the worker uses it to save each
finished analysis back into the database.

Written for a non-technical reader. You do this **once**. Take it slowly, one step at a time.

> ✅ **You do NOT need to be able to "find things in Supabase."** The value you need is already sitting
> in a file on your computer. **Method 1 below is the easy way — start there.** Method 2 (Supabase) is
> only a backup if you can't find the file.

---

## STEP 1 — Get the `DATABASE_URL` value

The value is one long line that looks exactly like this (yours is already filled in except the password):

```
postgresql://postgres.hedtphkfatmpqhuyndwk:YOUR_DB_PASSWORD@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require
```

You only need to swap **`YOUR_DB_PASSWORD`** for your real database password. Pick ONE method below.

### ⭐ Method 1 — Copy it from the file on your computer (easiest, no Supabase)

Your project already has the complete, correct value saved in a settings file. Just copy it:

1. On your computer, open the project folder:
   `C:\Users\DELL\Documents\NP team automation\ratings_module_build_kit`
2. Find the file named **`.env`** (just ".env", no name before the dot).
   - Can't see it? In File Explorer click the **View** menu → tick **Hidden items** (files starting
     with a dot are hidden by default). Or open the folder in **VS Code**, which shows it.
3. Open `.env` (right-click → **Open with → Notepad**, or open it in VS Code).
4. Find the line that starts with **`DATABASE_URL=`**.
5. Select and copy **everything after the `=` sign** — the whole `postgresql://...sslmode=require` line.
   That copied text is your value. **Done — skip to Step 2.**

> This line already has the real password in it, so you don't have to type or find anything else.

### Method 2 — Get it from the Supabase website (backup)

Use this only if you couldn't find the `.env` file.

1. Go to **[supabase.com/dashboard](https://supabase.com/dashboard)** and sign in.
2. Click your project to open it. (Its id is **hedtphkfatmpqhuyndwk** — the name may differ.)
3. Look at the **top bar** of the project. Click the green **`Connect`** button (top-right area, near
   the project name). *(This is the new location. If you don't see a Connect button, use the old path:
   click **⚙️ Project Settings** at the very bottom of the left menu → **Database**.)*
4. A **"Connect to your project"** popup opens. Near the top there are tabs like **Direct connection**,
   **Transaction pooler**, **Session pooler**. Click **Session pooler**.
5. It shows a line starting with `postgresql://postgres...`. Copy that whole line (there's a small
   **copy icon** ⧉ on the right).
6. The line has `[YOUR-PASSWORD]` in the middle. Replace `[YOUR-PASSWORD]` (including the square
   brackets) with your **database password** — the one you chose when the project was created (it's the
   same password stored in the `.env` file from Method 1).
7. Make sure the very end reads `?sslmode=require`. If it's missing, add it.

> 🔒 This value contains your database password — treat it like a password. Only paste it into Render's
> secure Environment box (Step 2). Never put it in a chat, email, or the public code.

---

## STEP 2 — Open your Worker on Render

1. Go to **[dashboard.render.com](https://dashboard.render.com)** and sign in.
2. You'll see your services listed. Click the **worker** service — it's the one that runs the analysis
   (its type is **Web Service**; the name is something like **feedback-loop-worker**).
   - Not sure which one? It's the service whose logs mention **uvicorn** / **service:app**, not the
     Next.js website.

---

## STEP 3 — Add the environment variables

1. In the worker's page, look at the **left-side menu** and click **Environment**.
2. You'll see a section called **Environment Variables**. Click **+ Add Environment Variable**.
3. Add the first one:
   - **Key** (or "NAME") box: type `DATABASE_URL`
   - **Value** box: paste the line you copied in Step 1.
4. Click **+ Add Environment Variable** again for each of the others you need:

   | Key (type this exactly) | Value (paste this) | Do I need it? |
   |---|---|---|
   | `DATABASE_URL` | the line from Step 1 | **Yes — required.** Lets the worker save results. |
   | `ANTHROPIC_API_KEY` | your Claude key (starts with `sk-ant-`) | **Yes — required.** Runs the AI. |
   | `VIMEO_ACCESS_TOKEN` | your Vimeo token | Yes, if you analyze **Vimeo links**. |
   | `WORKER_API_KEY` | a shared secret word | Only if your website already sends one. |
   | `GOOGLE_ACCESS_TOKEN` | a Google token | Only for **private** Google Drive materials (optional). |

   *(The Claude / Vimeo values are also in the same `.env` file from Step 1 — lines
   `ANTHROPIC_API_KEY=` and `VIMEO_ACCESS_TOKEN=`.)*
5. Click **Save Changes** (bottom or top-right of the Environment page).
6. Render will show **"Deploying"** and automatically restart the worker. This takes about **1–3 minutes**.

---

## STEP 4 — Check it worked

1. Still on the worker's page, click the **Logs** tab (left menu).
2. Wait for the deploy to finish. **Success looks like this:**
   ```
   INFO:     Application startup complete.
   INFO:     Uvicorn running on http://0.0.0.0:10000
   ```
3. Now open the **live website**, sign in, and run a **New analysis** on a class.
4. It should show **"Analyzing…"** and then, about a minute later, fill in the feedback on its own. 🎉

---

## If something goes wrong

| What you see | What it usually means | Fix |
|---|---|---|
| Class stuck on **"Analyzing…"** forever | `DATABASE_URL` is missing or wrong | Redo Step 1 → Step 3. Check the **password** is correct and the line ends with `?sslmode=require`. |
| Logs say **`No module named ...`** | A code file wasn't included in the deploy | Tell your developer (this is a code/Dockerfile fix, not a settings one). |
| Logs say **`DATABASE_URL is not set`** | The variable name is misspelled | It must be exactly `DATABASE_URL` (all caps, underscore). Re-check Step 3. |
| **"password authentication failed"** | Wrong DB password in the value | Get the password again (it's in the `.env` file) and re-paste the whole line. |
| First analysis of the day is slow (~1 min extra) | The free worker "sleeps" when idle and has to wake up | Normal — nothing to fix. |

---

## Quick answers

- **Do I need Render for testing on my own laptop?** No. Locally the worker reads these settings from
  the `.env` file automatically. Render is only for the shared **live** website.
- **I changed my database password.** Update `DATABASE_URL` in Render (Step 3) with the new password
  and click **Save Changes** — it redeploys on its own.
- **Which env vars are truly required?** Just two: `DATABASE_URL` and `ANTHROPIC_API_KEY`. The rest are
  optional depending on features.

Related: keeping these secrets safe — see [HOW_IT_WORKS.md](HOW_IT_WORKS.md) §7.
