# Feedback Loop — Executive Summary

**AI-assisted instructor feedback for Interview Kickstart's New Programs team.**
Turn a low-rated class recording into clear, ready-to-send instructor feedback — drafted by AI in
minutes, approved by a human before anyone sees it.

| | |
|---|---|
| **Live application** | https://feedback-loop-ten.vercel.app *(sign in with your @interviewkickstart.com Google account)* |
| **Source code (private)** | https://github.com/new-programs-ik/Feedback-Loop |
| **User guide** | [docs/USER_GUIDE.md](USER_GUIDE.md) — step-by-step, for anyone on the team |
| **Status** | Live and in use across teams · core analysis fully working · some intake steps still manual (see Roadmap) |
| **Owner** | New Programs — Bishal Roy (new-programs@interviewkickstart.com) |

---

## 1. The problem

When a class is rated poorly, someone has to watch the recording, work out *why* it underperformed, and
write useful, specific feedback for the instructor. Done well, that is 30–60 minutes of expert time per
class — so in practice it happens late, unevenly, or not at all. There was no consistent, scalable way to
tell an instructor **exactly** what to fix, or to flag a class that may need re-teaching.

## 2. The solution

Feedback Loop is a secure web application that automates the hard part while keeping a human in control:

1. A program manager enters a class (course, rating) and points it at the recording (a Vimeo link, or an
   uploaded transcript) plus, optionally, the class materials.
2. The AI reads the transcript, understands the whole session, and — when video analysis is switched
   on — **also looks at the class itself**, sampling frames to check camera, screen share and slides.
   It produces feedback grounded in **exact quotes and timestamps**.
3. A second AI pass **argues against the first one's findings**, dropping or softening anything not
   properly evidenced, before a human ever sees it.
4. The manager reviews, edits (or asks the AI to rewrite), and **approves** — nothing is auto-sent.

**The AI only reads and drafts. A human approves everything.**

## 3. What makes the analysis trustworthy

The system is built to behave like an intelligent reviewer, not a keyword matcher:

- **Understands the whole conversation.** It first reads the entire session to map who is speaking (the
  instructor vs. the learners) and how topics and doubts unfold — *before* judging any part of it.
- **Judges the instructor, fairly.** It never blames the instructor for a learner's words, and it will
  not flag a concern that the instructor resolves later in the same session. This removes the
  false-positives that make automated feedback untrustworthy.
- **Evidence or it doesn't exist.** Every point is backed by a verbatim quote and a timestamp; when
  unsure, it stays silent (precision is valued over volume).
- **It checks its own work.** After drafting, a second, deliberately sceptical pass re-examines every
  serious finding against the real transcript: is the quote genuine, does the rest of the session
  contradict it, does it truly meet the bar for that severity? It can **drop** or **downgrade**
  findings — never invent or escalate them — and the reviewer sees exactly what it changed and why.
- **It can see, not just read** *(optional per class)*. The AI samples a frame every 2–3 minutes and
  checks camera on/off, screen sharing, and whether the slides match the plan — problems a transcript
  can never reveal. In our measured A/B study, video analysis surfaced **~31% more real issues**
  (avg 8.0 → 10.5 flags per class).
- **Two class types.** Separate, purpose-built checklists for **Live classes** and **Assignment Review
  Sessions**.

## 4. Two feedback outputs

Every analysis produces two deliverables from one run:

- **A short, crisp note to send the instructor** — one opening line with the class rating, then
  **bullets: each bullet is one specific error (with its timestamp) and the concrete fix.** No
  walk-through, no padding — the instructor sees exactly what to change. Editable, one click to copy.
- **A detailed, timestamped analysis for the internal team** — every issue with its exact evidence, kept
  in-house for coaching and records. A **PM-only "should this class be re-taught?"** recommendation is
  included and never shown to the instructor.

## 5. Additional capabilities

- **Class materials, any way you have them** — upload a file, paste text, or paste a **link** (Google
  Drive / Docs / Slides, or an internal materials app). The AI checks the class against what was planned.
  Materials are used only for that one analysis and are **never stored**.
- **Built-in "which analysis?" helper** — the team's selection rule is encoded in the app. Enter the
  class rating, how many attended and how many rated, and it tells you whether to skip the class, run a
  transcript analysis, or run a video analysis — and switches video on with one click. (Rule: rating
  above 4.5 → usually no analysis; below 4.5 → rating participation ≥ 80% → video, otherwise
  transcript; any escalation → always video.) Works for every program: ML, Agentic, FDE, LevelUp, B2B, PwC.
- **Verify anything yourself** — every report links straight to the class recording, and each finding
  carries its timestamp, so a claim takes seconds to check.
- **Safe to operate** — the engine's status is shown on the dashboard, a stalled or failed analysis is
  detected and can be re-run with one click, and approved feedback can be marked as sent so the team
  knows what has actually gone out.
- **Cost transparency** — every analysis records its exact cost; the dashboard shows spend **this month,
  all-time, and month by month**.
- **Full audit trail** — who created, edited, approved, or discarded each analysis.
- **Roles & access** — Admin and Program Manager roles; sign-in restricted to @interviewkickstart.com.

## 6. How it's built (at a glance)

| Layer | Technology | Role |
|---|---|---|
| Web app | Next.js on **Vercel** | The interface, login, and all reads/writes |
| Database | **Supabase** (Postgres + Auth + Row-Level Security) | Single source of truth; enforces who sees what |
| Analysis worker | Python (FastAPI) on **Render** | Fetches transcripts, runs the AI, returns results |
| AI model | **Claude Sonnet 4.6** | The reasoning engine behind the analysis |

Long analyses run in the **background**, so the app stays fast and never times out. The codebase is
covered by **181 automated tests**.

## 7. Security & confidentiality

- Sign-in is limited to **@interviewkickstart.com** accounts; the database enforces access at the row
  level, so people only see what they should.
- **Uploaded materials are never stored** — read once for the analysis, then discarded. **Transcripts
  auto-delete after 20 days.** No confidential class data or credentials live in the source code.
- The repository is **private**.

## 8. What it costs

Measured on real classes:

| Analysis type | AI cost per class | Time to result |
|---|---|---|
| Transcript only | **~$0.51** | ~3–4 minutes |
| With video analysis | **~$0.70** | ~6–8 minutes |

At the team's typical 3–4 classes/week that is roughly **$7–11 per month** — negligible next to the
30–60 minutes of expert time (and up to a 4-hour recording) it replaces per class.

## 9. Status & roadmap

**Live today:** the full analysis → review → approve → mark-as-sent flow; both feedback outputs;
optional video analysis; the AI self-check pass; the which-analysis helper; materials by upload/link;
cost tracking; roles; and a full audit trail — in cross-team use, with a
[step-by-step user guide](USER_GUIDE.md).

**Still manual (by design, for now):** a manager copies the recording link from UpLevel, provides any
materials, and approves each draft.

**Planned (future scope):** pull the recording link (and low-rated classes) automatically from UpLevel
so the intake is end-to-end; extend analytics for learners, instructors, courses, and cohorts —
including a Learner Health Score already designed into the data model.

---

*Prepared for the New Programs team, Interview Kickstart. Live app:
https://feedback-loop-ten.vercel.app · Code: https://github.com/new-programs-ik/Feedback-Loop*
