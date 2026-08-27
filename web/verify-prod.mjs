// Waits for the redeployed worker, then runs a real analysis on PRODUCTION and prints the
// instructor note so we can see the new format live. One-off; deleted after use.
import puppeteer from "puppeteer-core";

const BASE = "https://feedback-loop-ten.vercel.app";
const VTT = "C:/Users/DELL/Documents/NP team automation/ratings_module_build_kit/sample_ars.vtt";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: "new",
  args: ["--no-sandbox", "--hide-scrollbars"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 950 });
const text = () => page.$eval("body", (e) => e.innerText).catch(() => "");

await page.goto(`${BASE}/login`, { waitUntil: "networkidle2", timeout: 60000 });
await page.type("#email", process.env.SHOT_EMAIL);
await page.type("#password", process.env.SHOT_PASS);
await Promise.all([
  page.waitForNavigation({ waitUntil: "networkidle2", timeout: 60000 }),
  page.click("button[type=submit]"),
]);

// 1) wait for the worker to come back up after the Render redeploy
let online = false;
for (let i = 0; i < 20; i++) {
  await page.goto(`${BASE}/dashboard`, { waitUntil: "networkidle2", timeout: 60000 });
  await sleep(1000);
  const chip = ((await text()).match(/AI engine[^\n]*/) || ["none"])[0];
  console.log(`[${i}] ${chip}`);
  if (/online/.test(chip)) { online = true; break; }
  await sleep(30000);
}
if (!online) { console.log("WORKER NEVER CAME ONLINE"); await browser.close(); process.exit(1); }

// 2) run a real analysis
await page.goto(`${BASE}/feedback/new`, { waitUntil: "networkidle2", timeout: 60000 });
await page.select("#course_id", await page.$eval("#course_id", (s) =>
  [...s.options].find((o) => o.value && o.value !== "__other__")?.value || ""));
await page.type("#topic", "ZZ FORMAT CHECK - delete me");
await page.type("#instructor", "Format Check");
await page.$eval("#class_date", (el) => {
  el.value = "2026-08-27";
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
});
await page.select("#class_type", "ars").catch(() => {});
await page.type("#rating", "4.1");
await page.type("#num_ratings", "12");
const radios = await page.$$('input[type=radio][name=source]');
await radios[1].click();
await sleep(400);
await (await page.$('input[name=file]')).uploadFile(VTT);
await Promise.all([
  page.waitForNavigation({ waitUntil: "networkidle2", timeout: 90000 }).catch(() => {}),
  page.click("button[type=submit]"),
]);
console.log("SUBMITTED ->", page.url());

// 3) poll, then read the note straight out of the textarea
for (let i = 0; i < 40; i++) {
  await sleep(15000);
  await page.reload({ waitUntil: "networkidle2", timeout: 60000 }).catch(() => {});
  const areas = await page.$$eval("textarea", (els) => els.map((e) => e.value));
  const note = areas.find((v) => v && v.includes("Fix:"));
  if (note) {
    console.log("======== INSTRUCTOR NOTE (LIVE PRODUCTION) ========");
    console.log(note);
    console.log("==================================================");
    console.log("bullets:", note.split("\n").filter((l) => l.trim().startsWith("-")).length);
    console.log("timestamps present:", /\d{1,2}:\d{2}/.test(note));
    break;
  }
  console.log(`  … still analyzing (${(i + 1) * 15}s)`);
}
await browser.close();
