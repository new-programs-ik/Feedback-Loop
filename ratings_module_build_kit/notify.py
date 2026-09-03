"""notify.py - Slack messages for flagged classes, via plain httpx (no slack-sdk dependency).

The confirmation is a LINK, not Slack buttons: interactive buttons need a public webhook +
signature verification; a URL button into the app's Needs-analysis queue needs nothing, and the
Confirm/Dismiss actions live where the data lives. Failures never raise - a missed ping must
not fail a sync (it retries next hour because review_status stays 'new').
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

import decision as D

log = logging.getLogger("notify")

SLACK_API = "https://slack.com/api"
BAND_LABELS = {"urgent": "Urgent", "look": "Needs a look", "borderline": "Borderline"}
REASON_TEXT = {"rating": f"rating below {D.GOOD}",
               "approval": f"approval under {D.APPROVAL_BAR:.0f}%",
               "escalated": "escalated by a PM"}


def slack_configured(env: dict | None = None) -> bool:
    env = env if env is not None else os.environ
    return bool(env.get("SLACK_BOT_TOKEN"))


def _post(env: dict, path: str, payload: dict,
          transport: Optional[httpx.BaseTransport] = None) -> dict:
    token = env.get("SLACK_BOT_TOKEN") or ""
    with httpx.Client(transport=transport, timeout=20) as client:
        r = client.post(f"{SLACK_API}/{path}", json=payload,
                        headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        return r.json()


def lookup_user_id(email: str, env: dict | None = None,
                   transport: Optional[httpx.BaseTransport] = None) -> Optional[str]:
    """users.lookupByEmail (needs the users:read.email scope). None on any failure."""
    env = env if env is not None else dict(os.environ)
    try:
        token = env.get("SLACK_BOT_TOKEN") or ""
        with httpx.Client(transport=transport, timeout=20) as client:
            r = client.get(f"{SLACK_API}/users.lookupByEmail", params={"email": email},
                           headers={"Authorization": f"Bearer {token}"})
            data = r.json()
        return data.get("user", {}).get("id") if data.get("ok") else None
    except Exception:
        log.warning("slack users.lookupByEmail failed for %s", email, exc_info=True)
        return None


def priority_line(row: dict) -> str:
    """One mrkdwn line - the band, the vote, and why it was flagged, e.g.
    '*Priority:* Urgent · *Vote:* 13 of 15 would have them back (87%) · *Why:* rating below 4.55'.
    Tolerates rows without the v2 fields (a pending row synced before the vote existed)."""
    parts = []
    band = row.get("health_band")
    if band:
        parts.append(f"*Priority:* {BAND_LABELS.get(band, band)}")
    yes, no = row.get("yes_votes"), row.get("no_votes")
    if yes is not None and no is not None and (yes + no) > 0:
        parts.append(f"*Vote:* {yes:.0f} of {yes + no:.0f} would have them back "
                     f"({yes / (yes + no) * 100:.0f}%)")
    else:
        parts.append("*Vote:* no vote recorded")
    reasons = [REASON_TEXT.get(r, r) for r in (row.get("flag_reasons") or ())]
    if reasons:
        parts.append("*Why:* " + ", ".join(reasons))
    return " · ".join(parts)


def flag_blocks(row: dict, link: str, slack_user_id: Optional[str]) -> list[dict]:
    """Block Kit card for one flagged class. `row` comes from rows_needing_notification."""
    verdict = "Video analysis" if row["decision"] == "video" else "Transcript analysis"
    pct = f"{row['participation_pct']:.0f}%" if row.get("participation_pct") is not None else "?"
    rated = (f"{row['num_ratings']:.0f} of {row['attended']:.0f} rated ({pct})"
             if row.get("num_ratings") is not None and row.get("attended") else "rating counts unknown")
    who = f"<@{slack_user_id}>" if slack_user_id else f"*{row['handler_name']}*"
    date = row["class_date"].strftime("%d %b %Y") if hasattr(row["class_date"], "strftime") else str(row["class_date"])
    return [
        {"type": "header",
         "text": {"type": "plain_text", "text": f"🚩 Class flagged: {verdict} suggested", "emoji": True}},
        {"type": "section",
         "text": {"type": "mrkdwn",
                  "text": f"*{row['course_name']}* — {row['topic'] or row['session_kind']}"},
         "fields": [
             {"type": "mrkdwn", "text": f"*Date*\n{date}"},
             {"type": "mrkdwn", "text": f"*Instructor*\n{row['instructor'] or '—'}"},
             {"type": "mrkdwn", "text": f"*Rating*\n{row['rating']} ★ ({rated})"},
             {"type": "mrkdwn", "text": f"*Rule says*\n{verdict}"},
         ]},
        {"type": "section",
         "text": {"type": "mrkdwn", "text": priority_line(row)}},
        {"type": "section",
         "text": {"type": "mrkdwn",
                  "text": f"{who} — does this class need an analysis? Please confirm or dismiss."}},
        {"type": "actions",
         "elements": [{"type": "button",
                       "text": {"type": "plain_text", "text": "Review in Feedback Loop"},
                       "url": link, "style": "primary"}]},
        {"type": "context",
         "elements": [{"type": "mrkdwn",
                       "text": "Auto-flagged from the ratings sheet · Feedback Loop"}]},
    ]


def post_flag_message(row: dict, env: dict | None = None,
                      transport: Optional[httpx.BaseTransport] = None) -> tuple[bool, str, str]:
    """Send one flag card to the PM channel. Returns (ok, slack_ts, error)."""
    env = env if env is not None else dict(os.environ)
    channel = env.get("SLACK_PM_CHANNEL_ID") or ""
    ui = (env.get("UI_URL") or "").rstrip("/")
    link = f"{ui}/ratings?focus={row['id']}" if ui else f"https://feedback-loop-ten.vercel.app/ratings?focus={row['id']}"
    try:
        data = _post(env, "chat.postMessage", {
            "channel": channel,
            "text": f"Class flagged for analysis: {row['course_name']} — {row['topic']}",
            "blocks": flag_blocks(row, link, row.get("slack_user_id")),
            "unfurl_links": False,
        }, transport)
        if not data.get("ok"):
            return False, "", str(data.get("error") or "slack error")
        return True, str(data.get("ts") or ""), ""
    except Exception as e:
        log.warning("slack post failed", exc_info=True)
        return False, "", str(e)


def post_sync_alert(text: str, env: dict | None = None,
                    transport: Optional[httpx.BaseTransport] = None) -> None:
    """Short ops alert (sync failed / sheet drifted). Best-effort."""
    env = env if env is not None else dict(os.environ)
    if not slack_configured(env) or not env.get("SLACK_PM_CHANNEL_ID"):
        return
    try:
        _post(env, "chat.postMessage",
              {"channel": env["SLACK_PM_CHANNEL_ID"], "text": text, "unfurl_links": False},
              transport)
    except Exception:
        log.warning("slack sync alert failed", exc_info=True)
