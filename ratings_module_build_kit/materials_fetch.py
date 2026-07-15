"""
materials_fetch.py — the "materials agent": fetch class materials from a LINK instead of an upload.

Big decks/notebooks blow past the web upload limit, so instead of uploading the file the PM can paste
a **link** (Google Drive / Docs / Slides / Sheets, or an internal web-manager URL, e.g. a Vercel app).
This module downloads the file(s) and returns raw (filename, bytes) pairs; the caller
(`service.extract_text`) turns those into text that feeds the analysis. Nothing is persisted.

Access model (important):
  - Files shared "Anyone with the link → Viewer" download with no credentials (the default here).
  - IK-domain-restricted files need a credential. Two supported, in priority order:
      1. GOOGLE_ACCESS_TOKEN  — a short-lived OAuth token (any IK account / service account).
      2. GOOGLE_API_KEY       — a Drive API key (works for link-shared files only).
    If neither is set we fall back to the public endpoints. On an access failure we raise a clear,
    actionable error so the UI can tell the PM exactly what to fix (share the file, or upload it).

No heavy Google SDKs — just httpx (already a dependency).
"""
from __future__ import annotations

import logging
import os
import re
from urllib.parse import urlparse, parse_qs, unquote

import httpx

log = logging.getLogger("materials_fetch")

# Guardrails (protect the worker's memory; keep latency sane).
MAX_BYTES = 40 * 1024 * 1024      # 40 MB per file
TIMEOUT_S = 45.0
MAX_LINKS = 8                     # a PM may paste a few links; cap it


class MaterialsFetchError(Exception):
    """Raised when a materials link cannot be fetched — the message is shown to the PM."""


# ─────────────────────────────────────────────────────────── link parsing
_GOOGLE_ID = r"[A-Za-z0-9_-]{20,}"


def classify(url: str) -> tuple[str, str | None]:
    """Return (kind, google_id). kind ∈ {doc, slides, sheet, drive_file, drive_folder, generic}."""
    u = url.strip()
    host = (urlparse(u).netloc or "").lower()
    if "docs.google.com" in host or "drive.google.com" in host:
        if "/document/" in u:
            m = re.search(rf"/document/d/({_GOOGLE_ID})", u)
            return ("doc", m.group(1) if m else None)
        if "/presentation/" in u:
            m = re.search(rf"/presentation/d/({_GOOGLE_ID})", u)
            return ("slides", m.group(1) if m else None)
        if "/spreadsheets/" in u:
            m = re.search(rf"/spreadsheets/d/({_GOOGLE_ID})", u)
            return ("sheet", m.group(1) if m else None)
        if "/folders/" in u:
            m = re.search(rf"/folders/({_GOOGLE_ID})", u)
            return ("drive_folder", m.group(1) if m else None)
        # /file/d/ID/..., open?id=ID, uc?id=ID
        m = re.search(rf"/file/d/({_GOOGLE_ID})", u) or re.search(rf"[?&]id=({_GOOGLE_ID})", u)
        return ("drive_file", m.group(1) if m else None)
    return ("generic", None)


# ─────────────────────────────────────────────────────────── low-level GET
def _auth_headers() -> dict:
    tok = os.environ.get("GOOGLE_ACCESS_TOKEN")
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def _looks_like_html_login(data: bytes, content_type: str) -> bool:
    """Google returns an HTML sign-in / error page when access is denied — detect that."""
    if "text/html" in content_type.lower():
        head = data[:2000].lower()
        return b"<html" in head or b"sign in" in head or b"accounts.google.com" in head
    return False


def _filename_from_headers(resp: httpx.Response, fallback: str) -> str:
    cd = resp.headers.get("content-disposition", "")
    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd)
    if m:
        return unquote(m.group(1)).strip()
    return fallback


def _sniff_ext(data: bytes) -> str:
    """Best-effort file type when the server gives no filename."""
    if data[:5] == b"%PDF-":
        return ".pdf"
    if data[:4] == b"PK\x03\x04":      # zip container → pptx/docx; default to pptx (decks are common)
        low = data[:4000].lower()
        return ".docx" if b"word/" in low else ".pptx"
    return ".txt"


def _get(url: str, headers: dict | None = None) -> httpx.Response:
    last: Exception | None = None
    for attempt in range(3):
        try:
            with httpx.Client(follow_redirects=True, timeout=TIMEOUT_S) as c:
                resp = c.get(url, headers=headers or {})
            if resp.status_code in (429, 500, 502, 503, 504):
                last = MaterialsFetchError(f"{resp.status_code} from source")
                continue
            return resp
        except httpx.HTTPError as e:
            last = e
    raise MaterialsFetchError(f"could not reach the materials link ({last})")


def _download(url: str, headers: dict, fallback_name: str) -> tuple[str, bytes]:
    resp = _get(url, headers)
    if resp.status_code == 403:
        raise MaterialsFetchError("access denied (403) — set the file to 'Anyone with the link → Viewer', "
                                  "or upload it instead")
    if resp.status_code == 404:
        raise MaterialsFetchError("materials link not found (404) — check the URL")
    if resp.status_code >= 400:
        raise MaterialsFetchError(f"materials source returned {resp.status_code}")
    data = resp.content
    ctype = resp.headers.get("content-type", "")
    if _looks_like_html_login(data, ctype):
        raise MaterialsFetchError("the link is not publicly viewable — share it 'Anyone with the link → "
                                  "Viewer' (or connect a Google account), or upload the file instead")
    if len(data) > MAX_BYTES:
        raise MaterialsFetchError(f"file is too large ({len(data)//(1024*1024)} MB > {MAX_BYTES//(1024*1024)} MB cap)")
    name = _filename_from_headers(resp, fallback_name)
    if "." not in os.path.basename(name):
        name += _sniff_ext(data)
    return name, data


# ─────────────────────────────────────────────────────────── per-kind fetch
def _fetch_one(url: str) -> tuple[str, bytes]:
    kind, gid = classify(url)
    h = _auth_headers()
    if kind == "drive_folder":
        raise MaterialsFetchError("that is a Google Drive FOLDER link — please link the specific file "
                                  "(slides / notebook / doc) instead")
    if kind in ("doc", "slides", "sheet"):
        if not gid:
            raise MaterialsFetchError("couldn't read the Google file id from the link")
        # Native Google formats must be exported to a real file we can read.
        export = {
            "doc":    (f"https://docs.google.com/document/d/{gid}/export?format=txt", "material.txt"),
            "slides": (f"https://docs.google.com/presentation/d/{gid}/export/pdf", "material.pdf"),
            "sheet":  (f"https://docs.google.com/spreadsheets/d/{gid}/export?format=csv", "material.csv"),
        }[kind]
        return _download(export[0], h, export[1])
    if kind == "drive_file":
        if not gid:
            raise MaterialsFetchError("couldn't read the Google Drive file id from the link")
        # usercontent endpoint with confirm=t bypasses the large-file virus-scan interstitial.
        url_dl = f"https://drive.usercontent.google.com/download?id={gid}&export=download&confirm=t"
        return _download(url_dl, h, "material")
    # generic (internal web-manager / Vercel / any direct file URL)
    base = os.path.basename(urlparse(url).path) or "material"
    return _download(url, {}, base)


def split_links(text: str) -> list[str]:
    """A PM may paste one or several links (newline/space/comma separated)."""
    parts = re.split(r"[\s,]+", (text or "").strip())
    return [p for p in parts if p.startswith("http")][:MAX_LINKS]


def fetch_all(materials_url: str) -> list[tuple[str, bytes]]:
    """Fetch every link in ``materials_url`` → list of (filename, bytes). Raises MaterialsFetchError
    with an actionable message if a link cannot be read."""
    links = split_links(materials_url)
    if not links:
        return []
    out: list[tuple[str, bytes]] = []
    for link in links:
        log.info("fetching materials link: %s", link)
        name, data = _fetch_one(link)
        out.append((name, data))
    return out
