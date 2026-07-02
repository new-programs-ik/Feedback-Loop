"""
engine.py — production engine for the Ratings & Feedback module (v1).

Reads a class transcript (+ the class agenda) and returns three things:
  1. flags    — per-quality-dimension findings, each with a timestamp + verbatim quote
  2. feedback — the coaching message for the instructor
  3. reclass  — a PM-only recommendation on whether the class needs to be re-taught

Pipeline:  parse -> chunk by time -> extract findings per window (LLM) -> synthesise + verify + write (LLM)
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
    repair_attempts: int = 1             # re-ask once if the JSON is malformed/invalid
    price_in_per_mtok: float = 3.0       # USD, for cost reporting only
    price_out_per_mtok: float = 15.0

CFG = Config()

FLAGS = {"pace", "clarity", "structure", "examples", "correctness", "logistics", "coverage",
         "coding_time", "agenda_balance", "concept_left", "doubt_handling", "engagement",
         "learner_gap", "camera"}
SEVERITY = {"minor", "moderate", "major"}
CONFIDENCE = {"low", "medium", "high"}
RECLASS = {"yes", "no", "maybe"}

# ──────────────────────────────────────────────────────── transcript: parse + chunk
@dataclass
class Cue:
    idx: int
    start: float   # seconds
    end: float
    text: str

def _ts_to_seconds(ts: str) -> float:
    ts = ts.strip().replace(",", ".")
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)

def _seconds_to_ts(sec: float) -> str:
    h = int(sec // 3600); m = int((sec % 3600) // 60); s = int(sec % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def parse_cues(raw: str) -> list[Cue]:
    """Parse .srt or .vtt *text* into timestamped cues. Tolerant of WEBVTT headers, indices, BOM, inline tags."""
    raw = re.sub(r"^WEBVTT.*?\n\n", "", raw, flags=re.S)
    cues: list[Cue] = []
    for block in re.split(r"\n\s*\n", raw.strip()):
        lines = [l for l in block.splitlines() if l.strip()]
        ti = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if ti is None:
            continue
        start_s = lines[ti].split("-->")[0]
        end_s = lines[ti].split("-->")[1].split()[0]
        text = re.sub(r"<[^>]+>", "", " ".join(lines[ti + 1:])).strip()
        if not text:
            continue
        try:
            idx = int(lines[0])
        except ValueError:
            idx = len(cues) + 1
        cues.append(Cue(idx, _ts_to_seconds(start_s), _ts_to_seconds(end_s), text))
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
    return "\n".join(f"[{_seconds_to_ts(c.start)}] {c.text}" for c in seg)

def est_tokens(cues: list[Cue]) -> int:
    return int(sum(len(c.text.split()) for c in cues) * 1.33)

# ─────────────────────────────────────────────────────────────────────── prompts
RUBRIC = """\
You are auditing a LIVE CLASS transcript to evaluate the instructor.

WHAT THIS TRANSCRIPT IS (read carefully):
- It captures the INSTRUCTOR's speech only. Learner questions (audio or chat) are usually NOT present.
- Judge only what the instructor SAID and DID. Do NOT assume what learners asked.
- The class AGENDA (the planned items) is given in CONTEXT — use it to judge coverage and time balance.
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

[B] Instructor-side only (we cannot see learners -> lower confidence; raise only with a clear instructor-side cue):
  doubt_handling - a question the instructor ACKNOWLEDGES, and whether they answer it well, poorly, or wave it off. Never assume unseen questions.
  engagement     - interactive vs a monologue; does the instructor invite questions / check understanding ("does that make sense?").
  learner_gap    - the instructor repeats or acknowledges a learner pointing out a concept that was not covered.

[C] Needs the video, not the transcript (raise ONLY on a clear verbal cue; otherwise leave for a separate check on the recording):
  camera         - whether the instructor's camera is on. The transcript cannot show this; only flag if they say e.g. "can you see me?".

RULES:
- Every finding MUST include a verbatim quote (<= 20 words) copied exactly, plus its timestamp.
- For coding_time and agenda_balance, give the time range you estimated and the quotes that mark the start and end.
- Prefer PRECISION over completeness: if unsure, do NOT raise the flag. A false criticism is worse than a miss.
- Never invent or paraphrase quotes."""

EXTRACT_SYS = (
    "You are a precise teaching-quality auditor reviewing one segment of a live class transcript. "
    "You extract only evidence-backed findings, as strict JSON. Rules you never break: every quote is "
    "copied verbatim from the segment; you never invent or paraphrase quotes; you prefer returning "
    "nothing over raising an unsupported flag; you output JSON only — no prose, no code fences."
)

def build_extract_user(ctx: str, segment_text: str) -> str:
    return (
        f"CLASS CONTEXT\n{ctx}\n\n{RUBRIC}\n\n"
        f"TRANSCRIPT SEGMENT (timestamps in [HH:MM:SS]):\n{segment_text}\n\n"
        'Return JSON ONLY in this shape:\n'
        '{"findings":[{"flag":"pace|clarity|structure|examples|correctness|logistics|coverage|'
        'coding_time|agenda_balance|concept_left|doubt_handling|engagement|learner_gap|camera",'
        '"observation":"one specific sentence","severity":"minor|moderate|major",'
        '"evidence":[{"timestamp":"HH:MM:SS","quote":"<=20 words, verbatim from THIS segment"}],'
        '"confidence":"low|medium|high"}]}\n'
        'Only include findings with real evidence in THIS segment. If the segment is fine, return {"findings":[]}.'
    )

SYNTH_SYS = (
    "You are a senior instructional reviewer. You consolidate per-segment findings into a verified, "
    "de-duplicated assessment, then produce two SEPARATE things: coaching feedback for the instructor, "
    "and a PM-only recommendation on whether the class needs to be re-taught. You drop any finding whose "
    "quote does not clearly support its claim. The re-class recommendation is for the PM and must never "
    "appear in the instructor feedback. Output JSON only — no prose, no code fences."
)

def build_synth_user(ctx: str, findings_json: str) -> str:
    return (
        f"CLASS CONTEXT\n{ctx}\n\n"
        f"RAW FINDINGS collected from segment passes:\n{findings_json}\n\n"
        "DO THIS, IN ORDER:\n"
        "1. VERIFY: for each finding, check the quote actually supports the observation. Drop any that don't.\n"
        "2. MERGE duplicates across segments; give each surviving flag an overall severity and confidence.\n"
        "3. WRITE feedback FOR THE INSTRUCTOR (this is what the instructor receives): warm, respectful and\n"
        "   specific; strengths first, then 2-3 areas to improve, each with a concrete suggestion and the\n"
        "   timestamp(s) it refers to. Do NOT mention the numeric rating or that the class was low-rated,\n"
        "   and do NOT mention re-classing here — keep it purely coaching.\n"
        "4. RE-CLASS CALL, FOR THE PM ONLY (must NOT appear in the feedback above): decide whether this\n"
        "   class likely needs to be re-taught to the learners. Judge whether the LEARNING was delivered:\n"
        '     - "yes"   : important planned agenda content was not covered or was badly rushed, OR core\n'
        "                 concepts were explained incorrectly or so unclearly that learners likely did not get them.\n"
        '     - "no"    : the problems are about pace / style / engagement, but the content was delivered correctly.\n'
        '     - "maybe" : genuinely borderline — say what the PM should check.\n'
        "   Give a 1-2 sentence reason for the PM, citing the deciding flags/timestamps. The PM makes the final call.\n\n"
        'Return JSON ONLY:\n'
        '{"overall":"2-3 sentence summary of what likely drove the low rating",'
        '"flags":[{"flag":"...","severity":"minor|moderate|major","confidence":"low|medium|high",'
        '"evidence":[{"timestamp":"HH:MM:SS","quote":"..."}]}],'
        '"feedback":"the coaching message the INSTRUCTOR receives, referencing timestamps",'
        '"reclass":{"recommended":"yes|no|maybe","reason":"1-2 sentences for the PM only","deciding_flags":["coverage","correctness"]}}'
    )

# ──────────────────────────────────────────────────────────────── schema validation
def _check_evidence(ev: Any) -> list[str]:
    errs: list[str] = []
    if not isinstance(ev, list) or not ev:
        return ["evidence must be a non-empty list"]
    for e in ev:
        if not isinstance(e, dict) or "timestamp" not in e or "quote" not in e:
            errs.append("each evidence item needs timestamp + quote")
    return errs

def _check_flag(fobj: Any, require_observation: bool) -> list[str]:
    errs: list[str] = []
    if not isinstance(fobj, dict):
        return ["flag entry must be an object"]
    if fobj.get("flag") not in FLAGS:
        errs.append(f"unknown flag: {fobj.get('flag')!r}")
    if fobj.get("severity") not in SEVERITY:
        errs.append(f"bad severity: {fobj.get('severity')!r}")
    if fobj.get("confidence") not in CONFIDENCE:
        errs.append(f"bad confidence: {fobj.get('confidence')!r}")
    if require_observation and not isinstance(fobj.get("observation"), str):
        errs.append("missing observation")
    errs += _check_evidence(fobj.get("evidence"))
    return errs

def validate_findings(obj: Any) -> list[str]:
    if not isinstance(obj, dict) or "findings" not in obj:
        return ["top level must be an object with 'findings'"]
    if not isinstance(obj["findings"], list):
        return ["'findings' must be a list"]
    errs: list[str] = []
    for i, f in enumerate(obj["findings"]):
        errs += [f"finding[{i}]: {e}" for e in _check_flag(f, require_observation=True)]
    return errs

def validate_result(obj: Any) -> list[str]:
    if not isinstance(obj, dict):
        return ["result must be an object"]
    errs: list[str] = []
    for key in ("overall", "feedback"):
        if not isinstance(obj.get(key), str) or not obj.get(key).strip():
            errs.append(f"missing/empty '{key}'")
    if not isinstance(obj.get("flags"), list):
        errs.append("'flags' must be a list")
    else:
        for i, f in enumerate(obj["flags"]):
            errs += [f"flags[{i}]: {e}" for e in _check_flag(f, require_observation=False)]
    rc = obj.get("reclass")
    if not isinstance(rc, dict):
        errs.append("missing 'reclass' object")
    else:
        if rc.get("recommended") not in RECLASS:
            errs.append(f"reclass.recommended must be yes/no/maybe, got {rc.get('recommended')!r}")
        if not isinstance(rc.get("reason"), str) or not rc.get("reason").strip():
            errs.append("reclass.reason missing/empty")
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

def extract_findings(client, seg: list[Cue], ctx: str, usage: Usage) -> list[dict]:
    obj = _call_json(client, EXTRACT_SYS, build_extract_user(ctx, format_segment(seg)),
                     CFG.max_tokens_extract, validate_findings, usage)
    return obj.get("findings", [])

def synthesise(client, findings: list[dict], ctx: str, usage: Usage) -> dict:
    return _call_json(client, SYNTH_SYS, build_synth_user(ctx, json.dumps(findings, ensure_ascii=False, indent=2)),
                      CFG.max_tokens_synth, validate_result, usage)

def analyse_cues(cues: list[Cue], ctx: str) -> tuple[dict, dict]:
    """Run the full LLM pipeline over already-parsed cues. Returns (result, run_metadata)."""
    if not cues:
        raise ValueError("no cues to analyse")
    chunks = chunk_by_time(cues)
    client = _client()
    usage = Usage()
    t0 = time.time()
    findings: list[dict] = []
    for i, seg in enumerate(chunks, 1):
        log.info("extract %d/%d  %s–%s", i, len(chunks), _seconds_to_ts(seg[0].start), _seconds_to_ts(seg[-1].end))
        findings += extract_findings(client, seg, ctx, usage)
    log.info("synthesise %d raw findings", len(findings))
    result = synthesise(client, findings, ctx, usage)
    meta = {
        "model": CFG.model, "windows": len(chunks), "cues": len(cues), "raw_findings": len(findings),
        "tokens_in": usage.input_tokens, "tokens_out": usage.output_tokens, "llm_calls": usage.calls,
        "cost_usd": round(usage.cost_usd(), 4), "seconds": round(time.time() - t0, 1),
    }
    log.info("done  cost=$%.4f  %.1fs  calls=%d", meta["cost_usd"], meta["seconds"], meta["llm_calls"])
    return result, meta

def analyse_text(raw: str, ctx: str) -> tuple[dict, dict]:
    """Analyse transcript *text* (used by the HTTP service)."""
    return analyse_cues(parse_cues(raw), ctx)

def analyse(transcript_path: str, ctx: str) -> tuple[dict, dict]:
    """Analyse a transcript *file* (used by the CLI)."""
    with open(transcript_path, encoding="utf-8-sig") as fh:
        return analyse_text(fh.read(), ctx)

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
    lines += ["", "## Feedback for the instructor", result.get("feedback", "").strip(), "",
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

    result, meta = analyse(a.transcript, ctx)
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
