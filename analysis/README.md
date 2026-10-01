# analysis/ — the studies, the report builders and the maintenance tools

Local scripts that sit beside the product. None of them is deployed. Most read the confidential
ratings workbook (`data/the rating sheet .xlsx`, never committed) or the database.

| Where | What is in it |
|---|---|
| this folder | **The scoring reference and its study.** `sentiment_score.py` is the reference the database function and the website mirror are held to; `test_sentiment_score.py` and `build_scoring_fixtures.py` keep the three in step. `sentiment_*.py` are the study that chose the settings (`sentiment_run_all.py` runs it). `approval_*.py`, `disputed_classes.py`, `missed_classes.py` and `score_formula_test.py` are the earlier studies. `ratings_data.py` and `instructor_names.py` load the workbook for all of them. |
| this folder | **Two tools the team uses.** `db_backup.py` (a backup before any change that rewrites many rows) and `build_prompts_doc.py` (regenerates `docs/THE_AI_ANALYSIS_PROMPTS.md` after a prompt change). |
| [`reports/`](reports/) | One-off documents for the manager and leadership: the score reports, the decision report, the case and story documents, the weekly report. Each writes a `.docx`, `.pdf` or `.csv`. |
| [`tools/`](tools/) | Maintenance that writes to the database: the full re-sync from the workbook, back-fills, identity seeding, the batch analysis run. Read the top of the file before running one; `db_backup.py` first. |
| [`formula/`](formula/) | The formula search: its own README. |
| `out/` | What the studies wrote. |

A script in `reports/` or `tools/` puts this folder on its import path itself, so it runs from
anywhere: `python analysis/tools/resync_from_workbook.py --check`.

The worker's modules are imported by folder (`from ratings import ratings_store`), after the
script has added `ratings_module_build_kit/` to its path.
