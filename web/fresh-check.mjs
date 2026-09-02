// Load the live site as a brand-new visitor (fresh profile, no cookies) and report anything
// that fails to load - to see exactly what a teammate sees.
import puppeteer from "puppeteer-core";

const browser = await puppeteer.launch({
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: "new",
  args: ["--no-sandbox", "--incognito"],
});
const page = await browser.newPage();
const failures = [];
page.on("requestfailed", (r) => failures.push(`${r.failure()?.errorText}  ${r.url().slice(0, 90)}`));
page.on("response", (r) => { if (r.status() >= 400) failures.push(`HTTP ${r.status()}  ${r.url().slice(0, 90)}`); });
page.on("pageerror", (e) => failures.push("JS ERROR: " + String(e).slice(0, 140)));

for (const path of ["/feedback/new", "/login", "/"]) {
  try {
    const resp = await page.goto("https://feedback-loop-ten.vercel.app" + path,
      { waitUntil: "networkidle2", timeout: 45000 });
    const title = await page.title();
    const text = (await page.$eval("body", (e) => e.innerText).catch(() => "")).slice(0, 80);
    console.log(`${path}  ->  HTTP ${resp?.status()}  final=${page.url().replace("https://feedback-loop-ten.vercel.app", "")}`);
    console.log(`   title="${title}"  body starts: ${JSON.stringify(text)}`);
  } catch (e) {
    console.log(`${path}  ->  NAVIGATION FAILED: ${String(e).slice(0, 160)}`);
  }
}
console.log("\nfailed/erroring requests:", failures.length ? "" : "none");
for (const f of failures.slice(0, 12)) console.log("  " + f);
await page.screenshot({ path: "C:/Users/DELL/AppData/Local/Temp/fresh-login.png" });
await browser.close();
