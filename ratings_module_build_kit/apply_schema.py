"""
apply_schema.py — apply schema.sql to the Postgres pointed at by DATABASE_URL (§9 M1).

schema.sql is idempotent (`create table if not exists`), so this is safe to re-run.
This is the one-command way to satisfy the M1 acceptance criterion "schema applied".

Usage:
  # with DATABASE_URL set in the environment (or a local .env you've exported):
  python apply_schema.py
  # or point at a specific database:
  python apply_schema.py "postgresql+psycopg2://user:pass@host:5432/db"

For local logic, no Postgres is needed — the unit tests build the schema on SQLite
from db.metadata (see test_db.py).
"""
from __future__ import annotations

import logging
import os
import sys

from sqlalchemy import text

import config
import db

config.load_env()  # pull DATABASE_URL etc. from .env if present

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("apply_schema")

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, "schema.sql")


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    url = argv[0] if argv else os.environ.get("DATABASE_URL")
    if not url:
        log.error("no DATABASE_URL given (pass it as an argument or set the env var)")
        return 2

    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        ddl = fh.read()

    engine = db.make_engine(url)
    with engine.begin() as conn:
        if url.startswith("postgresql"):
            # psycopg2 executes a multi-statement script in one call.
            conn.exec_driver_sql(ddl)
        else:
            # Other drivers (e.g. sqlite) need statements fed one at a time.
            for stmt in (s.strip() for s in ddl.split(";")):
                if stmt:
                    conn.execute(text(stmt))
    log.info("schema applied to %s", db._safe_url(url))

    # Confirm the four tables exist by touching them.
    with engine.connect() as conn:
        for tbl in ("classes", "analyses", "feedback", "audit_log"):
            conn.execute(text(f"select count(*) from {tbl}"))
    log.info("verified tables: classes, analyses, feedback, audit_log")
    return 0


if __name__ == "__main__":
    sys.exit(main())
