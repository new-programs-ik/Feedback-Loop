"""
apply_migrations.py — apply supabase/migrations/*.sql to the Supabase Postgres.

Reads DATABASE_URL from the environment, or from ../ratings_module_build_kit/.env.
Each .sql file runs in its own transaction (so an isolated failure — e.g. an auth-hook
permission issue — doesn't roll back the core schema). Files run in filename sort order.

Executes via a raw psycopg2 cursor (not SQLAlchemy) so `%` in the SQL — e.g. `format('%I', ...)`
inside PL/pgSQL — is sent verbatim rather than being treated as a query parameter.

Usage:
  ../ratings_module_build_kit/.venv/Scripts/python.exe supabase/apply_migrations.py
  ...              python supabase/apply_migrations.py 0001_init.sql   # a single file
"""
from __future__ import annotations

import glob
import logging
import os
import re
import sys

import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("apply_migrations")

HERE = os.path.dirname(os.path.abspath(__file__))
MIGRATIONS = os.path.join(HERE, "migrations")
ENV_FILE = os.path.join(HERE, "..", "ratings_module_build_kit", ".env")


def _load_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    if os.path.isfile(ENV_FILE):
        with open(ENV_FILE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("DATABASE_URL="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("DATABASE_URL not set (env or ratings_module_build_kit/.env)")


def _safe(url: str) -> str:
    return re.sub(r"://([^:]+):[^@]+@", r"://\1:***@", url)


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    # psycopg2/libpq understands the postgresql:// URI (incl. %40-encoded password + sslmode).
    url = _load_database_url().replace("postgresql+psycopg2://", "postgresql://")
    log.info("target: %s", _safe(url))
    conn = psycopg2.connect(url, connect_timeout=15)

    files = ([os.path.join(MIGRATIONS, a) for a in argv] if argv
             else sorted(glob.glob(os.path.join(MIGRATIONS, "*.sql"))))
    if not files:
        raise SystemExit(f"no .sql files found in {MIGRATIONS}")

    failures = 0
    for path in files:
        name = os.path.basename(path)
        with open(path, encoding="utf-8") as fh:
            ddl = fh.read()
        try:
            with conn.cursor() as cur:
                cur.execute(ddl)            # one arg → sent verbatim, no % interpolation
            conn.commit()
            log.info("applied %s", name)
        except Exception as e:               # noqa: BLE001 — report per-file, keep going
            conn.rollback()
            failures += 1
            log.error("FAILED %s: %s", name, str(e).strip().splitlines()[0])

    with conn.cursor() as cur:
        cur.execute("select table_name from information_schema.tables "
                    "where table_schema='public' and table_type='BASE TABLE' order by table_name")
        tables = [r[0] for r in cur.fetchall()]
    conn.close()
    log.info("public tables (%d): %s", len(tables), ", ".join(tables))
    if failures:
        log.warning("%d migration file(s) failed — see errors above", failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
