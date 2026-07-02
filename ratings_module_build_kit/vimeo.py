"""
vimeo.py — fetch a class recording's transcript (captions) from Vimeo.

Given a Vimeo video URL, this returns the WebVTT caption text, which feeds the engine
(`engine.parse_cues` already understands WebVTT). Used by the analysis worker so a PM can
paste a Vimeo link instead of uploading a file; manual upload stays as the fallback.

Auth: a Vimeo **Personal Access Token** with the `private` scope, issued by the account that
owns the videos (Interview Kickstart). Read from `VIMEO_ACCESS_TOKEN` at runtime — never hardcoded.

API (developer.vimeo.com):
  GET /videos/{id}/texttracks  → list tracks; each has type/language/active/link (a .vtt URL).
Empty list ⇒ the video has no captions yet ⇒ VimeoNoCaptions (worker falls back to upload).
"""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger("vimeo")

API_BASE = "https://api.vimeo.com"
RETRY_STATUS = {429, 500, 502, 503, 504}

# vimeo.com/ID, vimeo.com/ID/HASH, player.vimeo.com/video/ID, channels/x/ID,
# groups/x/videos/ID, event/N/video/ID
_URL_RE = re.compile(
    r"vimeo\.com/(?:channels/[^/]+/|groups/[^/]+/videos/|event/\d+/video/|video/)?(\d+)(?:/(\w+))?",
    re.I,
)


class VimeoError(RuntimeError):
    """Any failure talking to Vimeo."""


class VimeoAuthError(VimeoError):
    """Token missing/invalid, or no access to this (private) video."""


class VimeoNoCaptions(VimeoError):
    """The video exists but has no caption/subtitle track."""


def parse_vimeo_ref(url: str) -> tuple[str, Optional[str]]:
    """Extract (video_id, private_hash|None) from any common Vimeo URL (or a bare id)."""
    if not url or not url.strip():
        raise VimeoError("empty Vimeo URL")
    url = url.strip()
    if url.isdigit():
        return url, None
    m = _URL_RE.search(url)
    if not m:
        raise VimeoError(f"could not find a Vimeo video id in: {url!r}")
    video_id, phash = m.group(1), m.group(2)
    if not phash:
        mh = re.search(r"[?&]h=(\w+)", url)
        if mh:
            phash = mh.group(1)
    return video_id, phash


def _pick_track(tracks: list[dict]) -> Optional[dict]:
    """Choose the best caption/subtitle track: prefer active English captions, then any caption."""
    caps = [t for t in tracks if t.get("type") in ("captions", "subtitles") and t.get("link")]
    if not caps:
        return None

    def score(t: dict) -> tuple:
        lang = (t.get("language") or "").lower()
        return (
            1 if t.get("active") else 0,
            1 if lang.startswith("en") else 0,
            1 if t.get("type") == "captions" else 0,
        )

    return max(caps, key=score)


@dataclass
class VimeoConfig:
    access_token: Optional[str] = None
    timeout_s: float = 30.0
    max_retries: int = 3

    @classmethod
    def from_env(cls, env: Optional[dict] = None) -> "VimeoConfig":
        env = env or os.environ
        return cls(
            access_token=env.get("VIMEO_ACCESS_TOKEN") or None,
            timeout_s=float(env.get("VIMEO_TIMEOUT_S") or 30),
            max_retries=int(env.get("VIMEO_MAX_RETRIES") or 3),
        )


class VimeoClient:
    """Minimal Vimeo API client with retries/timeouts. Inject a transport for tests."""

    def __init__(self, config: VimeoConfig, transport: Optional[httpx.BaseTransport] = None):
        self.cfg = config
        self._client = httpx.Client(
            timeout=config.timeout_s,
            transport=transport,
            headers={"Accept": "application/vnd.vimeo.*+json;version=3.4"},
        )

    def _request(self, method: str, url: str, *, auth: bool = True) -> httpx.Response:
        headers = {}
        if auth and self.cfg.access_token:
            headers["Authorization"] = f"Bearer {self.cfg.access_token}"
        last: Optional[Exception] = None
        for attempt in range(1, self.cfg.max_retries + 1):
            try:
                r = self._client.request(method, url, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last = e
                logger.warning("vimeo %s network error (try %d/%d): %s", url, attempt, self.cfg.max_retries, e)
            else:
                if r.status_code in RETRY_STATUS:
                    last = VimeoError(f"{method} {url} → {r.status_code}")
                    logger.warning("vimeo %s → %d (try %d/%d)", url, r.status_code, attempt, self.cfg.max_retries)
                else:
                    return r
            if attempt < self.cfg.max_retries:
                time.sleep(min(2 ** attempt, 8))
        raise VimeoError(f"{method} {url} failed after {self.cfg.max_retries} tries: {last}")

    def list_text_tracks(self, video_id: str) -> list[dict]:
        r = self._request("GET", f"{API_BASE}/videos/{video_id}/texttracks")
        if r.status_code in (401, 403):
            raise VimeoAuthError(
                f"Vimeo returned {r.status_code} for video {video_id} — check the access token "
                "has the 'private' scope and the account owns this video."
            )
        if r.status_code == 404:
            raise VimeoError(f"Vimeo video {video_id} not found (check the link).")
        if not r.is_success:
            raise VimeoError(f"texttracks for {video_id} → {r.status_code}: {r.text[:200]}")
        data = r.json()
        return data.get("data", []) if isinstance(data, dict) else (data or [])

    def download_track(self, link: str) -> str:
        r = self._request("GET", link, auth=False)  # link is a pre-signed CDN URL
        if not r.is_success:
            raise VimeoError(f"downloading caption file → {r.status_code}")
        return r.text

    def fetch_transcript(self, url: str) -> dict:
        """Return {video_id, language, type, format, text} for a Vimeo URL, or raise VimeoNoCaptions."""
        video_id, _hash = parse_vimeo_ref(url)
        track = _pick_track(self.list_text_tracks(video_id))
        if not track:
            raise VimeoNoCaptions(f"Vimeo video {video_id} has no caption track — upload the transcript instead.")
        text = self.download_track(track["link"])
        if not text.strip():
            raise VimeoNoCaptions(f"Vimeo video {video_id}'s caption file was empty.")
        logger.info("fetched Vimeo transcript for %s (%s, %s chars)", video_id, track.get("language"), len(text))
        return {
            "video_id": video_id,
            "language": track.get("language"),
            "type": track.get("type"),
            "format": "vtt",
            "text": text,
        }

    def close(self) -> None:
        self._client.close()


def fetch_transcript(url: str, config: Optional[VimeoConfig] = None) -> dict:
    """Convenience wrapper: build a client from env (or the given config) and fetch."""
    cfg = config or VimeoConfig.from_env()
    if not cfg.access_token:
        raise VimeoAuthError("VIMEO_ACCESS_TOKEN is not set")
    client = VimeoClient(cfg)
    try:
        return client.fetch_transcript(url)
    finally:
        client.close()
