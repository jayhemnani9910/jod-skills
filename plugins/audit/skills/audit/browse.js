#!/usr/bin/env node
// Browser side of /audit. Opens the project in headless Chromium, clicks
// through it, and reports every console error, page exception and failed
// same-origin request. Exit 1 if anything broke.
//
//   node browse.js <project> [--url URL] [--spec FILE] [--timeout MS]
//
// No --url: the project folder is served as a static site and index.html
// (or the first *.html at the root) is opened.
// Spec: --spec or <project>/.audit/browse.json, shape:
//   { "entry": "index.html", "url": "http://...", "steps": [
//       {"click": "#calculate"}, {"fill": "#name", "value": "x"},
//       {"select": "#algo", "value": "rr"}, {"press": "Enter"},
//       {"wait": 1000}, {"expect": "#output"} ] }
// No spec: every visible button gets clicked once, top to bottom.

const fs = require("fs");
const path = require("path");
const http = require("http");
const { chromium } = require("playwright");

const MIME = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml",
  ".ico": "image/x-icon", ".woff": "font/woff", ".woff2": "font/woff2", ".map": "application/json" };

function arg(flag, dflt) {
  const i = process.argv.indexOf(flag);
  return i > -1 ? process.argv[i + 1] : dflt;
}

function serve(root) {
  return new Promise((resolve) => {
    const srv = http.createServer((req, res) => {
      let p = decodeURIComponent(req.url.split("?")[0]);
      if (p.endsWith("/")) p += "index.html";
      const file = path.join(root, p);
      if (!file.startsWith(root) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
        res.writeHead(404); res.end("not found"); return;
      }
      res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream" });
      fs.createReadStream(file).pipe(res);
    });
    srv.listen(0, "127.0.0.1", () => resolve({ srv, port: srv.address().port }));
  });
}

async function main() {
  const project = path.resolve(process.argv[2] || ".");
  if (!fs.existsSync(project)) { console.error(`FATAL: no folder ${project}`); process.exit(2); }
  const auditDir = path.join(project, ".audit");
  fs.mkdirSync(auditDir, { recursive: true });
  // spec lookup: --spec, then browse.json at the project root (committed), then .audit/browse.json (local)
  const rootSpec = path.join(project, "browse.json");
  const specPath = arg("--spec", fs.existsSync(rootSpec) ? rootSpec : path.join(auditDir, "browse.json"));
  let spec = {};
  if (fs.existsSync(specPath)) {
    try { spec = JSON.parse(fs.readFileSync(specPath, "utf8")); }
    catch (e) { console.error(`FATAL: bad spec ${specPath}: ${e.message}`); process.exit(2); }
  }
  const timeout = parseInt(arg("--timeout", "60000"), 10);
  let url = arg("--url", spec.url);
  let server = null;
  if (!url) {
    let entry = spec.entry;
    if (!entry) {
      const htmls = fs.readdirSync(project).filter((f) => f.endsWith(".html")).sort();
      entry = htmls.includes("index.html") ? "index.html" : htmls[0];
    }
    if (!entry) { console.log("browse: no html file at project root and no --url, nothing to open"); process.exit(0); }
    server = await serve(project);
    url = `http://127.0.0.1:${server.port}/${entry}`;
  }

  const errors = [];
  const notes = [];
  const browser = await chromium.launch();
  const page = await browser.newPage();
  page.setDefaultTimeout(8000);
  page.on("pageerror", (e) => errors.push({ kind: "exception", text: String(e.message || e).split("\n")[0], where: (e.stack || "").split("\n")[1] || "" }));
  page.on("console", (m) => { if (m.type() === "error") errors.push({ kind: "console", text: m.text().slice(0, 300), where: m.location().url ? `${m.location().url}:${m.location().lineNumber}` : "" }); });
  page.on("requestfailed", (r) => {
    const same = r.url().startsWith(url.split("/").slice(0, 3).join("/"));
    (same ? errors : notes).push({ kind: "request", text: `${r.failure() && r.failure().errorText} ${r.url()}`, where: "" });
  });
  page.on("response", (r) => { if (r.status() >= 400 && r.url().startsWith(url.split("/").slice(0, 3).join("/"))) errors.push({ kind: "http", text: `${r.status()} ${r.url()}`, where: "" }); });

  const log = [];
  const killer = setTimeout(async () => { log.push("timeout hit"); await finish(1); }, timeout);
  async function finish(code) {
    clearTimeout(killer);
    try { await page.screenshot({ path: path.join(auditDir, "browse.png"), fullPage: true }); } catch (e) { /* page may be gone */ }
    await browser.close();
    if (server) server.srv.close();
    console.log(`browse: ${url}`);
    console.log(`steps: ${log.length}`);
    for (const l of log) console.log(`  ${l}`);
    console.log(`errors: ${errors.length}`);
    for (const e of errors) console.log(`  [${e.kind}] ${e.text}${e.where ? "  at " + e.where : ""}`);
    if (notes.length) { console.log(`external requests that failed (not counted): ${notes.length}`); for (const n of notes.slice(0, 5)) console.log(`  ${n.text}`); }
    console.log(`screenshot: ${path.join(auditDir, "browse.png")}`);
    process.exit(code !== undefined ? code : (errors.length ? 1 : 0));
  }

  try {
    await page.goto(url, { waitUntil: "load" });
    log.push(`open ${url}`);
    await page.waitForTimeout(500);
    const steps = spec.steps;
    if (Array.isArray(steps) && steps.length) {
      for (const s of steps) {
        try {
          if (s.click) { await page.locator(s.click).first().click(); log.push(`click ${s.click}`); }
          else if (s.fill) { await page.locator(s.fill).first().fill(String(s.value ?? "")); log.push(`fill ${s.fill}`); }
          else if (s.select) { await page.locator(s.select).first().selectOption(String(s.value)); log.push(`select ${s.select} = ${s.value}`); }
          else if (s.press) { await page.keyboard.press(s.press); log.push(`press ${s.press}`); }
          else if (s.wait) { await page.waitForTimeout(s.wait); log.push(`wait ${s.wait}`); }
          else if (s.expect) { await page.locator(s.expect).first().waitFor({ state: "attached" }); log.push(`found ${s.expect}`); }
          else if (s.goto) { await page.goto(s.goto.startsWith("http") ? s.goto : url.replace(/\/[^/]*$/, "/") + s.goto, { waitUntil: "load" }); log.push(`open ${s.goto}`); }
          else log.push(`skip unknown step ${JSON.stringify(s)}`);
        } catch (e) {
          errors.push({ kind: "step", text: `${JSON.stringify(s)} failed: ${String(e.message).split("\n")[0]}`, where: "" });
          log.push(`FAILED ${JSON.stringify(s)}`);
        }
        await page.waitForTimeout(150);
      }
    } else {
      // grab the handles once, so a click that adds or removes rows does not shift the list
      const handles = (await page.locator("button:visible, input[type=submit]:visible, [role=button]:visible").elementHandles()).slice(0, 20);
      log.push(`no spec, clicking ${handles.length} visible buttons`);
      for (let i = 0; i < handles.length; i++) {
        const b = handles[i];
        let label = "";
        try {
          label = ((await b.innerText()) || (await b.getAttribute("id")) || `#${i}`).trim().slice(0, 30);
          if (/reload|reset|delete|remove|logout|sign out|clear/i.test(label) || /remove|delete|reset/i.test(await b.getAttribute("class") || "")) { log.push(`skip "${label}"`); continue; }
          await b.click({ timeout: 3000 });
          log.push(`click "${label}"`);
        } catch (e) {
          log.push(`could not click "${label}": ${String(e.message).split("\n")[0].slice(0, 80)}`);
        }
        await page.waitForTimeout(400);
      }
    }
    await page.waitForTimeout(1500);
  } catch (e) {
    errors.push({ kind: "fatal", text: String(e.message).split("\n")[0], where: "" });
  }
  await finish();
}

main();
