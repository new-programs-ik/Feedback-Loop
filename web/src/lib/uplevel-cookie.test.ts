import { test } from "node:test";
import assert from "node:assert/strict";
import { extractCookieHeader, parseUplevelPaste, sessionCookies } from "./uplevel-cookie.ts";

const COOKIES = "unique_visitor_id6=u1; refresh_token=eyJrefresh; csrftoken=CSRF123; sessionid=sess456; _ga=GA1; id_token=eyJid";

test("Copy as cURL (bash) with -b", () => {
  const curl = `curl 'https://uplevel.interviewkickstart.com/videos/' \\\n  -H 'accept: text/html' \\\n  -b '${COOKIES}' \\\n  -H 'user-agent: Mozilla'`;
  assert.equal(extractCookieHeader(curl), COOKIES);
  assert.deepEqual(parseUplevelPaste(curl), { ok: true, cookie: "sessionid=sess456; csrftoken=CSRF123" });
});

test("Copy as cURL (bash) with -H cookie", () => {
  const curl = `curl 'https://uplevel.interviewkickstart.com/videos/' -H 'cookie: ${COOKIES}'`;
  assert.deepEqual(parseUplevelPaste(curl), { ok: true, cookie: "sessionid=sess456; csrftoken=CSRF123" });
});

test("Copy as cURL (cmd) with ^ escapes", () => {
  const cmd = `curl ^"https://uplevel.interviewkickstart.com/videos/^" ^\n  -b ^"${COOKIES}^" ^\n  -H ^"accept: */*^"`;
  assert.deepEqual(parseUplevelPaste(cmd), { ok: true, cookie: "sessionid=sess456; csrftoken=CSRF123" });
});

test("Copy as PowerShell", () => {
  const ps = [
    '$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession',
    '$session.Cookies.Add((New-Object System.Net.Cookie("csrftoken", "CSRF123", "/", "uplevel.interviewkickstart.com")))',
    '$session.Cookies.Add((New-Object System.Net.Cookie("sessionid", "sess456", "/", "uplevel.interviewkickstart.com")))',
  ].join("\n");
  assert.deepEqual(parseUplevelPaste(ps), { ok: true, cookie: "sessionid=sess456; csrftoken=CSRF123" });
});

test("the raw request-headers view: a cookie line, then its value", () => {
  const raw = `:path\n/videos/\ncookie\n${COOKIES}\npriority\nu=0, i`;
  assert.deepEqual(parseUplevelPaste(raw), { ok: true, cookie: "sessionid=sess456; csrftoken=CSRF123" });
});

test("only the two session cookies are kept; the refresh and id tokens are dropped", () => {
  const kept = sessionCookies(COOKIES)!;
  assert.equal(kept, "sessionid=sess456; csrftoken=CSRF123");
  assert.ok(!kept.includes("refresh"));
  assert.ok(!kept.includes("id_token"));
});

test("no sessionid means not signed in, said in words", () => {
  const r = parseUplevelPaste("curl 'https://x' -b 'csrftoken=abc; _ga=1'");
  assert.equal(r.ok, false);
  assert.match((r as { error: string }).error, /not a signed-in session/);
});

test("nothing recognisable, empty, or absurdly long is refused with a reason", () => {
  for (const bad of ["", "   ", "hello world", "x".repeat(70_000)]) {
    const r = parseUplevelPaste(bad);
    assert.equal(r.ok, false, JSON.stringify(bad.slice(0, 20)));
  }
});
