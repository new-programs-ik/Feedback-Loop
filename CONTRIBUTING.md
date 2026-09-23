# How changes are made here

For: anyone changing Feedback Loop, whether a person or an AI assistant working with one.

## The one rule

**A change is not finished until the document that describes it is true again.** In the same
commit. Every time. The documents are part of the product: a programme manager reads the user
guide, leadership reads the summary, the next developer reads the rest. A document that
contradicts the system is a bug, and it is treated as one.

Which document, by what changed:

| You changed | Update |
|---|---|
| What a person sees or does on a page | [docs/USER_GUIDE.md](docs/USER_GUIDE.md) |
| What runs, when, or what is stored | [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md) (and the summary if leadership would notice) |
| A scoring rule or a band | HOW_IT_WORKS §6, the fixtures, and the user guide's score section |
| A prompt in the engine | run `analysis/build_prompts_doc.py` to regenerate [docs/THE_AI_ANALYSIS_PROMPTS.md](docs/THE_AI_ANALYSIS_PROMPTS.md) |
| An environment variable, a service, a schedule | [DEPLOY.md](DEPLOY.md) and the matching setup guide in `docs/` |
| A table, a policy or a function in the database | [supabase/README.md](supabase/README.md) |
| A worker module or endpoint | [ratings_module_build_kit/README.md](ratings_module_build_kit/README.md) |
| How to run or test locally | [docs/RUN_LOCAL.md](docs/RUN_LOCAL.md) |
| The words used for a code or an enum | `web/src/lib/labels.ts` and the user guide's glossary |

## Before every push, all green

```
ratings_module_build_kit/.venv/Scripts/python.exe -m pytest -q                    # the worker
cd web && npx tsc --noEmit && npx next build && npm test                          # the website
ratings_module_build_kit/.venv/Scripts/python.exe supabase/test_scoring_sql.py    # the database scorer
ratings_module_build_kit/.venv/Scripts/python.exe supabase/test_worker_sql.py     # the worker's SQL, run for real and rolled back
```

A push to `main` deploys to production within minutes. There is no staging environment, so the
tests are the gate. If a change cannot be tested, say so in the commit message and why.

**Tests never touch real services.** `ratings_module_build_kit/conftest.py` sets harmless values for
the database URL and every credential before any test imports the worker, so the production values
in `.env` are never loaded during a test run. A test that needs a database, the Claude API, Vimeo,
Slack or UpLevel fakes it. (Until 23 September 2026 one test ran a real, paid analysis.)

## The database

- Local work and production share one database. **Migrations are additive only**: add tables,
  columns, functions and policies; never drop or rename what exists. Each migration is safe to
  run twice.
- A scoring rule lives in three places that must agree: `analysis/sentiment_score.py` (the
  reference), `web/src/lib/sentiment.ts` (the website's mirror) and `score_class_rating` (a new
  migration). Add fixture cases in `analysis/build_scoring_fixtures.py`, regenerate the fixtures,
  and all three test suites will hold the rule.
- Before a change that rewrites many rows (a scoring switch, a full re-sync), take a backup:
  `analysis/db_backup.py`.
- Never edit the ratings sheet. The sync reads it; nothing writes to it.

## Words

The product uses one vocabulary, and the code follows it:

- "instructor approval" and "learners answered", never "vote" or "voting"
- "learners who rated ÷ learners who attended" or "rated / attended", never "reach" or "turnout"
- bands are Excellent, Good, Average, Bad; a class with fewer than 6 responses is "too few responses"
- actions are "watch the recording", "read the transcript", "nothing needed"
- a re-teach call is "Re-teach recommended", "Consider re-teaching", "No re-teach needed"

No stored code or enum value is ever shown to a person: map it in `web/src/lib/labels.ts`.

## Commits and secrets

- One change per commit, with a message that says what was wrong and what is true now, in
  plain words. The message is the first document of the change.
- Push flow: `git switch -c deploy-x origin/main && git cherry-pick <sha> && git push origin
  deploy-x:main && git switch main && git rebase deploy-x && git branch -d deploy-x`.
- No secrets in the repository, in commit messages, in documents or in chat. Keys live in Render,
  Vercel and a local `.env` that git ignores. A key that has been pasted anywhere is rotated.
- Confidential files (`.xlsx`, `.csv`, `.docx`, `.pdf`, `.env`, the Google key) are ignored by git;
  keep them out of the repository and, ideally, out of the project folder root
  (`local-reports/` is the place for reports).

## Definition of done

1. The behaviour is tested, and every suite is green.
2. The documents that describe the change are true again.
3. Nothing a person sees carries a raw code, a "soon", a placeholder or internal plumbing.
4. The commit message explains the change to someone who was not there.
