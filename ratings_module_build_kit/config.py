"""
config.py — load a local .env file into the process environment (dependency-free).

Entry points (apply_schema.py, service.py) call ``load_env()`` at startup so secrets
live in .env locally (never committed) and in real env vars / n8n credentials in prod.
Values already present in the environment win — we never override real env vars.
"""
from __future__ import annotations

import os
import re

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
            if line.startswith("export "):
                line = line[len("export "):].lstrip()
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            # A quoted value keeps everything inside the quotes; an unquoted one ends at the first
            # " #" comment. The example file writes settings WITH trailing comments, so copying it
            # used to store the comment as part of the value - and a value like
            # "1     # set to 1 to switch frame sampling off" is truthy, which silently turned the
            # video stage off and made every numeric setting fail to parse.
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            elif val.startswith("#"):
                val = ""                     # "KEY=   # a comment" means the key is simply unset
            else:
                val = re.split(r"\s+#", val, maxsplit=1)[0].strip()
            if key and val:
                os.environ.setdefault(key, val)
