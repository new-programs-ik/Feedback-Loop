# 📋 The manager's study — exactly what to do, step by step

Three things your manager asked for:

1. **How many bad classes happen in a week** (average).
2. **A monthly table** of tokens + approximate cost, **with video analysis and without**.
3. **The difference in the analysis** — at least **5 videos**, each run **both ways**.

You collect the numbers using the app. Then send them to me and I write the final report.
Nothing here needs technical skill — it's all clicking and copying what's on screen.

---

## PART 1 — Average bad classes per week

**What counts as a "bad class":** a class whose average rating is **below 4.5** (the line the tool uses).

**Where to get it:** wherever your team already tracks class ratings (the ratings sheet / dashboard your
team uses). You need one number per week.

**What to send me** — just fill this in (8–12 weeks is ideal; 4 is enough):

| Week starting | Total classes held | Classes rated below 4.5 |
|---|---|---|
| e.g. 2026-06-01 | 22 | 3 |
| … | | |

> If pulling "total classes held" is hard, **just send the bad-class count** — that's the number the
> manager asked for. The total only makes the report stronger (it lets us say "X% of classes").

**Reference (what the app itself has recorded so far):** 2.4 analyses per week over the last 5 weeks
(2, 5, 1, 1, 3). That's *classes you actually ran through the tool*, which may be lower than the real
number of bad classes — that's why the number from your ratings source is the one that counts.

---

## PART 2 — The token & cost table

Good news: **the app already tracks this for you.** Every analysis stores its exact tokens and cost.

**Steps:**
1. Open the app → **Dashboard**.
2. In the **AI spending** card, note: **this month**, **all time**, **average per class**, and the
   month-by-month bars.
3. Open **Feedback**. The list shows **Cost** per class, and above the table a line like
   *"14 classes · 210.5k tokens · $13.60"*.
4. Use the **Month filter** to get one month at a time, and write down the totals.

**What to send me:**

| Month | Analyses run | Total tokens | Total cost |
|---|---|---|---|
| Jul 2026 | 8 | 0.9M | $3.60 |
| … | | | |

(The with-video vs without-video comparison comes from Part 3 — I'll combine them into the final
monthly projection table.)

---

## PART 3 — The 5-video comparison (the important one)

You run **the same 5 class recordings twice**: once **without** video, once **with** video. Then we
compare what changed.

### Pick the 5 videos
Use real class recordings that have **captions on Vimeo** (all your recent ones do). Mix them up:
ideally **3 live classes + 2 ARS**, and at least one class you *know* had a problem (camera off,
screen issues) — that's where video should prove itself.

### For EACH video, do these two runs

**Run A — WITHOUT video**
1. **Feedback → New analysis**
2. Course: pick any (e.g. the real course) · **Topic: type `<class name> — A (no video)`** ← the label
   matters so you can tell the two runs apart later
3. Instructor, date, rating: fill in the real values
4. Class type: **Live class** or **Assignment review (ARS)** — must match reality
5. Recording: paste the **Vimeo link**
6. **Leave the "🎬 Analyze the video too" box UNTICKED**
7. Click **Analyze class** → wait until the page fills in (a few minutes)

**Run B — WITH video**
1. Same steps, but **Topic: `<class name> — B (with video)`**
2. **TICK the "🎬 Analyze the video too" box** (leave the extra link box empty — Vimeo works directly now)
3. Click **Analyze class** → this one takes longer (5–10 extra minutes)

> ⚠️ Do them **one at a time** — wait for one to finish before starting the next. Ten analyses total.
> Expect roughly **1.5–2 hours** of waiting overall and **$5–8** of AI cost for the whole study.

### What to record for each run

Open each finished analysis and copy these off the screen:

| What | Where to find it |
|---|---|
| **Video verified?** | The badge next to the class title: *"🎬 Video verified · N frames"* or *"Transcript only"* |
| **Cost** | The Feedback list, **Cost** column |
| **Tokens** | The Feedback list totals line (filter to that class) |
| **Number of flags** | The **Flags (N)** card heading |
| **The flags themselves** | Each flag's name + severity (e.g. `pace — moderate`) |
| **Re-class** | The re-class card: yes / no / maybe |
| **Self-check** | What the Self-check card says (confirmed / downgraded / removed) |
| **Anything video-only** | Flags with a **🎬 video** chip on their evidence |

**Easiest way to send it to me:** for each of the 10 runs, just copy-paste the **Overall**, the
**Flags list**, the **Re-class line**, and the **cost** — or simply screenshot each report. Raw is
fine; I'll structure it.

**Fill-in table (or just send screenshots):**

| # | Class name | Type | Mode | Video verified | Flags | Re-class | Tokens | Cost |
|---|---|---|---|---|---|---|---|---|
| 1 | CV-3 ARS | ARS | A no-video | Transcript only | | | | |
| 1 | CV-3 ARS | ARS | B with video | 🎬 60 frames | | | | |
| 2 | … | | | | | | | |

---

## Reference numbers already measured (you can reuse these)

These are real runs from this system — feel free to include them or re-run them yourself:

| Class | Mode | Result |
|---|---|---|
| Computer Vision 3 (ARS, 146 min) | **without video** | 10 flags · **$0.36** · 152 seconds |
| Computer Vision 3 (ARS, 146 min) | **video stage alone** | 60 frames · **$0.145** · 192 seconds |

The video stage on that class found: **camera off for the entire session**, **~18 minutes of blank/
frozen screen at the start**, **text too small to read** during the core code walkthrough, and
**~40 minutes of blank screen at the end** — none of which a transcript can show.

---

## When you're done

Send me:
1. The **weekly bad-class counts** (Part 1)
2. The **monthly totals** from the dashboard (Part 2)
3. The **10 run results** — table, copy-paste, or screenshots (Part 3)

I'll produce the finished manager report: the weekly average, the monthly cost table **with vs without
video**, a clear side-by-side of what video adds, and a recommendation on when video analysis is worth
turning on.
