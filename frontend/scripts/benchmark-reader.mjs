/** Local, synthetic PDF benchmark. Requires an installed Playwright Chromium. */
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { mkdtemp, readFile, writeFile, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const require = createRequire(import.meta.url);
const { chromium } = require("@playwright/test");
const root = fileURLToPath(new URL("../", import.meta.url));
const baseline = process.argv[2] ?? "8636a5c2";
const output = process.argv[3];
const temp = await mkdtemp(path.join(root, ".reader-benchmark-"));
const relative = path.basename(temp);
let server;
let browser;

// Identical bytes for both implementations: 100 selectable pages, with a
// landscape page at 40 and a unique Find target on page 90. No external data.
function fixture() {
  const objects = ["", "<< /Type /Catalog /Pages 2 0 R >>", ""];
  objects.push("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");
  const kids = [];
  for (let n = 1; n <= 100; n++) {
    const page = objects.length;
    kids.push(`${page} 0 R`);
    objects.push(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${n === 40 ? "792 612" : "612 792"}] /Resources << /Font << /F1 3 0 R >> >> /Contents ${page + 1} 0 R >>`);
    const text = Array.from({ length: 35 }, (_, line) =>
      `1 0 0 1 40 ${550 - line * 14} Tm (Page ${n} line ${line + 1}: ${n === 90 ? "needle" : "Synthetic research manuscript"}) Tj`,
    ).join("\n");
    const stream = `BT /F1 10 Tf\n${text}\nET`;
    objects.push(`<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`);
  }
  objects[2] = `<< /Type /Pages /Count 100 /Kids [${kids.join(" ")}] >>`;
  let pdf = "%PDF-1.4\n";
  const offsets = [0];
  objects.slice(1).forEach((body, i) => { offsets.push(pdf.length); pdf += `${i + 1} 0 obj\n${body}\nendobj\n`; });
  const xref = pdf.length;
  pdf += `xref\n0 ${objects.length}\n0000000000 65535 f \n`;
  pdf += offsets.slice(1).map((offset) => `${String(offset).padStart(10, "0")} 00000 n \n`).join("");
  return pdf + `trailer\n<< /Size ${objects.length} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
}

try {
  await writeFile(path.join(temp, "fixture.pdf"), fixture());
  for (const name of ["PaperPdfReader", "usePaperFind", "useReadingPosition"]) {
    const extension = name === "PaperPdfReader" ? "tsx" : "ts";
    const source = execFileSync("git", ["show", `${baseline}:frontend/src/features/records/paper-view/${name}.${extension}`], { cwd: root, encoding: "utf8" });
    const rewritten = source.replace(/from "\.\/(.*?)"/g, (_, dependency) =>
      `from "${["usePaperFind", "useReadingPosition"].includes(dependency) ? `./${dependency}` : `/src/features/records/paper-view/${dependency}`}"`,
    );
    await writeFile(path.join(temp, `${name}.${extension}`), rewritten);
  }
  await writeFile(path.join(temp, "pdf.ts"), `
    export * from '/src/lib/pdf.ts';
    import * as real from '/src/lib/pdf.ts';
    export async function loadPdfDocument(...args) {
      const loaded = await real.loadPdfDocument(...args);
      const doc = loaded.document;
      return { ...loaded, document: new Proxy(doc, { get(target, key) {
        if (key === 'getPage') return async (n) => {
          const page = await target.getPage(n);
          window.measure.loaded.add(n);
          return page;
        };
        const value = Reflect.get(target, key);
        return typeof value === 'function' ? value.bind(target) : value;
      }}) };
    }
    export function renderPageToCanvas(page, canvas, scale) {
      const rendering = real.renderPageToCanvas(page, canvas, scale);
      rendering.promise.then(() => {
        if (!window.measure.paints[page.pageNumber]) window.measure.paints[page.pageNumber] = {
          ms: performance.now() - window.measure.start,
          loaded: window.measure.loaded.size,
        };
      }, () => {});
      return rendering;
    }
  `);
  await writeFile(path.join(temp, "index.html"), '<html><body><div id="root"></div><script type="module" src="./main.tsx"></script></body></html>');
  await writeFile(path.join(temp, "main.tsx"), `
    import React from 'react';
    import {createRoot} from 'react-dom/client';
    import {PaperPdfReader as Before} from './PaperPdfReader';
    import {PaperPdfReader as After} from '/src/features/records/paper-view/PaperPdfReader';
    import {apiClient} from '/src/api/client';
    import '/src/index.css';
    const params = new URLSearchParams(location.search);
    const target = Number(params.get('target'));
    const bytes = await (await fetch('./fixture.pdf')).blob();
    window.measure = {start: performance.now(), loaded: new Set(), paints: {}, peak: 0};
    apiClient.defaults.adapter = async config => ({data: bytes, status: 200, statusText: 'OK', headers: {}, config});
    new MutationObserver(() => {
      window.measure.peak = Math.max(window.measure.peak, document.querySelectorAll('canvas').length);
    }).observe(document.body, {childList: true, subtree: true});
    const Reader = params.get('arm') === 'before' ? Before : After;
    createRoot(document.getElementById('root')).render(<div style={{height: '100vh', display: 'flex'}}>
      <Reader recordId={7} scrollToPage={target === 1 ? null : target} highlightRegions={[]} navKey="benchmark" contained fill />
    </div>);
  `);
  const config = await readFile(path.join(root, "vite.config.ts"), "utf8");
  // Use a separate server and the project's actual CSS and React transforms.
  await writeFile(path.join(temp, "vite.config.ts"), config.replace('"./src"', '"../src"').replace(
    'alias: {', `alias: { "@/lib/pdf": ${JSON.stringify(path.join(temp, "pdf.ts"))},`,
  ));
  server = await createServer({ root, configFile: path.join(temp, "vite.config.ts"), server: { host: "127.0.0.1", port: 5565, strictPort: true }, logLevel: "error" });
  await server.listen();
  console.log("Benchmark server ready");
  browser = await chromium.launch({ headless: true, timeout: 30000 });
  console.log("Chromium ready");
  const results = [];
  for (const target of [1, 60]) {
    for (const arm of ["before", "after"]) {
      for (let repetition = 1; repetition <= 3; repetition++) {
        const page = await browser.newPage({ viewport: { width: 360, height: 700 }, reducedMotion: "reduce" });
        page.setDefaultTimeout(20000);
        const errors = [];
        page.on("pageerror", (error) => { errors.push(error.message); console.error(error.message); });
        console.log(`Opening ${arm} target ${target}, repetition ${repetition}`);
        await page.goto(`http://127.0.0.1:5565/${relative}/index.html?arm=${arm}&target=${target}`, { waitUntil: "domcontentloaded", timeout: 30000 });
        console.log("Harness loaded");
        await page.waitForFunction(n => window.measure?.paints[n], target, { timeout: 30000 });
        console.log("Target painted");
        await page.waitForFunction(() => window.measure.loaded.size === 100);
        await page.getByRole("button", { name: "Find in this paper" }).click();
        await page.getByRole("searchbox", { name: "Find in this paper" }).fill("needle");
        await page.waitForFunction(() => window.measure.paints[90]);
        await page.getByRole("group", { name: "Page 90", exact: true }).getByText("needle", { exact: true }).first().waitFor();
        const result = await page.evaluate(n => ({
          readiness: window.measure.paints[n], peakCanvases: window.measure.peak,
          liveCanvases: document.querySelectorAll('canvas').length,
          liveTextLayers: document.querySelectorAll('.textLayer').length,
          find90: !!document.querySelector('[aria-label="Page 90"] mark'),
        }), target);
        results.push({ arm, target, repetition, ...result, errors });
        console.log(JSON.stringify(results.at(-1)));
        await page.close();
      }
    }
  }
  const report = { baseline, fixture: "100 pages, 35 selectable lines/page, landscape page 40, needle on page 90", viewport: "360x700", browser: await browser.version(), results };
  if (output) await writeFile(path.resolve(output), JSON.stringify(report, null, 2) + "\n");
} finally {
  await browser?.close();
  await server?.close();
  if (path.dirname(temp) !== path.resolve(root)) throw new Error("Unexpected benchmark temporary directory");
  await rm(temp, { recursive: true, force: true });
}
