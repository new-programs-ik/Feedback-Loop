"""Push the whole ratings history from the local workbook copy through the worker's v3 sync path -
the same tab parser, cohort parsing, instructor and topic resolution, and the scoring function in
the database - so the app carries cohorts, aliases, duplicate-name suggestions and scores without
waiting for the Google service-account key.

    python analysis/resync_from_workbook.py --check     # compare workbook vs database; writes nothing
    python analysis/resync_from_workbook.py --run       # full backup first, then the sync

The run never posts to Slack (the token is stripped from the run's environment and the per-run cap
is 0) and pings the LOCAL site's revalidate endpoint, not production. Local use only: the workbook
is confidential and never committed.
"""
import argparse
import datetime as dt
import json
import logging
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
KIT = os.path.join(ROOT, "ratings_module_build_kit")
sys.path.insert(0, KIT)
sys.path.insert(0, HERE)
import config  # noqa: E402

config.load_env()
import openpyxl  # noqa: E402
import ratings_store as ST  # noqa: E402
import ratings_sync  # noqa: E402
from ratings_data import BOOK  # noqa: E402
from sheet_source import DEFAULT_TABS, SheetRatingsSource  # noqa: E402

KIND_CODES = ("live class", "test review session", "review session")


class WorkbookRatingsSource(SheetRatingsSource):
    """The Google Sheet's tabs read from the local .xlsx copy, handed to the sheet source's own
    parser - so a workbook re-sync and a live sync produce identical canonical rows."""

    name = "sheet"  # the workbook IS the sheet: class_ratings.source stays 'sheet'

    def __init__(self, path: str = BOOK, tabs: str | None = None):
        super().__init__(env={"RATINGS_SHEET_ID": "workbook", "RATINGS_SHEET_TABS": tabs or DEFAULT_TABS})
        self.path = path

    def _get_values(self) -> dict:
        wb = openpyxl.load_workbook(self.path, read_only=True, data_only=True)
        ranges = []
        for tab in self.tabs:
            values = []
            for row in wb[tab].iter_rows(values_only=True):
                values.append([
                    "" if v is None else v.strftime("%Y-%m-%d") if isinstance(v, (dt.datetime, dt.date)) else v
                    for v in row
                ])
            ranges.append({"range": tab, "values": values})
        return {"valueRanges": ranges}


def natural_key(r: dict):
    return (r["class_date"], r["topic"], r["instructor"], r["session_kind"])


def check(src: WorkbookRatingsSource) -> None:
    rows = src.fetch_rows()
    conn = ST.connect()
    cur = conn.cursor()
    cur.execute("select class_date, topic, instructor, session_kind from class_ratings")
    db = {tuple(r) for r in cur.fetchall()}
    wk = {natural_key(r) for r in rows}
    new, gone = sorted(wk - db), sorted(db - wk)
    print(f"workbook rows: {len(rows)} · database rows: {len(db)}")
    print(f"  matched on the natural key: {len(wk & db)}")
    print(f"  new (would be inserted):    {len(new)}")
    for k in new[:15]:
        print("     +", k)
    print(f"  database-only (untouched):  {len(gone)}")
    for k in gone[:15]:
        print("     -", k)
    cur.execute("select count(*) from class_ratings where lower(topic) = any(%s)", (list(KIND_CODES),))
    print("  rows still carrying a kind code as the class name:", cur.fetchone()[0])
    cur.execute("select count(*) from class_ratings where instructor_id is not null")
    linked = cur.fetchone()[0]
    cur.execute("""select count(*) from (select 1 from class_ratings group by class_date, instructor, session_kind
                                          having count(*) > 1) d""")
    print(f"  instructor-linked today: {linked} · same-day repeat (date, instructor, kind) groups: {cur.fetchone()[0]}")
    conn.close()


def snapshot(cur) -> dict:
    q = {
        "class_ratings": "select count(*) from class_ratings",
        "instructor_linked": "select count(instructor_id) from class_ratings",
        "cohort_linked": "select count(cohort_id) from class_ratings",
        "topic_linked": "select count(topic_id) from class_ratings",
        "cohorts": "select count(*) from cohorts",
        "topics": "select count(*) from topics",
        "aliases": "select count(*) from instructor_aliases",
        "suggestions_pending": "select count(*) from instructor_match_suggestions where status = 'pending'",
        "score_history": "select count(*) from class_score_history",
    }
    out = {}
    for k, sql in q.items():
        cur.execute(sql)
        out[k] = cur.fetchone()[0]
    cur.execute("select coalesce(sentiment_band, 'none'), count(*) from class_ratings group by 1 order by 1")
    out["bands"] = dict(cur.fetchall())
    cur.execute("select coalesce(decision, 'none'), count(*) from class_ratings group by 1 order by 1")
    out["decisions"] = dict(cur.fetchall())
    return out


def run(src: WorkbookRatingsSource, ui_url: str) -> None:
    import db_backup

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    out_dir = os.path.join(ROOT, "_archive", "backups", stamp)
    print("1/3 backup ->", out_dir)
    db_backup.dump(out_dir)

    conn = ST.connect()
    cur = conn.cursor()
    before = snapshot(cur)
    conn.close()

    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("SLACK")}
    env["NOTIFY_MAX_PER_RUN"] = "0"
    env["UI_URL"] = ui_url
    print("2/3 sync (Slack off · revalidate ->", ui_url + ")")
    summary = ratings_sync.run_sync(trigger="workbook", env=env, source=src)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("unresolved_names",)}, indent=2, default=str))
    if summary.get("status") != "ok":
        print("SYNC DID NOT COMPLETE - the database was rolled back; the backup is at", out_dir)
        sys.exit(1)

    conn = ST.connect()
    cur = conn.cursor()
    after = snapshot(cur)
    conn.close()
    print("3/3 before -> after")
    for k in before:
        if before[k] != after[k]:
            print(f"  {k:<22} {before[k]} -> {after[k]}")
        else:
            print(f"  {k:<22} {after[k]} (unchanged)")
    names = summary.get("unresolved_names") or []
    print(f"unresolved instructor spellings: {summary.get('instructors_unresolved')} (top: {', '.join(names[:12])})")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="compare the workbook with the database; no writes")
    g.add_argument("--run", action="store_true", help="backup, then sync through the worker path")
    ap.add_argument("--ui-url", default="http://localhost:3000", help="site to revalidate after the run")
    ap.add_argument("--tabs", default=None, help="comma-separated workbook tabs (default: the sync's tabs)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    src = WorkbookRatingsSource(tabs=args.tabs)
    if args.check:
        check(src)
    else:
        run(src, args.ui_url)


if __name__ == "__main__":
    main()
