"""reports.py - the two automatic reports: one for leadership, one for the team.

Leadership (all courses, a few pages): the headline numbers against the previous period, the score
trend by course over the year, courses ranked by their share of Bad classes, the biggest movers,
instructors at risk and top performers by name, whether the loop works (flagged -> analysed ->
feedback sent -> did the next class improve), what the analyses cost, and three lines of what
changed and what to decide.

Team (one chapter per course, for the PMs): every class in the period with its score, band, action
and what happened to it; each instructor's classes, scores and feedback sent; the weakest modules;
open items; and what to do next.

Both read the same tables the website reads and use the website's definitions (lib/analytics.ts:
scoreSummary, movers, worst classes, loop outcomes), so the PDF and the screen never disagree.
Generated monthly for the previous month and yearly for the previous year (migration 0029), written
to Google Drive and announced in Slack. Nothing is stored in the database beyond one audit row: the
database is on the free tier and the PDFs do not belong there.

Command line, for a look before anything is scheduled:
    python reports.py --month 2026-08 --out ./out        # both PDFs for August 2026
    python reports.py --year 2026 --out ./out            # the yearly edition
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import io
import json
import logging
import os
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger("reports")

BANDS = ("excellent", "good", "average", "bad")
BAND_LABEL = {"excellent": "Excellent", "good": "Good", "average": "Average", "bad": "Bad", None: "Too few"}
ACTION_LABEL = {"video": "watch the recording", "transcript": "read the transcript", "none": "nothing needed",
                "watch": "too few responses"}
RATING_FLOOR = 4.3          # Sreejit's line: below it a class is always read
MIN_CLASSES_MOVER = 3       # a mover needs this many classes in both periods
RISK_LOW_CLASSES = 2        # at-risk: this many Bad (or under-the-floor) classes in the period
TOP_MIN_CLASSES = 3         # top performer: this many classes, none below Good
TOP_MIN_RATING = 4.7


# ── periods ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Period:
    start: dt.date
    end: dt.date            # inclusive
    label: str              # "August 2026" / "2026"
    kind: str               # "month" | "year"

    @property
    def previous(self) -> "Period":
        if self.kind == "year":
            return Period(dt.date(self.start.year - 1, 1, 1), dt.date(self.start.year - 1, 12, 31),
                          str(self.start.year - 1), "year")
        y, m = (self.start.year, self.start.month - 1) if self.start.month > 1 else (self.start.year - 1, 12)
        return month_period(y, m)

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def month_period(year: int, month: int) -> Period:
    last = calendar.monthrange(year, month)[1]
    return Period(dt.date(year, month, 1), dt.date(year, month, last),
                  f"{calendar.month_name[month]} {year}", "month")


def year_period(year: int) -> Period:
    return Period(dt.date(year, 1, 1), dt.date(year, 12, 31), str(year), "year")


def previous_month(today: Optional[dt.date] = None) -> Period:
    """The month before today's: what the 1st-of-the-month run reports on."""
    today = today or dt.date.today()
    y, m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    return month_period(y, m)


def previous_year(today: Optional[dt.date] = None) -> Period:
    today = today or dt.date.today()
    return year_period(today.year - 1)


# ── data ─────────────────────────────────────────────────────────────────────

ROW_SQL = """
select r.id, r.course_id, coalesce(c.name, r.course_label, 'Unmapped') as course, c.slug as course_slug,
       r.cohort_text, r.topic, coalesce(r.instructor_canonical, r.instructor, '') as instructor,
       r.instructor_id, r.class_date, r.session_kind, r.rating, r.num_ratings, r.attended,
       r.participation_pct, r.yes_votes, r.no_votes, r.approval_pct,
       r.sentiment_score as score, r.sentiment_band as band, r.sentiment_action as action,
       r.decision::text as decision, r.decision_override::text as decision_override,
       r.review_status, r.escalated, r.class_id,
       f.status::text as feedback_status, f.sent_at, f.approved_at,
       (select count(*) from analyses a where a.class_id = k.id) as analyses
from class_ratings r
left join courses c on c.id = r.course_id
-- The class the PM analysed: linked from the queue when there is a link, otherwise the class
-- created by hand for the same course, day and class name (the New Analysis form makes no link).
left join lateral (
    select cl.id from classes cl
     where cl.id = r.class_id
        or (r.class_id is null and cl.course_id = r.course_id and cl.class_date = r.class_date
            and lower(trim(cl.topic)) = lower(trim(r.topic)))
     order by (cl.id = r.class_id) desc, cl.created_at desc limit 1) k on true
left join lateral (select status, sent_at, approved_at from feedback
                    where class_id = k.id order by created_at desc limit 1) f on true
where r.class_date between %(start)s and %(end)s
order by r.class_date, course, r.topic
"""


def load_rows(cur, period: Period) -> list[dict]:
    cur.execute(ROW_SQL, {"start": period.start, "end": period.end})
    cols = [d[0] for d in cur.description]
    out = []
    for raw in cur.fetchall():
        row = dict(zip(cols, raw))
        for k in ("rating", "score", "approval_pct", "participation_pct"):
            if row.get(k) is not None:
                row[k] = float(row[k])
        out.append(row)
    return out


def load_trend(cur, end: dt.date, months: int = 12) -> dict[str, list[tuple[str, Optional[float], int]]]:
    """Average score per course per month for the `months` months ending at `end`."""
    start = dt.date(end.year, end.month, 1)
    for _ in range(months - 1):
        y, m = (start.year, start.month - 1) if start.month > 1 else (start.year - 1, 12)
        start = dt.date(y, m, 1)
    cur.execute(
        """
        select coalesce(c.name, r.course_label, 'Unmapped') as course,
               to_char(date_trunc('month', r.class_date), 'YYYY-MM') as month,
               avg(r.sentiment_score) as score, count(*) as n
        from class_ratings r left join courses c on c.id = r.course_id
        where r.class_date between %(start)s and %(end)s
        group by 1, 2 order by 1, 2
        """, {"start": start, "end": end})
    trend: dict[str, list] = defaultdict(list)
    for course, month, score, n in cur.fetchall():
        trend[course].append((month, float(score) if score is not None else None, int(n)))
    return dict(trend)


def load_analysis_spend(cur, period: Period) -> dict:
    cur.execute("select count(*) as n, coalesce(sum(cost_usd), 0) as usd, "
                "count(*) filter (where (result->'video'->>'video_used')::boolean) as with_video "
                "from analyses where created_at::date between %(start)s and %(end)s",
                {"start": period.start, "end": period.end})
    n, usd, with_video = cur.fetchone()
    return {"n": int(n), "usd": float(usd), "with_video": int(with_video or 0)}


def load_next_class_outcomes(cur, rows: list[dict]) -> dict:
    """For classes whose feedback was sent: did the same instructor's next class score higher?"""
    sent = [r for r in rows if r.get("feedback_status") == "sent" and r.get("instructor_id") and r.get("score") is not None]
    improved = worse = 0
    for r in sent:
        cur.execute("select sentiment_score from class_ratings where instructor_id = %s and class_date > %s "
                    "and sentiment_score is not null order by class_date limit 1", (r["instructor_id"], r["class_date"]))
        nxt = cur.fetchone()
        if nxt is None:
            continue
        if float(nxt[0]) > r["score"]:
            improved += 1
        else:
            worse += 1
    return {"sent": len(sent), "improved": improved, "not_improved": worse, "pending": len(sent) - improved - worse}


# ── the numbers (the website's definitions) ──────────────────────────────────

def _mean(xs: list) -> Optional[float]:
    xs = [x for x in xs if x is not None]
    return statistics.fmean(xs) if xs else None


def effective_action(r: dict) -> str:
    return r.get("decision_override") or r.get("decision") or r.get("action") or "watch"


def is_open_queue(r: dict) -> bool:
    """A due analysis nobody has closed: the website's rule, plus "an analysis was run" counts as
    closed even when the review status was never moved on."""
    return (r.get("review_status") in ("new", "notified", "confirmed")
            and effective_action(r) in ("video", "transcript") and not r.get("analyses"))


def summary(rows: list[dict]) -> dict:
    counts = {b: sum(1 for r in rows if r.get("band") == b) for b in BANDS}
    counts["none"] = sum(1 for r in rows if r.get("band") is None)
    scored = len(rows) - counts["none"]
    yes = sum(r.get("yes_votes") or 0 for r in rows)
    no = sum(r.get("no_votes") or 0 for r in rows)
    return {
        "n": len(rows), "scored": scored, "counts": counts,
        "avg_score": _mean([r.get("score") for r in rows]),
        "avg_rating": _mean([r.get("rating") for r in rows]),
        "approval": (yes / (yes + no) * 100) if (yes + no) else None,
        "rated_share": _mean([r.get("participation_pct") for r in rows]),
        "bad_share": (counts["bad"] / scored * 100) if scored else None,
        "low_share": ((counts["bad"] + counts["average"]) / scored * 100) if scored else None,
        "under_floor": sum(1 for r in rows if r.get("band") is not None and (r.get("rating") or 0) < RATING_FLOOR),
        "open_queue": sum(1 for r in rows if is_open_queue(r)),
        "avg_attended": _mean([r.get("attended") for r in rows]),
        "avg_rated": _mean([r.get("num_ratings") for r in rows]),
    }


def by_course(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r["course"]].append(r)
    return dict(sorted(out.items()))


def movers(before: list[dict], after: list[dict], key: str, label: str = None,
           min_classes: int = MIN_CLASSES_MOVER) -> list[dict]:
    """Groups (instructors, modules) with enough classes in both periods, by how far their average
    score moved. Positive = better."""
    label = label or key

    def group(rows):
        g: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            if r.get(key):
                g[str(r[key])].append(r)
        return g

    a, b = group(before), group(after)
    out = []
    for k, rows_b in b.items():
        rows_a = a.get(k)
        if not rows_a or len(rows_a) < min_classes or len(rows_b) < min_classes:
            continue
        sa, sb = _mean([r.get("score") for r in rows_a]), _mean([r.get("score") for r in rows_b])
        if sa is None or sb is None:
            continue
        out.append({"key": k, "label": str(rows_b[0].get(label) or k), "course": rows_b[0].get("course"),
                    "before": sa, "after": sb, "delta": sb - sa, "n_before": len(rows_a), "n_after": len(rows_b)})
    return sorted(out, key=lambda m: -abs(m["delta"]))


def worst_classes(rows: list[dict], limit: int = 12) -> list[dict]:
    low = [r for r in rows if r.get("band") in ("bad", "average")]
    return sorted(low, key=lambda r: (r.get("score") if r.get("score") is not None else 999))[:limit]


def class_reason(r: dict) -> str:
    """One line a PM would say. Mirrors classReason in lib/analytics.ts, with the 4.3 floor."""
    if r.get("band") is None:
        return f"Only {r.get('num_ratings') or 0} rated it: too few responses for a band."
    rating = r.get("rating") or 0.0
    appr = r.get("approval_pct")
    bits = []
    if rating < RATING_FLOOR:
        bits.append(f"Rated {rating:.2f}, below the {RATING_FLOOR} line")
    elif appr is not None and appr < 80:
        bits.append(f"Rated {rating:.2f} but only {appr:.0f}% would have the instructor back")
    else:
        bits.append(f"Rated {rating:.2f}" + (f", {appr:.0f}% would have the instructor back" if appr is not None else ""))
    if r.get("num_ratings") is not None and r["num_ratings"] < 10:
        bits.append(f"{r['num_ratings']} rated it")
    return " · ".join(bits) + f". Next: {ACTION_LABEL.get(effective_action(r), effective_action(r))}."


def what_happened(r: dict) -> str:
    fs = r.get("feedback_status")
    if fs == "sent":
        return "feedback sent"
    if fs == "approved":
        return "feedback approved"
    if r.get("analyses"):
        return "analysed, draft waiting"
    st = r.get("review_status")
    if st == "dismissed":
        return "dismissed by a PM"
    if st in ("analysis_started",):
        return "analysis running"
    if effective_action(r) in ("video", "transcript"):
        return "open in the queue"
    return "nothing needed"


def instructors_at_risk(rows: list[dict]) -> list[dict]:
    """Two or more Bad classes (or classes under the 4.3 line) in the period, by name."""
    g: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("instructor"):
            g[r["instructor"]].append(r)
    out = []
    for name, rs in g.items():
        low = [r for r in rs if r.get("band") == "bad" or (r.get("band") is not None and (r.get("rating") or 0) < RATING_FLOOR)]
        if len(low) >= RISK_LOW_CLASSES:
            out.append({"instructor": name, "courses": sorted({r["course"] for r in rs}), "classes": len(rs),
                        "low": len(low), "avg_rating": _mean([r.get("rating") for r in rs]),
                        "avg_score": _mean([r.get("score") for r in rs]),
                        "feedback_sent": sum(1 for r in rs if r.get("feedback_status") == "sent"),
                        "last": max(r["class_date"] for r in rs)})
    return sorted(out, key=lambda x: (-x["low"], x["avg_rating"] or 0))


def top_performers(rows: list[dict], limit: int = 8) -> list[dict]:
    g: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("instructor") and r.get("band") is not None:
            g[r["instructor"]].append(r)
    out = []
    for name, rs in g.items():
        if len(rs) < TOP_MIN_CLASSES or any(r.get("band") in ("average", "bad") for r in rs):
            continue
        avg_r = _mean([r.get("rating") for r in rs])
        if avg_r is None or avg_r < TOP_MIN_RATING:
            continue
        out.append({"instructor": name, "courses": sorted({r["course"] for r in rs}), "classes": len(rs),
                    "avg_rating": avg_r, "avg_score": _mean([r.get("score") for r in rs]),
                    "approval": _mean([r.get("approval_pct") for r in rs])})
    return sorted(out, key=lambda x: (-(x["avg_score"] or 0), -x["classes"]))[:limit]


def loop_funnel(rows: list[dict]) -> dict:
    flagged = [r for r in rows if effective_action(r) in ("video", "transcript")]
    return {
        "flagged": len(flagged),
        "confirmed": sum(1 for r in flagged if r.get("review_status") in ("confirmed", "analysis_started") or r.get("analyses")),
        "analysed": sum(1 for r in flagged if r.get("analyses")),
        "approved": sum(1 for r in flagged if r.get("feedback_status") in ("approved", "sent")),
        "sent": sum(1 for r in flagged if r.get("feedback_status") == "sent"),
        "dismissed": sum(1 for r in flagged if r.get("review_status") == "dismissed"),
        "open": sum(1 for r in flagged if is_open_queue(r)),
    }


def weakest_modules(rows: list[dict], min_classes: int = 2, limit: int = 6) -> list[dict]:
    g: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("topic") and r.get("score") is not None:
            g[r["topic"]].append(r)
    out = [{"topic": t, "classes": len(rs), "avg_score": _mean([r["score"] for r in rs]),
            "instructors": len({r.get("instructor") for r in rs})}
           for t, rs in g.items() if len(rs) >= min_classes]
    return sorted(out, key=lambda x: x["avg_score"])[:limit]


# ── plain-English lines ──────────────────────────────────────────────────────

def _pct(v: Optional[float], d: int = 0) -> str:
    return "n/a" if v is None else f"{v:.{d}f}%"


def _num(v: Optional[float], d: int = 1) -> str:
    return "n/a" if v is None else f"{v:.{d}f}"


def _delta(now: Optional[float], before: Optional[float], d: int = 1, unit: str = "") -> str:
    if now is None or before is None:
        return ""
    diff = now - before
    sign = "+" if diff > 0 else ""
    return f"{sign}{diff:.{d}f}{unit}"


def leadership_lines(cur_s: dict, prev_s: dict, per_course: list[dict], risk: list[dict], funnel: dict,
                     outcomes: dict, period: Period) -> list[str]:
    """What changed, what to decide: rule-based, from the numbers, never invented."""
    lines = []
    if cur_s["avg_score"] is not None and prev_s["avg_score"] is not None:
        d = cur_s["avg_score"] - prev_s["avg_score"]
        word = "up" if d > 0.5 else "down" if d < -0.5 else "flat"
        lines.append(f"Overall score {word} at {cur_s['avg_score']:.1f} ({_delta(cur_s['avg_score'], prev_s['avg_score'])} "
                     f"against {period.previous.label}) across {cur_s['n']} classes.")
    if cur_s["bad_share"] is not None:
        lines.append(f"{cur_s['counts']['bad']} classes ({_pct(cur_s['bad_share'])}) were Bad and {cur_s['under_floor']} "
                     f"were rated below {RATING_FLOOR}; {cur_s['counts']['none']} had too few responses to judge.")
    if per_course:
        worst = per_course[0]
        if worst["bad_share"]:
            lines.append(f"{worst['course']} has the highest share of Bad classes ({_pct(worst['bad_share'])} of "
                         f"{worst['scored']}); it needs a decision on its weakest instructors and modules.")
    if risk:
        names = ", ".join(x["instructor"] for x in risk[:3])
        lines.append(f"{len(risk)} instructor(s) had two or more low classes: {names}"
                     + (" and others" if len(risk) > 3 else "") + ".")
    if funnel["flagged"]:
        lines.append(f"Of {funnel['flagged']} classes flagged, {funnel['analysed']} were analysed and {funnel['sent']} "
                     f"got feedback; {funnel['open']} are still open.")
    if outcomes["improved"] + outcomes["not_improved"]:
        lines.append(f"After feedback, the instructor's next class scored higher {outcomes['improved']} time(s) "
                     f"and not higher {outcomes['not_improved']} time(s).")
    return lines


def team_lines(s: dict, rows: list[dict], funnel: dict) -> list[str]:
    lines = []
    open_rows = [r for r in rows if is_open_queue(r)]
    if open_rows:
        oldest = min(r["class_date"] for r in open_rows)
        lines.append(f"Clear the queue: {len(open_rows)} class(es) still need a look, the oldest from {oldest:%d %b}.")
    drafts = [r for r in rows if r.get("analyses") and r.get("feedback_status") == "draft"]
    if drafts:
        lines.append(f"{len(drafts)} analysed class(es) have a draft waiting for approval.")
    unresolved = {r["instructor"] for r in rows if r.get("instructor") and not r.get("instructor_id")}
    if unresolved:
        lines.append(f"{len(unresolved)} instructor spelling(s) did not match a known person; fix them in Admin > Identity.")
    if s["counts"]["none"]:
        lines.append(f"{s['counts']['none']} class(es) had fewer than 6 responses; ask instructors to run the poll earlier.")
    if not lines:
        lines.append("Nothing outstanding for this course.")
    return lines


# ── charts (matplotlib, headless) ────────────────────────────────────────────

def _chart_trend(trend: dict[str, list], period: Period) -> Optional[bytes]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:                                   # pragma: no cover - optional on a thin image
        log.warning("matplotlib unavailable; trend chart skipped", exc_info=True)
        return None
    if not trend:
        return None
    fig, ax = plt.subplots(figsize=(7.2, 3.0), dpi=150)
    months = sorted({m for pts in trend.values() for m, _, _ in pts})
    for course, pts in sorted(trend.items(), key=lambda kv: -len(kv[1])):
        if sum(n for _, _, n in pts) < 10:
            continue
        lookup = {m: s for m, s, _ in pts}
        ys = [lookup.get(m) for m in months]
        ax.plot(months, ys, marker="o", markersize=2.5, linewidth=1.2, label=course[:28])
    for y, c in ((90, "#d9d9d9"), (75, "#d9d9d9"), (60, "#d9d9d9")):
        ax.axhline(y, color=c, linewidth=0.8, zorder=0)
    ax.set_ylim(40, 100)
    ax.set_ylabel("average score")
    ax.set_title(f"Average Class Sentiment Score by course, 12 months to {period.label}", fontsize=9)
    ax.tick_params(axis="x", labelrotation=45, labelsize=7)
    ax.tick_params(axis="y", labelsize=7)
    ax.legend(fontsize=6, ncol=2, frameon=False)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def _chart_bands(per_course: list[dict], period: Period) -> Optional[bytes]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:                                   # pragma: no cover
        return None
    if not per_course:
        return None
    names = [c["course"][:22] for c in per_course][::-1]
    fig, ax = plt.subplots(figsize=(7.2, 0.32 * len(names) + 1.0), dpi=150)
    left = [0.0] * len(names)
    colours = {"excellent": "#2a9d8f", "good": "#6c8ebf", "average": "#e9c46a", "bad": "#b5473c", "none": "#cfcfcf"}
    for band in ("excellent", "good", "average", "bad", "none"):
        vals = [c["counts"][band] for c in per_course][::-1]
        ax.barh(names, vals, left=left, color=colours[band], label=BAND_LABEL.get(band, "Too few") if band != "none" else "Too few")
        left = [l + v for l, v in zip(left, vals)]
    ax.set_xlabel("classes")
    ax.set_title(f"Classes by band, {period.label}", fontsize=9)
    ax.tick_params(labelsize=7)
    ax.legend(fontsize=6, ncol=5, frameon=False, loc="lower right")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


# ── the PDFs ─────────────────────────────────────────────────────────────────

def _styles():
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    ss = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=ss["Title"], fontSize=18, spaceAfter=4, alignment=0),
        "sub": ParagraphStyle("s", parent=ss["Normal"], fontSize=9, textColor="#666666", spaceAfter=10),
        "h": ParagraphStyle("h", parent=ss["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("b", parent=ss["Normal"], fontSize=9, leading=12),
        "small": ParagraphStyle("sm", parent=ss["Normal"], fontSize=7.5, leading=9.5, textColor="#444444"),
        "bullet": ParagraphStyle("bl", parent=ss["Normal"], fontSize=9, leading=12, leftIndent=10, bulletIndent=0),
    }


def _table(data: list[list], col_widths=None, header=True, small=False):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    st = ParagraphStyle("cell", fontSize=7.5 if small else 8.5, leading=9.5 if small else 10.5)
    wrapped = [[Paragraph(str(c) if c is not None else "", st) for c in row] for row in data]
    t = Table(wrapped, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#dddddd")),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 3)]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
                  ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#999999"))]
    t.setStyle(TableStyle(style))
    return t


def _image(png: Optional[bytes], width: float):
    from reportlab.platypus import Image
    if not png:
        return None
    from reportlab.lib.utils import ImageReader
    ir = ImageReader(io.BytesIO(png))
    w, h = ir.getSize()
    return Image(io.BytesIO(png), width=width, height=width * h / w)


def _doc(buf: io.BytesIO, title: str):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate
    return SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                             topMargin=14 * mm, bottomMargin=14 * mm, title=title, author="Feedback Loop")


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillGray(0.45)
    canvas.drawString(doc.leftMargin, 8 * 2.83, f"Feedback Loop · generated automatically · page {doc.page}")
    canvas.restoreState()


def build_leadership_pdf(data: dict) -> bytes:
    """`data` is what `gather()` returns."""
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, Spacer
    st = _styles()
    p: Period = data["period"]
    cur_s, prev_s = data["summary"], data["prev_summary"]
    story = [Paragraph(f"Feedback Loop · Leadership report · {p.label}", st["title"]),
             Paragraph(f"All courses · {p.start:%d %b %Y} to {p.end:%d %b %Y} · compared with {p.previous.label} · "
                       f"generated {dt.datetime.now(dt.timezone.utc):%d %b %Y %H:%M} UTC", st["sub"])]

    story.append(Paragraph("What changed, what to decide", st["h"]))
    for line in data["lead_lines"]:
        story.append(Paragraph(line, st["bullet"], bulletText="•"))

    story.append(Paragraph("The numbers", st["h"]))
    rows = [["", p.label, p.previous.label, "change"],
            ["Classes", cur_s["n"], prev_s["n"], _delta(cur_s["n"], prev_s["n"], 0)],
            ["Average score (0-100)", _num(cur_s["avg_score"]), _num(prev_s["avg_score"]), _delta(cur_s["avg_score"], prev_s["avg_score"])],
            ["Average rating (of 5)", _num(cur_s["avg_rating"], 2), _num(prev_s["avg_rating"], 2), _delta(cur_s["avg_rating"], prev_s["avg_rating"], 2)],
            ["Share of Bad classes", _pct(cur_s["bad_share"]), _pct(prev_s["bad_share"]), _delta(cur_s["bad_share"], prev_s["bad_share"], 1, " pt")],
            ["Bad + Average", _pct(cur_s["low_share"]), _pct(prev_s["low_share"]), _delta(cur_s["low_share"], prev_s["low_share"], 1, " pt")],
            [f"Rated below {RATING_FLOOR}", cur_s["under_floor"], prev_s["under_floor"], _delta(cur_s["under_floor"], prev_s["under_floor"], 0)],
            ["Instructor approval", _pct(cur_s["approval"]), _pct(prev_s["approval"]), _delta(cur_s["approval"], prev_s["approval"], 1, " pt")],
            ["Learners who rated ÷ attended", _pct(cur_s["rated_share"]), _pct(prev_s["rated_share"]), _delta(cur_s["rated_share"], prev_s["rated_share"], 1, " pt")],
            ["Too few responses to judge", cur_s["counts"]["none"], prev_s["counts"]["none"], _delta(cur_s["counts"]["none"], prev_s["counts"]["none"], 0)]]
    story.append(_table(rows, col_widths=[62 * mm, 32 * mm, 32 * mm, 26 * mm]))

    img = _image(data["chart_trend"], 170 * mm)
    if img:
        story += [Spacer(1, 6), img]

    story.append(Paragraph("Courses, worst share of Bad classes first", st["h"]))
    rows = [["Course", "Classes", "Avg score", "Δ", "Bad", "Average", "Too few", "Open queue"]]
    for c in data["per_course"]:
        rows.append([c["course"], c["n"], _num(c["avg_score"]), _delta(c["avg_score"], c.get("prev_avg")),
                     f"{c['counts']['bad']} ({_pct(c['bad_share'])})", c["counts"]["average"], c["counts"]["none"], c["open_queue"]])
    story.append(_table(rows, col_widths=[52 * mm, 16 * mm, 18 * mm, 14 * mm, 26 * mm, 18 * mm, 16 * mm, 18 * mm], small=True))
    img = _image(data["chart_bands"], 170 * mm)
    if img:
        story += [Spacer(1, 6), img]

    story.append(PageBreak())
    story.append(Paragraph("Instructors at risk", st["h"]))
    story.append(Paragraph(f"Two or more classes in the period that were Bad or rated below {RATING_FLOOR}.", st["small"]))
    if data["risk"]:
        rows = [["Instructor", "Course(s)", "Classes", "Low", "Avg rating", "Avg score", "Feedback sent", "Last class"]]
        for x in data["risk"]:
            rows.append([x["instructor"], ", ".join(x["courses"]), x["classes"], x["low"], _num(x["avg_rating"], 2),
                         _num(x["avg_score"]), x["feedback_sent"], f"{x['last']:%d %b}"])
        story.append(_table(rows, col_widths=[36 * mm, 44 * mm, 14 * mm, 12 * mm, 18 * mm, 18 * mm, 20 * mm, 16 * mm], small=True))
    else:
        story.append(Paragraph("None this period.", st["body"]))

    story.append(Paragraph("Top performers", st["h"]))
    story.append(Paragraph(f"At least {TOP_MIN_CLASSES} classes, none below Good, average rating {TOP_MIN_RATING} or higher.", st["small"]))
    if data["top"]:
        rows = [["Instructor", "Course(s)", "Classes", "Avg rating", "Avg score", "Approval"]]
        for x in data["top"]:
            rows.append([x["instructor"], ", ".join(x["courses"]), x["classes"], _num(x["avg_rating"], 2), _num(x["avg_score"]), _pct(x["approval"])])
        story.append(_table(rows, col_widths=[40 * mm, 60 * mm, 16 * mm, 20 * mm, 20 * mm, 20 * mm], small=True))
    else:
        story.append(Paragraph("None qualified this period.", st["body"]))

    story.append(Paragraph("Biggest movers", st["h"]))
    story.append(Paragraph(f"Instructors with at least {MIN_CLASSES_MOVER} classes in both periods, by change in average score.", st["small"]))
    if data["movers_instructors"]:
        rows = [["Instructor", "Course", p.previous.label, p.label, "Change"]]
        for m in data["movers_instructors"][:10]:
            rows.append([m["label"], m["course"], f"{m['before']:.1f} ({m['n_before']})", f"{m['after']:.1f} ({m['n_after']})", _delta(m["after"], m["before"])])
        story.append(_table(rows, col_widths=[44 * mm, 52 * mm, 28 * mm, 28 * mm, 20 * mm], small=True))
    else:
        story.append(Paragraph("Not enough repeat classes to compare.", st["body"]))

    story.append(Paragraph("Does the loop work", st["h"]))
    f, o = data["funnel"], data["outcomes"]
    rows = [["Flagged", "Confirmed", "Analysed", "Approved", "Sent", "Dismissed", "Still open"],
            [f["flagged"], f["confirmed"], f["analysed"], f["approved"], f["sent"], f["dismissed"], f["open"]]]
    story.append(_table(rows))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"After feedback was sent, the instructor's next class scored higher {o['improved']} time(s) and not higher "
        f"{o['not_improved']} time(s); {o['pending']} have no next class yet.", st["body"]))
    sp = data["spend"]
    story.append(Paragraph(
        f"Analyses run in the period: {sp['n']} ({sp['with_video']} with the recording), costing about ${sp['usd']:.2f} in AI usage.",
        st["body"]))

    story.append(Paragraph("Worst classes", st["h"]))
    rows = [["Date", "Course", "Class", "Instructor", "Rating", "Score", "Band", "What happened"]]
    for r in data["worst"]:
        rows.append([f"{r['class_date']:%d %b}", r["course"][:26], r["topic"][:34], r["instructor"][:22], _num(r["rating"], 2),
                     _num(r["score"], 0), BAND_LABEL.get(r["band"]), what_happened(r)])
    story.append(_table(rows, col_widths=[14 * mm, 34 * mm, 42 * mm, 30 * mm, 14 * mm, 12 * mm, 16 * mm, 26 * mm], small=True))

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "How to read this: the Class Sentiment Score is 0-100 from the rating (60), instructor approval (30), responses (6) "
        f"and learners who rated ÷ attended (4); Bad = under 60, Average = 60-74, Good = 75-89, Excellent = 90+. A class rated "
        f"below {RATING_FLOOR} is always at least Average. Fewer than 6 responses = too few to judge.", st["small"]))

    buf = io.BytesIO()
    _doc(buf, f"Feedback Loop leadership report {p.label}").build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def build_team_pdf(data: dict) -> bytes:
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, Spacer
    st = _styles()
    p: Period = data["period"]
    story = [Paragraph(f"Feedback Loop · Team report · {p.label}", st["title"]),
             Paragraph(f"One chapter per course · {p.start:%d %b %Y} to {p.end:%d %b %Y} · "
                       f"generated {dt.datetime.now(dt.timezone.utc):%d %b %Y %H:%M} UTC", st["sub"])]
    courses = data["courses"]
    rows = [["Course", "Classes", "Avg score", "Bad", "Average", "Too few", "Open queue", "Feedback sent"]]
    for c in courses:
        s = c["summary"]
        rows.append([c["course"], s["n"], _num(s["avg_score"]), s["counts"]["bad"], s["counts"]["average"], s["counts"]["none"],
                     s["open_queue"], sum(1 for r in c["rows"] if r.get("feedback_status") == "sent")])
    story.append(_table(rows, col_widths=[54 * mm, 16 * mm, 20 * mm, 14 * mm, 18 * mm, 16 * mm, 20 * mm, 22 * mm], small=True))

    for c in courses:
        s, prev = c["summary"], c["prev_summary"]
        story.append(PageBreak())
        story.append(Paragraph(c["course"], st["title"]))
        story.append(Paragraph(
            f"{s['n']} classes · average score {_num(s['avg_score'])} ({_delta(s['avg_score'], prev['avg_score'])} vs {p.previous.label}) · "
            f"rating {_num(s['avg_rating'], 2)} · approval {_pct(s['approval'])} · "
            f"Bad {s['counts']['bad']} · Average {s['counts']['average']} · too few {s['counts']['none']}", st["sub"]))

        story.append(Paragraph("What to do next", st["h"]))
        for line in c["lines"]:
            story.append(Paragraph(line, st["bullet"], bulletText="•"))

        story.append(Paragraph("Instructors", st["h"]))
        rows = [["Instructor", "Classes", "Avg rating", "Avg score", "Bad", "Average", "Feedback sent"]]
        for x in c["instructors"]:
            rows.append([x["instructor"], x["classes"], _num(x["avg_rating"], 2), _num(x["avg_score"]), x["bad"], x["average"], x["sent"]])
        story.append(_table(rows, col_widths=[54 * mm, 16 * mm, 22 * mm, 22 * mm, 14 * mm, 18 * mm, 24 * mm], small=True))

        if c["modules"]:
            story.append(Paragraph("Weakest modules", st["h"]))
            rows = [["Module", "Classes", "Instructors", "Avg score"]]
            for m in c["modules"]:
                rows.append([m["topic"], m["classes"], m["instructors"], _num(m["avg_score"])])
            story.append(_table(rows, col_widths=[90 * mm, 20 * mm, 24 * mm, 24 * mm], small=True))

        story.append(Paragraph("Classes" if p.kind == "month" else "Lowest 40 classes", st["h"]))
        rows = [["Date", "Class", "Instructor", "Rated", "Rating", "Score", "Band", "Why", "What happened"]]  # widths below keep 'Rated' on one line
        listed = c["rows"] if p.kind == "month" else worst_classes(c["rows"], 40)
        for r in sorted(listed, key=lambda r: (r.get("score") if r.get("score") is not None else 999, r["class_date"])):
            rows.append([f"{r['class_date']:%d %b}", r["topic"][:36], r["instructor"][:20], r.get("num_ratings"), _num(r["rating"], 2),
                         _num(r["score"], 0), BAND_LABEL.get(r["band"]), class_reason(r), what_happened(r)])
        story.append(_table(rows, col_widths=[13 * mm, 34 * mm, 25 * mm, 13 * mm, 13 * mm, 12 * mm, 15 * mm, 39 * mm, 22 * mm], small=True))
        story.append(Spacer(1, 4))

    buf = io.BytesIO()
    _doc(buf, f"Feedback Loop team report {p.label}").build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


# ── putting it together ──────────────────────────────────────────────────────

def gather(cur, period: Period) -> dict:
    rows = load_rows(cur, period)
    prev_rows = load_rows(cur, period.previous)
    cur_s, prev_s = summary(rows), summary(prev_rows)
    prev_by = {k: summary(v) for k, v in by_course(prev_rows).items()}
    per_course = []
    for course, rs in by_course(rows).items():
        s = summary(rs)
        s.update({"course": course, "prev_avg": (prev_by.get(course) or {}).get("avg_score")})
        per_course.append(s)
    per_course.sort(key=lambda c: (-(c["bad_share"] or 0), -c["n"]))
    funnel = loop_funnel(rows)
    outcomes = load_next_class_outcomes(cur, rows)
    risk = instructors_at_risk(rows)
    trend = load_trend(cur, period.end, 12)
    courses = []
    for course, rs in by_course(rows).items():
        s = summary(rs)
        g: dict[str, list[dict]] = defaultdict(list)
        for r in rs:
            if r.get("instructor"):
                g[r["instructor"]].append(r)
        instructors = sorted([{"instructor": n, "classes": len(x), "avg_rating": _mean([r.get("rating") for r in x]),
                               "avg_score": _mean([r.get("score") for r in x]),
                               "bad": sum(1 for r in x if r.get("band") == "bad"),
                               "average": sum(1 for r in x if r.get("band") == "average"),
                               "sent": sum(1 for r in x if r.get("feedback_status") == "sent")}
                              for n, x in g.items()], key=lambda x: (x["avg_score"] if x["avg_score"] is not None else 999))
        courses.append({"course": course, "rows": rs, "summary": s, "prev_summary": prev_by.get(course) or summary([]),
                        "instructors": instructors, "modules": weakest_modules(rs), "lines": team_lines(s, rs, loop_funnel(rs))})
    data = {
        "period": period, "rows": rows, "summary": cur_s, "prev_summary": prev_s, "per_course": per_course,
        "movers_instructors": movers(prev_rows, rows, "instructor"),
        "movers_modules": movers(prev_rows, rows, "topic"),
        "worst": worst_classes(rows), "risk": risk, "top": top_performers(rows), "funnel": funnel,
        "outcomes": outcomes, "spend": load_analysis_spend(cur, period), "trend": trend, "courses": courses,
    }
    data["lead_lines"] = leadership_lines(cur_s, prev_s, per_course, risk, funnel, outcomes, period)
    data["chart_trend"] = _chart_trend(trend, period)
    data["chart_bands"] = _chart_bands(per_course, period)
    return data


def file_names(period: Period) -> tuple[str, str]:
    return (f"Feedback Loop - Leadership report - {period.label}.pdf",
            f"Feedback Loop - Team report - {period.label}.pdf")


# ── delivery: Drive and Slack, both best-effort ──────────────────────────────

def drive_token(env: dict) -> Optional[str]:
    """A Drive token for the service account (the same key that reads the sheet)."""
    try:
        from google.oauth2 import service_account
        import google.auth.transport.requests
        import sheet_source as SS
        sa_file = (env.get("GOOGLE_SA_JSON_FILE") or "").strip()
        found = SS._resolve_key_file(sa_file) if sa_file else None
        scopes = ["https://www.googleapis.com/auth/drive.file"]
        if found:
            creds = service_account.Credentials.from_service_account_file(found, scopes=scopes)
        elif env.get("GOOGLE_SA_JSON"):
            creds = service_account.Credentials.from_service_account_info(json.loads(env["GOOGLE_SA_JSON"]), scopes=scopes)
        else:
            return None
        creds.refresh(google.auth.transport.requests.Request())
        return creds.token
    except Exception:
        log.warning("could not mint a Drive token", exc_info=True)
        return None


def upload_to_drive(pdf: bytes, name: str, env: dict, transport=None) -> Optional[str]:
    """Put one PDF in the reports folder; returns the link, or None (logged) when it could not."""
    import httpx
    folder = (env.get("REPORTS_DRIVE_FOLDER_ID") or "").strip()
    token = drive_token(env)
    if not folder or not token:
        log.warning("Drive upload skipped: %s", "no REPORTS_DRIVE_FOLDER_ID" if not folder else "no service-account token")
        return None
    meta = json.dumps({"name": name, "parents": [folder], "mimeType": "application/pdf"})
    boundary = "feedback-loop-report"
    body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n"
            f"--{boundary}\r\nContent-Type: application/pdf\r\n\r\n").encode() + pdf + f"\r\n--{boundary}--".encode()
    try:
        with httpx.Client(transport=transport, timeout=120) as client:
            r = client.post("https://www.googleapis.com/upload/drive/v3/files",
                            params={"uploadType": "multipart", "supportsAllDrives": "true", "fields": "id,webViewLink"},
                            headers={"Authorization": f"Bearer {token}", "Content-Type": f"multipart/related; boundary={boundary}"},
                            content=body)
        if r.status_code >= 300:
            log.warning("Drive upload failed: %s %s", r.status_code, r.text[:300])
            return None
        return r.json().get("webViewLink")
    except Exception:
        log.warning("Drive upload failed", exc_info=True)
        return None


def post_report_to_slack(channel: str, title: str, link: Optional[str], lines: list[str], env: dict, transport=None) -> bool:
    import notify as N
    if not channel or not N.slack_configured(env):
        return False
    text = f"*{title}*" + (f"\n<{link}|Open the PDF on Drive>" if link else "\n(the PDF could not be uploaded to Drive; see the worker log)")
    if lines:
        text += "\n" + "\n".join(f"• {l}" for l in lines[:4])
    try:
        data = N._post(env, "chat.postMessage", {"channel": channel, "text": text, "unfurl_links": False}, transport)
        return bool(data.get("ok"))
    except Exception:
        log.warning("Slack post failed", exc_info=True)
        return False


def run_reports(kind: str = "monthly", env: Optional[dict] = None, today: Optional[dt.date] = None,
                out_dir: Optional[str] = None, deliver: bool = True) -> dict:
    """Generate both reports for the previous month (or year), deliver them, record one audit row."""
    import ratings_store as ST
    env = env if env is not None else dict(os.environ)
    period = previous_year(today) if kind == "yearly" else previous_month(today)
    conn = ST.connect()
    try:
        cur = conn.cursor()
        data = gather(cur, period)
        lead_pdf, team_pdf = build_leadership_pdf(data), build_team_pdf(data)
        lead_name, team_name = file_names(period)
        result = {"period": period.label, "kind": kind, "classes": data["summary"]["n"],
                  "leadership_bytes": len(lead_pdf), "team_bytes": len(team_pdf), "links": {}}
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            for name, pdf in ((lead_name, lead_pdf), (team_name, team_pdf)):
                with open(os.path.join(out_dir, name), "wb") as fh:
                    fh.write(pdf)
            result["out_dir"] = out_dir
        if deliver:
            lead_link = upload_to_drive(lead_pdf, lead_name, env)
            team_link = upload_to_drive(team_pdf, team_name, env)
            result["links"] = {"leadership": lead_link, "team": team_link}
            result["slack"] = {
                "leadership": post_report_to_slack(env.get("SLACK_LEADERSHIP_CHANNEL_ID") or "", f"Leadership report · {period.label}",
                                                   lead_link, data["lead_lines"], env),
                "team": post_report_to_slack(env.get("SLACK_PM_CHANNEL_ID") or "", f"Team report · {period.label}",
                                             team_link, [f"{c['course']}: {c['lines'][0]}" for c in data["courses"][:4]], env),
            }
        if deliver:                                    # a local preview leaves no trace
            try:
                cur.execute("insert into audit_log(actor_label, action, detail) values ('worker', 'report_generated', %s)",
                            (json.dumps(result, default=str),))
                conn.commit()
            except Exception:
                conn.rollback()
                log.warning("could not record the report run", exc_info=True)
        log.info("reports: %s", json.dumps(result, default=str))
        return result
    finally:
        conn.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generate the leadership and team reports.")
    ap.add_argument("--month", help="YYYY-MM (both PDFs for that month)")
    ap.add_argument("--year", type=int, help="YYYY (the yearly edition)")
    ap.add_argument("--out", default="out", help="folder for the PDFs")
    ap.add_argument("--deliver", action="store_true", help="also upload to Drive and post to Slack")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%H:%M:%S")
    import config
    config.load_env()
    if args.year:
        today = dt.date(args.year + 1, 1, 1)
        kind = "yearly"
    elif args.month:
        y, m = (int(x) for x in args.month.split("-"))
        today = dt.date(y + (1 if m == 12 else 0), 1 if m == 12 else m + 1, 1)
        kind = "monthly"
    else:
        today, kind = None, "monthly"
    res = run_reports(kind, today=today, out_dir=args.out, deliver=args.deliver)
    print(json.dumps(res, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
