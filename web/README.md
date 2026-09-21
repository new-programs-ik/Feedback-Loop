# The website

Next.js 16 (App Router), React 19, Tailwind 4, TypeScript. Deployed on Vercel from `main`. It
talks to Supabase directly (sign-in, reads and writes under row-level security) and to the
worker for two things only: starting an analysis and starting a sync.

## Run it

```
npm install
npm run dev          # http://localhost:3000, against the production database (see docs/RUN_LOCAL.md)
npm run build && npm start   # what production runs
npm test             # node's test runner over src/**/*.test.ts
npx tsc --noEmit     # the type check the deploy relies on
```

Environment: `.env.local` with `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`,
`SUPABASE_SERVICE_ROLE_KEY` (server-only), `ANALYSIS_WORKER_URL`, `WORKER_API_KEY`. The full
table is in [DEPLOY.md](../DEPLOY.md).

## Where things are

| Path | What |
|---|---|
| `src/app/(app)/c/[course]/…` | The course workspace: overview, classes, queue, instructors, cohorts, modules, feedback, reports, settings |
| `src/app/(app)/team/…` | The same across all courses, for leadership |
| `src/app/(app)/admin/…` | Scoring versions, instructor identity, people, sync, audit |
| `src/app/(app)/feedback/…` | The AI analysis: `new` (the form), `[id]` (the review page), `actions.ts` (start, retry, approve, discard, delete) |
| `src/app/(app)/share/[token]` | The read-only report behind a share link (staff only) |
| `src/lib/sentiment.ts` | The website's copy of the scoring function, pinned to `supabase/fixtures` by `sentiment.test.ts` |
| `src/lib/labels.ts` | Every stored code as the words a person sees |
| `src/lib/analytics.ts`, `src/lib/ratings.ts`, `src/lib/admin.ts` | The reads: summaries, movers, the queue, paging, band counts, admin lists |
| `src/lib/nav.ts`, `src/lib/workspace*.ts`, `src/lib/session.ts` | Navigation, workspaces (`/c/<slug>` and `/team`), roles (`admin`, `pm`, `learner`) |
| `src/components/…` | The UI: score pill and drawer, queue rows, charts, filter bar, admin panels |

## Rules that are not obvious

- Next 16: `middleware.ts` is `proxy.ts`; `cookies()`, `headers()` and route `params` are async.
  See [AGENTS.md](AGENTS.md).
- Authorisation is enforced by the database's row-level security; the page and action checks
  are the first line, not the only one. A server action still checks the role before writing.
- Server actions that finish with `redirect()` throw a `NEXT_REDIRECT` the client must treat as
  success (`feedback/[id]/action-buttons.tsx` shows the pattern); an action that returns
  `{ error }` is shown as a toast.
- Nothing shown to a person is a raw code: add words to `src/lib/labels.ts`.
- The documentation rule in [CONTRIBUTING.md](../CONTRIBUTING.md) applies to every change here.
