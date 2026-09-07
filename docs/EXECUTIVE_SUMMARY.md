# Feedback Loop — Executive Summary

**One platform for how the New Programs team judges and improves its classes.**
Every rated class gets the same score. The score decides which classes get an AI analysis. The AI
drafts the instructor feedback; a person approves it before anyone sees it.

| | |
|---|---|
| **Live application** | https://feedback-loop-ten.vercel.app *(sign in with your @interviewkickstart.com Google account)* |
| **Source code (private)** | https://github.com/new-programs-ik/Feedback-Loop |
| **User guide** | [docs/USER_GUIDE.md](USER_GUIDE.md) — task by task, for anyone on the team |
| **Status** | Version 3, September 2026: live ratings data, one score for every class, a workspace per course, a leadership view |
| **Owner** | New Programs — Bishal Roy (new-programs@interviewkickstart.com) |

---

## 1. The problem

The team runs many courses with many instructors, and every class is rated by its learners. Until
now those ratings sat in a spreadsheet, each PM read them their own way, and "how is this class
doing?" had no shared answer. When a class did go badly, writing useful feedback meant watching a
long recording and drafting by hand — 30–60 minutes of expert time per class, so it happened late,
unevenly, or not at all. And the same instructor could appear under several spellings, so nobody
could trust a per-instructor figure.

## 2. What Feedback Loop does now

1. **Pulls every rated class from the team's ratings sheet, every hour.** The sheet stays the
   source of truth; the app keeps a scored copy of all of it, not just the classes someone chose
   to look at.
2. **Scores every class the same way.** The **Class Sentiment Score** is one number from 0 to 100
   built from the star rating, the learners' "would you have this instructor back?" vote, how many
   responded, and how much of the room they represent. Four bands: **Excellent** (90+),
   **Good** (75–89), **Average** (60–74), **Bad** (under 60).
3. **Lets the band decide the work.** Bad → a video analysis. Average → a transcript analysis.
   Good or Excellent → none unless a PM asks. Too few votes → watch. The queue is the same for
   every course, and a Slack card tells the course's people why a class was flagged.
4. **Drafts the feedback with AI**, checks its own findings with a second sceptical pass, and hands
   a PM two things: a short note to send the instructor and a detailed internal version. The PM
   edits, approves and marks it sent. **Nothing is ever sent automatically.**
5. **Shows the picture.** A workspace per course — overview, every class, instructors and their
   portfolios, cohorts week by week, modules, reports — and a team level for leadership: every
   course on one axis, the biggest movers, queue capacity, and whether the loop is closing.

## 3. The score is a setting, not a rule carved in code

Every scoring setting — the weights, the 80% approval bar, the response target, the band edges,
the minimum number of votes, how a missing input is treated — is stored in the database as a
numbered **version**. Six versions are stored today: version 1 is the manager's original method
(60 / 30 / 6 / 4, pass-or-fail on approval and responses); versions 2–6 are drafts that change one
idea at a time (a minimum number of votes; approval earned gradually rather than all-or-nothing; a
guard for classes with only a handful of votes; weights derived from the data; the two agreed lines
of 4.55 and 80% as hard limits).

An admin edits a draft, sees a month of real classes re-scored on the same screen — how many
change band, how many analyses a week that means and what it costs, how many would be dropped from
today's queue, how many would flip on a single vote — and activates it with a name and a note.
Every class is re-scored in one step and the previous version stays one click away. Any PM can try
the same what-if and propose it.

The validation study (*Sentiment-Score-Validation.pdf* and the two-page *Sentiment-Score-One-Pager.pdf*,
shared separately because they contain instructor names) replayed eight months of real classes
through all six versions and recommends which one to activate. The version in force is always the
one marked **Active** on Admin › Scoring, and the queue names it.

## 4. Why the numbers can be trusted

- **One scoring function, inside the database.** The website's copy (used for live previews) and
  the study's Python reference are tested against the same 94 worked cases — the manager's own
  examples plus every awkward edge case we could think of — so the study, the preview, the queue
  and the Slack cards agree.
- **One instructor, one name.** Spellings are resolved through aliases at sync time; suspected
  duplicates are suggested after every sync and a person accepts or rejects them. Merges are
  reversible for 30 days.
- **Cohorts and modules read from the sheet's own text**, so journeys week by week and
  "is this module weak no matter who teaches it?" are answered from data, not memory.
- **Every change is recorded.** Scoring activations, merges, hand-overs, share links, confirmations
  and dismissals all land in an audit log.
- **Nothing destructive.** Database changes in v3 only add; the old rule's fields are kept for one
  release so before and after can be compared.

## 5. Why the AI analysis can be trusted

- It reads the whole session first — who is the instructor, who are the learners, which doubts get
  answered later — before judging any part of it, and never blames the instructor for a learner's
  words.
- Every finding carries a verbatim quote and a timestamp; when unsure it stays silent.
- A second, deliberately sceptical pass re-checks every serious finding and can drop or soften it,
  never invent or escalate one. The reviewer sees what changed and why.
- It can watch the recording as well as read it (a frame every few minutes: camera, screen share,
  slides against the plan). In our earlier A/B comparison, video analysis surfaced about 31% more
  real issues than the transcript alone.
- Two purpose-built checklists: live classes and assignment review sessions.

## 6. How it is built

| Layer | Technology | Role |
|---|---|---|
| Website | Next.js on **Vercel** | Course workspaces, the team level, admin, the review screens |
| Database | **Supabase** (Postgres, sign-in, row-level security) | Single source of truth; the scoring function; who sees what |
| Worker | Python (FastAPI) on **Render** | The hourly ratings sync and Slack cards; the AI analysis engine |
| AI model | **Claude Sonnet 5** | The reasoning behind the analysis and the self-check |
| Data source | The team's **Google Sheet**, read by a view-only service account | Every rated class, every hour |

Covered by **285 worker tests**, **99 web tests**, and the 94-case scoring fixture run against the
database function.

## 7. Security and confidentiality

- Sign-in is limited to **@interviewkickstart.com** accounts; the database enforces access row by
  row, and the ratings tables are readable by staff only.
- Uploaded materials and video frames are never stored; transcripts are deleted automatically after
  20 days. The ratings workbook, the study documents and all keys live outside the repository.
- Report share links are unguessable, expire (30 days by default), can be revoked, and still
  require an IK sign-in.

## 8. What it costs

| Analysis | AI cost per class | Time to result |
|---|---|---|
| Transcript only | about **$0.51** | 3–4 minutes |
| With video | about **$0.70** | 6–8 minutes |

The queue shows the week's cost in dollars and PM hours before anyone starts. Hosting runs on the
free tiers of Vercel, Supabase and Render today.

## 9. Status and roadmap

**Live today (v3):** the hourly sync; the Class Sentiment Score on every class; the queue by
band with Slack cards; course workspaces and the team level; instructor identity; cohorts and
modules; people and ownership with hand-over; the scoring admin with live preview and versions,
plus the what-if for PMs; reports with print, CSV and share links; the AI feedback engine,
unchanged; the audit log.

**Designed, not built (v1.1):** a weekly Slack digest to every course member; a server-rendered PDF;
the learner-level pages — the tables and the ingestion contract exist, the export does not yet;
per-course scoring overrides; a TA-quality view; the bump chart.

**What the team can decide now:** which scoring version to activate (the study's recommendation),
who owns which course (People), and the duplicate-name suggestions waiting on Identity.

---

*Prepared for the New Programs team, Interview Kickstart. Live app:
https://feedback-loop-ten.vercel.app · Code: https://github.com/new-programs-ik/Feedback-Loop*
