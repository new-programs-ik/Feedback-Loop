"""
service.py — HTTP analysis worker around the engine (stateless: no DB writes).

The Next.js app calls this server→server to analyze one class. Given a Vimeo link OR raw
transcript text plus the class context, it fetches the transcript (if needed) and runs the
engine, returning the structured result. Persistence lives in Supabase (owned by the web app).

Run locally:   uvicorn service:app --port 8000
Deploy (free): Render / Cloud Run. Set ANTHROPIC_API_KEY (+ VIMEO_ACCESS_TOKEN) in the env.

Endpoints:
  GET  /health           -> liveness + which capabilities are configured + the scoring version
  POST /dry-run          -> {cues, windows, est_tokens}         (transcript text; no Claude call)
  POST /transcript       -> {text, video_id, language, chars}   (fetch captions from a Vimeo URL)
  POST /analyze          -> {result, meta, transcript_source}   (needs ANTHROPIC_API_KEY)
  POST /sync-ratings     -> {status: accepted}                   (one ratings sync, in the background)
  POST /sync-ratings/cron-> {status: accepted}                   (same, started by the database's
                            schedule with a single-use token instead of the key; see migration 0027)
  While a background job runs the worker pings its own /health (RENDER_EXTERNAL_URL or SELF_URL)
  so a free instance is not spun down mid-analysis.

Optional shared secret: if WORKER_API_KEY is set, callers must send `Authorization: Bearer <it>`.
"""
from __future__ import annotations

import base64
import collections
import contextlib
import io
import json as _json
import logging
import hmac
import os
import re
import threading
import time
from typing import Literal, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

import config

config.load_env()

import engine as E  # noqa: E402  (after load_env so config is present)
import materials_fetch as MF  # noqa: E402
import ratings_store as RST  # noqa: E402  (the scoring version for /health; the sync's store)
import store as ST  # noqa: E402
import video as VD  # noqa: E402
import vimeo as V  # noqa: E402

log = logging.getLogger("service")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
MAX_BODY_BYTES = 40 * 1024 * 1024        # the largest honest request is a transcript + a few decks


# ─────────────────────────── jobs that survive a restart ───────────────────────────
# The platform restarts the worker on every deploy. A job running at that moment used to die
# silently: the class sat on "analyzing" until a sweep called it failed ninety minutes later, and
# a person had to notice and press Retry. Now the stopping instance puts its running classes back
# in the queue, and every instance looks for queued classes on its own - the ones the website
# could not hand over (worker asleep or unreachable, database blip) as well as the requeued ones.
RUNNING: set[str] = set()                 # class ids with a job in this process
_RUNNING_LOCK = threading.Lock()
RESUME_EVERY_S = 90                       # how often a running worker looks for queued classes
RESUME_MIN_AGE_S = 60                     # a queued class must be this old: the website's own request has
#                                           come and gone, and a stopping instance (30 s grace) is dead
_RESUME_STOP = threading.Event()


def _resume_enabled() -> bool:
    return (os.environ.get("RESUME_SCHEDULED") or "1").strip().lower() not in ("0", "false", "no")


RESUME_STATE: dict = {"last_check": None, "last_error": None, "resumed": 0}   # shown on /health


def _resume_scheduled() -> int:
    """Run the classes the website queued that nobody took. One at a time, never while another
    job runs in this process (memory), never when the database cannot be asked. What happened
    last is on /health, because the platform's logs are not where the team looks."""
    if not _resume_enabled():
        return 0
    with _RUNNING_LOCK:
        if RUNNING:
            return 0
    RESUME_STATE["last_check"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        rows = ST.scheduled_to_resume(min_age_s=RESUME_MIN_AGE_S)
    except Exception as e:
        RESUME_STATE["last_error"] = f"looking for queued classes: {str(e).strip()[:160]}"
        log.warning("could not look for queued classes to resume; trying again later", exc_info=True)
        return 0
    done = 0
    for row in rows:
        req = AnalyzeAsyncRequest(
            class_id=row["class_id"], vimeo_url=row["vimeo_url"], course=row["course"] or "(unspecified)",
            topic=row["topic"] or "(unspecified)", instructor=row["instructor"] or "(unspecified)",
            rating=row["rating"] or "(unspecified)", agenda=row["agenda"] or "(not provided)",
            class_type="ars" if row["class_type"] == "ars" else "live_class")
        try:
            if not ST.claim_for_analysis(req.class_id):
                continue                          # someone took it in the meantime
        except ST.StoreUnavailable as e:
            RESUME_STATE["last_error"] = f"claiming {req.class_id[:8]}: {str(e).strip()[:160]}"
            break
        RESUME_STATE["last_error"] = None
        ST.record_resume(req.class_id)
        log.warning("resuming queued class %s (%s)", req.class_id, req.topic)
        _run_analysis_job(req)
        done += 1
        RESUME_STATE["resumed"] += 1
    if not rows:
        RESUME_STATE["last_error"] = None
    return done


def _resume_loop() -> None:
    delay = RESUME_MIN_AGE_S
    while not _RESUME_STOP.wait(delay):
        delay = RESUME_EVERY_S
        try:
            _resume_scheduled()
        except Exception:                             # pragma: no cover - defensive
            log.exception("the resume loop failed once; it keeps going")
        try:
            _recheck_credit_if_empty()
        except Exception:                             # pragma: no cover - defensive
            log.exception("the credit re-check failed once; it keeps going")
        try:
            _check_uplevel_if_untested()
        except Exception:                             # pragma: no cover - defensive
            log.exception("the UpLevel self-check failed once; it keeps going")


# ─────────────────────────── the Claude API credit: say "empty" only while it is ───────────────────────────
# A refusal for want of credit marks the credit 'empty' (integration_status, migration 0032) and the
# website says so on the analysis pages. Nothing else would ever clear it until someone paid for an
# analysis, so a recharged account kept showing "empty". While the state is 'empty', the worker
# re-checks with the smallest possible request (one token, a fraction of a cent) at most every
# CREDIT_RECHECK_S, and the website asks for a re-check when a person opens an analysis page.
CREDIT_RECHECK_S = 600
CREDIT_CACHE_S = 90
_CREDIT: dict = {"state": None, "at": 0.0}


def probe_credit(force: bool = False) -> str:
    """'ok', 'empty' or 'unknown' for the Claude API credit right now, from a one-token request.
    Cached for CREDIT_CACHE_S so a busy page cannot turn into a stream of requests."""
    now = time.monotonic()
    if not force and _CREDIT["state"] and now - _CREDIT["at"] < CREDIT_CACHE_S:
        return _CREDIT["state"]
    try:
        E._client().messages.create(model=E.CFG.model, max_tokens=1,
                                    messages=[{"role": "user", "content": "ok"}])
        state = "ok"
    except Exception as e:                            # noqa: BLE001 - classified below
        state = "empty" if failure_kind(e) == "no_credit" else "unknown"
        if state == "unknown":
            log.warning("credit re-check could not tell: %s", str(e)[:200])
    _CREDIT.update(state=state, at=now)
    if state == "ok":
        ST.set_integration_status("claude_credit", "ok")
    elif state == "empty":
        ST.set_integration_status("claude_credit", "empty",
                                  "The Claude API credit is empty: analyses are refused until it is recharged.")
    return state


_LAST_CREDIT_RECHECK = {"at": 0.0}


def _recheck_credit_if_empty() -> None:
    """Called from the resume loop: only when the stored state says 'empty', at most every
    CREDIT_RECHECK_S. Costs nothing when the credit is fine (no request is made)."""
    now = time.monotonic()
    if now - _LAST_CREDIT_RECHECK["at"] < CREDIT_RECHECK_S:
        return
    _LAST_CREDIT_RECHECK["at"] = now
    if ST.get_integration_state("claude_credit") == "empty":
        probe_credit(force=True)


def _requeue_running() -> int:
    with _RUNNING_LOCK:
        ids = sorted(RUNNING)
    if not ids:
        return 0
    moved = ST.requeue_running(ids)
    log.warning("stopping with %d job(s) running; %d class(es) queued again for the next instance", len(ids), moved)
    return moved


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    thread = threading.Thread(target=_resume_loop, name="resume-queued", daemon=True)
    thread.start()
    try:
        yield
    finally:
        _RESUME_STOP.set()
        _requeue_running()


app = FastAPI(title="Ratings Analysis Worker", version="2.0", lifespan=lifespan)


@app.middleware("http")
async def _refuse_oversized_bodies(request: Request, call_next):
    """A 400 MB body used to be parsed whole into a 512 MB instance, taking any running analysis
    down with it. Refuse by the declared length before reading anything."""
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
        return JSONResponse(status_code=413, content={"detail": f"request body over {MAX_BODY_BYTES // (1024 * 1024)} MB"})
    return await call_next(request)

WORKER_API_KEY = os.environ.get("WORKER_API_KEY") or None


# Set this only for a local machine that is not reachable from outside.
ALLOW_NO_AUTH = (os.environ.get("WORKER_ALLOW_NO_AUTH") or "").strip().lower() in ("1", "true", "yes")


def require_worker_auth(authorization: Optional[str] = Header(default=None)) -> None:
    """Require WORKER_API_KEY as a Bearer token.

    This used to return early when no key was configured - which is the shipped default - so a
    deployed worker with the variable unset accepted every request from anyone who found its
    address: analyses written against any class, and the Anthropic bill paid by us. Missing
    configuration now refuses the request instead of disabling the lock. Set WORKER_ALLOW_NO_AUTH=1
    to run without a key on a machine that is not reachable from the internet.
    """
    if not WORKER_API_KEY:
        if ALLOW_NO_AUTH:
            return
        raise HTTPException(
            status_code=503,
            detail="worker is not configured: set WORKER_API_KEY (or WORKER_ALLOW_NO_AUTH=1 for "
                   "a local, unreachable machine)")
    # Bytes, not str: compare_digest raises on non-ASCII text, which turned a bad header into a 500.
    if not authorization or not hmac.compare_digest(authorization.encode("utf-8", "replace"),
                                                    f"Bearer {WORKER_API_KEY}".encode("utf-8")):
        raise HTTPException(status_code=401, detail="invalid worker credentials")


class MaterialFile(BaseModel):
    filename: str = "materials.txt"
    b64: str                                     # base64-encoded file bytes


# A class transcript is a few hundred KB; 25 MB is far beyond any real one and well inside memory.
MAX_TRANSCRIPT_CHARS = 25_000_000
MAX_MATERIAL_FILES = 20


class AnalyzeRequest(BaseModel):
    transcript: Optional[str] = Field(default=None, max_length=MAX_TRANSCRIPT_CHARS)
    vimeo_url: Optional[str] = None
    course: str = "(unspecified)"
    cohort: str = "(unspecified)"
    topic: str = "(unspecified)"
    instructor: str = "(unspecified)"
    rating: str = "(unspecified)"
    num_ratings: Optional[int] = None
    agenda: str = "(not provided)"
    class_type: Literal["live_class", "ars"] = "live_class"
    materials_text: str = ""                     # pasted class-materials text (optional)
    materials_files: list[MaterialFile] = Field(default_factory=list, max_length=MAX_MATERIAL_FILES)
    materials_url: str = ""                       # link(s) to fetch instead of uploading (Drive/Docs/web-manager)
    video_url: Optional[str] = None               # direct video link (mp4/Drive) for the frames stage
    analyze_video: bool = False                   # opt-in: sample + analyse recording frames too
    # NOTE: materials and video frames are used in-memory for this analysis only and are NEVER persisted.

    @model_validator(mode="after")
    def _need_a_source(self):
        has_tx = bool(self.transcript and self.transcript.strip())
        has_url = bool(self.vimeo_url and self.vimeo_url.strip())
        if not has_tx and not has_url:
            raise ValueError("provide either 'transcript' text or a 'vimeo_url'")
        return self

    def context(self) -> str:
        base = E.build_context(self.course, self.topic, self.instructor, self.rating, self.agenda)
        label = ("Assignment Review Session (ARS) — solutions to assigned problems are reviewed and doubts cleared"
                 if self.class_type == "ars" else "Live class (weekly teaching session)")
        return base + f"\nSession type: {label}"


class AnalyzeAsyncRequest(AnalyzeRequest):
    class_id: str                                # the queued class row to write the result back to


class TranscriptRequest(BaseModel):
    vimeo_url: str


# ─────────────────────────── class-materials text extraction ───────────────────────────
# Hard caps so a huge deck can never blow the worker's memory (Render free tier = 512MB).
# Files are processed ONE AT A TIME and the raw bytes are released before the next file;
# the extracted text is capped per file; the combined text is capped again before the
# materials agent converts it to Markdown (engine.MATERIALS_MAX_CHARS).
MATERIALS_MAX_FILES = 8
MATERIALS_MAX_FILE_BYTES = 25 * 1024 * 1024      # 25 MB per file
MATERIALS_MAX_FILE_CHARS = 40_000                # extracted text per file


def _cap_text(text: str, filename: str) -> str:
    if len(text) > MATERIALS_MAX_FILE_CHARS:
        log.info("materials '%s': extracted %d chars, capped to %d",
                 filename, len(text), MATERIALS_MAX_FILE_CHARS)
        return text[:MATERIALS_MAX_FILE_CHARS] + "\n[... truncated for length ...]"
    return text


def extract_text(filename: str, data: bytes) -> str:
    """Pull plain text out of an uploaded materials file (slides / notebook / doc)."""
    name = (filename or "").lower()
    try:
        if name.endswith((".txt", ".md", ".vtt", ".srt", ".csv")):
            return data.decode("utf-8", "ignore")
        if name.endswith(".ipynb"):
            nb = _json.loads(data.decode("utf-8", "ignore"))
            parts = []
            for cell in nb.get("cells", []):
                src = "".join(cell.get("source", []))
                parts.append(f"```\n{src}\n```" if cell.get("cell_type") == "code" else src)
            return "\n\n".join(p for p in parts if p.strip())
        if name.endswith(".pdf"):
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            return "\n\n".join((page.extract_text() or "") for page in reader.pages)
        if name.endswith(".pptx"):
            from pptx import Presentation
            prs = Presentation(io.BytesIO(data))
            parts = []
            for i, slide in enumerate(prs.slides, 1):
                texts = [sh.text_frame.text for sh in slide.shapes
                         if sh.has_text_frame and sh.text_frame.text.strip()]
                if texts:
                    parts.append(f"[Slide {i}]\n" + "\n".join(texts))
            return "\n\n".join(parts)
        if name.endswith(".docx"):
            from docx import Document
            doc = Document(io.BytesIO(data))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except HTTPException:
        raise
    except Exception as e:  # corrupt file, parser error
        raise HTTPException(status_code=422, detail=f"could not read materials file '{filename}': {e}")
    raise HTTPException(status_code=422,
                        detail=f"unsupported materials file type: '{filename}' "
                               "(use .pdf, .pptx, .docx, .txt, .md or .ipynb)")


def gather_materials(req: AnalyzeRequest) -> str:
    """Combine pasted text + uploaded files + fetched link(s) into one raw materials string.
    The engine's MATERIALS AGENT then converts that to clean Markdown, and the Markdown - not
    the raw dump - is what the analysis reads. Everything here is held in memory for this
    request only and released as soon as each file's text is out — never persisted anywhere."""
    parts = []
    if req.materials_text and req.materials_text.strip():
        parts.append(_cap_text(req.materials_text.strip(), "pasted text"))
    if len(req.materials_files) > MATERIALS_MAX_FILES:
        raise HTTPException(status_code=422,
                            detail=f"too many materials files ({len(req.materials_files)}) — "
                                   f"attach at most {MATERIALS_MAX_FILES}")
    for mf in req.materials_files:
        try:
            data = base64.b64decode(mf.b64)
        except Exception:
            raise HTTPException(status_code=422, detail=f"materials file '{mf.filename}' is not valid base64")
        if len(data) > MATERIALS_MAX_FILE_BYTES:
            raise HTTPException(status_code=422,
                                detail=f"materials file '{mf.filename}' is "
                                       f"{len(data) // (1024 * 1024)}MB — the limit is "
                                       f"{MATERIALS_MAX_FILE_BYTES // (1024 * 1024)}MB per file "
                                       "(share a link instead of uploading)")
        text = extract_text(mf.filename or "materials.txt", data)
        del data                                    # release the raw bytes before the next file
        if text.strip():
            parts.append(f"=== {mf.filename} ===\n{_cap_text(text, mf.filename)}")
    # Materials-by-link: fetched from a Drive/Docs/web-manager link so big files never hit the
    # upload limit. Fetched in memory, extracted, then discarded.
    if req.materials_url and req.materials_url.strip():
        try:
            for filename, data in MF.fetch_all(req.materials_url):
                if len(data) > MATERIALS_MAX_FILE_BYTES:
                    raise HTTPException(status_code=422,
                                        detail=f"linked file '{filename}' is "
                                               f"{len(data) // (1024 * 1024)}MB — the limit is "
                                               f"{MATERIALS_MAX_FILE_BYTES // (1024 * 1024)}MB")
                text = extract_text(filename, data)
                del data
                if text.strip():
                    parts.append(f"=== {filename} (from link) ===\n{_cap_text(text, filename)}")
        except MF.MaterialsFetchError as e:
            raise HTTPException(status_code=422, detail=f"couldn't read the materials link: {e}")
    return "\n\n".join(parts)


class ReviseRequest(BaseModel):
    feedback: str                 # the current draft/edited text
    instruction: str              # the PM's plain-English change request
    context: str = ""             # optional class context for grounding
    flags_json: str = ""          # optional verified flags (grounding)
    kind: Literal["feedback", "summary"] = "feedback"   # which text: detailed feedback or send-summary


@app.get("/health")
def health() -> dict:
    # 'commit' and 'anthropic_sdk' answer "which build is actually live?" — the question we could not
    # answer during the 2026-08-27 outage, when a rebuild silently pulled a breaking SDK major.
    try:
        import anthropic
        sdk = getattr(anthropic, "__version__", "unknown")
    except Exception:                                   # pragma: no cover - import can't realistically fail
        sdk = "missing"
    return {
        "status": "ok",
        "model": E.CFG.model,
        "commit": (os.environ.get("RENDER_GIT_COMMIT") or "local")[:7],
        "anthropic_sdk": sdk,
        "anthropic_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "vimeo_token": bool(os.environ.get("VIMEO_ACCESS_TOKEN")),
        "ffmpeg": VD.ffmpeg_path() is not None,
        "video_enabled": not os.environ.get("VIDEO_DISABLED"),
        "video_max_frames": VD.VCFG.max_frames,
        "review_enabled": E.CFG.review_enabled,
        "ratings_source": "sheet",
        # v3: the queue decision is the Class Sentiment Score, computed in the database with the
        # active scoring_configs row; this is the version it is scoring with (None = none active
        # or the database could not be asked - cached, never blocks the health check for long).
        "rule_version": RST.RULE_VERSION,
        "scoring_config_version": RST.cached_config_version(),
        "sheet_configured": bool(os.environ.get("RATINGS_SHEET_ID")
                                 and (os.environ.get("GOOGLE_SA_JSON_FILE")
                                      or os.environ.get("GOOGLE_SA_JSON"))),
        "slack_configured": bool(os.environ.get("SLACK_BOT_TOKEN")),
        # Can this instance reach the database right now? "unreachable" is the answer to
        # "why does my analysis say the service could not be reached" (checked at most once a minute).
        "database": ST.ping(),
        "jobs_running": len(RUNNING),
        "resume": dict(RESUME_STATE),
    }


@app.post("/dry-run", dependencies=[Depends(require_worker_auth)])
def dry_run(req: AnalyzeRequest) -> dict:
    if not (req.transcript and req.transcript.strip()):
        raise HTTPException(status_code=422, detail="dry-run needs 'transcript' text")
    cues = E.parse_cues(req.transcript)
    if not cues:
        raise HTTPException(status_code=422, detail="no cues parsed from transcript")
    return {"cues": len(cues), "windows": len(E.chunk_by_time(cues)), "est_tokens": E.est_tokens(cues)}


@app.post("/transcript", dependencies=[Depends(require_worker_auth)])
def transcript(req: TranscriptRequest) -> dict:
    """Fetch captions from a Vimeo URL only (lets the UI preview before spending on analysis)."""
    try:
        info = V.fetch_transcript(req.vimeo_url)
        return {
            "video_id": info["video_id"],
            "language": info["language"],
            "format": info["format"],
            "chars": len(info["text"]),
            "text": info["text"],
        }
    except V.VimeoNoCaptions as e:
        raise HTTPException(status_code=422, detail=str(e))
    except V.VimeoAuthError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except V.VimeoError as e:
        raise HTTPException(status_code=502, detail=str(e))


def _run_video_stage(req: AnalyzeRequest, cues) -> tuple[str, dict]:
    """The opt-in frames stage. VD.analyze_video never raises — a broken video can never kill the
    analysis; it degrades to transcript-only with a clear video_error."""
    if not req.analyze_video:
        return "", {"video_used": False}
    duration = cues[-1].end if cues else None
    return VD.analyze_video(req.vimeo_url, req.video_url, duration, class_hint=req.topic)


def _merge_video_meta(result: dict, meta: dict, video_meta: dict) -> None:
    """Roll video tokens/cost into the meta totals (→ analyses columns) and ride the video meta
    inside result jsonb so the UI can show it."""
    meta.update(video_meta)
    meta["tokens_in"] = meta.get("tokens_in", 0) + video_meta.get("video_tokens_in", 0)
    meta["tokens_out"] = meta.get("tokens_out", 0) + video_meta.get("video_tokens_out", 0)
    meta["cost_usd"] = round(meta.get("cost_usd", 0) + video_meta.get("video_cost_usd", 0), 4)
    result["video"] = video_meta


def self_url() -> str:
    """This worker's own public address, or "" when it does not know it (local runs, tests)."""
    return (os.environ.get("SELF_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")


class KeepAwake:
    """Ping our own /health every `every_s` seconds until the work is done.

    A hosted instance with no inbound traffic is put to sleep, and a background analysis is exactly
    that: ten to fifteen minutes of silence. The ping is the traffic. It is best-effort - a failed
    ping is logged once and never touches the analysis - and it stops itself when the job ends.
    """

    def __init__(self, every_s: int = 240, timeout_s: int = 10):
        self.every_s = every_s
        self.timeout_s = timeout_s
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _loop(self, url: str) -> None:
        import httpx
        while not self._stop.wait(self.every_s):
            try:
                with httpx.Client(timeout=self.timeout_s) as client:
                    client.get(url)
            except Exception:                              # pragma: no cover - network
                log.warning("keep-awake ping failed (%s); the instance may sleep", url, exc_info=True)

    def __enter__(self) -> "KeepAwake":
        base = self_url()
        if not base:
            log.info("keep-awake: no SELF_URL/RENDER_EXTERNAL_URL, not pinging")
            return self
        self._thread = threading.Thread(target=self._loop, args=(base + "/health",),
                                        name="keep-awake", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        return None


def _run_analysis_job(req: AnalyzeAsyncRequest) -> None:
    """The background job: fetch transcript + digest materials (+ sample video) + analyze + save."""
    with _RUNNING_LOCK:
        RUNNING.add(req.class_id)
    try:
        with KeepAwake():
            transcript_text = req.transcript
            source = "upload"
            if not (transcript_text and transcript_text.strip()):
                info = V.fetch_transcript(req.vimeo_url)  # type: ignore[arg-type]
                transcript_text = info["text"]
                source = "vimeo"
            materials = gather_materials(req)
            cues = E.parse_cues(transcript_text)
            visual_track, video_meta = _run_video_stage(req, cues)
            result, meta = E.analyse_cues(cues, req.context(), req.class_type, materials,
                                          visual_track=visual_track)
            _merge_video_meta(result, meta, video_meta)
            ST.persist_analysis(req.class_id, result, meta, transcript_text, source)
            logging.info("async analysis stored for class %s (cost $%s)", req.class_id, meta.get("cost_usd"))
        ST.set_integration_status("claude_credit", "ok")          # a paid analysis proves the credit
    except Exception as e:  # noqa: BLE001 — background job, record failure so the UI can show it
        logging.exception("async analysis failed for class %s", req.class_id)
        kind = failure_kind(e)
        ST.mark_failed(req.class_id, plain_failure(e), technical=str(e), kind=kind)
        if kind == "no_credit":
            ST.set_integration_status("claude_credit", "empty",
                                      "The last analysis was refused because the Claude API credit was empty.")
    finally:
        with _RUNNING_LOCK:
            RUNNING.discard(req.class_id)


# What the review page says when a job fails: the reason in words, and what to do. The technical
# text is kept in the audit row for whoever debugs it; nobody should have to read a JSON error
# from the AI provider to learn that the account needs credit. The `kind` lets the website tell
# an empty fund apart from everything else and say so at the top of every page, because a failed
# analysis otherwise reads as a fault in the system.
NO_CREDIT_WORDS = ("The Claude API fund is empty, so the analysis could not run. This is not a fault in the "
                   "system. Please recharge the Claude API credit first (console.anthropic.com › Plans & "
                   "Billing), then press Retry.")
PLAIN_FAILURES: tuple[tuple[str, str, str], ...] = (
    ("credit balance is too low", "no_credit", NO_CREDIT_WORDS),
    ("invalid x-api-key|authentication_error|401", "bad_key",
     "The Claude API key on the worker is not accepted. Check ANTHROPIC_API_KEY on Render, then press Retry."),
    ("rate_limit|429", "rate_limited",
     "The Claude API is rate-limited right now. Press Retry in a few minutes."),
    ("overloaded|529|503 Service Unavailable", "overloaded",
     "The Claude API is overloaded right now. Press Retry in a few minutes."),
    ("no transcript|no text track|has no captions|no captions", "no_transcript",
     "This recording has no transcript on Vimeo yet. Vimeo makes one a while after upload; press Retry later, or upload a transcript file."),
    ("vimeo.*(403|404|not found|forbidden)|(403|404).*vimeo", "vimeo",
     "The recording could not be fetched from Vimeo: the link is wrong, private, or the worker's Vimeo token cannot see it."),
    ("ffmpeg", "video",
     "The video stage failed on the worker. Run it again without 'Analyze the video too'."),
)


def _match_failure(err: BaseException) -> tuple[str, str] | None:
    text = str(err)
    for pattern, kind, words in PLAIN_FAILURES:
        if re.search(pattern, text, re.I | re.S):
            return kind, words
    return None


def plain_failure(err: BaseException) -> str:
    hit = _match_failure(err)
    if hit:
        return hit[1]
    return str(err)[:400] or type(err).__name__


def failure_kind(err: BaseException) -> Optional[str]:
    hit = _match_failure(err)
    return hit[0] if hit else None


def _sweep_stuck() -> int:
    """Release classes whose job died or was never picked up, so a retry can claim them.

    The sweep used to run only at the start of a sync, and the sync was broken for a fortnight, so
    nothing ever released them. Best-effort: a failure here is logged and never blocks a job.
    """
    try:
        conn = ST._connect(attempts=1, connect_timeout=5)   # quick: a request is waiting on this
        try:
            cur = conn.cursor()
            released = RST.reset_stuck_analyses(cur)
            conn.commit()
            if released:
                log.warning("released %d class(es) stuck mid-analysis or never started", released)
            return released
        finally:
            conn.close()
    except Exception:
        log.warning("could not sweep stuck analyses; continuing", exc_info=True)
        return 0


@app.post("/analyze-async", dependencies=[Depends(require_worker_auth)])
def analyze_async(req: AnalyzeAsyncRequest, background: BackgroundTasks):
    """Start the analysis in the background and return immediately (so the web request never times
    out). The worker writes the result straight to the DB when done; the UI polls for it.

    The website marks the class `scheduled` and then calls this; taking the job moves it to
    `analyzing`. A class already in `analyzing` belongs to a running job and is refused with 409.
    This used to answer 200 for a refusal, the website took 200 as success, and - because the
    website itself had just written `analyzing` - every single request was refused. No analysis
    completed for two weeks and every review page spun forever.
    """
    if not os.environ.get("DATABASE_URL"):
        raise HTTPException(status_code=500, detail="worker has no DATABASE_URL configured for async persistence")
    _sweep_stuck()
    # One analysis per class at a time. The UI offers Retry while a job may still be running, and
    # each press used to start another full analysis: both were paid for, both wrote a row, and the
    # review page could then show one run's findings above the other run's draft.
    try:
        won = ST.claim_for_analysis(req.class_id)
    except ST.StoreUnavailable:
        raise HTTPException(status_code=503, detail="the database could not be reached; try again in a moment")
    if not won:
        return JSONResponse(status_code=409, content={"status": "already running", "class_id": req.class_id})
    background.add_task(_run_analysis_job, req)
    return {"status": "accepted", "class_id": req.class_id}


@app.post("/sync-ratings", dependencies=[Depends(require_worker_auth)])
def sync_ratings(background: BackgroundTasks, body: Optional[dict] = None) -> dict:
    """Pull the ratings sheet into class_ratings and notify handlers.
    Called hourly by pg_cron (via pg_net) and by the web app's "Sync now" button. Runs in the
    background so the caller returns immediately; progress lands in sync_runs, which the web
    reads under RLS. ratings_sync itself guards against concurrent runs."""
    if not os.environ.get("DATABASE_URL"):
        raise HTTPException(status_code=500, detail="worker has no DATABASE_URL configured")
    trigger = str((body or {}).get("trigger") or "manual")
    full = bool((body or {}).get("full"))            # every row, not only the changed ones
    import ratings_sync as RSY
    background.add_task(RSY.run_sync, trigger, full=full)
    return {"status": "accepted", "trigger": trigger, "full": full}


_TOKEN_SHAPE = re.compile(r"^[0-9a-f]{64}$")
_CRON_ATTEMPTS: collections.deque = collections.deque()
CRON_ATTEMPTS_PER_MINUTE = 30


def _cron_attempts_allowed(now: Optional[float] = None) -> bool:
    """At most CRON_ATTEMPTS_PER_MINUTE token checks a minute, process-wide. The schedule needs
    six a day; anything more is someone guessing."""
    now = time.monotonic() if now is None else now
    while _CRON_ATTEMPTS and now - _CRON_ATTEMPTS[0] > 60:
        _CRON_ATTEMPTS.popleft()
    if len(_CRON_ATTEMPTS) >= CRON_ATTEMPTS_PER_MINUTE:
        return False
    _CRON_ATTEMPTS.append(now)
    return True


@app.post("/sync-ratings/cron")
def sync_ratings_cron(background: BackgroundTasks, body: Optional[dict] = None) -> dict:
    """The scheduled sync. The database (pg_cron, migration 0027) mints a single-use token per run
    and posts it here, because it does not hold the worker's key. A token that is unknown, already
    used or older than ten minutes is refused; a good one starts exactly what "Sync now" starts."""
    if not os.environ.get("DATABASE_URL"):
        raise HTTPException(status_code=500, detail="worker has no DATABASE_URL configured")
    token = str((body or {}).get("token") or "")
    # The token is 64 hex characters (migration 0027). Anything else is refused before the
    # database is asked, and guesses are throttled: each check used to open a connection.
    if not _TOKEN_SHAPE.match(token) or not _cron_attempts_allowed():
        raise HTTPException(status_code=401, detail="no fresh scheduler token")
    if not ST.consume_sync_token(token):
        raise HTTPException(status_code=401, detail="no fresh scheduler token")
    trigger = str((body or {}).get("trigger") or "cron")
    full = bool((body or {}).get("full"))
    import ratings_sync as RSY
    background.add_task(RSY.run_sync, trigger, full=full)
    return {"status": "accepted", "trigger": trigger}



@app.post("/ai-credit/check", dependencies=[Depends(require_worker_auth)])
def ai_credit_check() -> dict:
    """The website asks this when it is about to tell a person the credit is empty: is it still?"""
    return {"credit": probe_credit()}


# ─────────────────────────── UpLevel: find a class's recording (uplevel.py) ───────────────────────────
class UplevelFindRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=300)
    instructor: str = Field(default="", max_length=200)
    class_date: Optional[str] = Field(default=None, max_length=10)     # YYYY-MM-DD
    class_type: Literal["live_class", "ars"] = "live_class"


def _match_json(m) -> dict:
    v = m.video
    return {
        "vimeo_link": v.vimeo_link, "vimeo_id": v.vimeo_id, "name": v.name, "topic": v.topic,
        "category": v.category, "class_date": v.class_date.isoformat() if v.class_date else None,
        "duration_min": round(v.duration_s / 60) if v.duration_s else None,
        "score": m.score, "reasons": m.reasons,
    }


def _keep_refreshed_uplevel_cookie(session, before: str) -> None:
    """If UpLevel handed back a new session cookie while we used it, keep the new one."""
    import uplevel as UP
    after = UP.cookie_header_of(session)
    if after and before and after != before and "sessionid=" in after:
        ST.save_integration_secret("uplevel", after)


def _uplevel_session():
    """(session, the cookie it started with) or a dict answer for the caller to return as-is."""
    import uplevel as UP
    try:
        s = UP._session()
    except UP.UplevelNotConnected as e:
        return None, {"status": "not_connected", "message": str(e), "matches": []}
    except UP.UplevelAuthError as e:
        ST.set_integration_status("uplevel", "expired", str(e))
        return None, {"status": "expired", "message": str(e), "matches": []}
    return s, UP.cookie_header_of(s)


@app.post("/uplevel/find", dependencies=[Depends(require_worker_auth)])
def uplevel_find(req: UplevelFindRequest) -> dict:
    """The recordings on UpLevel that could be this class, best first, with the reasons in words.
    Always answers with a status the website can put in a sentence; never a 500 for a login
    problem. 'none' means we looked and found nothing; 'unreachable' means we could not look."""
    import datetime as _dt
    import uplevel as UP
    date = None
    if req.class_date:
        try:
            date = _dt.date.fromisoformat(req.class_date)
        except ValueError:
            raise HTTPException(status_code=422, detail="class_date must be YYYY-MM-DD")
    session, before = _uplevel_session()
    if session is None:
        return before
    try:
        matches = UP.find_recording(topic=req.topic, instructor=req.instructor, class_date=date,
                                    kind=req.class_type, session=session)
    except UP.UplevelAuthError as e:
        ST.set_integration_status("uplevel", "expired",
                                  "UpLevel did not accept the saved session: it has expired or its owner logged out.")
        return {"status": "expired", "message": str(e), "matches": []}
    except UP.UplevelError as e:
        return {"status": "unreachable", "message": str(e), "matches": []}
    ST.set_integration_status("uplevel", "ok")
    _keep_refreshed_uplevel_cookie(session, before)
    return {"status": "ok" if matches else "none", "matches": [_match_json(m) for m in matches[:6]]}


def _run_uplevel_check() -> dict:
    """One small search with the saved session, and the result recorded (ok / expired)."""
    import uplevel as UP
    session, before = _uplevel_session()
    if session is None:
        return {"status": before["status"], "message": before["message"]}
    try:
        rows = UP.search_rows("live", limit=1, session=session)
    except UP.UplevelAuthError:
        msg = "UpLevel did not accept the saved session: it has expired or its owner logged out."
        ST.set_integration_status("uplevel", "expired", msg)
        return {"status": "expired", "message": msg}
    except UP.UplevelError as e:
        return {"status": "unreachable", "message": str(e)}
    ST.set_integration_status("uplevel", "ok", "Connected: the Videos list answered.")
    _keep_refreshed_uplevel_cookie(session, before)
    return {"status": "ok", "message": f"Connected. UpLevel answered ({len(rows)} row checked)."}


@app.post("/uplevel/check", dependencies=[Depends(require_worker_auth)])
def uplevel_check() -> dict:
    """Admin › UpLevel's 'Test connection'."""
    return _run_uplevel_check()


_LAST_UPLEVEL_SELF_CHECK = {"at": 0.0}
UPLEVEL_SELF_CHECK_S = 300


def _check_uplevel_if_untested() -> None:
    """A session an admin saved but nobody could test yet (the worker was asleep, busy or being
    deployed) is tested here, from the resume loop, so the admin page settles on its own. Only while
    the state is 'unknown', at most every five minutes: nothing is spent once it is known."""
    now = time.monotonic()
    if now - _LAST_UPLEVEL_SELF_CHECK["at"] < UPLEVEL_SELF_CHECK_S:
        return
    _LAST_UPLEVEL_SELF_CHECK["at"] = now
    if ST.get_integration_state("uplevel") == "unknown":
        result = _run_uplevel_check()
        log.info("saved UpLevel session tested on its own: %s", result.get("status"))


@app.post("/revise", dependencies=[Depends(require_worker_auth)])
def revise(req: ReviseRequest) -> dict:
    """Rewrite a feedback draft per the PM's instruction (the review-page 'fix it' agent)."""
    try:
        text, meta = E.revise_feedback(req.feedback, req.instruction, req.context, req.flags_json, req.kind)
        return {"feedback": text, "meta": meta}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logging.exception("revise failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze", dependencies=[Depends(require_worker_auth)])
def analyze(req: AnalyzeRequest) -> dict:
    transcript_text = req.transcript
    source = "upload"
    try:
        if not (transcript_text and transcript_text.strip()):
            info = V.fetch_transcript(req.vimeo_url)  # type: ignore[arg-type]
            transcript_text = info["text"]
            source = "vimeo"
        materials = gather_materials(req)
        cues = E.parse_cues(transcript_text)
        visual_track, video_meta = _run_video_stage(req, cues)
        result, meta = E.analyse_cues(cues, req.context(), req.class_type, materials,
                                      visual_track=visual_track)
        _merge_video_meta(result, meta, video_meta)
        return {
            "result": result,
            "meta": meta,
            "transcript_source": source,
            "transcript_chars": len(transcript_text),
            "transcript_used": transcript_text,
            "materials_chars": len(materials),
            "video": video_meta,
        }
    except HTTPException:
        raise  # e.g. a 422 from materials extraction — don't relabel as 500
    except V.VimeoNoCaptions as e:
        raise HTTPException(status_code=422, detail=str(e))
    except V.VimeoAuthError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except V.VimeoError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except ValueError as e:  # empty/garbled transcript, invalid model output
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:  # auth, network, etc.
        logging.exception("analyze failed")
        raise HTTPException(status_code=500, detail=str(e))
