# Feedback Loop — Executive Summary

**AI-assisted instructor feedback for Interview Kickstart's New Programs team.**
Turn a low-rated class recording into clear, ready-to-send instructor feedback — drafted by AI in
minutes, approved by a human before anyone sees it.

| | |
|---|---|
| **Live application** | https://feedback-loop-ten.vercel.app *(sign in with your @interviewkickstart.com Google account)* |
| **Source code (private)** | https://github.com/new-programs-ik/Feedback-Loop |
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
2. The AI reads the transcript, understands the whole session, and produces feedback grounded in
   **exact quotes and timestamps**.
3. The manager reviews, edits (or asks the AI to rewrite), and **approves** — nothing is auto-sent.

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
- **Two class types.** Separate, purpose-built checklists for **Live classes** and **Assignment Review
  Sessions**.

## 4. Two feedback outputs

Every analysis produces two deliverables from one run:

- **A short note to send the instructor** — 6–7 warm sentences: what went well, what didn't, the class
  rating, one concrete suggestion, and an encouraging close. Editable, and one click to copy.
- **A detailed, timestamped analysis for the internal team** — every issue with its exact evidence, kept
  in-house for coaching and records. A **PM-only "should this class be re-taught?"** recommendation is
  included and never shown to the instructor.

## 5. Additional capabilities

- **Class materials, any way you have them** — upload a file, paste text, or paste a **link** (Google
  Drive / Docs / Slides, or an internal materials app). The AI checks the class against what was planned.
  Materials are used only for that one analysis and are **never stored**.
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
covered by 100+ automated tests.

## 7. Security & confidentiality

- Sign-in is limited to **@interviewkickstart.com** accounts; the database enforces access at the row
  level, so people only see what they should.
- **Uploaded materials are never stored** — read once for the analysis, then discarded. **Transcripts
  auto-delete after 20 days.** No confidential class data or credentials live in the source code.
- The repository is **private**.

## 8. What it costs

Roughly **~$1 of AI cost per class** (a little more when materials are included). At the team's typical
3–4 classes/week, that is about **$12–16 per month** — negligible next to the expert time it saves.

## 9. Status & roadmap

**Live today:** the full analysis → review → approve flow, both feedback outputs, materials by
upload/link, cost tracking, roles, and audit trail — in cross-team use.

**Still manual (by design, for now):** a manager provides the recording link and materials link and
approves each draft.

**Planned (future scope):** progressively automate the intake end-to-end (auto-pull low-rated classes
and their recordings/materials), and extend analytics for learners, instructors, courses, and cohorts —
including a Learner Health Score already designed into the data model.

---

*Prepared for the New Programs team, Interview Kickstart. Live app:
https://feedback-loop-ten.vercel.app · Code: https://github.com/new-programs-ik/Feedback-Loop*
