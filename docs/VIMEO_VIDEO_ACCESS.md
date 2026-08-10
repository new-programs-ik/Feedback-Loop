# 🎬 Enabling Vimeo VIDEO access — step by step (simple English)

The Feedback Loop can now **watch the class video** (not just read the transcript): it samples a
frame every couple of minutes and checks — was the camera on, was the screen shared, did the slides
match the plan, was there real live coding.

For that it needs permission to **play your Vimeo videos through the API**. Your current Vimeo token
can only read **captions** (that's why transcript fetching already works). This guide adds the one
missing permission. You do it **once**, it takes ~5 minutes, and nothing needs to be redeployed —
the system detects the new permission by itself.

> 🔎 **How we know this is needed:** we tested your current token live. It has the `private public`
> permissions only, and Vimeo returns an empty "play" list for your videos. Adding the
> **`video_files`** permission is the fix.

---

## Step 1 — Open your Vimeo developer app

1. Go to **[developer.vimeo.com/apps](https://developer.vimeo.com/apps)** and sign in with the
   **New Programs** Vimeo account (the one that owns the class recordings).
2. You'll see your app in the list: **"IK Ratings Transcript Fetcher"**. Click it.
   *(It's the app that was created earlier for transcript fetching.)*

## Step 2 — Generate a new token WITH video access

1. Inside the app page, find the **"Authentication"** section (scroll down — it's where personal
   access tokens are generated).
2. Under **"Generate an access token"**, choose **Authenticated (you)**.
3. In the **Scopes** checkboxes, tick ALL THREE of:
   - ✅ **`public`**
   - ✅ **`private`**
   - ✅ **`video_files`**  ← this is the new one that enables video
4. Click **Generate**. Vimeo shows a long token string — **copy it immediately** (it's shown once).

## Step 3 — Put the new token in both places

The token lives in two places — update **both**:

1. **Your computer (local runs):** open
   `C:\Users\DELL\Documents\NP team automation\ratings_module_build_kit\.env`
   in Notepad, find the line starting `VIMEO_ACCESS_TOKEN=`, and replace everything after the `=`
   with the new token. Save.
2. **Render (the live site):** [dashboard.render.com](https://dashboard.render.com) → your worker
   service → **Environment** → find `VIMEO_ACCESS_TOKEN` → **Edit** → paste the new token →
   **Save Changes** (Render redeploys itself, ~1–3 min).

## Step 4 — Check it worked

1. Restart the local worker (or wait for Render's redeploy).
2. Run a **New analysis** with a Vimeo link and tick **"🎬 Analyze the video too"** — leave the
   direct-link box empty.
3. If the analysis page later shows "🎬 Video analyzed: N frames", you're done. 🎉

---

## If it still says "no playable video source"

Two possible reasons, in order of likelihood:

1. **The account tier.** Vimeo only exposes video files through the API on **paid plans**
   (Starter/Standard/Advanced — anything above the free Basic plan). Check which plan the
   **New Programs** account is on at [vimeo.com/settings/membership](https://vimeo.com/settings/membership).
   If it's Basic/free, ask whoever manages IK's Vimeo billing whether the account can be upgraded —
   or keep using the workaround below.
2. **The videos belong to a different Vimeo account.** The token can only play videos owned by (or
   shared with) the account that generated it. If the recordings live in another team's account,
   that account's owner needs to do Steps 1–3 instead.

**Workaround that always works (no Vimeo changes):** when creating the analysis, tick
"🎬 Analyze the video too" and paste a **direct video link** — an mp4 link or a **Google Drive**
link to the recording (shared "Anyone with the link → Viewer"). The system streams frames from it
directly. And if the video can't be read at all, the analysis simply continues transcript-only —
nothing breaks.

---

## What this does NOT do

- It does **not** download or store your videos. The system streams ~40–60 single frames (a few KB
  each) straight from Vimeo's servers, analyzes them in memory, and keeps only the text observations.
- It does **not** give anyone else access to your videos — the token stays in your `.env` and
  Render's secure settings, like the other keys.

Related: [RENDER_SETUP.md](RENDER_SETUP.md) (env vars) · [HOW_IT_WORKS.md](HOW_IT_WORKS.md) (the
video stage in plain English) · [THE_AI_ANALYSIS_PROMPTS.md](THE_AI_ANALYSIS_PROMPTS.md) (the exact
prompts the video stage uses).
