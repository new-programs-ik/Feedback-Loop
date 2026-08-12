"""
video.py — the video-analysis stage: SEE the class, not just read it.

Given a class recording, this samples ~1 frame every 2-3 minutes (streaming each frame straight
from the video URL with ffmpeg — the multi-GB file is NEVER downloaded), has Claude describe each
frame as a neutral visual observer (camera on? screen shared? slides/code/notebook visible? what
slide title?), and compresses the observations into a timestamped VISUAL TRACK that the engine
merges into its context — so camera/screen/slides findings become evidence-based.

Source priority:  1) Vimeo progressive URL (self-activates when the token gains the `video_files`
scope — see docs/VIMEO_VIDEO_ACCESS.md);  2) an explicit direct link (mp4 or Google Drive);
3) none → the analysis silently continues transcript-only. `analyze_video()` NEVER raises.

Confidentiality: frames live only in memory, are sent only to the Anthropic API for this one
analysis, and are never written to disk or the database. Nothing is logged except timestamps/counts.

ffmpeg: bundled via the `imageio-ffmpeg` wheel (verified to include https/tls support), or a system
ffmpeg on PATH. `VIDEO_DISABLED=1` is the kill-switch.

CLI (local testing):  python video.py <url-or-file> [--duration N] [--probe] [--frames-only]
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import httpx

import engine as E
import materials_fetch as MF

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
    min_frames: int = 8              # fewer than this → the track would mislead; abort stage
    batch_size: int = 10             # frames per vision call
    max_tokens_observe: int = 2000

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
            import vimeo as V
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
        r = c.get(url, headers={"Range": "bytes=0-1023"})
        ctype = r.headers.get("content-type", "")
        head = r.content[:1024]
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
    interval = max(cfg.min_interval_s, min(cfg.target_interval_s, duration_s / cfg.max_frames))
    t = interval / 2
    out = []
    while t < duration_s and len(out) < cfg.max_frames:
        out.append(round(t, 1))
        t += interval
    return out


def _run_ffmpeg(args: list[str], timeout_s: float) -> bytes:
    """The single subprocess seam (tests monkeypatch THIS). Returns stdout bytes."""
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout_s)
    if proc.returncode != 0 or not proc.stdout:
        tail = proc.stderr.decode("utf-8", "ignore")[-300:]
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
    args += ["-ss", f"{t:.1f}", "-i", url, "-frames:v", "1",
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
                first_error = str(e)[:300]
            log.warning("frame at %.0fs failed (%d in a row): %s", t, consecutive, str(e)[:160])
            if consecutive >= cfg.max_consecutive_failures:
                log.warning("aborting extraction after %d consecutive failures", consecutive)
                break
    if len(frames) < cfg.min_frames:
        raise VideoStageError(
            f"could not read frames from the video ({len(frames)}/{len(times)} extracted)"
            + (f" - first failure: {first_error}" if first_error else ""))
    return frames


# ── vision pass ────────────────────────────────────────────────────────────────
FRAME_OBSERVER_SYS = (
    "You are a neutral visual observer describing sampled frames from a class recording. You "
    "describe only what is visibly present — you never evaluate, praise, or criticise. For each "
    "frame return strict JSON with: ts (the given timestamp string), camera_on (bool|null — is an "
    "instructor webcam feed visible and live), instructor_visible (bool|null), screen_shared "
    "(bool|null — is a screen/window being presented), content_type (one of "
    "slides|code|notebook|browser|doc|video|blank|other|null), heading_or_slide_title (string|null — "
    "verbatim ONLY if clearly legible; never guess), anomalies (array from: frozen, blank, "
    "tiny_text, low_light, notification_popup, wrong_window; empty if none). Use null whenever a "
    "frame is ambiguous. Output JSON only — no prose, no code fences: "
    '{"frames":[{"ts":"HH:MM:SS", ...}]}'
)


def _validate_observations(obj, expect_n: int) -> list[str]:
    if not isinstance(obj, dict) or not isinstance(obj.get("frames"), list):
        return ["top level must be an object with a 'frames' list"]
    if len(obj["frames"]) != expect_n:
        return [f"expected {expect_n} frame objects, got {len(obj['frames'])}"]
    errs = []
    for i, f in enumerate(obj["frames"]):
        if not isinstance(f, dict) or not f.get("ts"):
            errs.append(f"frames[{i}] needs a ts")
    return errs


def _call_vision(client, system: str, blocks: list[dict], max_tokens: int, usage: "E.Usage") -> str:
    """Multimodal twin of engine._call: same model/temperature/usage accounting, image blocks."""
    t = time.time()
    msg = client.messages.create(
        model=E.CFG.model, max_tokens=max_tokens, temperature=E.CFG.temperature,
        system=system, messages=[{"role": "user", "content": blocks}],
    )
    usage.input_tokens += msg.usage.input_tokens
    usage.output_tokens += msg.usage.output_tokens
    usage.calls += 1
    log.info("vision call ok  in=%d out=%d  %.1fs", msg.usage.input_tokens, msg.usage.output_tokens,
             time.time() - t)
    return "".join(b.text for b in msg.content if b.type == "text")


def observe_frames(client, frames: list[tuple[float, bytes]], class_hint: str,
                   usage: "E.Usage", cfg: VideoConfig = VCFG) -> list[dict]:
    """Describe frames in batches. A failed batch (after one repair) is dropped — partial is fine."""
    out: list[dict] = []
    for start in range(0, len(frames), cfg.batch_size):
        batch = frames[start:start + cfg.batch_size]
        blocks: list[dict] = [{"type": "text", "text":
                               f"Class: {class_hint or '(unknown)'} — describe these "
                               f"{len(batch)} sampled frames."}]
        for t, data in batch:
            blocks.append({"type": "text", "text": f"FRAME at [{E._seconds_to_ts(t)}]"})
            blocks.append({"type": "image", "source": {
                "type": "base64", "media_type": "image/jpeg",
                "data": base64.b64encode(data).decode()}})
        text = _call_vision(client, FRAME_OBSERVER_SYS, blocks, cfg.max_tokens_observe, usage)
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
                blocks.append({"type": "text", "text":
                               f"Your previous reply was invalid ({'; '.join(errs[:3])}). "
                               "Return corrected JSON only."})
                text = _call_vision(client, FRAME_OBSERVER_SYS, blocks, cfg.max_tokens_observe, usage)
        if obj and not errs:
            out.extend(obj["frames"])
        else:
            log.warning("dropping a vision batch (%d frames): %s", len(batch), "; ".join(errs[:3]))
    return out


# ── visual track (pure python — deterministic, free) ───────────────────────────
def _state_of(o: dict) -> tuple:
    return (o.get("camera_on"), o.get("screen_shared"), o.get("content_type"))


def compress_to_visual_track(observations: list[dict], n_sampled: int, interval_s: float) -> str:
    """Merge consecutive same-state observations into timestamped spans; list legible slide titles
    in order; list anomalies. Ends with an honesty line about sampling gaps."""
    if not observations:
        return ""
    lines: list[str] = ["VISUAL STATES (camera | screen | content):"]
    span_start = observations[0]
    prev = observations[0]
    def fmt_state(o: dict) -> str:
        cam = {True: "camera ON", False: "camera OFF", None: "camera ?"}[o.get("camera_on")]
        scr = {True: "screen shared", False: "no screen", None: "screen ?"}[o.get("screen_shared")]
        return f"{cam} | {scr} | {o.get('content_type') or '?'}"
    for o in observations[1:] + [None]:  # sentinel flushes the last span
        if o is not None and _state_of(o) == _state_of(prev):
            prev = o
            continue
        lines.append(f"  [{span_start.get('ts')}–{prev.get('ts')}] {fmt_state(prev)}")
        if o is not None:
            span_start = o
            prev = o
    titles, seen = [], set()
    for o in observations:
        t = (o.get("heading_or_slide_title") or "").strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            titles.append(f"  [{o.get('ts')}] {t}")
    if titles:
        lines.append("SLIDE TITLES / HEADINGS SEEN (verbatim, in order):")
        lines.extend(titles[:25])
    anomalies = [f"  [{o.get('ts')}] {', '.join(o['anomalies'])}"
                 for o in observations if o.get("anomalies")]
    if anomalies:
        lines.append("ANOMALIES:")
        lines.extend(anomalies[:15])
    lines.append(f"SAMPLED: {len(observations)}/{n_sampled} frames at ~{int(interval_s)}s intervals — "
                 "states between samples are interpolated; short events can fall between frames.")
    return "\n".join(lines)


# ── the orchestrator (the ONLY function the service calls) ─────────────────────
def analyze_video(vimeo_url: Optional[str], video_url: Optional[str],
                  duration_hint_s: Optional[float], class_hint: str = "") -> tuple[str, dict]:
    """Run the whole video stage. NEVER raises: on any failure returns ('', meta-with-video_error)
    and the analysis continues transcript-only."""
    t0 = time.time()
    meta: dict = {"video_used": False, "video_source": None, "frames_sampled": 0,
                  "frames_analyzed": 0, "video_tokens_in": 0, "video_tokens_out": 0,
                  "video_cost_usd": 0.0, "video_seconds": 0.0, "video_error": None}

    def fail(msg: str) -> tuple[str, dict]:
        meta["video_error"] = msg
        meta["video_seconds"] = round(time.time() - t0, 1)
        log.warning("video stage skipped: %s", msg)
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
        times = sample_times(float(duration))
        if not times:
            return fail("nothing to sample (video too short?)")
        meta["frames_sampled"] = len(times)
        deadline = time.monotonic() + VCFG.stage_timeout_s
        log.info("video stage: %s, %.0fs, sampling %d frames", source.kind, duration, len(times))
        frames = extract_frames(source, times, deadline)
        usage = E.Usage()
        client = E._client()
        observations = observe_frames(client, frames, class_hint, usage)
        if not observations:
            return fail("frame descriptions failed — no usable visual observations")
        interval = times[1] - times[0] if len(times) > 1 else float(duration)
        track = compress_to_visual_track(observations, len(times), interval)
        meta.update({
            "video_used": True, "frames_analyzed": len(observations),
            "video_tokens_in": usage.input_tokens, "video_tokens_out": usage.output_tokens,
            "video_cost_usd": round(usage.cost_usd(), 4),
            "video_seconds": round(time.time() - t0, 1), "video_error": None,
        })
        log.info("video stage done: %d frames analyzed, $%.4f, %.0fs",
                 len(observations), meta["video_cost_usd"], meta["video_seconds"])
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
