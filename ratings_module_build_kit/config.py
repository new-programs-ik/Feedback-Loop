"""
config.py — load a local .env file into the process environment (dependency-free).

Entry points (apply_schema.py, service.py) call ``load_env()`` at startup so secrets
live in .env locally (never committed) and in real env vars / n8n credentials in prod.
Values already present in the environment win — we never override real env vars.
"""
from __future__ import annotations

import os

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ENV = os.path.join(HERE, ".env")


def load_env(path: str | None = None) -> None:
    path = path or DEFAULT_ENV
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and val:
                os.environ.setdefault(key, val)
