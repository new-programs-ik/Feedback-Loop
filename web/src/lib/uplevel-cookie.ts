/** Reading the UpLevel session an admin pastes on Admin › UpLevel.
 *
 *  People copy a request from Chrome in several shapes: "Copy as cURL (bash)" (`-b '…'` or
 *  `-H 'cookie: …'`), "Copy as cURL (cmd)" (the same with `^` escapes), "Copy as PowerShell"
 *  (`New-Object System.Net.Cookie("sessionid", "…")`), or the raw request-headers view (a
 *  `cookie` line, then its value). All of them are accepted. Only `sessionid` and `csrftoken` are
 *  kept: they are all UpLevel's Videos list needs (tested 22 Sep 2026), and storing less means a
 *  stolen copy is worth less. The refresh and access tokens in the paste are thrown away. */

export const UPLEVEL_SESSION_COOKIES = ["sessionid", "csrftoken"] as const;
const MAX_PASTE = 60_000;

/** Undo cmd.exe's `^` escaping (`^"` → `"`, `^^` → `^`) when the text looks like a cmd copy. */
function unescapeCmd(text: string): string {
  if (!text.includes('^"')) return text;
  return text.replace(/\^\^/g, "\u0000").replace(/\^([\s\S])/g, "$1").replace(/\u0000/g, "^");
}

/** The cookie header string inside whatever was pasted, or null. */
export function extractCookieHeader(pasted: string): string | null {
  const text = unescapeCmd(pasted.trim());
  if (!text) return null;

  let m = text.match(/(?:^|\s)(?:-b|--cookie)\s+(['"])([\s\S]*?)\1/);
  if (m) return m[2].trim();
  m = text.match(/-H\s+(['"])cookie:\s*([\s\S]*?)\1/i);
  if (m) return m[2].trim();

  // PowerShell: $session.Cookies.Add((New-Object System.Net.Cookie("sessionid", "abc", "/", "…")))
  const ps = [...text.matchAll(/System\.Net\.Cookie\(\s*"([^"]+)"\s*,\s*"([^"]*)"/g)];
  if (ps.length) return ps.map(([, k, v]) => `${k}=${v}`).join("; ");

  const lines = text.split(/\r?\n/).map((l) => l.trim());
  for (let i = 0; i < lines.length; i++) {
    if (/^cookie:\s*\S/i.test(lines[i])) return lines[i].replace(/^cookie:\s*/i, "").trim();
    if (/^cookie$/i.test(lines[i]) && lines[i + 1]) return lines[i + 1].trim();
  }
  if (!text.includes("\n") && /(^|;\s*)sessionid=/.test(text)) return text;
  return null;
}

/** Only the session cookies, in a fixed order, or null when there is no sessionid. */
export function sessionCookies(header: string): string | null {
  const found = new Map<string, string>();
  for (const part of header.split(";")) {
    const i = part.indexOf("=");
    if (i <= 0) continue;
    const key = part.slice(0, i).trim();
    const value = part.slice(i + 1).trim();
    if ((UPLEVEL_SESSION_COOKIES as readonly string[]).includes(key) && value) found.set(key, value);
  }
  if (!found.get("sessionid")) return null;
  return UPLEVEL_SESSION_COOKIES.filter((k) => found.has(k)).map((k) => `${k}=${found.get(k)}`).join("; ");
}

export type UplevelPaste = { ok: true; cookie: string } | { ok: false; error: string };

/** What an admin pasted → the minimal cookie header we store, or the reason in words. */
export function parseUplevelPaste(pasted: string): UplevelPaste {
  if (!pasted || !pasted.trim()) return { ok: false, error: "Paste the copied request first." };
  if (pasted.length > MAX_PASTE) {
    return { ok: false, error: "That is far longer than one copied request. Copy a single request and paste it." };
  }
  const header = extractCookieHeader(pasted);
  if (!header) {
    return {
      ok: false,
      error:
        "No cookies found in what you pasted. In Chrome on UpLevel: F12 › Network › right-click any request › Copy › Copy as cURL (bash), then paste it here unchanged.",
    };
  }
  const cookie = sessionCookies(header);
  if (!cookie) {
    return {
      ok: false,
      error: "This request has no sessionid cookie, so it is not a signed-in session. Sign in to UpLevel, open the Videos page, then copy a request.",
    };
  }
  if (!/^[A-Za-z0-9_=;\s.\-:%+/]+$/.test(cookie)) {
    return { ok: false, error: "The session cookie looks damaged. Copy the request again and paste it unchanged." };
  }
  return { ok: true, cookie };
}
