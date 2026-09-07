# The formula study (Feedback Loop v3)

What the Class Sentiment Score should be made of, decided on eight months of real classes and on
every case we could construct. Research only: nothing here touches `web/`, `ratings_module_build_kit/`
or `supabase/`, and the active scoring version in the database is never changed.

## Re-run everything (one command)

```
python analysis/formula/run_all.py             # about 3-4 minutes on the laptop
python analysis/formula/run_all.py --no-loop   # rebuild the report from the last loop
python analysis/formula/run_all.py --full-grid # also run the properties on the full 377k-point grid (slower)
python -m unittest analysis.formula.test_properties
```

Needs `DATABASE_URL` in `ratings_module_build_kit/.env` (the feature table reads the database for cohort,
module and instructor identity; it falls back to the workbook loader without them). Chrome at
`C:/Program Files/Google/Chrome/Application/chrome.exe` prints the PDFs.

## What each script does

| Script | Step | Reads | Writes (under `analysis/out/`) |
|---|---|---|---|
| `common.py` | shared pieces: the two human lines, the time split (fit Jan-May, selection folds Mar/Apr/May, held-out Jun-Aug), AUC, cluster bootstrap, anonymised ids | - | - |
| `features.py` | 1. the feature table: every input measurable at scoring time from a sheet row plus history (time-safe), plus the targets | database (`class_ratings` + `cohorts` + `topics` + `instructors`) | `formula_features.csv`, `formula_features_meta.json` |
| `inputs_signal.py` | 2. which inputs carry signal for which target: univariate AUC / rank correlation, regularised logistic and gradient-boosted ceilings, fixed and rolling time splits, permutation importance | features | `formula_signal.json`, `formula_signal.csv` |
| `trust.py` | 2b. how many votes make a low average believable; the shrinkage strength the data supports (k); the vote's beta prior; the asymmetry test | features | `formula_trust.json` |
| `families.py` | 3. the formula families as small JSON settings: weighted points + trust (a strict superset of the scoring contract, verified against it), monotone logistic, sequential; fitting within the design box | - | - |
| `cases.py` | 4a. the case generator: the full grid (axes), 1,000 random draws, the named adversarial cases | - | `formula_cases.json` |
| `properties.py` | 4b. the 23 properties (principles, not numbers) and the runner over every family; `--full` runs the whole grid | cases, trust | `formula_properties.json` (and `formula_properties_fullgrid.json` from `run_all.py --full-grid`) |
| `evaluate.py` | 5a. the measurements for one formula on one set of months: signal, bands, stability, the two lines, workload, fairness | - | - |
| `loop.py` | 5. the loop: propose, fit on the training months, check the properties, judge on the selection months, simplify; the pre-registered decision rule; the weights ablation | everything above | `formula_log.jsonl`, `formula_results.json`, `formula_recommended.json` |
| `report.py` | 6. the study and the one-pager in the house style (HTML -> Chrome PDF), plus the short summary | all outputs | `formula-study.html`, `formula-one-pager.html`, `formula_summary.md`; `Formula-Study.pdf` and `Formula-One-Pager.pdf` at the repo root |
| `test_properties.py` | the permanent test: the recommended settings and today's v7 pass every property; the manager's original fails exactly the ones the study says | cases, recommended | - |
| `run_all.py` | runs the steps in order and times them | - | - |

`formula_log_dryrun.jsonl` is the first dry run of the loop, kept because the decision rule was amended
after it (see the docstring of `loop.py`).

## The rules the loop follows (fixed before it ran)

- Fit on the training months only; judge on the selection months (Mar, Apr, May - each after fitting on
  the months before); report the held-out months (Jun-Aug) for every candidate, never choose on them.
- Objective: the mean AUC of (100 - score) for "the instructor's next class is low" and "the cohort's next
  class is low", with a cluster-bootstrap standard error.
- Admissible: every property passes; on the selection months false comfort <= 2%, false alarm <= 5%,
  at most 12 analyses and 5 videos a week.
- Adopt: a gain of more than one standard error; or within one standard error and simpler; or as simple
  with fewer verdict flips; or one part more with verdict flips at 10+ votes down by more than 3 points.
- Stop: the fixed exploration (families, inputs, shapes) completes; from the simplification phase on,
  three consecutive iterations without adoption end it; 40 at most.
