"""Dump every table in the database's public schema to JSON lines, one file per table, under
_archive/backups/<UTC timestamp>/ (the _archive folder is gitignored).

Run it before anything that rewrites many rows - a scoring version switch, a full re-sync, a
migration - so a bad outcome can be put back row by row:

    python analysis/db_backup.py            # every public table
    python analysis/db_backup.py --tables class_ratings,cohorts

Restoring is a manual, table-by-table step on purpose (see docs/DEPLOY.md).
"""
import argparse
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "ratings_module_build_kit"))
import config  # noqa: E402

config.load_env()
import ratings_store as ST  # noqa: E402


def public_tables(cur) -> list[str]:
    cur.execute("""select table_name from information_schema.tables
                    where table_schema = 'public' and table_type = 'BASE TABLE' order by 1""")
    return [r[0] for r in cur.fetchall()]


def dump(out_dir: str, only: list[str] | None = None) -> dict:
    conn = ST.connect()
    cur = conn.cursor()
    tables = [t for t in public_tables(cur) if not only or t in only]
    os.makedirs(out_dir, exist_ok=True)
    manifest = {"taken_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "tables": {}}
    for t in tables:
        path = os.path.join(out_dir, f"{t}.jsonl")
        n = 0
        with conn.cursor(name=f"bk_{t}") as stream, open(path, "w", encoding="utf-8") as fh:
            stream.itersize = 2000
            stream.execute(f'select row_to_json(t) from "{t}" t')
            for (row,) in stream:
                fh.write(json.dumps(row, default=str) + "\n")
                n += 1
        manifest["tables"][t] = n
        print(f"  {t:<36} {n:>7} rows")
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    conn.close()
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tables", help="comma-separated subset (default: every public table)")
    ap.add_argument("--out", help="destination folder (default: _archive/backups/<timestamp>)")
    args = ap.parse_args()
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    out_dir = args.out or os.path.join(ROOT, "_archive", "backups", stamp)
    only = [t.strip() for t in args.tables.split(",")] if args.tables else None
    print("backup ->", out_dir)
    m = dump(out_dir, only)
    print(f"done: {len(m['tables'])} tables, {sum(m['tables'].values())} rows")


if __name__ == "__main__":
    main()
