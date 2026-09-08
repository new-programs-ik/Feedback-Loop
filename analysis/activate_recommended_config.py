"""Store the validation study's recommended scoring settings as a new version and activate it.

    python analysis/activate_recommended_config.py --dry-run   # what would change; writes nothing
    python analysis/activate_recommended_config.py --apply     # store the version (once) and activate it

Reads analysis/out/recommended_config.json (written by analysis/sentiment_decide.py). Activation
runs apply_scoring_config in the database: every class is re-scored in one statement, the score
history and the audit row are written by the function itself. Rollback = activate the previous
version on Admin > Scoring (one click) - nothing here is destructive.
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

RECOMMENDED = os.path.join(HERE, "out", "recommended_config.json")
KEY = "validated-2026-08"
NAME = "Recommended — validated on Jan–Aug 2026"
WINDOW = ("2026-01-01", "2026-08-31")


def load_recommended() -> tuple[dict, str]:
    with open(RECOMMENDED, encoding="utf-8") as fh:
        raw = json.load(fh)
    note = raw.pop("note", "") or ""
    cfg = {**raw, "name": NAME}
    return cfg, note


def current_state(cur) -> dict:
    cur.execute("select version, name, status from scoring_configs where status = 'active'")
    active = cur.fetchone()
    cur.execute("select coalesce(sentiment_band, 'none'), count(*) from class_ratings group by 1 order by 1")
    bands = dict(cur.fetchall())
    cur.execute("select coalesce(decision, 'none'), count(*) from class_ratings group by 1 order by 1")
    decisions = dict(cur.fetchall())
    cur.execute("""select coalesce(decision, 'none'), count(*) from class_ratings
                    where class_date >= current_date - 45 group by 1 order by 1""")
    recent = dict(cur.fetchall())
    cur.execute("select count(*) from class_score_history")
    return {"active": active, "bands": bands, "decisions": decisions, "last_45_days": recent,
            "history_rows": cur.fetchone()[0]}


def whatif(cur, cfg: dict) -> dict:
    cur.execute("select scoring_whatif_summary(%s::jsonb, %s::date, %s::date)",
                (json.dumps(cfg), WINDOW[0], WINDOW[1]))
    return cur.fetchone()[0]


def ensure_version(cur, cfg: dict, note: str) -> tuple[str, int, bool]:
    cur.execute("select id, version, status from scoring_configs where key = %s", (KEY,))
    row = cur.fetchone()
    if row:
        return row[0], row[1], False
    cur.execute("""insert into scoring_configs (version, key, name, status, config, note)
                   values ((select coalesce(max(version), 0) + 1 from scoring_configs), %s, %s, 'draft', %s::jsonb, %s)
                   returning id, version""", (KEY, NAME, json.dumps(cfg), note))
    cid, version = cur.fetchone()
    return cid, version, True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    cfg, note = load_recommended()
    conn = ST.connect()
    conn.autocommit = False
    cur = conn.cursor()
    before = current_state(cur)
    print("active today:", before["active"])
    print("bands today:", before["bands"])
    print("queue actions today (all rows):", before["decisions"], "· last 45 days:", before["last_45_days"])

    summary = whatif(cur, cfg)
    keep = {k: v for k, v in summary.items() if k in (
        "n", "band_counts", "action_counts", "videos_per_week", "transcripts_per_week", "analyses_per_week",
        "cost_per_week", "changed_band", "dropped", "added", "flip_share", "weeks")}
    print(f"what-if over {WINDOW[0]} .. {WINDOW[1]} with the recommended settings:")
    print(json.dumps(keep or summary, indent=2, default=str)[:3000])

    if args.dry_run:
        conn.rollback()
        conn.close()
        return

    cid, version, created = ensure_version(cur, cfg, note)
    print(f"version v{version} ({'created' if created else 'already stored'}) id={cid}")
    cur.execute("select apply_scoring_config(%s::uuid)", (cid,))
    result = cur.fetchone()[0]
    conn.commit()
    print("activated:", json.dumps(result, default=str)[:1500])
    after = current_state(cur)
    print("active now:", after["active"])
    print("bands now:", after["bands"])
    print("queue actions now (all rows):", after["decisions"], "· last 45 days:", after["last_45_days"])
    print(f"score history rows: {before['history_rows']} -> {after['history_rows']}")
    ST.remember_config_version(version) if hasattr(ST, "remember_config_version") else None
    conn.close()
    print("done", dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))


if __name__ == "__main__":
    main()
