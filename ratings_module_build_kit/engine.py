"""
engine.py — production engine for the Ratings & Feedback module (v1).

Reads a class transcript (+ the class agenda) and returns three things:
  1. flags    — per-quality-dimension findings, each with a timestamp + verbatim quote
  2. feedback — the coaching message for the instructor
  3. reclass  — a PM-only recommendation on whether the class needs to be re-taught

Pipeline:  parse (+ keep speakers)
           -> MAP the whole conversation once: who speaks, the real flow, what gets resolved (LLM)
           -> chunk by time
           -> extract INSTRUCTOR findings per window, judged in full-session context (LLM)
           -> synthesise: verify against the whole session, drop learner-attributed / resolved-later
              artefacts, de-duplicate, write feedback + PM re-class call (LLM)
Model:     Claude Sonnet 4.6 (pinned in Config). Set ANTHROPIC_API_KEY in the environment.

Run:
  # plumbing check, no API key needed:
  python engine.py --dry-run transcript.srt
  # full run:
  python engine.py transcript.srt --course "Python for ML" --topic "pandas indexing" \
      --instructor "Justin" --rating 4.47 --agenda agenda.txt
Outputs land in  ./outputs/<run_id>/  as result.json, feedback.md and run.json.

This is evolved from the validated prototype (class_analyzer.py) and adds the production
concerns: configuration, retries/timeouts, schema validation with a self-repair retry,
structured logging, real cost/latency tracking, persisted outputs and idempotency.
"""
from __future__ import annotations
import re, json, sys, os, time, hashlib, logging, argparse
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("ratings_engine")

# ───────────────────────────────────────────────────────────────────── config
@dataclass(frozen=True)
class Config:
    model: str = "claude-sonnet-4-6"     # pinned for reproducibility
    temperature: float = 0.0
    window_min: int = 30                 # extraction window length
    overlap_min: int = 2                 # carry context across windows
    max_retries: int = 4                 # network/5xx retries (SDK level)
    timeout_s: float = 120.0
    max_tokens_extract: int = 4000
    max_tokens_synth: int = 3000
    max_tokens_skeptic: int = 1500       # the adversarial second-pass verdict call
    repair_attempts: int = 1             # re-ask once if the JSON is malformed/invalid
    review_enabled: bool = True          # kill-switch: False restores the un-verified pipeline exactly
    price_in_per_mtok: float = 3.0       # USD, for cost reporting only
    price_out_per_mtok: float = 15.0

CFG = Config()

CLASS_TYPES = {"live_class", "ars"}   # ars = Assignment Review Session

FLAGS_LIVE = {"pace", "clarity", "structure", "examples", "correctness", "logistics", "coverage",
              "coding_time", "agenda_balance", "concept_left", "doubt_handling", "engagement",
              "learner_gap", "camera", "screen_share", "slides_mismatch"}
FLAGS_ARS = {"problem_coverage", "time_balance", "solution_walkthrough", "approach_reasoning",
             "complexity_tradeoffs", "edge_cases", "common_mistakes", "problem_deferred",
             "pace", "clarity", "structure", "correctness", "logistics",
             "doubt_handling", "engagement", "learner_gap", "camera", "screen_share"}
FLAGS = FLAGS_LIVE | FLAGS_ARS        # union — fallback when the class type is unknown


def flags_for(class_type: str) -> set[str]:
    return FLAGS_ARS if class_type == "ars" else FLAGS_LIVE


SEVERITY_ORDER = ("minor", "moderate", "major")   # ordinal, low → high
SEVERITY = set(SEVERITY_ORDER)
CONFIDENCE = {"low", "medium", "high"}
RECLASS = {"yes", "no", "maybe"}


def severity_rank(s: str) -> int:
    """minor→0, moderate→1, major→2 (unknown → -1 so it always compares lowest)."""
    return SEVERITY_ORDER.index(s) if s in SEVERITY_ORDER else -1


def one_level_down(s: str) -> str:
    """One severity step softer; minor stays minor."""
    return SEVERITY_ORDER[max(0, severity_rank(s) - 1)]


# Flags whose MAJOR failures mean the LEARNING itself wasn't delivered — the only flags that can
# justify a re-class "yes" (see gate_reclass).
CONTENT_DELIVERY_FLAGS = {"coverage", "correctness", "problem_coverage", "solution_walkthrough"}

# Code-enforced severity floors: (class_type, flag) → minimum severity. A floor violation is never
# legitimate (learners treat reviewed ARS solutions as canonical), so this is code, not just prompt.
SEVERITY_FLOORS = {("ars", "correctness"): "major"}

# The severity bars. ONE constant, injected into the extraction, synthesis AND skeptic prompts —
# never copy-pasted into rubric literals (tests assert identity). This is the fix for
# "the AI called something critical that wasn't".
SEVERITY_ANCHORS = """\
SEVERITY — use these exact bars; they are checkable claims, not impressions:
  major    - reserved for a provable delivery failure. At least ONE of:
             (a) content taught that is provably WRONG (contradicts the planned materials or
                 established fact - quote the wrong statement);
             (b) a PLANNED core agenda item / assigned problem skipped ENTIRELY, or compressed so
                 badly it cannot have landed (cite the time range);
             (c) learners demonstrably lost - their OWN quoted words show confusion - and the
                 session map shows it was never recovered by the end.
  moderate - a real, evidenced problem that hurt the session but did not break the learning:
             noticeably rushed or unbalanced time, a muddled explanation later patched, a doubt
             handled poorly but eventually addressed, a shallow walkthrough of a covered item.
  minor    - a polish issue with little learning impact: brief dead air, a missed recap, sparse
             check-ins, a small logistics hiccup, low interactivity in an otherwise clear class.
TIE-BREAK: if the evidence does not CLEARLY meet the bar for a severity, use the LOWER one.
CEILINGS: engagement, camera, screen_share, logistics, structure, examples and coding_time are at
most MODERATE unless the evidence is catastrophic AND quoted (e.g. a tech failure consuming a large
fraction of the class). FLOOR: correctness in an ARS is MAJOR at minimum - learners treat reviewed
solutions as canonical."""

# ──────────────────────────────────────────────────────── transcript: parse + chunk
@dataclass
class Cue:
    idx: int
    start: float   # seconds
    end: float
    text: str
    speaker: str | None = None   # who said it, when the transcript tells us (instructor / a learner)

def _ts_to_seconds(ts: str) -> float:
    ts = ts.strip().replace(",", ".")
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)

def _seconds_to_ts(sec: float) -> str:
    h = int(sec // 3600); m = int((sec % 3600) // 60); s = int(sec % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

# Speaker detection. These transcripts contain BOTH the instructor and learners, and the auditor
# must never blame the instructor for a learner's words — so we preserve who is speaking.
_VOICE_RE = re.compile(r"<v\s+([^>]+?)>", re.I)   # WebVTT voice tag:  <v Speaker Name>
# A "Name:" line prefix — conservative: 1–3 capitalised words then a colon (avoids "Problem two:" etc.)
_SPEAKER_PREFIX_RE = re.compile(r"^([A-Z][A-Za-z.'’-]*(?:\s+[A-Z][A-Za-z.'’-]*){0,2}):\s+(?=\S)")

def parse_cues(raw: str) -> list[Cue]:
    """Parse .srt or .vtt *text* into timestamped cues, PRESERVING the speaker when the transcript
    marks it. Tolerant of WEBVTT headers, indices, BOM and inline tags.

    Speaker comes from a WebVTT ``<v Name>`` voice tag, or from a ``Name:`` line prefix that RECURS
    (a one-off "Problem two:" is not mistaken for a speaker). Speaker labelling is what lets the
    analysis tell the instructor apart from the learners.
    """
    raw = re.sub(r"^WEBVTT.*?\n\n", "", raw, flags=re.S)
    rows: list[list] = []   # [idx, start, end, text, voice_speaker, prefix_candidate]
    for block in re.split(r"\n\s*\n", raw.strip()):
        lines = [l for l in block.splitlines() if l.strip()]
        ti = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if ti is None:
            continue
        start_s = lines[ti].split("-->")[0]
        end_s = lines[ti].split("-->")[1].split()[0]
        raw_text = " ".join(lines[ti + 1:])
        mv = _VOICE_RE.search(raw_text)
        voice = mv.group(1).strip() if mv else None
        text = re.sub(r"<[^>]+>", "", raw_text).strip()
        if not text:
            continue
        cand = None
        if voice is None:
            mp = _SPEAKER_PREFIX_RE.match(text)
            if mp:
                cand = mp.group(1).strip()
        try:
            idx = int(lines[0])
        except ValueError:
            idx = len(rows) + 1
        rows.append([idx, _ts_to_seconds(start_s), _ts_to_seconds(end_s), text, voice, cand])

    # Promote a "Name:" prefix to a real speaker only if it RECURS (>= 2 cues); voice-tag speakers
    # are always trusted. This keeps stray colon-lines from being read as speakers.
    from collections import Counter
    recurring = {n for n, c in Counter(r[5] for r in rows if r[5]).items() if c >= 2}
    cues: list[Cue] = []
    for idx, start, end, text, voice, cand in rows:
        speaker = voice
        if speaker is None and cand in recurring:
            speaker = cand
            text = _SPEAKER_PREFIX_RE.sub("", text, count=1).strip() or text
        cues.append(Cue(idx, start, end, text, speaker))
    return cues

def parse_transcript(path: str) -> list[Cue]:
    """Read a .srt/.vtt file from disk and parse it."""
    with open(path, encoding="utf-8-sig") as fh:
        return parse_cues(fh.read())

def chunk_by_time(cues: list[Cue], window_min: int = CFG.window_min, overlap_min: int = CFG.overlap_min) -> list[list[Cue]]:
    if not cues:
        return []
    window, overlap = window_min * 60, overlap_min * 60
    end = cues[-1].end
    chunks: list[list[Cue]] = []
    start = cues[0].start
    while start < end:
        lo = start - (overlap if chunks else 0)
        seg = [c for c in cues if lo <= c.start < start + window]
        if seg:
            chunks.append(seg)
        start += window
    return chunks

def format_segment(seg: list[Cue]) -> str:
    """Render cues for the model, keeping the speaker label when known ([time] Name: text)."""
    out = []
    for c in seg:
        who = f"{c.speaker}: " if c.speaker else ""
        out.append(f"[{_seconds_to_ts(c.start)}] {who}{c.text}")
    return "\n".join(out)

def est_tokens(cues: list[Cue]) -> int:
    return int(sum(len(c.text.split()) for c in cues) * 1.33)


# ── verification helpers (pure) ────────────────────────────────────────────────
def _normalise_quote(s: str) -> str:
    """Lowercase, straighten curly quotes/dashes, collapse whitespace, strip punctuation edges —
    so 'did the model quote the transcript?' survives cosmetic differences."""
    s = s.lower()
    for a, b in (("‘", "'"), ("’", "'"), ("“", '"'), ("”", '"'),
                 ("—", "-"), ("–", "-"), ("…", "...")):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9' ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def quote_present(transcript_text: str, quote: str) -> bool:
    """True if the (normalised) quote appears in the (normalised) transcript. A visual observation
    ('<visual: …>') is not a transcript quote — callers handle those separately."""
    q = _normalise_quote(quote)
    return bool(q) and q in _normalise_quote(transcript_text)


def excerpt_around(cues: list[Cue], timestamp: str, window_s: int = 120) -> str:
    """The transcript ±window_s around an HH:MM:SS timestamp — the skeptic reads the REAL context,
    not just the 450-word session map."""
    try:
        centre = _ts_to_seconds(timestamp)
    except Exception:
        return ""
    seg = [c for c in cues if centre - window_s <= c.start <= centre + window_s]
    return format_segment(seg)

# ─────────────────────────────────────────────────────────────────────── prompts
RUBRIC_LIVE = """\
You are auditing a LIVE CLASS transcript to evaluate the instructor.

WHAT THIS TRANSCRIPT IS (read carefully):
- It may contain MORE THAN ONE speaker: the INSTRUCTOR (the person teaching / leading the class) and
  LEARNERS (who ask questions or respond). Speaker labels are often MISSING — infer turns from content.
- FIRST attribute who is speaking, THEN judge. You are evaluating the INSTRUCTOR ONLY. NEVER flag a
  learner's words as the instructor's mistake. A learner being confused or wrong is not, by itself, an
  instructor flag — only flag the instructor if their OWN explanation caused it or they fail to resolve it.
- Read the WHOLE-SESSION MAP given in CONTEXT first, and judge each segment IN THE CONTEXT OF THE WHOLE
  SESSION, not in isolation. If a concern here is RESOLVED or addressed later (per the map), do NOT flag
  it — that would be a text-segmentation artefact, not a real problem.
- The class AGENDA (the planned items) is given in CONTEXT — use it to judge coverage and time balance.
- PLANNED CLASS MATERIALS (an outline of the content that was supposed to be taught) may also be given
  in CONTEXT — check the transcript against them for coverage, agenda_balance and correctness.
- Use the [HH:MM:SS] timestamps to estimate how long was spent on each thing.

The class is ALREADY known to be low-rated. Your job is to diagnose WHY and find specific moments —
not to re-score whether it was good or bad.

ASSESS THESE FLAGS. Raise a flag ONLY when there is concrete evidence (a timestamped quote).
If a dimension is fine, raise nothing for it.

[A] Read directly from the transcript:
  pace           - too fast or too slow; visible rushing (e.g. final agenda items compressed near the end).
  clarity        - concepts explained clearly and correctly; jargon defined; no muddled/contradictory bits.
  structure      - logical flow, signposting ("first... now... to recap"), and a wrap-up/summary.
  examples       - concrete examples, live demos, or worked problems used to illustrate concepts.
  correctness    - statements that appear technically wrong or misleading (a human verifies; be honest on confidence).
  logistics      - late start, long dead-air gaps, or tech problems the instructor mentions.
  coverage       - were the planned AGENDA items actually covered? Flag any planned item skipped or rushed.
  coding_time    - was a coding notebook / live coding actually used, and roughly >= 30 min spent on it? Estimate from timestamps.
  agenda_balance - did each agenda item get enough time (aim ~45 min), and did the IMPORTANT items get MORE time? Use timestamps.
  concept_left   - did the instructor DEFER a planned concept to a future class ("we'll cover this next time / next class")? Quote it.

[B] Interaction quality (judge from the ACTUAL learner turns in the transcript; if a learner's words are
    not captured, stay at lower confidence and never assume an unseen question):
  doubt_handling - a learner question/doubt, and whether the instructor answers it well, poorly, or waves it
                   off. Attribute the QUESTION to the learner and the HANDLING to the instructor. If the doubt
                   is resolved later in the session, it is handled.
  engagement     - interactive vs a monologue; does the instructor invite questions / check understanding ("does that make sense?").
  learner_gap    - a learner points out a concept that was not covered, and how the instructor responds.

[C] Needs the video, not the transcript (raise ONLY on a clear verbal cue; otherwise leave for a separate check on the recording):
  camera         - whether the instructor's camera is on. The transcript cannot show this; only flag if they say e.g. "can you see me?".

RULES:
- Every finding MUST include a verbatim quote (<= 20 words) copied exactly, plus its timestamp.
- For coding_time and agenda_balance, give the time range you estimated and the quotes that mark the start and end.
- Prefer PRECISION over completeness: if unsure, do NOT raise the flag. A false criticism is worse than a miss.
- Never invent or paraphrase quotes."""

RUBRIC_ARS = """\
You are auditing an ASSIGNMENT REVIEW SESSION (ARS) transcript to evaluate the instructor.

WHAT AN ARS IS (read carefully):
- Learners were assigned problems; this session reviews the solutions and clears doubts.
- The transcript may contain MORE THAN ONE speaker: the INSTRUCTOR (leading the review) and LEARNERS
  (asking about problems / raising doubts). Speaker labels are often MISSING — infer turns from content.
- FIRST attribute who is speaking, THEN judge. You evaluate the INSTRUCTOR ONLY. NEVER flag a learner's
  words as the instructor's mistake.
- Read the WHOLE-SESSION MAP given in CONTEXT first, and judge each segment IN THE CONTEXT OF THE WHOLE
  SESSION. If a doubt raised here is RESOLVED later (per the map), do NOT flag it as unresolved — that
  would be a text-segmentation artefact, not a real problem.
- The assignment / planned problems are given in CONTEXT when available — use them to judge coverage.
- PLANNED CLASS MATERIALS (the assignment content / solutions outline) may also be given in CONTEXT —
  check the transcript against them for problem_coverage and correctness.
- Use the [HH:MM:SS] timestamps to estimate how long was spent on each problem.

The session is ALREADY known to be low-rated. Your job is to diagnose WHY and find specific moments —
not to re-score whether it was good or bad.

ASSESS THESE FLAGS. Raise a flag ONLY when there is concrete evidence (a timestamped quote).
If a dimension is fine, raise nothing for it.

[A] Read directly from the transcript:
  problem_coverage     - was every assigned problem actually reviewed? Flag any skipped or badly rushed.
  time_balance         - harder problems get more time; nothing crammed at the end (time spent on doubts is fine).
  solution_walkthrough - is each solution actually stepped through live — not just stated, or read off a slide/notebook?
  approach_reasoning   - do they teach HOW to arrive at the solution (intuition, brute-force -> optimal,
                         interview thinking), not just present the final code/answer?
  complexity_tradeoffs - ONLY where code or a model is actually discussed: time/space complexity for coding
                         problems; model/metric/cost trade-offs for ML. If the session involves no code, do NOT raise this.
  edge_cases           - tricky inputs, failure modes, tests; data leakage/overfitting for ML problems.
  common_mistakes      - did they surface submission patterns ("a lot of you did X — here's why it fails")?
                         Raise only from what is said aloud.
  problem_deferred     - a problem pushed to a future session ("we'll do this one next time"). Quote it.
  pace                 - too fast or too slow; visible rushing.
  clarity              - explanations clear and correct; jargon defined; no muddled/contradictory bits.
  structure            - per-problem flow (restate -> approach -> solution -> complexity -> mistakes) and a recap.
  correctness          - anything technically wrong in a presented solution. Raise at MAJOR severity at
                         minimum — learners treat reviewed solutions as canonical.
  logistics            - late start, long dead-air gaps, or tech problems the instructor mentions.

[B] Interaction quality (judge from the ACTUAL learner turns when present; never assume an unseen question):
  doubt_handling - WEIGHTED HEAVILY in an ARS: clearing doubts is the point of the session. Attribute the
                   doubt to the LEARNER and judge how the instructor handles it (well / poorly / waved off).
                   If a doubt is resolved later in the session, it is handled. If no doubts surface at all,
                   that alone is NOT a flag.
  engagement     - interactive vs a monologue; invites questions, checks understanding.
  learner_gap    - a learner (or the instructor) notes a prerequisite wasn't taught, or the assignment
                   didn't match what the class covered.

[C] Needs the video, not the transcript (raise ONLY on a clear verbal cue):
  camera - whether the instructor's camera is on; only flag if they say e.g. "can you see me?".

RULES:
- Every finding MUST include a verbatim quote (<= 20 words) copied exactly, plus its timestamp.
- For problem_coverage and time_balance, give the time range you estimated and the quotes that mark start and end.
- Prefer PRECISION over completeness: if unsure, do NOT raise the flag. A false criticism is worse than a miss.
- Never invent or paraphrase quotes."""

RUBRICS = {"live_class": RUBRIC_LIVE, "ars": RUBRIC_ARS}

# ── Pass 0: understand the WHOLE conversation before judging any part of it ──────────────────
# This is what makes the analysis intelligent rather than a per-segment text matcher: one pass reads
# the entire transcript, works out who the instructor is vs the learners, the real flow, and — crucially
# — which doubts/concerns get RESOLVED later. That map is fed into every later step so nothing is flagged
# out of context.
CONV_MAP_SYS = (
    "You are analysing a FULL class/session transcript to understand it as a whole BEFORE any judgement. "
    "The transcript may contain multiple speakers — the INSTRUCTOR (who teaches / leads) and LEARNERS "
    "(who ask or respond) — and speaker labels are often missing, so infer turns from content. Produce a "
    "compact, NEUTRAL map (no criticism, no scoring, no advice):\n"
    "1) SPEAKERS — who is the instructor vs learners; note any names/labels you can infer.\n"
    "2) SESSION ARC — the ordered topics/problems actually taught, with rough [HH:MM:SS] ranges.\n"
    "3) INTERACTIONS — notable learner questions/doubts and WHERE (timestamp) the instructor resolved each,\n"
    "   or 'not resolved'.\n"
    "4) OPEN THREADS — anything deferred, skipped, or left unresolved by the END of the session.\n"
    "Output plain text, <= 450 words. Be accurate; this map is the shared context a later auditor relies on."
)

CONV_MAP_MAX_CHARS = 60000   # cap the transcript fed to the map pass (very long sessions are truncated)

def map_conversation(client, cues: list[Cue], ctx: str, usage: "Usage") -> str:
    """Read the whole transcript once and return a neutral session map (speakers, arc, what got resolved)."""
    body = format_segment(cues)
    truncated = len(body) > CONV_MAP_MAX_CHARS
    if truncated:
        body = body[:CONV_MAP_MAX_CHARS]
    user = (
        f"CLASS CONTEXT\n{ctx}\n\n"
        f"FULL TRANSCRIPT (timestamps [HH:MM:SS]; a leading 'Name:' marks the speaker when known):\n{body}\n\n"
        + ("[note: transcript truncated for length — map what you can]\n\n" if truncated else "")
        + "Produce the session map now."
    )
    return _call(client, CONV_MAP_SYS, user, 1200, usage).strip()

EXTRACT_SYS = (
    "You are a precise teaching-quality auditor reviewing ONE segment of a class transcript that may "
    "contain multiple speakers (an instructor and learners). You FIRST attribute who is speaking, then "
    "extract only evidence-backed findings ABOUT THE INSTRUCTOR, as strict JSON. Rules you never break: "
    "never blame the instructor for a learner's words; use the whole-session map for context and never "
    "flag something the session resolves elsewhere; every quote is copied verbatim from the segment; you "
    "never invent or paraphrase quotes; you prefer returning nothing over raising an unsupported flag; "
    "you output JSON only — no prose, no code fences."
)

def build_extract_user(ctx: str, segment_text: str, class_type: str = "live_class") -> str:
    allowed = "|".join(sorted(flags_for(class_type)))
    return (
        f"CLASS CONTEXT\n{ctx}\n\n{RUBRICS[class_type]}\n\n{SEVERITY_ANCHORS}\n\n"
        f"TRANSCRIPT SEGMENT (timestamps [HH:MM:SS]; a leading 'Name:' marks the speaker when known — "
        f"lines with no name are usually the instructor, but confirm from content):\n{segment_text}\n\n"
        "BEFORE extracting: attribute each line to the instructor or a learner. Judge ONLY the instructor. "
        "Do not raise anything the whole-session map shows is resolved later, and never turn a learner's "
        "words into an instructor flag.\n"
        'Return JSON ONLY in this shape:\n'
        '{"findings":[{"flag":"' + allowed + '",'
        '"observation":"one specific sentence","severity":"minor|moderate|major",'
        '"evidence":[{"timestamp":"HH:MM:SS","quote":"<=20 words, verbatim from THIS segment"}],'
        '"confidence":"low|medium|high"}]}\n'
        'Only include findings with real evidence in THIS segment. If the segment is fine, return {"findings":[]}.'
    )

SYNTH_SYS = (
    "You are a senior instructional reviewer. You consolidate per-segment findings into a verified, "
    "de-duplicated assessment, then produce THREE SEPARATE things: (1) DETAILED coaching feedback with "
    "timestamps, for the INTERNAL team; (2) a SHORT, warm summary note to SEND to the instructor "
    "(6-7 sentences, may state the class rating); (3) a PM-only recommendation on whether the class "
    "needs to be re-taught. You DROP any finding whose quote does not clearly support its claim, whose "
    "quote is actually a LEARNER speaking (not the instructor), or that the whole-session map shows was "
    "resolved later in the session. The re-class recommendation is for the PM and must never appear in "
    "either instructor-facing text. Output JSON only — no prose, no code fences."
)

def build_synth_user(ctx: str, findings_json: str, class_type: str = "live_class") -> str:
    if class_type == "ars":
        frame = ("   - Frame the points around the PROBLEMS reviewed (coverage, walkthrough depth, reasoning),\n"
                 "     not agenda items.\n")
        yes_rule = ('     - "yes"   : assigned problems were skipped or badly rushed, OR a presented solution was\n'
                    "                 technically wrong or so unclear that learners likely did not get it (learners\n"
                    "                 treat reviewed solutions as canonical).\n")
    else:
        frame = ""
        yes_rule = ('     - "yes"   : important planned agenda content was not covered or was badly rushed, OR core\n'
                    "                 concepts were explained incorrectly or so unclearly that learners likely did not get them.\n")
    return (
        f"CLASS CONTEXT\n{ctx}\n\n"
        f"RAW FINDINGS collected from segment passes:\n{findings_json}\n\n"
        f"{SEVERITY_ANCHORS}\n\n"
        "DO THIS, IN ORDER:\n"
        "1. VERIFY each finding against the WHOLE SESSION, and DROP it if ANY of these is true:\n"
        "   - the quote does not actually support the observation;\n"
        "   - the quote is a LEARNER speaking, not the instructor (never blame the instructor for a learner's words);\n"
        "   - the concern is RESOLVED or addressed later in the session (per the whole-session map) — a\n"
        "     text-segmentation artefact, not a real problem;\n"
        "   - read in full context, the moment is not actually a problem.\n"
        "2. MERGE duplicates across segments; give each surviving flag an overall severity PER THE\n"
        "   SEVERITY ANCHORS above (tie-break low) and a confidence.\n"
        "3. WRITE feedback FOR THE INSTRUCTOR (this is what the instructor receives). STYLE — strict:\n"
        "   - Formal, respectful and kind; direct but NEVER harsh; no filler praise, no lecturing.\n"
        "   - CONCISE and to the point: 150-250 words total.\n"
        "   - Shape: one sentence on what genuinely worked; then 2-4 numbered improvement points, each\n"
        "     anchored to its [HH:MM:SS] timestamp(s) and ending in ONE concrete, actionable suggestion;\n"
        "     then a one-line close.\n"
        "   - Every improvement point MUST cite at least one timestamp. Never invent quotes or timestamps.\n"
        + frame +
        "   - This DETAILED feedback is for the internal team; it may be candid but stays kind. Do NOT mention\n"
        "     the numeric rating, that the class was low-rated, or re-classing here — purely coaching.\n"
        "4. WRITE the SUMMARY NOTE TO SEND TO THE INSTRUCTOR (field 'instructor_summary'). This is the polished\n"
        "   message the instructor actually receives. STYLE — strict:\n"
        "   - MAX 6-7 sentences total. Warm, respectful, encouraging; specific but never harsh; no timestamps needed.\n"
        "   - Cover, in this order: (a) 1-2 sentences on what genuinely went WELL; (b) 1-2 sentences on what did\n"
        "     NOT go well / needs improvement; (c) STATE the average class rating (use the rating from CLASS\n"
        "     CONTEXT — e.g. 'This session averaged X/5'; if the rating is unknown, omit this sentence);\n"
        "     (d) ONE clear, concrete suggestion for improvement; (e) a single closing line capturing the essence\n"
        "     of what worked and an encouraging conclusion.\n"
        "   - Self-contained prose (no bullet list, no headings). Do NOT mention re-classing.\n"
        "5. RE-CLASS CALL, FOR THE PM ONLY (must NOT appear in either instructor text): decide whether this\n"
        "   class likely needs to be re-taught to the learners. Judge whether the LEARNING was delivered:\n"
        + yes_rule +
        '     - "no"    : the problems are about pace / style / engagement, but the content was delivered correctly.\n'
        '     - "maybe" : genuinely borderline — say what the PM should check.\n'
        "   Give a 1-2 sentence reason for the PM, citing the deciding flags/timestamps. The PM makes the final call.\n\n"
        'Return JSON ONLY:\n'
        '{"overall":"2-3 sentence summary of what likely drove the low rating",'
        '"flags":[{"flag":"...","severity":"minor|moderate|major","confidence":"low|medium|high",'
        '"evidence":[{"timestamp":"HH:MM:SS","quote":"..."}]}],'
        '"feedback":"the DETAILED coaching message (internal), referencing timestamps",'
        '"instructor_summary":"the 6-7 sentence note to SEND to the instructor, stating the rating",'
        '"reclass":{"recommended":"yes|no|maybe","reason":"1-2 sentences for the PM only","deciding_flags":["coverage","correctness"]}}'
    )

# ── Stage 4: adversarial verification (the skeptic) ────────────────────────────────
# A second, independent reviewer that tries to REFUTE each serious finding before the PM sees it.
# Verdicts are applied by CODE (apply_verdicts/gate_reclass) — the skeptic cannot invent findings,
# raise severities, or rewrite text. This is the fix for over-flagged "critical" findings.
SKEPTIC_SYS = (
    "You are an adversarial verifier — an independent second reviewer whose job is to try to REFUTE "
    "each finding, not to confirm it. For each finding check exactly three things: "
    "(1) QUOTE — is the quote real (see quote_found) and, read in its transcript excerpt, does it "
    "actually show what the finding claims, said by the INSTRUCTOR (not a learner)? A quote beginning "
    "'<visual:' is an observation from the recording's VISUAL TRACK — verify it against that track "
    "instead of the transcript. "
    "(2) CONTEXT — does the whole-session map (or visual track) contradict the finding: resolved "
    "later, wrong attribution, mischaracterised arc? "
    "(3) SEVERITY BAR — does the evidence CLEARLY meet the anchor bar for the stated severity? "
    "Verdicts: 'uphold' (survives all three); 'downgrade' (a real problem, but the evidence does not "
    "meet the severity bar — state the corrected_severity); 'drop' (refuted — you MUST state the "
    "specific contradiction: the map line, excerpt evidence, or attribution error that refutes it; "
    "'feels harsh' or general doubt is NEVER a reason to drop; if merely unsure, downgrade instead). "
    "HARD LIMITS: you may NEVER invent new problems, add findings, raise a severity, or rewrite any "
    "text — only uphold, downgrade, or drop what you are given. Every verdict must name the anchor "
    "rule it applied. Output JSON only — no prose, no code fences."
)


def build_skeptic_user(ctx: str, candidates_json: str, excerpts: str,
                       reclass_framing: bool = False) -> str:
    frame = (
        "These majors are the sole basis for a recommendation that learners RE-ATTEND this class. "
        "Would you sign off on that? Hold them to the strictest reading of the anchors.\n\n"
        if reclass_framing else ""
    )
    return (
        f"CLASS CONTEXT\n{ctx}\n\n"
        f"{SEVERITY_ANCHORS}\n\n"
        + frame +
        "FINDINGS TO VERIFY (each has an id; quote_found tells you whether the quote appears "
        "verbatim in the transcript — if false, treat that evidence as suspect):\n"
        f"{candidates_json}\n\n"
        "TRANSCRIPT EXCERPTS around each finding's evidence (about 2 minutes either side):\n"
        f"{excerpts}\n\n"
        "Try to REFUTE each finding. Return exactly one verdict per id. JSON ONLY:\n"
        '{"verdicts":[{"id":0,"verdict":"uphold|downgrade|drop",'
        '"corrected_severity":"minor|moderate|major",'
        '"anchor_rule":"the anchor line you applied",'
        '"reason":"1-2 sentences; for drop this MUST state the specific contradiction"}]}'
    )


def select_review_candidates(result: dict) -> list[dict]:
    """Flags worth a second look: severity major/moderate, plus anything the re-class call leans on.
    Minors are never reviewed — verifying polish notes is ceremony."""
    flags = result.get("flags") or []
    deciding = set((result.get("reclass") or {}).get("deciding_flags") or []) \
        if (result.get("reclass") or {}).get("recommended") == "yes" else set()
    out = []
    for i, f in enumerate(flags):
        if not isinstance(f, dict):
            continue
        if f.get("severity") in ("major", "moderate") or f.get("flag") in deciding:
            out.append({"id": i, **f})
    return out


def validate_verdicts(obj: Any, candidates: list[dict]) -> list[str]:
    """The skeptic must return exactly one verdict per candidate id — an extra id is the verifier
    inventing a finding, and it is rejected."""
    if not isinstance(obj, dict) or not isinstance(obj.get("verdicts"), list):
        return ["top level must be an object with a 'verdicts' list"]
    errs: list[str] = []
    want = {c["id"] for c in candidates}
    seen: list = []
    by_id = {c["id"]: c for c in candidates}
    for i, v in enumerate(obj["verdicts"]):
        if not isinstance(v, dict):
            errs.append(f"verdicts[{i}] must be an object"); continue
        vid = v.get("id")
        if vid not in want:
            errs.append(f"verdicts[{i}]: unknown id {vid!r} — verdicts only for the given findings")
            continue
        seen.append(vid)
        if v.get("verdict") not in ("uphold", "downgrade", "drop"):
            errs.append(f"verdicts[{i}]: verdict must be uphold|downgrade|drop")
        if v.get("verdict") == "downgrade":
            corr = v.get("corrected_severity")
            if corr not in SEVERITY:
                errs.append(f"verdicts[{i}]: downgrade needs corrected_severity")
            elif severity_rank(corr) >= severity_rank(by_id[vid].get("severity", "major")):
                errs.append(f"verdicts[{i}]: corrected_severity must be LOWER than the original")
        for key in ("anchor_rule", "reason"):
            if not isinstance(v.get(key), str) or not v.get(key).strip():
                errs.append(f"verdicts[{i}]: missing {key}")
    missing = want - set(seen)
    if missing:
        errs.append(f"missing verdicts for ids: {sorted(missing)}")
    dupes = {x for x in seen if seen.count(x) > 1}
    if dupes:
        errs.append(f"duplicate verdicts for ids: {sorted(dupes)}")
    return errs


def merge_conservative(v1: list[dict], v2: list[dict]) -> list[dict]:
    """Two votes on the same ids → the more skeptical verdict wins (drop > downgrade > uphold);
    for two downgrades keep the lower corrected severity."""
    strength = {"uphold": 0, "downgrade": 1, "drop": 2}
    by_id = {v["id"]: v for v in v1}
    for v in v2:
        cur = by_id.get(v["id"])
        if cur is None:
            continue  # the second vote may only cover a subset — never adds new ids
        if strength[v["verdict"]] > strength[cur["verdict"]]:
            by_id[v["id"]] = v
        elif v["verdict"] == cur["verdict"] == "downgrade":
            if severity_rank(v.get("corrected_severity", "major")) < severity_rank(cur.get("corrected_severity", "major")):
                by_id[v["id"]] = v
    return [by_id[k] for k in sorted(by_id)]


def apply_verdicts(result: dict, verdicts: list[dict], class_type: str) -> tuple[dict, list[dict]]:
    """Apply skeptic verdicts mechanically. Guards: downgrades move at most ONE level per pass
    (a bigger swing is recorded, not applied); code-side severity floors always win; drops keep a
    full review record so nothing disappears silently. Input is not mutated."""
    import copy
    out = copy.deepcopy(result)
    flags = out.get("flags") or []
    by_id = {v["id"]: v for v in verdicts}
    review: list[dict] = []
    kept: list = []
    for i, f in enumerate(flags):
        v = by_id.get(i)
        if v is None:
            kept.append(f)
            continue
        name = f.get("flag", "?")
        sev = f.get("severity", "moderate")
        rec = {"flag": name, "verdict": v["verdict"], "from_severity": sev,
               "anchor_rule": v.get("anchor_rule", ""), "reason": v.get("reason", "")}
        if v["verdict"] == "drop":
            rec["to_severity"] = None
            review.append(rec)
            continue  # flag removed
        if v["verdict"] == "downgrade":
            wanted = v.get("corrected_severity", one_level_down(sev))
            applied = one_level_down(sev)                       # one-level clamp
            if severity_rank(wanted) < severity_rank(applied):
                rec["skeptic_wanted"] = wanted
            floor = SEVERITY_FLOORS.get((class_type, name))
            if floor and severity_rank(applied) < severity_rank(floor):
                # floor blocks the downgrade entirely (a false claim should be dropped, not softened)
                rec["verdict"] = "uphold"
                rec["to_severity"] = sev
                rec["reason"] = (rec["reason"] + " [floor: ARS correctness is major minimum]").strip()
                review.append(rec)
                kept.append(f)
                continue
            f["severity"] = applied
            rec["to_severity"] = applied
            review.append(rec)
            kept.append(f)
            continue
        rec["to_severity"] = sev                                 # uphold
        review.append(rec)
        kept.append(f)
    out["flags"] = kept
    return out, review


def gate_reclass(result: dict) -> dict:
    """A re-class 'yes' must rest on at least one surviving MAJOR content-delivery flag; otherwise
    it is auto-softened to 'maybe' (visibly). 'maybe' is never upgraded; 'no' is never touched."""
    rc = result.get("reclass") or {}
    if rc.get("recommended") != "yes":
        return result
    has_support = any(
        f.get("severity") == "major" and f.get("flag") in CONTENT_DELIVERY_FLAGS
        for f in (result.get("flags") or []) if isinstance(f, dict)
    )
    if not has_support:
        rc["softened_from"] = "yes"
        rc["recommended"] = "maybe"
        rc["reason"] = ("[auto-softened from 'yes': no confirmed major content-delivery flag "
                        "survived verification] " + str(rc.get("reason", ""))).strip()
    return result


def skeptic_review(client, candidates: list[dict], cues: list[Cue], transcript_text: str,
                   ctx: str, usage: "Usage", reclass_framing: bool = False) -> list[dict]:
    """One adversarial call covering every candidate (cross-flag context beats per-flag calls).
    Each candidate is annotated with quote_found + a real transcript excerpt first."""
    annotated = []
    excerpt_parts = []
    for c in candidates:
        evs = c.get("evidence") or []
        ann_evs = []
        for e in evs:
            q = str(e.get("quote", ""))
            found = True if q.startswith("<visual:") else quote_present(transcript_text, q)
            ann_evs.append({**e, "quote_found": found})
            ex = excerpt_around(cues, str(e.get("timestamp", "")))
            if ex:
                excerpt_parts.append(f"--- finding id {c['id']} ({c.get('flag')}) around [{e.get('timestamp')}] ---\n{ex}")
        annotated.append({**c, "evidence": ann_evs})
    obj = _call_json(client, SKEPTIC_SYS,
                     build_skeptic_user(ctx, json.dumps(annotated, ensure_ascii=False, indent=1),
                                        "\n\n".join(excerpt_parts), reclass_framing),
                     CFG.max_tokens_skeptic, lambda o: validate_verdicts(o, candidates), usage)
    return obj["verdicts"]


# ──────────────────────────────────────────────────────────────── schema validation
def _check_evidence(ev: Any) -> list[str]:
    errs: list[str] = []
    if not isinstance(ev, list) or not ev:
        return ["evidence must be a non-empty list"]
    for e in ev:
        if not isinstance(e, dict) or "timestamp" not in e or "quote" not in e:
            errs.append("each evidence item needs timestamp + quote")
    return errs

def _check_flag(fobj: Any, require_observation: bool, allowed: set | None = None) -> list[str]:
    errs: list[str] = []
    if not isinstance(fobj, dict):
        return ["flag entry must be an object"]
    if fobj.get("flag") not in (allowed or FLAGS):
        errs.append(f"unknown flag: {fobj.get('flag')!r}")
    if fobj.get("severity") not in SEVERITY:
        errs.append(f"bad severity: {fobj.get('severity')!r}")
    if fobj.get("confidence") not in CONFIDENCE:
        errs.append(f"bad confidence: {fobj.get('confidence')!r}")
    if require_observation and not isinstance(fobj.get("observation"), str):
        errs.append("missing observation")
    errs += _check_evidence(fobj.get("evidence"))
    return errs

def validate_findings(obj: Any, allowed: set | None = None) -> list[str]:
    if not isinstance(obj, dict) or "findings" not in obj:
        return ["top level must be an object with 'findings'"]
    if not isinstance(obj["findings"], list):
        return ["'findings' must be a list"]
    errs: list[str] = []
    for i, f in enumerate(obj["findings"]):
        errs += [f"finding[{i}]: {e}" for e in _check_flag(f, require_observation=True, allowed=allowed)]
    return errs

def validate_result(obj: Any, allowed: set | None = None) -> list[str]:
    if not isinstance(obj, dict):
        return ["result must be an object"]
    errs: list[str] = []
    for key in ("overall", "feedback", "instructor_summary"):
        if not isinstance(obj.get(key), str) or not obj.get(key).strip():
            errs.append(f"missing/empty '{key}'")
    if not isinstance(obj.get("flags"), list):
        errs.append("'flags' must be a list")
    else:
        for i, f in enumerate(obj["flags"]):
            errs += [f"flags[{i}]: {e}" for e in _check_flag(f, require_observation=False, allowed=allowed)]
    rc = obj.get("reclass")
    if not isinstance(rc, dict):
        errs.append("missing 'reclass' object")
    else:
        if rc.get("recommended") not in RECLASS:
            errs.append(f"reclass.recommended must be yes/no/maybe, got {rc.get('recommended')!r}")
        if not isinstance(rc.get("reason"), str) or not rc.get("reason").strip():
            errs.append("reclass.reason missing/empty")
        if "softened_from" in rc and rc["softened_from"] != "yes":
            errs.append("reclass.softened_from, when present, must be 'yes'")
    # 'review' is added by code after the skeptic pass (the synthesiser never emits it) — but the
    # final persisted result must stay self-validating.
    if "review" in obj:
        if not isinstance(obj["review"], list):
            errs.append("'review' must be a list")
        else:
            for i, r in enumerate(obj["review"]):
                if not isinstance(r, dict) or r.get("verdict") not in ("uphold", "downgrade", "drop"):
                    errs.append(f"review[{i}]: bad verdict")
                    continue
                if r.get("from_severity") not in SEVERITY:
                    errs.append(f"review[{i}]: bad from_severity")
                if r.get("to_severity") is not None and r.get("to_severity") not in SEVERITY:
                    errs.append(f"review[{i}]: bad to_severity")
                if not str(r.get("reason", "")).strip():
                    errs.append(f"review[{i}]: missing reason")
    return errs

# ──────────────────────────────────────────────────────────────────── LLM client
@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    def cost_usd(self) -> float:
        return (self.input_tokens * CFG.price_in_per_mtok + self.output_tokens * CFG.price_out_per_mtok) / 1_000_000

def _client():
    import anthropic
    return anthropic.Anthropic(max_retries=CFG.max_retries, timeout=CFG.timeout_s)

def _strip_fences(s: str) -> str:
    return re.sub(r"^```(?:json)?|```$", "", s.strip(), flags=re.M).strip()

def _call(client, system: str, user: str, max_tokens: int, usage: Usage) -> str:
    t = time.time()
    msg = client.messages.create(
        model=CFG.model, max_tokens=max_tokens, temperature=CFG.temperature,
        system=system, messages=[{"role": "user", "content": user}],
    )
    usage.input_tokens += msg.usage.input_tokens
    usage.output_tokens += msg.usage.output_tokens
    usage.calls += 1
    log.info("llm call ok  in=%d out=%d  %.1fs", msg.usage.input_tokens, msg.usage.output_tokens, time.time() - t)
    return "".join(b.text for b in msg.content if b.type == "text")

def _call_json(client, system: str, user: str, max_tokens: int, validate: Callable[[Any], list[str]], usage: Usage) -> dict:
    """Call the model, parse + validate JSON, and re-ask once if it is malformed or invalid."""
    text = _call(client, system, user, max_tokens, usage)
    for attempt in range(CFG.repair_attempts + 1):
        try:
            obj = json.loads(_strip_fences(text))
            errs = validate(obj)
            if not errs:
                return obj
            problem = "Validation errors: " + "; ".join(errs[:8])
        except json.JSONDecodeError as e:
            problem = f"Invalid JSON: {e}"
        if attempt >= CFG.repair_attempts:
            raise ValueError(f"model output still invalid after repair — {problem}")
        log.warning("repairing model output: %s", problem)
        text = _call(client, system,
                     user + f"\n\nYour previous reply was invalid. {problem}\nReturn corrected JSON only.",
                     max_tokens, usage)
    raise RuntimeError("unreachable")

def extract_findings(client, seg: list[Cue], ctx: str, usage: Usage,
                     class_type: str = "live_class") -> list[dict]:
    allowed = flags_for(class_type)
    obj = _call_json(client, EXTRACT_SYS, build_extract_user(ctx, format_segment(seg), class_type),
                     CFG.max_tokens_extract, lambda o: validate_findings(o, allowed), usage)
    return obj.get("findings", [])

def synthesise(client, findings: list[dict], ctx: str, usage: Usage,
               class_type: str = "live_class") -> dict:
    allowed = flags_for(class_type)
    return _call_json(client, SYNTH_SYS,
                      build_synth_user(ctx, json.dumps(findings, ensure_ascii=False, indent=2), class_type),
                      CFG.max_tokens_synth, lambda o: validate_result(o, allowed), usage)

MATERIALS_SYS = (
    "You compress class materials into a compact teaching outline that an auditor will check a class "
    "transcript against. Output plain text, <= 400 words: the topics in order, key concepts/definitions, "
    "planned examples/exercises/problems, and anything marked as important. No commentary, no preamble."
)

# Materials shorter than this go into the context verbatim; longer ones are LLM-compressed first.
MATERIALS_DIGEST_THRESHOLD = 4000
MATERIALS_MAX_CHARS = 60000


def _digest_materials(client, text: str, usage: Usage) -> str:
    """Boil raw class materials down to an outline the extraction prompts can carry."""
    text = text.strip()
    if len(text) <= MATERIALS_DIGEST_THRESHOLD:
        return text
    return _call(client, MATERIALS_SYS,
                 f"MATERIALS:\n{text[:MATERIALS_MAX_CHARS]}\n\nCompress to the outline now.",
                 1500, usage).strip()


# Two revise modes — the DETAILED internal feedback keeps timestamps and hides the rating; the
# send-to-instructor SUMMARY keeps it short and MAY state the rating.
REVISE_SYS = (
    "You revise coaching feedback that a PM will send to a class instructor, following the PM's "
    "instruction exactly. Rules you never break: stay formal, concise, respectful and specific; never "
    "use harsh words; keep (or tighten) the [HH:MM:SS] timestamp references; never invent new claims, "
    "quotes or timestamps that are not in the current feedback or the provided flags; never mention the "
    "numeric rating, that the class was low-rated, or any re-class decision. "
    'Output JSON only — no prose, no code fences: {"feedback":"..."}'
)

REVISE_SUMMARY_SYS = (
    "You revise the SHORT summary note a PM will SEND to a class instructor, following the PM's "
    "instruction exactly. Rules you never break: keep it a warm, respectful, self-contained note of "
    "roughly 6-7 sentences (no bullet lists, no headings, no timestamps needed); never use harsh words; "
    "you MAY keep the class rating if it is present; never invent new claims that are not in the current "
    "summary or the provided flags; never mention any re-class decision. "
    'Output JSON only — no prose, no code fences: {"feedback":"..."}'
)

def revise_feedback(current: str, instruction: str, ctx: str = "", flags_json: str = "",
                    kind: str = "feedback") -> tuple[str, dict]:
    """Rewrite an existing draft per the PM's plain-English instruction (the review-page agent).
    kind='feedback' rewrites the detailed internal note; kind='summary' rewrites the send-to-instructor note."""
    if not current or not current.strip():
        raise ValueError("no feedback text to revise")
    if not instruction or not instruction.strip():
        raise ValueError("no revision instruction given")
    client = _client()
    usage = Usage()
    t0 = time.time()
    parts = []
    if ctx.strip():
        parts.append(f"CLASS CONTEXT\n{ctx}\n")
    if flags_json.strip():
        parts.append(f"VERIFIED FLAGS (grounding — the only claims allowed):\n{flags_json}\n")
    parts.append(f"CURRENT FEEDBACK:\n{current}\n")
    parts.append(f"PM'S INSTRUCTION:\n{instruction}\n")
    parts.append('Rewrite the feedback per the instruction. Return JSON ONLY: {"feedback":"..."}')

    def _validate(obj: Any) -> list[str]:
        if not isinstance(obj, dict) or not isinstance(obj.get("feedback"), str) or not obj["feedback"].strip():
            return ["top level must be an object with a non-empty 'feedback' string"]
        return []

    sys_prompt = REVISE_SUMMARY_SYS if kind == "summary" else REVISE_SYS
    obj = _call_json(client, sys_prompt, "\n".join(parts), CFG.max_tokens_synth, _validate, usage)
    meta = {"model": CFG.model, "tokens_in": usage.input_tokens, "tokens_out": usage.output_tokens,
            "llm_calls": usage.calls, "cost_usd": round(usage.cost_usd(), 4),
            "seconds": round(time.time() - t0, 1)}
    log.info("revise done  cost=$%.4f  %.1fs", meta["cost_usd"], meta["seconds"])
    return obj["feedback"].strip(), meta

RECONCILE_SYS = (
    "You adjust two feedback texts after a second-pass review changed the findings behind them. "
    "Remove or soften ONLY what the review changed: strip any point that rests on a DROPPED finding; "
    "soften the emphasis of DOWNGRADED ones. Change nothing else — keep the tone, structure, length "
    "style, timestamps and every other point exactly as they are. Never add new claims. "
    'Output JSON only — no prose, no code fences: {"feedback":"...","instructor_summary":"..."}'
)


def _reconcile_prose(client, result: dict, changed: list[dict], usage: "Usage") -> dict:
    """After drops/downgrades, one call keeps the two prose outputs honest (they may still reference
    a removed finding). Flags/severities/reclass stay exactly as code applied them."""
    user = (
        "REVIEW CHANGES (what the second-pass verification did):\n"
        + json.dumps(changed, ensure_ascii=False, indent=1)
        + "\n\nSURVIVING FLAGS (the only claims allowed):\n"
        + json.dumps(result.get("flags") or [], ensure_ascii=False, indent=1)
        + "\n\nCURRENT DETAILED FEEDBACK (internal):\n" + str(result.get("feedback", ""))
        + "\n\nCURRENT SUMMARY TO SEND THE INSTRUCTOR:\n" + str(result.get("instructor_summary", ""))
        + '\n\nAdjust both texts per the review changes. Return JSON ONLY: '
          '{"feedback":"...","instructor_summary":"..."}'
    )

    def _validate(obj: Any) -> list[str]:
        errs = []
        for key in ("feedback", "instructor_summary"):
            if not isinstance(obj.get(key), str) or not obj.get(key).strip():
                errs.append(f"missing/empty '{key}'")
        return errs

    try:
        obj = _call_json(client, RECONCILE_SYS, user, CFG.max_tokens_synth, _validate, usage)
        result["feedback"] = obj["feedback"].strip()
        result["instructor_summary"] = obj["instructor_summary"].strip()
    except Exception:  # reconciliation is best-effort — never lose the analysis over prose polish
        log.exception("prose reconciliation failed; keeping the original texts")
    return result


def analyse_cues(cues: list[Cue], ctx: str, class_type: str = "live_class",
                 materials: str = "") -> tuple[dict, dict]:
    """Run the full LLM pipeline over already-parsed cues. Returns (result, run_metadata).

    ``materials`` is the raw text of the planned class content (slides/notebook/doc); when given,
    it is digested to an outline and added to the context so coverage/correctness are judged
    against what was actually supposed to be taught.
    """
    if class_type not in CLASS_TYPES:
        raise ValueError(f"unknown class_type: {class_type!r} (expected one of {sorted(CLASS_TYPES)})")
    if not cues:
        raise ValueError("no cues to analyse")
    chunks = chunk_by_time(cues)
    client = _client()
    usage = Usage()
    t0 = time.time()
    if materials and materials.strip():
        log.info("digesting %d chars of class materials", len(materials))
        outline = _digest_materials(client, materials, usage)
        ctx = ctx + "\n\nPLANNED CLASS MATERIALS (outline of what was supposed to be taught):\n" + outline
    # Pass 0 — read the whole conversation first, so every later segment is judged in full context
    # (who speaks, the real flow, and which doubts get resolved). This is the anti-"text-segmentation" step.
    log.info("mapping the whole conversation (%d cues) before judging any segment", len(cues))
    convo_map = map_conversation(client, cues, ctx, usage)
    ctx = ctx + ("\n\nWHOLE-SESSION MAP (read this FIRST — it tells you who speaks, the real flow, and what "
                 "gets resolved later; do not flag anything resolved elsewhere):\n" + convo_map)
    findings: list[dict] = []
    for i, seg in enumerate(chunks, 1):
        log.info("extract %d/%d  %s–%s", i, len(chunks), _seconds_to_ts(seg[0].start), _seconds_to_ts(seg[-1].end))
        findings += extract_findings(client, seg, ctx, usage, class_type)
    log.info("synthesise %d raw findings", len(findings))
    result = synthesise(client, findings, ctx, usage, class_type)

    # Stage 4 — adversarial verification: a skeptic tries to REFUTE every serious finding, then code
    # applies the verdicts and gates the re-class call. This is what stops over-flagged "criticals".
    transcript_text = "\n".join(c.text for c in cues)
    review_records: list[dict] = []
    flags_raised = len(result.get("flags") or [])
    n_candidates = 0
    reclass_softened = False
    if CFG.review_enabled:
        candidates = select_review_candidates(result)
        n_candidates = len(candidates)
        if candidates:
            log.info("skeptic review of %d finding(s)", len(candidates))
            verdicts = skeptic_review(client, candidates, cues, transcript_text, ctx, usage)
            if (result.get("reclass") or {}).get("recommended") == "yes":
                # highest-stakes output → a second, narrower vote on the content-delivery majors
                content_majors = [c for c in candidates
                                  if c.get("flag") in CONTENT_DELIVERY_FLAGS and c.get("severity") == "major"]
                if content_majors:
                    log.info("re-class second vote on %d content major(s)", len(content_majors))
                    vote2 = skeptic_review(client, content_majors, cues, transcript_text, ctx, usage,
                                           reclass_framing=True)
                    verdicts = merge_conservative(verdicts, vote2)
            result, review_records = apply_verdicts(result, verdicts, class_type)
        before = (result.get("reclass") or {}).get("recommended")
        result = gate_reclass(result)
        reclass_softened = bool(before == "yes"
                                and (result.get("reclass") or {}).get("recommended") == "maybe")
        changed = [r for r in review_records if r["verdict"] in ("drop", "downgrade")]
        if changed:
            log.info("reconciling prose after %d verification change(s)", len(changed))
            result = _reconcile_prose(client, result, changed, usage)
    result["review"] = review_records

    dropped = sum(1 for r in review_records if r["verdict"] == "drop")
    meta = {
        "model": CFG.model, "class_type": class_type, "windows": len(chunks), "cues": len(cues),
        "speakers": sorted({c.speaker for c in cues if c.speaker}),
        "conversation_mapped": True,
        "raw_findings": len(findings), "materials_used": bool(materials and materials.strip()),
        "review_ran": bool(CFG.review_enabled),
        "flags_raised": flags_raised,
        "flags_reviewed": n_candidates,
        "flags_upheld": sum(1 for r in review_records if r["verdict"] == "uphold"),
        "flags_downgraded": sum(1 for r in review_records if r["verdict"] == "downgrade"),
        "flags_dropped": dropped,
        "reclass_softened": reclass_softened,
        "review_heavy_drop": bool(n_candidates and dropped > n_candidates / 2),
        "tokens_in": usage.input_tokens, "tokens_out": usage.output_tokens, "llm_calls": usage.calls,
        "cost_usd": round(usage.cost_usd(), 4), "seconds": round(time.time() - t0, 1),
    }
    log.info("done  cost=$%.4f  %.1fs  calls=%d", meta["cost_usd"], meta["seconds"], meta["llm_calls"])
    return result, meta

def analyse_text(raw: str, ctx: str, class_type: str = "live_class",
                 materials: str = "") -> tuple[dict, dict]:
    """Analyse transcript *text* (used by the HTTP service)."""
    return analyse_cues(parse_cues(raw), ctx, class_type, materials)

def analyse(transcript_path: str, ctx: str, class_type: str = "live_class",
            materials: str = "") -> tuple[dict, dict]:
    """Analyse a transcript *file* (used by the CLI)."""
    with open(transcript_path, encoding="utf-8-sig") as fh:
        return analyse_text(fh.read(), ctx, class_type, materials)

# ───────────────────────────────────────────────────────────────────────── report
def report_markdown(result: dict, ctx: str, meta: dict) -> str:
    rc = result.get("reclass", {})
    lines = ["# Class review\n", "## Context", "```", ctx, "```\n",
             "## Overall", result.get("overall", "").strip(), "",
             "## Flags"]
    flags = result.get("flags", [])
    if not flags:
        lines.append("_None raised._")
    for f in flags:
        ev = "; ".join(f'[{e.get("timestamp","")}] “{e.get("quote","")}”' for e in f.get("evidence", []))
        lines.append(f"- **{f.get('flag')}** ({f.get('severity')}, {f.get('confidence')} confidence) — {ev}")
    review = result.get("review") or []
    if review:
        lines += ["", "## Verification (second-pass review)"]
        for r in review:
            arrow = ("dropped" if r.get("verdict") == "drop"
                     else f"{r.get('from_severity')} → {r.get('to_severity')}"
                     if r.get("verdict") == "downgrade" else "upheld")
            lines.append(f"- **{r.get('flag')}**: {arrow} — {r.get('reason','')}")
    lines += ["", "## Summary to send to the instructor", result.get("instructor_summary", "").strip(), "",
              "## Detailed feedback (internal team)", result.get("feedback", "").strip(), "",
              "## Re-class recommendation (PM only — not for the instructor)",
              f"**{str(rc.get('recommended','?')).upper()}** — {rc.get('reason','')}".strip()]
    if rc.get("deciding_flags"):
        lines.append(f"_Deciding flags: {', '.join(rc['deciding_flags'])}_")
    lines += ["", "---",
              f"_Model {meta.get('model')} · {meta.get('windows')} windows · "
              f"{meta.get('tokens_in')}+{meta.get('tokens_out')} tokens · "
              f"${meta.get('cost_usd')} · {meta.get('seconds')}s_"]
    return "\n".join(lines)

# ────────────────────────────────────────────────────────────────────────── CLI
def read_agenda(value: str) -> str:
    if value and os.path.isfile(value):
        with open(value, encoding="utf-8") as fh:
            return fh.read().strip()
    return value or "(not provided)"

def build_context(course: str, topic: str, instructor: str, rating: str, agenda: str) -> str:
    return (f"Course: {course}\nPlanned topic: {topic}\nInstructor: {instructor}\n"
            f"Learner rating: {rating}/5 (below the 4.5 line -> this class was flagged).\n"
            f"Class agenda (planned items, with expected time if known):\n{agenda}")

def main(argv=None):
    p = argparse.ArgumentParser(description="Analyse a low-rated class transcript.")
    p.add_argument("transcript")
    p.add_argument("--course", default="(unspecified)")
    p.add_argument("--topic", default="(unspecified)")
    p.add_argument("--instructor", default="(unspecified)")
    p.add_argument("--rating", default="(unspecified)")
    p.add_argument("--agenda", default="(not provided)", help="agenda text, or a path to an agenda file")
    p.add_argument("--class-type", choices=sorted(CLASS_TYPES), default="live_class",
                   help="live_class (default) or ars (assignment review session)")
    p.add_argument("--out-dir", default="outputs")
    p.add_argument("--dry-run", action="store_true", help="parse + chunk only; no API calls")
    p.add_argument("--force", action="store_true", help="re-run even if a result already exists")
    p.add_argument("--debug", action="store_true")
    a = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if a.debug else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    cues = parse_transcript(a.transcript)
    chunks = chunk_by_time(cues)
    dur = (cues[-1].end - cues[0].start) if cues else 0
    log.info("parsed %d cues | %s–%s (~%.1f h) | ~%d tokens | %d windows",
             len(cues), _seconds_to_ts(cues[0].start) if cues else "-",
             _seconds_to_ts(cues[-1].end) if cues else "-", dur / 3600, est_tokens(cues), len(chunks))
    if a.dry_run:
        for i, seg in enumerate(chunks, 1):
            print(f"  window {i:>2}: {_seconds_to_ts(seg[0].start)}–{_seconds_to_ts(seg[-1].end)}  "
                  f"({len(seg)} cues, ~{est_tokens(seg):,} tok)")
        return 0

    agenda = read_agenda(a.agenda)
    ctx = build_context(a.course, a.topic, a.instructor, a.rating, agenda)

    # idempotency: a stable id from the transcript + context
    with open(a.transcript, encoding="utf-8-sig") as fh:
        _tx = fh.read()
    run_id = hashlib.sha256((_tx + ctx).encode()).hexdigest()[:10]
    out = os.path.join(a.out_dir, run_id)
    if os.path.isdir(out) and not a.force:
        log.info("result already exists at %s (use --force to re-run)", out)
        return 0
    os.makedirs(out, exist_ok=True)

    result, meta = analyse(a.transcript, ctx, a.class_type)
    meta["run_id"] = run_id
    with open(os.path.join(out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out, "feedback.md"), "w", encoding="utf-8") as f:
        f.write(report_markdown(result, ctx, meta))
    with open(os.path.join(out, "run.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    log.info("wrote %s/{result.json, feedback.md, run.json}", out)
    print(f"\nRe-class: {str(result.get('reclass', {}).get('recommended','?')).upper()}  ·  "
          f"cost ${meta['cost_usd']}  ·  {out}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
