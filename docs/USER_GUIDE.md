# 📖 Feedback Loop — User Guide

**How the New Programs team finds the classes that need attention, understands why, and turns
them into ready-to-send instructor feedback.**

Written for anyone on the team — no technical background needed. Each section is one task.

| | |
|---|---|
| **The app** | https://feedback-loop-ten.vercel.app |
| **Illustrated version** | A version of this guide with real screenshots is shared by the New Programs team (ask Bishal Roy). Screenshots stay out of this repo because they show real class and instructor data. |
| **Questions / ideas** | Message **Bishal Roy** (New Programs) or open an [Issue](https://github.com/new-programs-ik/Feedback-Loop/issues). |

---

## Before you start — five things to know

1. **Sign in** at the app with **Continue with Google** and your **@interviewkickstart.com**
   account. (On a local copy, an email + password login is used instead.)
2. **Where you land.** Your own course, if you are on one — otherwise the last course you used,
   or *All courses* (`/team`) if you are an admin. The coloured square at the top of the left rail
   is the **course switcher**: *My courses* first, then every course, with *All courses* pinned at
   the bottom. Course is a label, not a wall — everyone on the team can read every course.
3. **`⌘K` (Ctrl-K on Windows)** opens the command palette: type any page, course or instructor
   name, or *Sync now*.
4. **The score.** Every class has a **Class Sentiment Score** from 0 to 100 and a band:
   **Excellent** (90 and up) · **Good** (75–89) · **Average** (60–74) · **Bad** (under 60).
   The band decides the work: Bad → video analysis, Average → transcript analysis, Good or
   Excellent → nothing unless you ask, too few responses → watch. Hover any score to see how it
   was made. A pill that says **avg** and is drawn outlined is an average, not a class. **"— · too
   few responses"** means fewer than 6 learners answered, so no band is shown.
5. **The filter bar** (period · cohort · live/review · instructor · band) sits on every data page
   and lives in the address bar, so a filtered view is a link you can send.
6. **Every table sorts.** Click a column heading to sort by it; click again to flip the order. Lists
   that are not tables (the course cards, the queue) have a **Sort by** control instead. Next to
   every score you will also see the raw numbers — the star rating, then *who rated / who came*
   (for example **4.62 · 12/26**).

---

## To find which classes need analysis this week

1. Open your course and click **Needs analysis** in the rail (or **Queue** at *All courses*, which
   has a chip per course).
2. The queue has three sections: **Bad → video**, **Average → transcript**, and **Watch** (too few
   votes yet). Under each row is the reason in plain words — *"Rated 4.31 · 7 of 16 would have the
   instructor back (44%) → Bad → video analysis."*
3. The line at the top is the week's bill before you start: *"5 videos · 9 transcripts ≈ $8.09 ·
   ~1.1 h"*. The filter bar defaults to the last 45 days and to *open* rows (new · handler pinged ·
   confirmed).
4. For each row decide:
   - **Confirm** — yes, analyse it (this is the acknowledgement of the Slack card).
   - **Dismiss** — no analysis needed. The row fades out and never comes back on its own.
   - **Escalate** — something was reported: force a video analysis whatever the numbers say.
   - **Analyze** — go straight to the analysis form, prefilled.
5. Not seeing today's classes? Click **Sync now** (top right). The sheet is pulled on its own
   at 10:00, 12:00 and 14:00 India time; the small line under the cost tells you when it last
   ran. A run takes seconds: only rows the sheet changed are written.

> 💬 **The Slack card.** When a class is flagged, a card appears in the team's Slack channel:
> *"Sentiment 58 · Bad → video"*, the course and class, the instructor, the rating, the vote, why,
> and a **Review in Feedback Loop** button that opens this queue with the class in focus. It
> mentions the course's people — the handler first.

## To understand why a class got its score

1. Open **Classes** (every class in the period, scored) or the queue, and click the row. A
   **drawer** opens on the right; the address bar gains `?class=…`, so you can send the link.
   *Full page* at the top opens the same thing as a page you can print.
2. Read it top to bottom:
   - The score and band, with a bar showing where it sits in the four zones.
   - **Rule says** — one sentence: the band, the action, and why.
   - The flags in words — *no approval answer recorded*, *more learners rated than attended*, *the
     rating and the instructor approval disagree*, *instructor approval below the bar the team set*…
   - **What the score is made of** — each part (rating, approval, responses, rated ÷ attended, track
     record when the version uses it), what was measured, and the points it earned out of its weight.
   - **The room** — *Would have the instructor back* (9 of 12 · 75%) and *Rated / attended*
     (12 of 30).
   - The instructor's recent classes and **This module** (the module's average).
   - **Actions** — Analyze · Confirm · Dismiss · Escalate.
   - **History** — the class's score under each scoring version it has been through, and the
     Slack pings.
3. To see which scoring version is in force, look at the queue's filter bar (*Scoring: … · v1*)
   or Admin › Scoring.

## To run an AI analysis on a class

1. From the queue or the drawer, click **Analyze**. The New analysis form opens with the course,
   class name, instructor, date, kind, rating and responses filled in. Starting from a blank
   form also works: **Feedback → New analysis** inside your course. The queue's band is the
   team's verdict on which analysis to run.
2. Give it the recording. The class's **Vimeo link** lives in IK's UpLevel: *Resources → Videos →*
   open the class *→ Basic Details →* copy the **VIMEO URL** box. Or upload a `.vtt` / `.srt`
   transcript file.
3. Tick **🎬 Analyze the video too** when the band says video. It adds a few minutes and about
   $0.20, and catches camera and screen problems that words never show.
4. Optionally attach **materials** — upload slides or a notebook, paste a Google Drive link, or
   paste text. It makes the analysis more precise; materials are never stored.
5. Click **Analyze class** and wait. The page refreshes itself: 3–4 minutes transcript-only, 6–8
   with video. If it fails or looks stuck for more than 30 minutes, the page says so and offers
   **Retry analysis**.
6. Read the report. Check the badges first — **🎬 Video verified · N frames** or **Transcript
   only** (hover for why), and **✓ Self-checked**. **▶ Watch recording** opens the video so you can
   check any flag yourself. The report has five parts: *Overall*, the *Flags* (each with severity,
   an exact quote and a timestamp), the *Self-check* (what the second reviewer confirmed, softened
   or removed), the **Summary to send the instructor** (one opening line with the rating, then at
   most four or five bullets — one error and its Fix each; **this is the only part the instructor
   receives**), and the PM-only *Re-class recommendation*.
7. **Edit** the text directly, or type what you want changed under it — "warmer", "focus on the
   skipped problems" — and click **Revise**. Repeat until it is right.
8. **Approve & store**, **copy** the summary, send it the way you normally do, then click
   **Mark as sent**. The class shows *Sent to instructor ✓*, and the report's loop funnel counts
   it.

> **Nothing is ever sent automatically.** The AI only drafts. A person approves and sends.

## To see how a course is doing

1. Open the course → **Overview**. The KPI row (classes rated, average score, band mix, approval
   against the 80% bar, rated / attended, attended per class, open queue) compares the period with
   the one before it.
2. Change the period in the filter bar (7 / 30 / 45 / 90 days, this month, or custom) and narrow
   by cohort, live vs review, instructor or band.
3. Then read down: **Score by week** (the four band zones shaded), **Band mix by week**, **Worst
   classes** (a row opens the class), **Instructors** (three or more classes; the bullet compares
   with the course average), **Live vs review**, **Module hot-spots**, **Cohorts** side by side,
   **Score against how many learners rated** ("is a low score just a few people rating?"), and the
   **Calendar** ("do bad classes cluster on certain days?").
4. For the whole team, open **All courses**: a card per course sorted by the share of Bad classes,
   every course on one axis, the instructors and modules that moved month over month, the course ×
   month matrix, queue capacity, and whether the loop is closing. The housekeeping line at the top
   names what is silently wrong — an unmapped sheet label, a course without a handler, duplicate
   names waiting — with a link to the page that fixes it.

## To look at one instructor

1. Course → **Instructors**. The leaderboard ranks instructors with three or more classes (sort by
   best, worst, most classes or recent); those with fewer are listed below it. *All courses →
   Instructors* is the same across every course.
2. Click a name for the **portfolio**: the header (the name, *also recorded as …* for other
   spellings, classes, average score, band mix, approval, rated / attended, against the course), **Score
   trend** (a marker on each week AI feedback was sent), **Modules** (this instructor against the
   course's module averages — strengths and weaknesses), **Monthly approval** against the 80% bar,
   **The four boxes** (fine on both lines / polite rating / hard class, good teacher / fails both),
   **Best five** and **Worst five** classes, and **AI feedback** — every note sent, with the
   average of the next three classes.

## To see where attendance drops, where the rating dips, and who lifts a module

Course → **Cohorts** opens the **curriculum map**: one row per cohort, one column per module in
the order the course teaches them. Every cell shows the class's **rating** over **who rated / who
came**, tinted by its band. Read it across a row to follow one cohort; read it down a column to
see how one module goes for every cohort. The bottom row is the module's average line, with the
fall in attendance against the module before it (red from −10%).

- **Insights** at the top say it in sentences — *attendance falls most at…*, *the rating dips
  most at…*, *… is under the line in 4 of 6 cohorts, taught by 3 different instructors*, *… teaches
  it above its average* — each one a link to the cohort or module.
- **Tint** switches what the colour means: *Score* (the band), *Rating* alone, *Attendance*
  against that cohort's first class, or *Reach* (the share that rated). The numbers never change.
- **Show instructors** prints the instructor's initials in each cell; hover any cell for date,
  instructor, kind and score. **Click a cell** (or press Enter on it) to open that class in place.
- A course with several **tracks** (SWEs, EMs, PMs …) is read one track at a time — the biggest
  first — or all together.
- Below the map: **Attendance along the course** and **Rating along the course** (one line per
  cohort, the median in bold; switch the axis between module and week), then the cohort table
  (avg score, avg rating, avg attended, rated / attended, retention — sortable).

Click a cohort for its own page: avg attended and retention next to the score, **The journey**,
**How many attended, and how many rated, by week**, and every class as a sortable table (week ·
module · date · kind · instructor · rating · rated / attended · score).

Course → **Modules** lists every module in curriculum order with the raw numbers, the change in
attendance and rating against the module before it, **Teaches it best** (the instructor whose
rating on that module is highest, against the module's average) and **Struggles with it**. The
**tag** tells you where the problem is: **content** = low across two or more instructors (the
material), **delivery** = low for one of several (the teaching). The **Module × instructor**
matrix switches between rating, attendance and score. Click a module for *By instructor* (who
lifts it, who needs coaching), *Every class*, and *Rating by cohort* — a module that got fixed over
time shows there.

An instructor's page has the same idea from their side: **Modules this instructor lifts** and
**Modules that need coaching**.

## To print the weekly report (or share it)

1. Course → **Reports** (or *All courses → Reports* for every course). Pick **Weekly**, **Monthly**
   or **Custom**; the arrows move to the previous or next period.
2. The page has the headline tiles against the previous period, *Score vs the previous period*,
   the instructors and modules that moved, the worst classes and what happened to each, the
   instructors, the cohorts, the modules, and *Loop outcomes* (flagged → confirmed → analysed →
   approved → sent, with days per step).
3. Three buttons at the top right:
   - **Print / Save PDF** — your browser's print dialog; choose *Save as PDF*. The page breaks
     cleanly between sections on A4.
   - **CSV** — every scored class in the period as a spreadsheet.
   - **Share** — creates a read-only link that works for 30 days, and copies it. The person you
     send it to still signs in with an IK account, and sees the report with no filters or actions.
     To withdraw a link: course → **Settings → Shares** (or Admin › People for every course) →
     revoke.

## To suggest a different scoring setting

Ask an admin: **Admin → Scoring** has the editor with a live preview on real months (how many
classes change band, how many analyses a week that means, which classes move). A change goes
live only when an admin activates it, and the previous version stays one click away.

## To change a scoring setting (admin)

1. Open **Admin → Scoring**. The header names the version that is live. The *Versions* table
   lists every stored version — draft, active or retired — with **New draft**, **Roll back to
   this** (retired versions) and **Delete** (drafts).
2. Start a draft: **New draft from this version** (from the live one), from any stored version, or
   from one of the two presets (the manager's original; *Two lines + graded score*). Proposals
   from PMs appear here as drafts too.
3. Edit the settings on the left and watch the preview on the right. **Compare with the database**
   asks the database itself to compute the same summary, so the two agree before you go further.
   Give the draft a name, a key and a note; **Save draft** at any time.
4. **Publish this version**, then **Publish and re-score**. The note is required — it goes into
   the audit trail. Every class in the database is re-scored in one step, the queue follows the
   new bands, a history row is written for every class that changed, and every page refreshes.
5. To go back: **Roll back to this** on the previously active version (version 1 is the manager's
   original). Same one-step re-score, same audit trail.

> Version 1 is the manager's original method. Versions 2–6 are the candidates from the validation
> study (*Sentiment-Score-Validation.pdf*, shared separately), which recommends which to activate.

## To merge two spellings of an instructor (admin)

1. Open **Admin → Identity**. The header counts suspected duplicates, unresolved names and
   instructors.
2. **Suspected duplicates** shows each suggestion side by side — classes, first and last dates,
   average, top modules — with a confidence. Click **Accept** (the spelling becomes an alias and
   its classes move) or **Not the same person** (never suggested again). **Accept all** above a
   confidence you choose handles the obvious ones in one go.
3. **Unresolved names** are spellings the sync could not link to anyone: **Link to an existing
   instructor**, or create a new instructor from the spelling.
4. **Instructors** is the directory. To merge two rows: pick **Merge this (duplicate)** and **Into
   this (keep)**, read the preview of what moves, confirm. The duplicate spelling stays as an alias
   so future syncs resolve it.
5. Changed your mind? The recent merges at the bottom have **Undo** for 30 days. Undo puts every
   moved row back exactly.

Merged identities flow everywhere: the classes table, the leaderboard, the portfolio (which lists
*also recorded as …*), the track record inside the score, the Slack card, and the analysis form's
instructor autocomplete.

## To hand a course to another PM, or change who is on it

1. Course → **Settings → Team**. You can edit if you are the course's **owner** or an admin;
   everyone else reads.
2. **Add by IK email** — type the person's IK address, pick a role (**Owner**, **PM** or
   **Viewer**) and, if they only look after one cohort, the cohort. They are linked to their login
   the first time they sign in.
3. The ★ marks the **handler** — the one person a flagged class is addressed to first. There is
   exactly one per course. **Hand over to…** picks the new handler and asks for a short note; both
   go into the audit trail, and Slack routing follows on the next sync.
4. **Notifications** tab: Slack on or off per person (you can always change your own). Who gets
   pinged: every member with Slack on, the handler first; a member scoped to a cohort only for
   that cohort's classes. A course with nobody on it gets a card that says *No owner assigned*.
5. **Cohorts** tab: rename a cohort. **Modules** tab: map a raw class name to a module once — it
   sticks for every sync.
6. Admins see the whole **people × courses** matrix on **Admin → People**, plus each course's
   colour and initials and every share link.

## To check the sync, or map a sheet label the app does not know

1. **Admin → Sync** lists the last runs: status, trigger (*cron:Asia/Kolkata* = the schedule,
   *manual* = Sync now), how long it took, rows read, written and unchanged (with the scoring
   version), the band counts, cohorts it could not parse, unresolved names, suggestions created,
   any error, and "scheduled runs not picked up" (the worker did not answer a scheduled run).
2. **Unmapped course labels** are cohort texts the app could not match to a course — their classes
   are missing from course pages until mapped. Pick the course and click **Map**; existing rows
   are moved at once. (The same box appears at the top of *All courses → Queue*.)
3. Unresolved instructor names and waiting suggestions link to **Identity**.
4. A failed run also posts a warning to the Slack channel with the reason (a renamed column in the
   sheet is the usual cause).

## To check that the score can be trusted

The scoring page (**Admin → Scoring**) previews any version on real months, and the shared
fixtures pin the formula in the database, the website and the reference scorer alike. The formula
study that chose the live settings is in `analysis/formula/` and the manager's reports are in
`local-reports/` on the project computer.

## Questions people ask

| Question | Answer |
|---|---|
| The score looks harsh — one "no" answer sank a class. | Hover the score: the breakdown shows what each part earned. With fewer than 6 responses the approval answers are not trusted at all: the class shows "too few responses" instead of a band, unless it is rated below 4.3, in which case its transcript is read. |
| A class shows "— · too few responses". | Fewer than 6 learners answered. It sits in the queue's **Watch** section until more responses arrive; a PM can escalate it if something is known to be wrong. |
| I dismissed a class by mistake. | In the queue, set the **Status** filter to *Dismissed*, open the row and click **Escalate** — it re-opens as a video analysis. |
| The instructor's name is spelled two ways. | Admin → Identity; see *To merge two spellings*. Until then both spellings show separately. |
| A cohort is missing from the Cohorts page. | Its text in the sheet could not be parsed, or the class is unmapped. Admin → Sync shows unparsed cohorts per run; Settings → Cohorts lets you rename. |
| What does one analysis cost? | About $0.51 transcript-only, about $0.70 with video. The queue shows the week's total; each analysis shows its exact cost. |
| A class says **Starting…** for a while. | The analysis service was asleep, or could not be reached for a moment. The class is queued and the service picks it up on its own within a couple of minutes; the page updates by itself. After ten minutes with no taker it says so and offers **Retry**. |
| The analysis didn't finish. | The reason is on the page, in words, with what to do. **Retry** runs it again (transcript-only: materials and video are not stored). If the reason mentions the database, wait a minute first. |
| "The AI account has no credit left." | The Anthropic account that runs the analyses is empty. Whoever holds it adds credit at console.anthropic.com › Plans & Billing; then press **Retry**. Nothing was charged for the failed run. |
| Is my materials file stored? | No. Materials and video frames are used in memory for that one analysis, then discarded. Transcripts auto-delete after 20 days. |
| Who can see the re-class recommendation? | Only signed-in IK staff, in this tool. It is never part of the instructor note. |
| An old Slack link goes to a page I do not recognise. | Old links redirect to the new course pages; the class they pointed at opens in the queue with the drawer. |
| Something is wrong / I have an idea. | Message **Bishal Roy** (New Programs), or open an issue on this repo. |

---

**More reading:** [How it works](HOW_IT_WORKS.md) · [The exact AI prompts](THE_AI_ANALYSIS_PROMPTS.md)
· [Executive summary](EXECUTIVE_SUMMARY.md)
