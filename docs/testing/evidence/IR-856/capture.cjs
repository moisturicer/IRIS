const { chromium } = require('playwright');
const path = require('path');

async function main() {
  const browser = await chromium.launch({ headless: true });
  try {
    for (const [screen, url] of [['sign-in', '/login'], ['registration', '/signup']]) {
      for (const [size, width, height, zoom] of [
        ['phone', 360, 800, 1],
        ['desktop', 1440, 900, 1],
        ['zoom-200', 720, 900, 2],
      ]) {
        const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: zoom, reducedMotion: 'reduce' });
        const page = await context.newPage();
        await page.goto(`http://127.0.0.1:5173${url}`);
        await page.locator('main').waitFor();
        await page.screenshot({ path: path.join(__dirname, `${screen}-${size}.png`), fullPage: true });
        const geometry = await page.evaluate(() => {
          const card = document.querySelector('main .shadow-card-md');
          const label = document.querySelector('main [aria-current="step"]') ??
            document.querySelector('main .border-t-brand');
          const header = document.querySelector('header');
          const box = (el) => {
            const r = el?.getBoundingClientRect();
            return r && { x: r.x, y: r.y, width: r.width, height: r.height };
          };
          return {
            viewport: innerWidth,
            documentWidth: document.documentElement.scrollWidth,
            card: box(card),
            label: box(label),
            headerActions: [...header.querySelectorAll('a')].map(a => ({ text: a.textContent.trim(), href: a.getAttribute('href') })),
          };
        });
        console.log(`${screen} ${size}: ${JSON.stringify(geometry)}`);
        if (size === 'phone') {
          await page.keyboard.press('Tab');
          console.log(`${screen} first focus: ${await page.evaluate(() => document.activeElement?.textContent?.trim())}`);
          await page.screenshot({ path: path.join(__dirname, `${screen}-focus-phone.png`), fullPage: true });
          await page.addScriptTag({ path: path.resolve(__dirname, '../../../../frontend/node_modules/axe-core/axe.min.js') });
          const audit = await page.evaluate(async () => window.axe.run(document, {
            runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
          }));
          console.log(`${screen} axe: ${JSON.stringify(audit.violations.map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.length })))}`);
        }
        await context.close();
      }
    }
    const context = await browser.newContext({ viewport: { width: 360, height: 800 }, reducedMotion: 'reduce' });
    const page = await context.newPage();
    await page.goto('http://127.0.0.1:5173/entry/help');
    console.log(`help: ${await page.locator('h2').first().textContent()}`);
    await context.close();
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
