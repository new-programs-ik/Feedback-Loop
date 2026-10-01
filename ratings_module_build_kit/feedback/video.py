"""
video.py — the video-analysis stage: SEE the class, not just read it.

Given a class recording, this takes ONE SCREENSHOT A MINUTE across the part of the recording where
the class is actually being spoken (first caption to last), in a single ffmpeg read of the file
that decodes key frames only and keeps nothing on disk. Screenshots identical to the one before
are not paid for twice. Claude describes each one as a neutral visual observer (camera on? screen
shared? slides/code/notebook visible? what slide title?), and the observations are compressed into
a timestamped VISUAL TRACK the engine merges into its context - so camera/screen/slides findings
rest on what was on screen minute by minute.

Until 1 Oct 2026 this took at most 40 screenshots however long the class was, by seeking to each
one separately, and looked at nothing after the fourth hour: on a four-hour class that is one
screenshot every six minutes, so a camera off for an hour could show as two frames or as none.
That sampler is kept only as the fallback when the single read cannot be done.

Source priority:  1) Vimeo progressive URL (self-activates when the token gains the `video_files`
scope — see docs/VIMEO_VIDEO_ACCESS.md);  2) an explicit direct link (mp4 or Google Drive);
3) none → the analysis silently continues transcript-only. `analyze_video()` NEVER raises.

Confidentiality: frames live only in memory, are sent only to the Anthropic API for this one
analysis, and are never written to disk or the database. Nothing is logged except timestamps/counts.

ffmpeg: bundled via the `imageio-ffmpeg` wheel (verified to include https/tls support), or a system
ffmpeg on PATH. `VIDEO_DISABLED=1` is the kill-switch.

CLI (local testing):  python -m feedback.video <url-or-file> [--duration N] [--probe] [--frames-only]
"""
from __future__ import annotations

import base64
import json
import logging
import math
import os
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from typing import Optional
from urllib.parse import urlparse

import httpx

from feedback import engine as E
from feedback import materials_fetch as MF

log = logging.getLogger("video")


# ── config ─────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class VideoConfig:
    max_frames: int = 60             # hard cap (env VIDEO_MAX_FRAMES; 40 recommended on Render free)
    target_interval_s: int = 150     # ~1 frame / 2.5 min
    min_interval_s: int = 120
    max_duration_s: int = 4 * 3600   # refuse to sample beyond 4h
    scale_width: int = 768           # -vf scale=768:-2 (≈768x432 for 16:9)
    jpeg_q: int = 4                  # ffmpeg -q:v 4 ≈ JPEG quality ~70
    per_frame_timeout_s: int = 25
    stage_timeout_s: int = 900       # overall wall-clock deadline for the whole video stage
    max_consecutive_failures: int = 5
    min_frames: int = 4              # fewer than this → the track would mislead; abort stage
    batch_size: int = 10             # frames per vision call
    max_tokens_observe: int = 6000   # ten frame objects plus the thinking that shares this budget
    # The every-minute pass (one read of the file). VIDEO_MAX_FRAMES above now only limits the
    # fallback sampler, so an old "40" on the server does not thin this out.
    dense_interval_s: int = 120      # a screenshot every two minutes (env VIDEO_DENSE_INTERVAL_S)
    dense_max_frames: int = 480      # past this many the screenshots are spaced wider, never cut short
    dense_width: int = 640           # the instructor's camera tile is clearly readable at this size
    # ONE screenshot per call. Measured on a real class against an exact answer key (1 Oct 2026):
    # 20 a call got the camera right on 84% of screenshots, 5 a call 95%, 1 a call 100% - shown
    # several at once the model gives the right description to the wrong picture.
    dense_batch_size: int = 1
    dense_parallel: int = 6          # calls in flight at once
    scan_timeout_s: int = 600        # the single read of the recording
    observe_model: str = ""          # env VIDEO_OBSERVE_MODEL; empty = the engine's own model

    @classmethod
    def from_env(cls, env: Optional[dict] = None) -> "VideoConfig":
        env = env or os.environ
        def _i(key: str, default: int) -> int:
            try:
                return int(env.get(key) or default)
            except ValueError:
                return default
        return cls(
            max_frames=_i("VIDEO_MAX_FRAMES", cls.max_frames),
            target_interval_s=_i("VIDEO_TARGET_INTERVAL_S", cls.target_interval_s),
            stage_timeout_s=_i("VIDEO_STAGE_TIMEOUT_S", cls.stage_timeout_s),
            dense_interval_s=max(10, _i("VIDEO_DENSE_INTERVAL_S", cls.dense_interval_s)),
            dense_max_frames=max(1, _i("VIDEO_DENSE_MAX_FRAMES", cls.dense_max_frames)),
            observe_model=(env.get("VIDEO_OBSERVE_MODEL") or "").strip(),
        )


VCFG = VideoConfig.from_env()


class VideoStageError(Exception):
    """Internal umbrella — analyze_video() catches it; it never escapes this module."""


# ── capability ─────────────────────────────────────────────────────────────────
_FFMPEG_CACHE: list = []   # [path|None] once resolved


def ffmpeg_path() -> Optional[str]:
    """The ffmpeg binary: imageio-ffmpeg's bundled build, else one on PATH, else None.
    VIDEO_DISABLED=1 forces None (kill-switch)."""
    if os.environ.get("VIDEO_DISABLED"):
        return None
    if _FFMPEG_CACHE:
        return _FFMPEG_CACHE[0]
    path: Optional[str] = shutil.which("ffmpeg")     # the container installs a real ffmpeg
    if not path:
        try:
            import imageio_ffmpeg                     # dev fallback (Windows box)
            path = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            path = None
    _FFMPEG_CACHE.append(path)
    return path


# ── source resolution ──────────────────────────────────────────────────────────
@dataclass
class VideoSource:
    url: str                       # direct, seekable media URL (or a local file path)
    kind: str                      # vimeo_progressive | drive | direct | local_file
    duration_s: Optional[float]


def _drive_direct_url(url: str) -> str:
    """A Google Drive share link → its direct-download form (same endpoint materials_fetch uses).
    Non-Drive URLs pass through unchanged."""
    kind, gid = MF.classify(url)
    if kind == "drive_file" and gid:
        return f"https://drive.usercontent.google.com/download?id={gid}&export=download&confirm=t"
    if kind == "drive_folder":
        raise VideoStageError("that is a Drive FOLDER link — link the video file itself")
    return url


def resolve_video_source(vimeo_url: Optional[str], video_url: Optional[str],
                         duration_hint_s: Optional[float]) -> Optional[VideoSource]:
    """Priority: Vimeo progressive (capability-probed) → explicit link (Drive rewritten) → None."""
    if vimeo_url and vimeo_url.strip():
        try:
            from recordings import vimeo as V
            src = V.get_progressive_source(vimeo_url)
        except Exception:
            src = None
        if src:
            return VideoSource(src["link"], "vimeo_progressive", src.get("duration") or duration_hint_s)
    if video_url and video_url.strip():
        u = video_url.strip()
        if not urlparse(u).scheme and os.path.isfile(u):
            return VideoSource(u, "local_file", duration_hint_s)
        direct = _drive_direct_url(u)
        return VideoSource(direct, "drive" if direct != u else "direct", duration_hint_s)
    return None


def probe_source(url: str, client: Optional[httpx.Client] = None) -> dict:
    """Check the URL is real media we can seek in: Range support (206), not an HTML login page,
    plausibly a video container. Local files pass trivially."""
    if not urlparse(url).scheme:
        return {"ranges": True, "size": os.path.getsize(url) if os.path.isfile(url) else None,
                "looks_like_media": True}
    own = client is None
    c = client or httpx.Client(follow_redirects=True, timeout=30)
    try:
        # Streamed on purpose: a host that ignores the Range header answers with the WHOLE file,
        # and a plain get() buffers all of it. On a multi-gigabyte recording that is enough to get
        # the worker killed for memory, which takes the entire analysis with it.
        with c.stream("GET", url, headers={"Range": "bytes=0-1023"}) as r:
            ctype = r.headers.get("content-type", "")
            head = next(r.iter_bytes(1024), b"")[:1024]
            status = r.status_code
            headers = dict(r.headers)
        r = type("R", (), {"status_code": status, "headers": headers, "content": head})()
        html = "text/html" in ctype.lower() and (b"<html" in head.lower() or b"sign in" in head.lower())
        ranges = r.status_code == 206
        total = None
        cr = r.headers.get("content-range", "")
        m = re.search(r"/(\d+)$", cr)
        if m:
            total = int(m.group(1))
        elif r.headers.get("content-length") and not ranges:
            total = int(r.headers["content-length"])
        looks = (head[4:8] == b"ftyp") or ctype.lower().startswith("video/") or head[:4] == b"\x1a\x45\xdf\xa3"
        return {"ranges": ranges, "size": total, "looks_like_media": looks and not html,
                "html_login": html}
    finally:
        if own:
            c.close()


# ── frame extraction (stream-seek; never download) ─────────────────────────────
def sample_times(duration_s: float, cfg: VideoConfig = VCFG) -> list[float]:
    """Evenly spaced sample points: interval = clamp(duration/max_frames, min, target).
    Starts at interval/2 (skips intros/black frames). 8776s → 58 frames at default config."""
    if duration_s <= 0:
        return []
    if duration_s > cfg.max_duration_s:
        duration_s = cfg.max_duration_s
    # The interval used to be floored at min_interval_s, so on a long class the frame budget ran
    # out before the recording did: a four-hour class was sampled only to 2h29m and the summary
    # still said "60/60 frames", while the rubric treats the visual track as ground truth about
    # what was on screen. Spread the frames we have across the whole class instead.
    interval = min(cfg.target_interval_s, duration_s / cfg.max_frames)
    interval = max(interval, cfg.min_interval_s)
    if interval * cfg.max_frames < duration_s:
        interval = duration_s / cfg.max_frames        # cover the end, at a coarser spacing
    t = interval / 2
    out = []
    while t < duration_s and len(out) < cfg.max_frames:
        out.append(round(t, 1))
        t += interval
    return out


_URLISH = re.compile(r"""(?:https?://|file://)\S+|(?<=[\s'"])/\S+/\S+""", re.I)


def redact(text: str) -> str:
    """Any URL removed. A Vimeo progressive link carries an hmac and a bearer token that open the
    whole recording, and ffmpeg prints the URL it was given straight into its error output. That
    error used to travel into the class's stored analysis and onto the review page."""
    return _URLISH.sub("<video url>", str(text))


def _run_ffmpeg(args: list[str], timeout_s: float) -> bytes:
    """The single subprocess seam (tests monkeypatch THIS). Returns stdout bytes."""
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout_s)
    if proc.returncode != 0 or not proc.stdout:
        tail = redact(proc.stderr.decode("utf-8", "ignore"))[-300:]
        raise VideoStageError(f"ffmpeg exit {proc.returncode}: {tail}")
    return proc.stdout


def extract_frame(url: str, t: float, cfg: VideoConfig = VCFG) -> bytes:
    """One JPEG frame at second `t`, streamed straight from the URL to stdout — no temp files,
    nothing on disk. ffmpeg's -ss before -i seeks over HTTP and reads only nearby bytes."""
    exe = ffmpeg_path()
    if not exe:
        raise VideoStageError("ffmpeg not available")
    args = [exe, "-hide_banner", "-loglevel", "error", "-nostdin"]
    if urlparse(url).scheme in ("http", "https"):
        args += ["-reconnect", "1", "-reconnect_streamed", "1"]
    args += ["-ss", f"{t:.1f}", "-protocol_whitelist", "file,http,https,tcp,tls,crypto", "-i", url, "-frames:v", "1",
             "-vf", f"scale={cfg.scale_width}:-2", "-q:v", str(cfg.jpeg_q),
             "-f", "image2pipe", "-c:v", "mjpeg", "pipe:1"]
    return _run_ffmpeg(args, cfg.per_frame_timeout_s)


def extract_frames(source: VideoSource, times: list[float], deadline: float,
                   cfg: VideoConfig = VCFG) -> list[tuple[float, bytes]]:
    """Sequential extraction: skip individual failures, abort after max_consecutive_failures in a
    row or at the deadline; require >= min_frames overall."""
    frames: list[tuple[float, bytes]] = []
    consecutive = 0
    first_error = ""
    for t in times:
        if time.monotonic() > deadline:
            log.warning("video stage deadline hit at %.0fs — keeping %d frames", t, len(frames))
            break
        try:
            frames.append((t, extract_frame(source.url, t, cfg)))
            consecutive = 0
        except (VideoStageError, subprocess.TimeoutExpired) as e:
            consecutive += 1
            if not first_error:
                first_error = redact(e)[:300]
            log.warning("frame at %.0fs failed (%d in a row): %s", t, consecutive, redact(e)[:160])
            if consecutive >= cfg.max_consecutive_failures:
                log.warning("aborting extraction after %d consecutive failures", consecutive)
                break
    if len(frames) < cfg.min_frames:
        if len(frames) == len(times):
            # Every frame we asked for came back; there simply were not many to ask for. Saying the
            # video could not be read sent PMs chasing a recording link that was perfectly fine.
            raise VideoStageError(
                f"this class is too short to sample usefully ({len(times)} frame(s) available, "
                f"{cfg.min_frames} needed) - the recording itself is fine")
        raise VideoStageError(
            f"could not read frames from the video ({len(frames)}/{len(times)} extracted)"
            + (f" - first failure: {first_error}" if first_error else ""))
    return frames


# ── one screenshot a minute, in a single read of the file ───────────────────────
def plan_scan(start_s: float, end_s: float, cfg: VideoConfig = VCFG) -> tuple[float, int]:
    """(seconds between screenshots, how many to expect) for the stretch start..end. One a minute,
    spaced wider only when the stretch is longer than dense_max_frames minutes."""
    span = max(0.0, float(end_s) - float(start_s))
    if span <= 0:
        return float(cfg.dense_interval_s), 0
    interval = float(cfg.dense_interval_s)
    if span / interval > cfg.dense_max_frames:
        interval = span / cfg.dense_max_frames
    return interval, int(span // interval) + 1


_JPEG_JOIN = b"\xff\xd9\xff\xd8"      # end of one image, start of the next


def take_jpegs(buf: bytearray) -> list[bytes]:
    """Every COMPLETE image at the front of `buf`, removed from it. ffmpeg writes the screenshots
    one after another on one pipe; an image is complete once the next one has begun."""
    out: list[bytes] = []
    while True:
        cut = buf.find(_JPEG_JOIN)
        if cut < 0:
            return out
        out.append(bytes(buf[:cut + 2]))
        del buf[:cut + 2]


def _stream_ffmpeg(args: list[str], timeout_s: float, on_chunk) -> tuple[int, str]:
    """The streaming subprocess seam (tests monkeypatch THIS). Feeds stdout to `on_chunk` as it
    arrives and returns (exit code, redacted tail of stderr). Killed at `timeout_s`: a stalled
    download must not hold the analysis."""
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    killer = threading.Timer(max(1.0, timeout_s), proc.kill)
    killer.daemon = True
    killer.start()
    err: list[bytes] = []
    drain = threading.Thread(target=lambda: err.append(proc.stderr.read()[-4000:]), daemon=True)
    drain.start()
    try:
        while True:
            chunk = proc.stdout.read(65536)
            if not chunk:
                break
            on_chunk(chunk)
    finally:
        proc.wait()
        killer.cancel()
        drain.join(timeout=5)
    return proc.returncode, redact(b"".join(err).decode("utf-8", "ignore"))[-300:]


def scan_frames(source: VideoSource, start_s: float, end_s: float, deadline: float,
                cfg: VideoConfig = VCFG) -> tuple[list[tuple[float, bytes]], float]:
    """A screenshot every `interval` seconds between start_s and end_s, from ONE read of the file.

    Only key frames are decoded, so a seven-hour recording is read in a few minutes and nothing
    is written to disk. Seeking to each screenshot separately (the old way) re-opens the file and
    re-reads its index every time: about four seconds a screenshot, half an hour for this many.
    Returns (frames with their real times, the interval used). Whatever was read before a failure
    or the deadline is kept; the caller reports how far it got.
    """
    exe = ffmpeg_path()
    if not exe:
        raise VideoStageError("ffmpeg not available")
    interval, expected = plan_scan(start_s, end_s, cfg)
    if not expected:
        raise VideoStageError("nothing to sample (no class time to look at)")
    args = [exe, "-hide_banner", "-loglevel", "error", "-nostdin"]
    if urlparse(source.url).scheme in ("http", "https"):
        args += ["-reconnect", "1", "-reconnect_streamed", "1"]
    args += ["-skip_frame", "nokey", "-ss", f"{start_s:.1f}", "-t", f"{end_s - start_s:.1f}",
             "-protocol_whitelist", "file,http,https,tcp,tls,crypto", "-i", source.url, "-an",
             "-vf", f"fps=1/{interval:.3f},scale={cfg.dense_width}:-2", "-q:v", str(cfg.jpeg_q + 1),
             "-f", "image2pipe", "-c:v", "mjpeg", "pipe:1"]
    buf = bytearray()
    images: list[bytes] = []

    def on_chunk(chunk: bytes) -> None:
        buf.extend(chunk)
        images.extend(take_jpegs(buf))

    budget = min(float(cfg.scan_timeout_s), max(1.0, deadline - time.monotonic()))
    code, err = _stream_ffmpeg(args, budget, on_chunk)
    if bytes(buf[:2]) == b"\xff\xd8" and bytes(buf).rstrip().endswith(b"\xff\xd9"):
        images.append(bytes(buf))                       # the last image has no successor
    if code != 0:
        log.warning("the single read of the recording stopped early (exit %s) with %d of %d "
                    "screenshots: %s", code, len(images), expected, err[:160])
        if not images:
            raise VideoStageError(f"could not read the recording in one pass (exit {code}): {err}")
    frames = [(round(start_s + i * interval, 1), data) for i, data in enumerate(images[:expected])]
    return frames, interval


def mark_repeats(frames: list[tuple[float, bytes]]) -> list[bool]:
    """True where a screenshot is byte for byte the one before it: a still slide with the camera
    off, a waiting screen. The same picture gets the same description, so it is not sent again."""
    return [i > 0 and data == frames[i - 1][1] for i, (_t, data) in enumerate(frames)]


# What a model other than the engine's costs, in USD per million tokens (input, output). Anything
# not listed is priced as the engine's model.
MODEL_PRICES = {"claude-haiku-4-5": (1.0, 5.0)}


def observe_model(cfg: VideoConfig = VCFG) -> str:
    return cfg.observe_model or E.CFG.model


def cost_usd(usage: "E.Usage", model: str) -> float:
    p_in, p_out = MODEL_PRICES.get(model, (E.CFG.price_in_per_mtok, E.CFG.price_out_per_mtok))
    return (usage.input_tokens * p_in
            + usage.cache_write_tokens * p_in * E.CFG.cache_write_mult
            + usage.cache_read_tokens * p_in * E.CFG.cache_read_mult
            + usage.output_tokens * p_out) / 1_000_000


# ── vision pass ────────────────────────────────────────────────────────────────
FRAME_OBSERVER_SYS = (
    "You are a neutral visual observer describing sampled frames from a recording of an online "
    "class. You describe only what is visibly present. You never evaluate, praise or criticise, "
    "and you never guess: null is the right answer whenever a frame does not show you something.\n"
    "Return ONE object per frame, in the SAME ORDER the frames were given. Do not include a "
    "timestamp - the times are already known and yours would only conflict with them.\n"
    "Look at each frame on its own: frames that sit next to each other often differ in one small "
    "thing, such as a webcam tile that is there in one and gone in the next.\n"
    "\n"
    "Each object has:\n"
    "  n                int        - the number on that frame's label (FRAME 1, FRAME 2, ...)\n"
    "  camera_on        bool|null  - is a live webcam picture of a person visible anywhere in the "
    "frame\n"
    "  screen_shared    bool|null  - is a screen or window being presented\n"
    "  content_type     one of slides|code|notebook|terminal|browser|whiteboard|document|video|"
    "face_only|other, or null\n"
    "  heading_or_slide_title  string|null - copied VERBATIM only if you can clearly read it. If "
    "you are reading letter shapes rather than words, use null.\n"
    "  learner_count    int|null   - how many participants are visible in a participant list, "
    "gallery or attendee count. null if no such list is on screen.\n"
    "  unanswered_chat  bool|null  - is a chat panel visible with a learner question in it that has "
    "no reply under it. null if no chat panel is visible.\n"
    "  anomalies        array, empty if none, from exactly: blank (nothing on screen), low_light "
    "(the camera image is too dark to make out), error_on_screen (a visible error message, "
    "traceback or failed cell).\n"
    "\n"
    "How to read a class recording:\n"
    "- The webcam picture is a photograph of a real person, usually head and shoulders. While a "
    "screen is being presented it is normally a small tile in a corner or along one edge, often "
    "with the person's name under it; when nothing is presented it can fill the whole frame. "
    "Either way camera_on is true. Check the corners and edges before deciding there is no tile: "
    "the tile is small and the presented screen takes up most of the frame.\n"
    "- A dark or plain frame showing only a name or initials is a participant whose camera is "
    "switched off: camera_on is false, screen_shared is false, content_type is other.\n"
    "- A small round profile picture in a browser or application toolbar is an account icon, not "
    "a camera. A photograph or illustration inside a slide or a web page is content, not a "
    "camera.\n"
    "- An empty band beside the presented screen, where a tile would sit, means no camera is "
    "showing in this frame: camera_on is false.\n"
    "- screen_shared is true when a slide, document, code, notebook, whiteboard, browser page or "
    "application window fills most of the frame. It is false when the frame shows only camera "
    "pictures or only a name on a plain background.\n"
    "\n"
    "content_type, by what fills the presented area:\n"
    "- slides: a designed slide - a title, bullet points, diagrams - from a presentation tool, "
    "including a slide deck shown inside an online whiteboard.\n"
    "- whiteboard: handwriting or drawing on a blank or ruled canvas (a note-taking app, a digital "
    "whiteboard) with no designed slide behind it.\n"
    "- notebook: a notebook with cells of code and output (Jupyter, Colab).\n"
    "- code: a code editor or IDE that is not a notebook.\n"
    "- terminal: a command line.\n"
    "- browser: a web page that is none of the above.\n"
    "- document: a text document, PDF or spreadsheet.\n"
    "- video: a video being played.\n"
    "- face_only: only camera pictures of people, nothing presented.\n"
    "- other: anything else, including a name on a plain background.\n"
    "\n"
    "heading_or_slide_title is the title of the slide, or the main heading of the page or "
    "document on screen. For a notebook or code, use the file or notebook name only if it is "
    "clearly readable. Do not use the name under a webcam tile, a browser tab label or a menu "
    "item.\n"
    "learner_count comes only from a participant list, a gallery of tiles or an attendee number "
    "on screen. One webcam tile is not a count.\n"
    "anomalies: use blank only when the whole frame is empty, low_light only for a camera picture "
    "too dark to make out a person, and error_on_screen only for an error message that is "
    "visible in the presented content.\n"
    "\n"
    "To keep the reply short, leave out any field whose value would be null or an empty array.\n"
    "Output JSON only - no prose, no code fences: "
    '{"frames":[{"n":1, "camera_on":true, "screen_shared":true, ...}]}'
)


CONTENT_TYPES = {"slides", "code", "notebook", "terminal", "browser", "whiteboard",
                 "document", "video", "face_only", "other"}


def _tri(v):
    """true / false / unknown, from whatever the model actually sent. A string "true" used to raise
    and take the entire visual track with it."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        t = v.strip().lower()
        if t in ("true", "yes", "y", "on", "1"):
            return True
        if t in ("false", "no", "n", "off", "0"):
            return False
    if isinstance(v, int) and v in (0, 1):
        return bool(v)
    return None


def clean_observation(f: dict) -> dict:
    """One frame's description with every field coerced to something the rest of the code can use."""
    ct = str(f.get("content_type") or "").strip().lower() or None
    anomalies = f.get("anomalies")
    if isinstance(anomalies, str):
        anomalies = [anomalies]
    return {
        "camera_on": _tri(f.get("camera_on")),
        "screen_shared": _tri(f.get("screen_shared")),
        "content_type": ct if ct in CONTENT_TYPES else None,
        "heading_or_slide_title": str(f.get("heading_or_slide_title") or "").strip() or None,
        "learner_count": f.get("learner_count") if isinstance(f.get("learner_count"), int) else None,
        "unanswered_chat": _tri(f.get("unanswered_chat")),
        "anomalies": [str(a) for a in anomalies if a] if isinstance(anomalies, list) else [],
    }


def _validate_observations(obj, expect_n: int) -> list[str]:
    if not isinstance(obj, dict) or not isinstance(obj.get("frames"), list):
        return ["top level must be an object with a 'frames' list"]
    if len(obj["frames"]) != expect_n:
        return [f"expected {expect_n} frame objects, got {len(obj['frames'])}"]
    errs = [f"frames[{i}] must be an object" for i, f in enumerate(obj["frames"])
            if not isinstance(f, dict)]
    if errs:
        return errs
    # Each description says which frame it is about. Shown twenty frames at once, the model gave
    # the right descriptions to the wrong frames: a camera plainly on was reported off for the
    # frame next to it, and nothing noticed. A description whose number is not its position is
    # one of those.
    return [f"frames[{i}] says it describes frame {f['n']}, but it is in position {i + 1}"
            for i, f in enumerate(obj["frames"])
            if isinstance(f.get("n"), int) and not isinstance(f.get("n"), bool) and f["n"] != i + 1]


def _call_vision(client, system: str, blocks: list[dict], max_tokens: int, usage: "E.Usage",
                 model: str | None = None) -> str:
    """Multimodal twin of engine._call: same usage accounting, image blocks.

    Describing a screenshot is looking, not reasoning, so thinking is switched off where the model
    lets us: it was most of what the 40-frame version paid for. (Haiku does not think unless asked.)
    The instructions are the same in every call of a class, so they are marked for caching: after
    the first call they are read back at a tenth of the price. (A model whose minimum cacheable
    length they do not reach simply ignores the mark.)
    """
    t = time.time()
    model = model or E.CFG.model
    extra = {} if model.startswith("claude-haiku") else {"thinking": {"type": "disabled"}}
    msg = E._create_message(          # shared SDK-drift guard (see engine._create_message)
        client,
        model=model, max_tokens=max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": blocks}], **extra,
    )
    wrote = getattr(msg.usage, "cache_creation_input_tokens", 0) or 0
    read = getattr(msg.usage, "cache_read_input_tokens", 0) or 0
    usage.input_tokens += msg.usage.input_tokens
    usage.cache_write_tokens += wrote if isinstance(wrote, int) else 0
    usage.cache_read_tokens += read if isinstance(read, int) else 0
    usage.output_tokens += msg.usage.output_tokens
    usage.calls += 1
    log.info("vision call ok  in=%d out=%d  %.1fs", msg.usage.input_tokens, msg.usage.output_tokens,
             time.time() - t)
    return "".join(b.text for b in msg.content if b.type == "text")


def observe_frames(client, frames: list[tuple[float, bytes]], class_hint: str,
                   usage: "E.Usage", cfg: VideoConfig = VCFG,
                   deadline: float | None = None, batch_size: int | None = None,
                   model: str | None = None) -> list[dict]:
    """Describe frames in batches, returning one record per frame with the frame's REAL time on it.

    A batch that cannot be read is dropped and the gap is recorded, rather than taking the class
    with it: an API error in the middle used to discard every batch already paid for.
    """
    out: list[dict] = []
    size = batch_size or cfg.batch_size
    for start in range(0, len(frames), size):
        if deadline is not None and time.monotonic() > deadline:
            log.warning("video stage deadline hit; describing %d of %d frames", len(out), len(frames))
            break
        batch = frames[start:start + size]
        blocks: list[dict] = [{"type": "text", "text":
                               f"Class: {class_hint or '(unknown)'} — describe these "
                               f"{len(batch)} sampled frames."}]
        for i, (t, data) in enumerate(batch, 1):
            blocks.append({"type": "text", "text": f"FRAME {i} at [{E._seconds_to_ts(t)}]"})
            blocks.append({"type": "image", "source": {
                "type": "base64", "media_type": "image/jpeg",
                "data": base64.b64encode(data).decode()}})
        try:
            text = _call_vision(client, FRAME_OBSERVER_SYS, blocks, cfg.max_tokens_observe, usage,
                                model)
        except Exception as e:  # noqa: BLE001  one bad batch must not cost the ones already paid for
            log.warning("vision call failed for the batch at %s: %s",
                        E._seconds_to_ts(batch[0][0]), redact(e)[:160])
            continue
        obj, errs = None, ["unparsed"]
        for attempt in range(2):  # one repair re-ask, same policy as engine._call_json
            try:
                obj = json.loads(E._strip_fences(text))
                errs = _validate_observations(obj, len(batch))
                if not errs:
                    break
            except json.JSONDecodeError as e:
                errs = [f"invalid JSON: {e}"]
            if attempt == 0:
                # Re-ask WITHOUT the images: the model only has to fix its own JSON, and resending
                # ten pictures to be told that costs as much as the original call did.
                fix = [blocks[0],
                       {"type": "text", "text":
                        f"You were shown {len(batch)} frames and your reply could not be read "
                        f"({'; '.join(errs[:3])}). Send the same answer again as valid JSON only: "
                        f"an object with a 'frames' list of exactly {len(batch)} objects, in the "
                        f"order the frames were given. No prose, no code fences."}]
                try:
                    text = _call_vision(client, FRAME_OBSERVER_SYS, fix, cfg.max_tokens_observe,
                                        usage, model)
                except Exception as e:  # noqa: BLE001
                    log.warning("vision repair failed: %s", redact(e)[:160])
                    break
        if obj and not errs:
            # The model is asked for one object per frame, in order, so the real time comes from
            # the frame we sent - not from a timestamp the model typed. Reading its `ts` back meant
            # a transposed pair produced a span running backwards, presented as ground truth.
            for (t, _data), f in zip(batch, obj["frames"]):
                one = clean_observation(f)
                one["at"] = t
                out.append(one)
        else:
            log.warning("dropping a vision batch (%d frames at %s-%s): %s", len(batch),
                        E._seconds_to_ts(batch[0][0]), E._seconds_to_ts(batch[-1][0]),
                        "; ".join(errs[:3]))
    return out


def _add_usage(total: "E.Usage", part: "E.Usage") -> None:
    for f in ("input_tokens", "output_tokens", "calls", "truncated", "cache_write_tokens",
              "cache_read_tokens"):
        setattr(total, f, getattr(total, f) + getattr(part, f))


def observe_one_per_call(client, frames: list[tuple[float, bytes]], class_hint: str,
                         usage: "E.Usage", cfg: VideoConfig = VCFG, deadline: float | None = None,
                         model: str | None = None) -> list[dict]:
    """Each screenshot in a call of its own, `dense_parallel` calls at a time.

    The first goes alone so that it writes the cached instructions; the rest then read them. A
    call that fails costs its own screenshot only, and shows as a gap in the track."""
    if not frames:
        return []
    lock = threading.Lock()

    def one(frame: tuple[float, bytes]) -> list[dict]:
        if deadline is not None and time.monotonic() > deadline:
            return []
        mine = E.Usage()
        try:
            return observe_frames(client, [frame], class_hint, mine, cfg, deadline,
                                  batch_size=1, model=model)
        finally:
            with lock:
                _add_usage(usage, mine)

    out = list(one(frames[0]))
    rest = frames[1:]
    if rest:
        with ThreadPoolExecutor(max_workers=max(1, cfg.dense_parallel)) as pool:
            for got in pool.map(one, rest):
                out.extend(got)
    return sorted(out, key=lambda o: o["at"])


def observe_once_each(client, frames: list[tuple[float, bytes]], class_hint: str,
                      usage: "E.Usage", cfg: VideoConfig = VCFG, deadline: float | None = None,
                      model: str | None = None) -> tuple[list[dict], int]:
    """Describe every DIFFERENT screenshot once and give each repeat the description of the one it
    repeats. Returns (one record per screenshot that could be described, how many were repeats)."""
    repeats = mark_repeats(frames)
    fresh = [f for f, same in zip(frames, repeats) if not same]
    if cfg.dense_batch_size <= 1:
        described = observe_one_per_call(client, fresh, class_hint, usage, cfg, deadline, model)
    else:
        described = observe_frames(client, fresh, class_hint, usage, cfg, deadline,
                                   batch_size=cfg.dense_batch_size, model=model)
    seen = {o["at"]: o for o in described}
    out: list[dict] = []
    last: dict | None = None
    reused = 0
    for (t, _data), same in zip(frames, repeats):
        if not same:
            last = seen.get(t)
            if last is not None:
                out.append(last)
        elif last is not None:
            out.append({**last, "at": t})
            reused += 1
    return out, reused


# ── visual track (pure python — deterministic, free) ───────────────────────────
def _state_of(o: dict) -> tuple:
    return (o.get("camera_on"), o.get("screen_shared"), o.get("content_type"))


def _ts(x: float) -> str:
    return f"{int(x // 3600):02d}:{int(x % 3600 // 60):02d}:{int(x % 60):02d}"


def track_is_informative(observations: list[dict], planned: int) -> bool:
    """Did we actually see enough to be worth calling a visual track?

    A list of empty objects used to pass, and an empty-but-present track flipped the rubric from
    "only flag on a clear verbal cue" to "treat this as ground truth about what was on screen" -
    and switched on two more flags. So a track that saw nothing made the analysis MORE willing to
    raise visual findings than having no video at all.
    """
    if not observations or not planned:
        return False
    known = sum(1 for o in observations
                if isinstance(o, dict)
                and o.get("camera_on") is not None and o.get("screen_shared") is not None)
    return known >= 0.6 * len(observations) and len(observations) >= 0.5 * planned


MAX_SPAN_LINES = 60     # past this the per-content detail is dropped so the track stays readable


def _span_lines(obs: list[dict], state_of, fmt, gap_s: float) -> list[str]:
    """Consecutive same-state observations merged into timestamped spans. A gap wider than `gap_s`
    means frames were never described: merging straight across it used to produce one long span
    asserting a state for minutes nobody saw."""
    lines: list[str] = []
    span_start = prev = obs[0]
    for o in list(obs[1:]) + [None]:
        broke = o is None or state_of(o) != state_of(prev)
        hole = (o is not None
                and isinstance(o.get("at"), (int, float)) and isinstance(prev.get("at"), (int, float))
                and o["at"] - prev["at"] > gap_s)
        if not broke and not hole:
            prev = o
            continue
        lines.append(f"  [{_ts(span_start.get('at', 0))}-{_ts(prev.get('at', 0))}] {fmt(prev)}")
        if hole and o is not None:
            lines.append(f"  [{_ts(prev.get('at', 0))}-{_ts(o.get('at', 0))}] NOT OBSERVED - these "
                         f"frames could not be described; nothing is known about this stretch")
        if o is not None:
            span_start = prev = o
    return lines


def _share_line(obs: list[dict], key: str, label: str, without: str,
                interval_s: float, gap_s: float) -> str | None:
    """"<label> in X of N screenshots (P%)", plus the longest unbroken stretch without it."""
    known = [o for o in obs if isinstance(o.get(key), bool)]
    if len(known) < 5:
        return None
    on = sum(1 for o in known if o[key])
    best: list[dict] = []
    run: list[dict] = []
    for o in obs:
        if o.get(key) is False and isinstance(o.get("at"), (int, float)):
            if run and o["at"] - run[-1]["at"] > gap_s:
                run = []
            run.append(o)
            if len(run) > len(best):
                best = list(run)
        else:
            run = []
    line = f"{label} in {on} of {len(known)} screenshots ({round(100 * on / len(known))}%)."
    if len(best) >= 3:
        minutes = round((best[-1]["at"] - best[0]["at"] + interval_s) / 60)
        line += (f" Longest stretch {without}: [{_ts(best[0]['at'])}-{_ts(best[-1]['at'])}], "
                 f"about {minutes} min.")
    return line


# A recording shows the instructor's camera tile only while they are the one speaking, in the
# layout most classes are recorded in: measured on a real class (1 Oct 2026) the tile came and
# went 34 times in twenty minutes and was in 78% of screenshots although the camera never went
# off. So one screenshot without it says nothing, and the old sampler - 40 screenshots, each
# "interpolated" to its neighbours - would report the camera off for a fifth of any class.
# What does mean something is the tile missing from EVERY screenshot for this long.
CAMERA_OFF_STRETCH_S = 600
CAMERA_OFF_MIN_SCREENSHOTS = 3
SCREEN_ONLY_MIN_SCREENSHOTS = 10


def camera_off_stretches(obs: list[dict], interval_s: float, gap_s: float) -> list[list[dict]]:
    """Unbroken runs of screenshots with no camera picture that last at least ten minutes (and
    at least three screenshots). A screenshot that shows the camera, one whose camera state is
    unknown, or a stretch nobody saw ends a run."""
    need = max(CAMERA_OFF_MIN_SCREENSHOTS, math.ceil(CAMERA_OFF_STRETCH_S / max(interval_s, 1.0)))
    runs: list[list[dict]] = []
    run: list[dict] = []

    def close() -> None:
        if len(run) >= need:
            runs.append(list(run))
        run.clear()

    for o in obs:
        if o.get("camera_on") is False and isinstance(o.get("at"), (int, float)):
            if run and o["at"] - run[-1]["at"] > gap_s:
                close()
            run.append(o)
        else:
            close()
    close()
    return runs


def is_screen_only(obs: list[dict]) -> bool:
    """True when a screen is shared in many screenshots and a camera picture is beside it in none:
    the recording was made without the speaker's tile, so it cannot say whether the camera was on."""
    shared = [o for o in obs if o.get("screen_shared") is True]
    return len(shared) >= SCREEN_ONLY_MIN_SCREENSHOTS and not any(o.get("camera_on") for o in shared)


def compress_to_visual_track(observations: list[dict], n_sampled: int, interval_s: float,
                            duration_s: float | None = None,
                            last_sampled_s: float | None = None, reused: int = 0) -> str:
    """Merge consecutive same-state observations into timestamped spans; say when the camera
    picture was missing for a real stretch and how much of the class a screen was shared; list
    legible slide titles in order; list anomalies. Ends with an honesty line about sampling gaps."""
    if not observations:
        return ""
    obs = sorted((o for o in observations if isinstance(o, dict)),
                 key=lambda o: o.get("at") if isinstance(o.get("at"), (int, float)) else 0.0)
    gap_s = max(interval_s * 2.5, 60)

    screen_only = is_screen_only(obs)
    stretches = [] if screen_only else camera_off_stretches(obs, interval_s, gap_s)
    truly_off = {id(o) for run in stretches for o in run}
    seen_at_all = any(o.get("camera_on") is True for o in obs)

    def camera(o: dict):
        """The camera state of the STRETCH this screenshot sits in, not of the one screenshot."""
        c = o.get("camera_on")
        if screen_only and o.get("screen_shared") is True:
            return None                                   # this recording cannot tell us
        if c is False and id(o) not in truly_off and seen_at_all:
            return True                                   # the tile comes and goes with who speaks
        return c

    def cam_scr(o: dict) -> str:
        cam = {True: "camera ON", False: "camera OFF"}.get(camera(o), "camera ?")
        scr = {True: "screen shared", False: "no screen"}.get(o.get("screen_shared"), "screen ?")
        return f"{cam} | {scr}"

    spans = _span_lines(obs, lambda o: (camera(o), o.get("screen_shared"), o.get("content_type")),
                        lambda o: f"{cam_scr(o)} | {o.get('content_type') or '?'}", gap_s)
    if len(spans) > MAX_SPAN_LINES:
        # A class that flips between slides and a notebook every few minutes: keep the camera and
        # the screen, which is what the checks turn on, and give the content as shares below.
        spans = _span_lines(obs, lambda o: (camera(o), o.get("screen_shared")), cam_scr, gap_s)
        lines: list[str] = ["VISUAL STATES (camera | screen):"]
    else:
        lines = ["VISUAL STATES (camera | screen | content):"]
    lines.extend(spans)

    known = [o for o in obs if isinstance(o.get("camera_on"), bool)]
    if screen_only:
        lines.append("CAMERA: no camera picture appears beside the shared screen in any screenshot. "
                     "This recording was made without the speaker's tile, so it CANNOT show whether "
                     "the instructor's camera was on - raise nothing about the camera from it.")
    elif len(known) >= 5:
        on = sum(1 for o in known if o["camera_on"])
        line = (f"CAMERA: a camera picture was on screen in {on} of {len(known)} screenshots "
                f"({round(100 * on / len(known))}%). A recording shows the tile only while that "
                f"person is speaking, so one screenshot without it means nothing; camera ON above "
                f"means it kept appearing through that stretch. ")
        if stretches:
            parts = [f"[{_ts(r[0]['at'])}-{_ts(r[-1]['at'])}] about "
                     f"{round((r[-1]['at'] - r[0]['at'] + interval_s) / 60)} min" for r in stretches]
            line += ("NO camera picture in ANY screenshot for 10 minutes or more: "
                     + "; ".join(parts[:8]) + ".")
        else:
            line += "There was no stretch of 10 minutes or more without a camera picture."
        lines.append(line)
    share = _share_line(obs, "screen_shared", "SCREEN: something was being shared",
                        "with nothing shared", interval_s, gap_s)
    if share:
        lines.append(share)
    kinds = [o.get("content_type") for o in obs if o.get("content_type")]
    if len(kinds) >= 5:
        top = sorted(((kinds.count(k), k) for k in set(kinds)), key=lambda x: (-x[0], x[1]))[:5]
        lines.append("ON SCREEN: " + ", ".join(f"{k} {round(100 * n / len(kinds))}%" for n, k in top) + ".")

    counts = [o.get("learner_count") for o in obs if isinstance(o.get("learner_count"), int)]
    if len(counts) >= 3:
        lines.append(f"LEARNERS VISIBLE: {counts[0]} at the start, {min(counts)} at the lowest, "
                     f"{counts[-1]} at the end.")
    if any(o.get("unanswered_chat") for o in obs):
        when = [_ts(o.get("at", 0)) for o in obs if o.get("unanswered_chat")][:6]
        lines.append("CHAT LEFT UNANSWERED on screen at: " + ", ".join(when))

    titles, seen = [], set()
    for o in obs:
        t = (o.get("heading_or_slide_title") or "").strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            titles.append(f"  [{_ts(o.get('at', 0))}] {t}")
    if titles:
        lines.append("SLIDE TITLES / HEADINGS SEEN (verbatim, in order):")
        lines.extend(titles[:25])
        if len(titles) > 25:
            lines.append(f"  ...and {len(titles) - 25} more headings not listed - this list is NOT "
                         f"complete, so do not conclude a topic never appeared from its absence here.")
    anomalies = [f"  [{_ts(o.get('at', 0))}] {', '.join(o['anomalies'])}"
                 for o in obs if o.get("anomalies")]
    if anomalies:
        lines.append("ANOMALIES:")
        lines.extend(anomalies[:15])
        if len(anomalies) > 15:
            lines.append(f"  ...and {len(anomalies) - 15} more not listed.")
    covered = ""
    if duration_s and last_sampled_s is not None and duration_s - last_sampled_s > max(120, interval_s * 2):
        covered = (f" SAMPLING STOPPED AT {_ts(last_sampled_s)} of a {_ts(duration_s)} recording — "
                   f"NOTHING after that point was looked at, so do not treat the visual track as "
                   f"evidence about it.")
    same = (f" {reused} of them showed exactly the picture before them and carry its description."
            if reused else "")
    lines.append(f"SAMPLED: {len(observations)}/{n_sampled} frames at ~{int(interval_s)}s intervals — "
                 "states between samples are interpolated; short events can fall between frames."
                 + same + covered)
    return "\n".join(lines)


# ── the orchestrator (the ONLY function the service calls) ─────────────────────
def analyze_video(vimeo_url: Optional[str], video_url: Optional[str],
                  duration_hint_s: Optional[float], class_hint: str = "",
                  start_hint_s: Optional[float] = None) -> tuple[str, dict]:
    """Run the whole video stage. NEVER raises: on any failure returns ('', meta-with-video_error)
    and the analysis continues transcript-only.

    `start_hint_s` / `duration_hint_s` are the first and last caption times. A recording often
    runs long before the class starts and after it ends (one was 7.1 h for a 5.7 h class): that
    dead time is not looked at, so a waiting screen is neither paid for nor counted as "camera off".
    """
    t0 = time.time()
    model = observe_model()
    meta: dict = {"video_used": False, "video_source": None, "frames_sampled": 0,
                  "frames_extracted": 0, "frames_analyzed": 0, "frames_reused": 0,
                  "video_tokens_in": 0, "video_tokens_out": 0,
                  "video_cost_usd": 0.0, "video_seconds": 0.0, "video_error": None,
                  "video_covered_to": None, "video_interval_s": None, "video_mode": None,
                  "video_model": model}
    # Created here, not inside the try, so that a failure halfway still reports what it spent.
    # Every failure path used to report $0 for calls that had already been billed.
    usage = E.Usage()

    def fail(msg: str) -> tuple[str, dict]:
        meta["video_error"] = redact(msg)[:400]
        meta["video_seconds"] = round(time.time() - t0, 1)
        meta["video_tokens_in"] = usage.input_tokens
        meta["video_tokens_out"] = usage.output_tokens
        meta["video_cost_usd"] = round(cost_usd(usage, model), 4)
        log.warning("video stage skipped after $%.4f: %s", meta["video_cost_usd"], redact(msg)[:200])
        return "", meta

    try:
        if os.environ.get("VIDEO_DISABLED"):
            return fail("video analysis is disabled on this deployment (VIDEO_DISABLED)")
        if not ffmpeg_path():
            return fail("ffmpeg is not available on this worker")
        source = resolve_video_source(vimeo_url, video_url, duration_hint_s)
        if source is None:
            return fail("no playable video source (Vimeo token lacks the video_files scope and no "
                        "direct video link was given — see docs/VIMEO_VIDEO_ACCESS.md)")
        meta["video_source"] = source.kind
        probe = probe_source(source.url)
        if probe.get("html_login"):
            return fail("the video link is not publicly downloadable — share it 'Anyone with the "
                        "link' or use a direct mp4 link")
        if not probe.get("ranges"):
            return fail("the video host does not support byte-range requests (streaming frames "
                        "would require downloading the whole file)")
        if not probe.get("looks_like_media"):
            return fail("the link does not look like a video file")
        duration = source.duration_s or duration_hint_s
        if not duration or duration <= 0:
            return fail("video duration unknown — cannot plan frame sampling")
        # The stretch to look at: a minute either side of the spoken class, inside the recording.
        start = max(0.0, float(start_hint_s) - 60) if start_hint_s and start_hint_s > 0 else 0.0
        end = float(duration)
        if duration_hint_s and duration_hint_s > 0:
            end = min(end, float(duration_hint_s) + 60)
        if end - start < 60:
            start, end = 0.0, float(duration)
        deadline = time.monotonic() + VCFG.stage_timeout_s
        try:
            interval, planned = plan_scan(start, end)
            log.info("video stage: %s, looking at %s-%s, one screenshot every %.0fs (%d planned)",
                     source.kind, _ts(start), _ts(end), interval, planned)
            frames, interval = scan_frames(source, start, end, deadline)
            if len(frames) < VCFG.min_frames:
                raise VideoStageError(f"the single read gave {len(frames)} screenshot(s)")
            meta["video_mode"] = "every_minute"
        except (VideoStageError, OSError, subprocess.SubprocessError) as e:
            # The old sampler: far fewer screenshots, each fetched by seeking. Better than nothing
            # when a host will not serve the file in one read.
            log.warning("single read failed (%s) - falling back to seeking", redact(e)[:160])
            wide = replace(VCFG, max_duration_s=max(VCFG.max_duration_s, int(end - start) + 1))
            times = [round(start + t, 1) for t in sample_times(end - start, wide)]
            if not times:
                return fail("nothing to sample (video too short?)")
            planned = len(times)
            frames = extract_frames(source, times, deadline)
            interval = times[1] - times[0] if len(times) > 1 else end - start
            meta["video_mode"] = "seek"
        meta["frames_sampled"] = planned
        meta["frames_extracted"] = len(frames)
        meta["video_interval_s"] = round(interval)
        client = E._client()
        observations, reused = observe_once_each(client, frames, class_hint, usage,
                                                 deadline=deadline, model=model)
        if not observations:
            return fail("frame descriptions failed — no usable visual observations")
        if not track_is_informative(observations, planned):
            # Better no visual track than an empty one: an empty one still told the analysis to
            # treat the screen as observed fact and switched on two more flags.
            return fail(f"the recording was sampled but too little could be made out "
                        f"({len(observations)} of {planned} frames described) — treating this "
                        f"class as transcript-only")
        # The LAST FRAME ACTUALLY TAKEN, not the last one planned. The deadline can stop extraction
        # early, and using the plan meant the coverage warning stayed silent in exactly that case.
        covered_to = frames[-1][0] if frames else None
        track = compress_to_visual_track(observations, planned, interval, duration_s=end,
                                         last_sampled_s=covered_to, reused=reused)
        meta.update({
            "video_used": True, "frames_analyzed": len(observations), "frames_reused": reused,
            "video_covered_to": round(covered_to, 1) if covered_to is not None else None,
            "video_tokens_in": usage.input_tokens, "video_tokens_out": usage.output_tokens,
            "video_cost_usd": round(cost_usd(usage, model), 4),
            "video_seconds": round(time.time() - t0, 1), "video_error": None,
        })
        log.info("video stage done: %d screenshots (%d repeats), $%.4f, %.0fs",
                 len(observations), reused, meta["video_cost_usd"], meta["video_seconds"])
        return track, meta
    except VideoStageError as e:
        return fail(str(e))
    except Exception as e:  # noqa: BLE001 — the video stage must never kill the analysis
        log.exception("unexpected video-stage failure")
        return fail(f"unexpected video-stage error: {e}")


# ── CLI for live local testing ─────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    import config as _config
    _config.load_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    p = argparse.ArgumentParser(description="Test the video-analysis stage on one URL/file.")
    p.add_argument("url", help="video URL (Vimeo/Drive/direct) or a local file path")
    p.add_argument("--duration", type=float, default=None, help="duration in seconds (else probed)")
    p.add_argument("--probe", action="store_true", help="only probe the source and exit")
    p.add_argument("--frames-only", action="store_true", help="extract frames, skip the vision pass")
    a = p.parse_args()

    src = resolve_video_source(a.url if "vimeo.com" in a.url else None,
                               a.url, a.duration)
    print("source:", src)
    if src is None:
        raise SystemExit("no source resolved")
    print("probe:", probe_source(src.url))
    if a.probe:
        raise SystemExit(0)
    dur = src.duration_s or a.duration
    if not dur:
        raise SystemExit("pass --duration (seconds)")
    times = sample_times(float(dur))
    print(f"sample plan: {len(times)} frames, first at {times[0]}s, last at {times[-1]}s")
    if a.frames_only:
        frames = extract_frames(src, times[:6], time.monotonic() + 120)
        print(f"extracted {len(frames)} test frames; sizes:", [len(b) for _, b in frames])
        raise SystemExit(0)
    is_vimeo = "vimeo.com" in a.url.lower()
    track, meta = analyze_video(a.url if is_vimeo else None,
                                None if is_vimeo else a.url, dur, class_hint="CLI test")
    print("\n=== VISUAL TRACK ===\n" + (track or "(empty)"))
    print("\nmeta:", json.dumps(meta, indent=2))
