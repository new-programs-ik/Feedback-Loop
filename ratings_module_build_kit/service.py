"""
service.py — HTTP analysis worker around the engine (stateless: no DB writes).

The Next.js app calls this server→server to analyze one class. Given a Vimeo link OR raw
transcript text plus the class context, it fetches the transcript (if needed) and runs the
engine, returning the structured result. Persistence lives in Supabase (owned by the web app).

Run locally:   uvicorn service:app --port 8000
Deploy (free): Render / Cloud Run. Set ANTHROPIC_API_KEY (+ VIMEO_ACCESS_TOKEN) in the env.

Endpoints:
  GET  /health           -> liveness + which capabilities are configured
  POST /dry-run          -> {cues, windows, est_tokens}         (transcript text; no API key)
  POST /transcript       -> {text, video_id, language, chars}   (fetch captions from a Vimeo URL)
  POST /analyze          -> {result, meta, transcript_source}   (needs ANTHROPIC_API_KEY)

Optional shared secret: if WORKER_API_KEY is set, callers must send `Authorization: Bearer <it>`.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, model_validator

import config

config.load_env()

import engine as E  # noqa: E402  (after load_env so config is present)
import vimeo as V  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
app = FastAPI(title="Ratings Analysis Worker", version="2.0")

WORKER_API_KEY = os.environ.get("WORKER_API_KEY") or None


def require_worker_auth(authorization: Optional[str] = Header(default=None)) -> None:
    """If WORKER_API_KEY is configured, require it as a Bearer token (server→server)."""
    if not WORKER_API_KEY:
        return
    if authorization != f"Bearer {WORKER_API_KEY}":
        raise HTTPException(status_code=401, detail="invalid worker credentials")


class AnalyzeRequest(BaseModel):
    transcript: Optional[str] = None
    vimeo_url: Optional[str] = None
    course: str = "(unspecified)"
    cohort: str = "(unspecified)"
    topic: str = "(unspecified)"
    instructor: str = "(unspecified)"
    rating: str = "(unspecified)"
    num_ratings: Optional[int] = None
    agenda: str = "(not provided)"

    @model_validator(mode="after")
    def _need_a_source(self):
        has_tx = bool(self.transcript and self.transcript.strip())
        has_url = bool(self.vimeo_url and self.vimeo_url.strip())
        if not has_tx and not has_url:
            raise ValueError("provide either 'transcript' text or a 'vimeo_url'")
        return self

    def context(self) -> str:
        return E.build_context(self.course, self.topic, self.instructor, self.rating, self.agenda)


class TranscriptRequest(BaseModel):
    vimeo_url: str


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "model": E.CFG.model,
        "anthropic_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "vimeo_token": bool(os.environ.get("VIMEO_ACCESS_TOKEN")),
    }


@app.post("/dry-run")
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


@app.post("/analyze", dependencies=[Depends(require_worker_auth)])
def analyze(req: AnalyzeRequest) -> dict:
    transcript_text = req.transcript
    source = "upload"
    try:
        if not (transcript_text and transcript_text.strip()):
            info = V.fetch_transcript(req.vimeo_url)  # type: ignore[arg-type]
            transcript_text = info["text"]
            source = "vimeo"
        result, meta = E.analyse_text(transcript_text, req.context())
        return {
            "result": result,
            "meta": meta,
            "transcript_source": source,
            "transcript_chars": len(transcript_text),
            "transcript_used": transcript_text,
        }
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
