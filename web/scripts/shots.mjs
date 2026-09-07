/**
 * shots.mjs — full-page screenshots of the app in light and dark, for design review.
 *
 *   SHOT_EMAIL=… SHOT_PASSWORD=… node scripts/shots.mjs [baseUrl] [outDir] [path ...]
 *
 * Logs in through the real sign-in form, then visits each path. Credentials come from the
 * environment only — never from this file. Needs puppeteer-core + a local Chrome.
 * SHOT_WIDTH (default 1440; 375 for the phone pass) and SHOT_THEMES ("light,dark" by default)
 * narrow a run.
 */
import puppeteer from "puppeteer-core";
import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const CHROME = process.env.CHROME || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const [, , baseArg, outArg, ...paths] = process.argv;
const BASE = baseArg || "http://localhost:3000";
const OUT = outArg || "shots";
const WIDTH = Number(process.env.SHOT_WIDTH || 1440);
const THEMES = (process.env.SHOT_THEMES || "light,dark").split(",").map((t) => t.trim()).filter(Boolean);
const PATHS = paths.length
  ? paths
  : [
      "/team",
      "/team/queue",
      "/team/instructors",
      "/team/reports",
      "/team/insights",
      "/c/applied-agentic-ai/overview",
      "/c/applied-agentic-ai/queue",
      "/c/applied-agentic-ai/classes",
      "/c/applied-agentic-ai/instructors",
      "/c/applied-agentic-ai/cohorts",
      "/c/applied-agentic-ai/modules",
      "/c/applied-agentic-ai/feedback",
      "/c/applied-agentic-ai/reports",
      "/c/applied-agentic-ai/settings",
      "/admin/scoring",
      "/admin/identity",
      "/admin/people",
      "/admin/sync",
      "/tools/what-if",
    ];
// The login comes from the environment, or from SHOT_EMAIL / SHOT_PASSWORD lines in web/.env.local
// (gitignored) — never from this file or the command line.
function fromEnvLocal(key) {
  try {
    const txt = readFileSync(new URL("../.env.local", import.meta.url), "utf8");
    const line = txt.split(/\r?\n/).find((l) => l.startsWith(`${key}=`));
    return line ? line.slice(key.length + 1).trim().replace(/^["']|["']$/g, "") : undefined;
  } catch {
    return undefined;
  }
}
const email = process.env.SHOT_EMAIL || fromEnvLocal("SHOT_EMAIL");
const password = process.env.SHOT_PASSWORD || fromEnvLocal("SHOT_PASSWORD");
if (!email || !password) {
  console.error("set SHOT_EMAIL and SHOT_PASSWORD (environment, or two lines in web/.env.local)");
  process.exit(1);
}
mkdirSync(OUT, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: "new",
  args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--no-sandbox"],
});
const page = await browser.newPage();
await page.setViewport({ width: WIDTH, height: WIDTH < 800 ? 812 : 900, deviceScaleFactor: 1, isMobile: WIDTH < 800, hasTouch: WIDTH < 800 });

// login page first (also a screenshot target), then the form
await page.goto(`${BASE}/login`, { waitUntil: "networkidle0" });
await page.screenshot({ path: join(OUT, "login.png"), fullPage: true });
await page.type('input[type="email"]', email);
await page.type('input[type="password"]', password);
// the form signs in client-side and soft-navigates, so wait for the app shell rather than a page load
await page.click('button[type="submit"]');
await page.waitForSelector("aside nav", { timeout: 90000 });

const slug = (p) => p.replace(/^\//, "").replace(/[^a-z0-9]+/gi, "-").replace(/-+$/, "") || "root";
for (const theme of THEMES) {
  await page.evaluate((t) => localStorage.setItem("theme", t), theme);
  for (const p of PATHS) {
    // "load" rather than networkidle: pages with polling or a live 3D canvas never go idle
    try {
      await page.goto(`${BASE}${p}`, { waitUntil: "load", timeout: 60000 });
    } catch (e) {
      console.warn("goto timed out, capturing anyway:", p, e.message);
    }
    // scroll through the page so every in-view reveal fires, then return to the top
    await page.evaluate(async () => {
      const step = 600;
      for (let y = 0; y < document.body.scrollHeight; y += step) {
        window.scrollTo(0, y);
        await new Promise((r) => setTimeout(r, 120));
      }
      window.scrollTo(0, 0);
    });
    // let entrance animations finish and lazy 3D settle
    await new Promise((r) => setTimeout(r, 2200));
    await page.screenshot({ path: join(OUT, `${slug(p)}-${theme}.png`), fullPage: true });
    console.log("shot", theme, p);
  }
}
await browser.close();
