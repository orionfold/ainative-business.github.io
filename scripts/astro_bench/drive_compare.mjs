// Drive the VISIBLE CDP Chromium (:9222) to the Arena Compare page and run a
// Kepler-vs-baseline head-to-head — browser-use dogfood for the T2 head-to-head.
// Usage: node scripts/astro_bench/drive_compare.mjs <mode>
//   inspect  — navigate to /arena/compare/ and dump interactive controls
//   run      — select Kepler vs DeepSeek-R1, submit an astro prompt, stream
import puppeteer from "/home/nvidia/ainative-business.github.io/node_modules/puppeteer-core/lib/esm/puppeteer/puppeteer-core.js";

const COCKPIT = "http://127.0.0.1:7866/arena/compare/";
const PROMPT =
  "A satellite orbits Earth in a circular orbit at altitude 550 km. " +
  "Compute its orbital period in minutes. Give your final answer as \\boxed{value unit}.";
const mode = process.argv[2] || "inspect";

const browser = await puppeteer.connect({
  browserURL: "http://127.0.0.1:9222",
  defaultViewport: null,
});
const pages = await browser.pages();
// reuse the first visible page (the operator's window)
const page = pages.find((p) => p.url().startsWith("http")) || (await browser.newPage());
await page.bringToFront();
// Only (re)navigate when not already on the compare page — a reload wipes the
// stream + resets the lane selects.
if (!page.url().includes("/arena/compare")) {
  await page.goto(COCKPIT, { waitUntil: "domcontentloaded" });
  await new Promise((r) => setTimeout(r, 1500));
}

if (mode === "duel") {
  const laneA = process.env.LANE_A || "local:kepler::Q8_0";
  const laneB = process.env.LANE_B || "openrouter:deepseek/deepseek-r1-0528";
  const out = process.env.SHOT_OUT || "/tmp/aifn-smoke/compare/duel.png";
  // navigate fresh so we start from a clean composer
  await page.goto(COCKPIT, { waitUntil: "domcontentloaded" });
  await new Promise((r) => setTimeout(r, 1500));
  // Set both lane <select>s the React-safe way (native value setter + change
  // event), then read back to confirm the option actually exists + took. A
  // missing option silently leaves the select on its default (the bug that made
  // lane B fall back to the unserved resident → "connection refused").
  const setSel = async (idx, value) => {
    return await page.evaluate(
      (i, v) => {
        const sel = document.querySelectorAll("select")[i];
        if (!sel) return { ok: false, why: "no select" };
        const opt = [...sel.options].find((o) => o.value === v);
        if (!opt) return { ok: false, why: "option absent", have: [...sel.options].map((o) => o.value).filter((x) => x.includes(v.split(":").pop().split("/").pop().slice(0, 6))) };
        const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, "value").set;
        setter.call(sel, v);
        sel.dispatchEvent(new Event("change", { bubbles: true }));
        return { ok: sel.value === v, value: sel.value };
      },
      idx,
      value
    );
  };
  const ra = await setSel(0, laneA);
  const rb = await setSel(1, laneB);
  console.log("laneA set:", JSON.stringify(ra), "| laneB set:", JSON.stringify(rb));
  if (!ra.ok || !rb.ok) {
    console.log("ABORT — a lane select did not take; not clicking COMPARE");
    await browser.disconnect();
    process.exit(2);
  }
  await new Promise((r) => setTimeout(r, 400));
  const ta = (await page.$$("textarea"))[0];
  await ta.click();
  await ta.type(PROMPT, { delay: 6 });
  await new Promise((r) => setTimeout(r, 400));
  const clicked = await page.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find(
      (x) => /compare/i.test(x.innerText) && !x.disabled
    );
    if (b) { b.click(); return true; }
    return false;
  });
  console.log(`laneA=${laneA} laneB=${laneB} compareClicked=${clicked}`);
  // poll up to ~150s for both columns to leave "(no answer yet)" (Kepler boots
  // the on-demand lane first ~40-60s, then both stream; DeepSeek-R1 reasons long)
  let cols = [];
  for (let i = 0; i < 50; i++) {
    await new Promise((r) => setTimeout(r, 3000));
    cols = await page.evaluate(() =>
      [...document.querySelectorAll("article")]
        .map((c) => c.innerText)
        .filter((t) => /^[AB]\n/.test(t))
        .slice(0, 2)
    );
    const answered = cols.filter((t) => !/no answer yet/i.test(t) && t.length > 60).length;
    if (answered >= 2) break;
  }
  await page.screenshot({ path: out, fullPage: true });
  console.log("SHOT -> " + out);
  console.log(JSON.stringify(cols.map((c) => c.slice(0, 500)), null, 2));
}

if (mode === "shot") {
  const out = process.env.SHOT_OUT || "/tmp/aifn-smoke/compare/shot.png";
  await page.screenshot({ path: out, fullPage: true });
  // also dump the two lane columns' text so we can verify content headlessly
  const cols = await page.evaluate(() =>
    [...document.querySelectorAll("article, .lane, [class*=column], [class*=Column]")]
      .map((c) => c.innerText.slice(0, 600))
      .filter((t) => t.length > 40)
      .slice(0, 4)
  );
  console.log("SHOT -> " + out);
  console.log(JSON.stringify(cols, null, 2));
}

if (mode === "inspect") {
  const controls = await page.evaluate(() => {
    const out = [];
    for (const el of document.querySelectorAll("select, button, textarea, input")) {
      out.push({
        tag: el.tagName.toLowerCase(),
        type: el.type || "",
        text: (el.innerText || el.placeholder || el.value || "").slice(0, 50),
        opts: el.tagName === "SELECT" ? [...el.options].map((o) => o.value) : undefined,
        disabled: el.disabled || false,
      });
    }
    return out;
  });
  console.log(JSON.stringify(controls, null, 2));
}

await browser.disconnect();
console.log("DONE mode=" + mode + " url=" + page.url());
