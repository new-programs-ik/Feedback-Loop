/**
 * shots.mjs — full-page screenshots of the app in light and dark, for design review.
 *
 *   SHOT_EMAIL=… SHOT_PASSWORD=… node scripts/shots.mjs [baseUrl] [outDir] [path ...]
 *
 * Logs in through the real sign-in form, then visits each path. Credentials come from the
 * environment only — never from this file. Needs puppeteer-core + a local Chrome.
 */
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const CHROME = process.env.CHROME || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const [, , baseArg, outArg, ...paths] = process.argv;
const BASE = baseArg || "http://localhost:3000";
const OUT = outArg || "shots";
const PATHS = paths.length
  ? paths
  : [
      "/dashboard",
      "/ratings",
      "/instructor-analytics?range=custom&from=2026-01-01&to=2026-08-31",
      "/reports?range=custom&from=2026-08-01&to=2026-08-31",
      "/insights",
      "/course-analytics?range=custom&from=2026-01-01&to=2026-08-31",
      "/feedback",
    ];
const email = process.env.SHOT_EMAIL;
const password = process.env.SHOT_PASSWORD;
if (!email || !password) {
  console.error("set SHOT_EMAIL and SHOT_PASSWORD");
  process.exit(1);
}
mkdirSync(OUT, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: "new",
  args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--no-sandbox"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });

// login page first (also a screenshot target), then the form
await page.goto(`${BASE}/login`, { waitUntil: "networkidle0" });
await page.screenshot({ path: join(OUT, "login.png"), fullPage: true });
await page.type('input[type="email"]', email);
await page.type('input[type="password"]', password);
// the form signs in client-side and soft-navigates, so wait for the app shell rather than a page load
await page.click('button[type="submit"]');
await page.waitForSelector("aside nav", { timeout: 90000 });

const slug = (p) => p.replace(/^\//, "").replace(/[^a-z0-9]+/gi, "-").replace(/-+$/, "") || "root";
for (const theme of ["light", "dark"]) {
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
