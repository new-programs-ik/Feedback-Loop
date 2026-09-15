"""notify.py - Slack messages for flagged classes, via plain httpx (no slack-sdk dependency).

The card leads with the Class Sentiment Score - "Sentiment 58 · Bad → video" - and says why in
plain words (under the 4.55 line / under the 80% bar / few votes), then mentions the course's
people (course_members; the legacy handler when a course has none) and links into the course
workspace's queue. The confirmation is a LINK, not Slack buttons: interactive buttons need a
public webhook + signature verification; a URL button into the queue needs nothing, and the
Confirm/Dismiss actions live where the data lives. Failures never raise - a missed ping must not
fail a sync (it retries next hour because review_status stays 'new').
"""
from __future__ import annotations

import logging
import os
from typing import Optional, Union

import httpx

import decision as D

log = logging.getLogger("notify")

SLACK_API = "https://slack.com/api"
DEFAULT_UI = "https://feedback-loop-ten.vercel.app"
NO_OWNER_TEXT = "No owner assigned — set one in Admin › People"

# sentiment_flags (score_class_rating) -> the words a PM would say. None = internal, not shown.
FLAG_WORDS = {
    "under_rating_line": f"under the {D.GOOD} line",
    "under_approval_bar": f"under the {D.APPROVAL_BAR:.0f}% bar",
    "thin_provisional": "few votes",
    "thin_no_band": "few votes",
    "escalated": "escalated by a PM",
    "thin_approval_not_counted": "too few approval answers for a yes to count",
    "thin_under_rating_line": "too few approval answers, rating under 4.6",
    "thin_low_rating_read": "too few responses, but rated below 4.3, so the transcript is read",
    "rating_vote_disagree": "rating and vote disagree",
    "no_vote": "no vote recorded",
    "votes_ne_responses": "votes and responses differ",
    "reach_clamped": "more raters than attendees",
    "no_attendance": "attendance unknown",
    "no_responses": "response count unknown",
    "zero_responses": "nobody rated",
    "guarded": None, "no_track": None, "no_rating": "no rating", "rating_zero": "rating is 0",
}
# Legacy rule-v2 reasons (rows synced before v3) - still readable.
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


# ── the words ────────────────────────────────────────────────────────────────

def format_score(score) -> str:
    """58.0 -> '58', 89.6 -> '89.6', None -> '—'."""
    if score is None:
        return "—"
    return f"{float(score):.1f}".rstrip("0").rstrip(".")


def verdict_word(decision: str) -> str:
    return "video" if decision == "video" else "transcript"


def headline(row: dict) -> str:
    """'Sentiment 58 · Bad → video'. A row without a score (escalated, or synced before v3) says so."""
    verdict = verdict_word(row.get("decision") or "")
    score, band = row.get("sentiment_score"), row.get("sentiment_band")
    if score is None:
        return f"Class flagged → {verdict}"
    band_txt = band.capitalize() if band else "No band yet"
    prov = " (provisional)" if row.get("sentiment_provisional") else ""
    return f"Sentiment {format_score(score)} · {band_txt}{prov} → {verdict}"


def reason_words(row: dict) -> str:
    """Plain words for sentiment_flags; falls back to the legacy flag_reasons; '' when nothing applies."""
    words: list[str] = []
    for f in row.get("sentiment_flags") or ():
        w = FLAG_WORDS.get(f, None if f in FLAG_WORDS else f.replace("_", " "))
        if w and w not in words:
            words.append(w)
    if not words:
        for r in row.get("flag_reasons") or ():
            w = REASON_TEXT.get(r, r)
            if w not in words:
                words.append(w)
    return ", ".join(words)


def vote_text(row: dict) -> str:
    yes, no = row.get("yes_votes"), row.get("no_votes")
    if yes is not None and no is not None and (yes + no) > 0:
        return f"{yes:.0f} of {yes + no:.0f} would have them back ({yes / (yes + no) * 100:.0f}%)"
    return "no vote recorded"


def priority_line(row: dict) -> str:
    """One mrkdwn line: the band or legacy priority, the vote, and why. Tolerates any row shape."""
    parts = []
    if row.get("sentiment_score") is not None:
        parts.append(f"*Score:* {format_score(row['sentiment_score'])}"
                     + (f" · {row['sentiment_band'].capitalize()}" if row.get("sentiment_band") else ""))
    elif row.get("health_band"):
        parts.append(f"*Priority:* {BAND_LABELS.get(row['health_band'], row['health_band'])}")
    parts.append(f"*Vote:* {vote_text(row)}")
    why = reason_words(row)
    if why:
        parts.append(f"*Why:* {why}")
    return " · ".join(parts)


def mention_line(recipients: list[dict]) -> str:
    if not recipients:
        return NO_OWNER_TEXT
    who = " ".join(f"<@{r['slack_user_id']}>" if r.get("slack_user_id") else f"*{r.get('name') or r.get('email')}*"
                   for r in recipients)
    return f"{who} — does this class need an analysis? Please confirm or dismiss."


def class_link(row: dict, env: dict | None = None) -> str:
    """${UI_URL}/c/<course slug>/queue?focus=<id>; /ratings?focus=<id> when the slug is unknown."""
    env = env if env is not None else dict(os.environ)
    ui = (env.get("UI_URL") or DEFAULT_UI).rstrip("/")
    slug = row.get("course_slug")
    return f"{ui}/c/{slug}/queue?focus={row['id']}" if slug else f"{ui}/ratings?focus={row['id']}"


def _recipients_of(row: dict, who: Union[None, str, list]) -> list[dict]:
    if isinstance(who, list):
        return who
    if isinstance(who, str) and who:
        return [{"slack_user_id": who, "name": row.get("handler_name")}]
    if row.get("recipients") is not None:
        return list(row["recipients"])
    if row.get("slack_user_id") or row.get("handler_name"):            # legacy handler row
        return [{"slack_user_id": row.get("slack_user_id"), "name": row.get("handler_name"),
                 "email": row.get("handler_email")}]
    return []


def flag_blocks(row: dict, link: str, recipients: Union[None, str, list] = None) -> list[dict]:
    """Block Kit card for one flagged class. `row` comes from rows_needing_notification;
    `recipients` is its list of people (a bare Slack user id is accepted for older callers)."""
    people = _recipients_of(row, recipients)
    verdict = verdict_word(row.get("decision") or "")
    pct = f"{row['participation_pct']:.0f}%" if row.get("participation_pct") is not None else "?"
    rated = (f"{row['num_ratings']:.0f} of {row['attended']:.0f} rated ({pct})"
             if row.get("num_ratings") is not None and row.get("attended") else "rating counts unknown")
    date = row["class_date"].strftime("%d %b %Y") if hasattr(row["class_date"], "strftime") else str(row["class_date"])
    who = row.get("instructor_canonical") or row.get("instructor") or "—"
    if row.get("instructor_canonical") and row.get("instructor") and row["instructor_canonical"] != row["instructor"]:
        who += f" (recorded as {row['instructor']})"
    why = reason_words(row)
    return [
        {"type": "header",
         "text": {"type": "plain_text", "text": headline(row), "emoji": True}},
        {"type": "section",
         "text": {"type": "mrkdwn",
                  "text": f"*{row['course_name']}* — {row['topic'] or row['session_kind']}"},
         "fields": [
             {"type": "mrkdwn", "text": f"*Date*\n{date}"},
             {"type": "mrkdwn", "text": f"*Instructor*\n{who}"},
             {"type": "mrkdwn", "text": f"*Rating*\n{row['rating']} ★ ({rated})"},
             {"type": "mrkdwn", "text": f"*Vote*\n{vote_text(row)}"},
         ]},
        {"type": "section",
         "text": {"type": "mrkdwn",
                  "text": (f"*Why:* {why}" if why else "*Why:* the score's band") +
                          f" · *Rule says:* {'Video' if verdict == 'video' else 'Transcript'} analysis"}},
        {"type": "section",
         "text": {"type": "mrkdwn", "text": mention_line(people)}},
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
    link = class_link(row, env)
    try:
        data = _post(env, "chat.postMessage", {
            "channel": channel,
            "text": f"{headline(row)}: {row['course_name']} — {row['topic']}",
            "blocks": flag_blocks(row, link, row.get("recipients")),
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
