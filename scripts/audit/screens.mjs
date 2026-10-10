// Screen-size audit for the Master Terminal frontend. Run it with scripts/audit/run_screens.sh
// (Playwright Docker image). Env: WEB_URL (default http://host.docker.internal:5173), OUT (default audit-output/screens).
// For every page x width x theme: full-page PNG plus checks for horizontal overflow, elements past the
// viewport edge, console errors, failed requests, small tap targets, and (on the first page) modal fit.
import { chromium } from "playwright";
import { lookup } from "node:dns/promises";
import { mkdirSync, writeFileSync } from "node:fs";

const OUT = process.env.OUT || "audit-output/screens";
const WIDTHS = [[360, 740], [390, 844], [768, 1024], [834, 1194], [1024, 768], [1280, 800], [1440, 900], [1920, 1080]];
mkdirSync(OUT, { recursive: true });

// Vite rejects unknown Host headers; an IP literal always passes its host check.
const web = new URL(process.env.WEB_URL || "http://host.docker.internal:5173");
if (!/^[\d.]+$/.test(web.hostname) && web.hostname !== "localhost") web.hostname = (await lookup(web.hostname)).address;
const BASE = web.toString().replace(/\/$/, "");

// PAGES="#/overview,#/holdings" overrides discovery.
const PAGES = (process.env.PAGES || "").split(",").filter(Boolean);

async function settle(page) {
  await page.waitForLoadState("networkidle", { timeout: 20000 }).catch(() => {});
  await page.waitForSelector(".loading-overlay, [aria-busy='true']", { state: "detached", timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(400); // chart animations
}

// Matches visible text or aria-label (icon-only buttons such as the phone "+" have no text).
async function clickText(page, pattern) {
  const all = page.locator("button, a");
  for (let i = 0, n = await all.count(); i < n; i++) {
    const el = all.nth(i);
    if (!(await el.isVisible())) continue;
    const text = (await el.innerText()).trim();
    const label = (await el.getAttribute("aria-label")) || "";
    if (!pattern.test(text) && !pattern.test(label)) continue;
    await el.click();
    await settle(page);
    return true;
  }
  return false;
}

// Pages: hash routes when the app has them (new UI), else the legacy view flow.
async function discoverPages(page) {
  await page.goto(BASE + "/", { waitUntil: "domcontentloaded" });
  await settle(page);
  const links = await page.$$eval("a[href^='#/']", (as) => [...new Set(as.map((a) => a.getAttribute("href")))]);
  const hashes = PAGES.length ? PAGES : links;
  if (hashes.length) return hashes.map((hash) => ({ label: hash.replace(/[#/]+/g, "") || "home", go: (p) => p.goto(BASE + "/" + hash) }));
  return [
    { label: "dashboard", go: (p) => p.goto(BASE + "/") },
    { label: "account", go: async (p) => { await p.goto(BASE + "/"); await settle(p); return p.locator(".account-card").first().click(); } },
    { label: "limits", go: async (p) => {
      await p.goto(BASE + "/"); await settle(p); await p.locator(".account-card").first().click(); await settle(p);
      return clickText(p, /Contribution Limits/);
    } },
  ];
}

function measure() {
  const vw = window.innerWidth;
  const scroller = (el) => { for (let n = el.parentElement; n; n = n.parentElement) { const o = getComputedStyle(n).overflowX; if (o === "auto" || o === "scroll" || o === "hidden") return true; } return false; };
  const name = (el) => el.tagName.toLowerCase() + (el.id ? "#" + el.id : "") + (typeof el.className === "string" && el.className.trim() ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".") : "");
  const offenders = [...document.body.querySelectorAll("*")].filter((el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.right > vw + 1 && !scroller(el);
  }).slice(0, 8).map((el) => `${name(el)} right=${Math.round(el.getBoundingClientRect().right)}`);
  const small = [...document.querySelectorAll("button, a[href], input:not([type=hidden]), select")].filter((el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && (r.height < 32 || r.width < 32);
  });
  return {
    overflowPx: Math.max(0, document.scrollingElement.scrollWidth - vw),
    offenders,
    smallTapTargets: small.length,
    smallSample: small.slice(0, 5).map((el) => `${name(el)} ${Math.round(el.getBoundingClientRect().width)}x${Math.round(el.getBoundingClientRect().height)}`),
    bodyBg: getComputedStyle(document.body).backgroundColor,
  };
}

async function checkModal(page, file) {
  const opened = (await clickText(page, /New Account Transaction|New transaction|^\s*New\s*$|^New entry$|^\+$/)) || (await clickText(page, /New Contribution/));
  if (!opened) return { opened: false };
  const SUBMIT = "button[type=submit], button.btn-primary, button.btn-p";
  const open = page.locator("dialog[open], [role=dialog]").first();
  if (!(await open.count())) await clickText(page, /Transaction/); // "+ New" menus
  else if (!(await open.locator(SUBMIT).count())) await clickText(page, /^Transaction/); // phone "Add" chooser sheet
  const dialog = page.locator("dialog[open], [role=dialog]").first();
  if (!(await dialog.count())) return { opened: false };
  const info = await dialog.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const box = (el.querySelector(".modal-content, form") || el).getBoundingClientRect();
    const submit = el.querySelector("button[type=submit], button.btn-primary, button.btn-p");
    const s = submit && submit.getBoundingClientRect();
    const wide = [...el.querySelectorAll("input[type=checkbox]")].filter((c) => c.getBoundingClientRect().width > 40).length;
    return {
      fitsWidth: box.width <= innerWidth && r.left >= 0,
      fitsHeight: r.height <= innerHeight && r.top >= 0, // the dialog box; inner form may scroll
      submitVisibleWithoutScroll: !!s && s.top >= 0 && s.bottom <= innerHeight,
      oversizedCheckboxes: wide,
    };
  });
  const submit = dialog.locator("button[type=submit], button.btn-primary, button.btn-p").first();
  info.submitReachable = (await submit.count()) ? await submit.scrollIntoViewIfNeeded({ timeout: 2000 }).then(() => submit.isVisible()).catch(() => false) : false;
  await page.screenshot({ path: file });
  await page.keyboard.press("Escape");
  info.closesWithEscape = !(await dialog.isVisible().catch(() => false));
  info.opened = true;
  return info;
}

const browser = await chromium.launch();
const report = [];
const probe = await browser.newPage();
const pages = await discoverPages(probe);

// Theme support: compare body background under light vs dark emulation + data-theme.
async function bgFor(theme) {
  await probe.emulateMedia({ colorScheme: theme });
  await probe.goto(BASE + "/"); await settle(probe);
  return probe.evaluate((t) => { document.documentElement.setAttribute("data-theme", t); return getComputedStyle(document.body).backgroundColor; }, theme);
}
const themes = (await bgFor("light")) !== (await bgFor("dark")) ? ["light", "dark"] : ["default"];
await probe.close();

for (const theme of themes) {
  for (const [width, height] of WIDTHS) {
    const context = await browser.newContext({ viewport: { width, height }, colorScheme: theme === "dark" ? "dark" : "light", reducedMotion: "reduce" });
    for (const [index, def] of pages.entries()) {
      const page = await context.newPage();
      const errors = [];
      page.on("console", (m) => m.type() === "error" && errors.push(m.text().slice(0, 160)));
      page.on("pageerror", (e) => errors.push("pageerror: " + e.message.slice(0, 160)));
      page.on("requestfailed", (r) => errors.push(`requestfailed: ${r.url()} ${r.failure()?.errorText}`));
      page.on("response", (r) => r.status() >= 400 && errors.push(`http ${r.status()}: ${r.url()}`));
      const row = { page: def.label, width, theme };
      try {
        await def.go(page);
        await settle(page);
        if (theme !== "default") await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
        Object.assign(row, await page.evaluate(measure));
        const file = `${OUT}/${def.label}-${width}-${theme}.png`;
        await page.screenshot({ path: file, fullPage: true });
        row.screenshot = file;
        if (index === 0) row.modal = await checkModal(page, `${OUT}/${def.label}-${width}-${theme}-modal.png`);
      } catch (error) {
        row.failed = String(error).slice(0, 200);
      }
      row.consoleErrors = errors;
      report.push(row);
      await page.close();
    }
    await context.close();
  }
}
await browser.close();

writeFileSync(`${OUT}/report.json`, JSON.stringify({ base: BASE, themes, report }, null, 2));
const lines = report.map((r) => {
  const issues = [];
  if (r.failed) issues.push("FAILED " + r.failed);
  if (r.overflowPx) issues.push(`overflow ${r.overflowPx}px [${r.offenders.slice(0, 3).join("; ")}]`);
  if (r.consoleErrors.length) issues.push(`${r.consoleErrors.length} console/network errors`);
  if (r.width <= 834 && r.smallTapTargets) issues.push(`${r.smallTapTargets} tap targets <32px`);
  if (r.modal?.opened) {
    const m = r.modal;
    if (!m.fitsWidth || !m.fitsHeight) issues.push(`modal does not fit (${m.fitsWidth ? "" : "width "}${m.fitsHeight ? "" : "height"})`);
    if (!m.submitVisibleWithoutScroll) issues.push(m.submitReachable ? "modal submit needs scrolling" : "modal submit unreachable");
    if (m.oversizedCheckboxes) issues.push(`${m.oversizedCheckboxes} oversized checkboxes`);
    if (!m.closesWithEscape) issues.push("modal ignores Escape");
  }
  return `${r.page.padEnd(10)} ${String(r.width).padStart(4)} ${r.theme.padEnd(7)} ${issues.join(" | ") || "ok"}`;
});
writeFileSync(`${OUT}/summary.txt`, lines.join("\n") + "\n");
console.log(lines.join("\n"));
