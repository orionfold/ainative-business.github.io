// S6 browser-smoke — drive the VISIBLE CDP Chromium (:9222) to verify AE-10
// (scout candidates panel on Compare) + AE-11 (astro-bench preview in the Eval
// drawer). Read-only: opens panels, asserts the rendered text, screenshots.
// Usage: node scripts/astro_bench/drive_s6_smoke.mjs
import puppeteer from "/home/nvidia/ainative-business.github.io/node_modules/puppeteer-core/lib/esm/puppeteer/puppeteer-core.js";

const BASE = "http://127.0.0.1:7866";
const OUT = "/tmp/aifn-smoke/s6";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.connect({ browserURL: "http://127.0.0.1:9222", defaultViewport: null });
const pages = await browser.pages();
const page = pages.find((p) => p.url().startsWith("http")) || (await browser.newPage());
await page.bringToFront();

function ok(label, cond, extra = "") {
  console.log(`${cond ? "✓" : "✗"} ${label}${extra ? " — " + extra : ""}`);
  if (!cond) process.exitCode = 1;
}

// ---- AE-10: Compare scout panel ----
await page.goto(`${BASE}/arena/compare/`, { waitUntil: "domcontentloaded" });
await sleep(2000);
// open the scout <details>
await page.evaluate(() => {
  const d = document.querySelector(".scout-panel");
  if (d) d.open = true;
});
await sleep(400);
const scout = await page.evaluate(() => {
  const panel = document.querySelector(".scout-panel");
  if (!panel) return { present: false };
  const picks = [...panel.querySelectorAll(".scout-pick")].map((el) => ({
    repo: el.querySelector(".scout-pick__repo")?.textContent || "",
    score: el.querySelector(".scout-pick__score")?.textContent || "",
    axes: [...el.querySelectorAll(".scout-axis")].length,
  }));
  return {
    present: true,
    run: panel.querySelector(".scout-panel__run")?.textContent || "",
    gate: (panel.querySelector(".scout-panel__gate")?.textContent || "").includes("behavioral gate"),
    picks,
    ruled: panel.querySelectorAll(".scout-panel__ruled-list li").length,
    gatebtn: !!panel.querySelector(".scout-panel__gatebtn"),
  };
});
ok("AE-10 scout panel present", scout.present);
ok("AE-10 scout run label", /astrodynamics/.test(scout.run || ""), scout.run);
ok("AE-10 top pick = Qwen3-8B 95/100", scout.picks?.[0]?.repo?.includes("Qwen3-8B") && scout.picks?.[0]?.score?.includes("95"), JSON.stringify(scout.picks?.[0] || {}));
ok("AE-10 three ranked picks w/ axes", scout.picks?.length === 3 && scout.picks.every((p) => p.axes >= 4));
ok("AE-10 ruled-out rows", scout.ruled >= 4, `${scout.ruled} rows`);
ok("AE-10 lock-time gate framing", scout.gate);
ok("AE-10 gate-prompt button", scout.gatebtn);
await page.screenshot({ path: `${OUT}/ae10-scout-panel.png` });

// click the gate button → opens the eval drawer
if (scout.gatebtn) {
  await page.evaluate(() => document.querySelector(".scout-panel__gatebtn")?.click());
  await sleep(600);
}

// ---- AE-11: astro-bench in the Eval drawer ----
// Ensure the drawer is open (gate button opens it; else click the 🧪 trigger).
const drawerOpen = await page.evaluate(() => !!document.querySelector(".eval-drawer"));
if (!drawerOpen) {
  await page.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find((x) => x.textContent.includes("Eval prompts"));
    if (b) b.click();
  });
  await sleep(600);
}
// select the astro-bench pill
await page.evaluate(() => {
  const pill = [...document.querySelectorAll(".eval-drawer__benchpill")].find((b) => /astro/i.test(b.textContent));
  if (pill) pill.click();
});
await sleep(700);
// filter to held-out via the family <select> if present
await page.evaluate(() => {
  const sel = document.querySelector(".eval-drawer__familysel");
  if (sel) {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, "value").set;
    setter.call(sel, "heldout");
    sel.dispatchEvent(new Event("change", { bubbles: true }));
  }
});
await sleep(800);
const drawer = await page.evaluate(() => {
  const pills = [...document.querySelectorAll(".eval-drawer__benchpill")].map((b) => b.textContent);
  const rows = [...document.querySelectorAll(".eval-row")].slice(0, 3).map((r) => ({
    tier: !!r.querySelector(".eval-badge--tier"),
    sub: !!r.querySelector(".eval-badge--sub"),
    gold: r.querySelector(".eval-badge--gold")?.textContent || "",
    scorer: r.querySelector(".eval-badge--det")?.textContent || "",
  }));
  return { pills, nRows: document.querySelectorAll(".eval-row").length, rows };
});
ok("AE-11 astro-bench pill in drawer", drawer.pills.some((p) => /astro/i.test(p)), JSON.stringify(drawer.pills));
ok("AE-11 astro rows render", drawer.nRows > 0, `${drawer.nRows} rows`);
ok("AE-11 row has tier badge", drawer.rows?.[0]?.tier);
ok("AE-11 row has subtopic badge", drawer.rows?.[0]?.sub);
ok("AE-11 row shows inline gold", /◆/.test(drawer.rows?.[0]?.gold || ""), drawer.rows?.[0]?.gold);
ok("AE-11 scorer label unit-aware", /unit-aware/.test(drawer.rows?.[0]?.scorer || ""), drawer.rows?.[0]?.scorer);
await page.screenshot({ path: `${OUT}/ae11-eval-drawer.png` });

console.log("\nshots → " + OUT);
await browser.disconnect();
