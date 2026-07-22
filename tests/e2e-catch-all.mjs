#!/usr/bin/env node
/**
 * Playwright end-to-end test — drives the live frontend (Vite dev server)
 * with the mock backend on :8787.  Captures:
 *   • every URL the frontend calls vs the response status
 *   • every console error
 *   • every visible page route
 *   • the BOQ total rendered by the UI vs the reference total
 *
 * Run: BASE=http://localhost:5174 node tests/e2e-catch-all.mjs
 */
import { chromium } from '@playwright/test';
import { writeFileSync, mkdirSync } from 'node:fs';

const FRONTEND = process.env.BASE || 'https://auto-cost-engine.vercel.app';
const REFERENCE_TOTAL = 6251940;
const OUT = 'tests/out/e2e';
mkdirSync(OUT, { recursive: true });

const report = { frontend: FRONTEND, runs: [] };

const browser = await chromium.launch({ args: ['--no-sandbox'] });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });

const routes = [
  { name: '00-projects',        url: '/projects' },
  { name: '01-workspace-plan',       url: '/projects/1/plan' },
  { name: '02-workspace-quantities', url: '/projects/1/quantities' },
  { name: '03-workspace-materials',  url: '/projects/1/materials' },
  { name: '04-workspace-costs',      url: '/projects/1/costs' },
  { name: '05-workspace-ai',         url: '/projects/1/ai' },
  { name: '06-workspace-export',     url: '/projects/1/export' },
];

for (const r of routes) {
  const page = await context.newPage();
  const consoleErrors = [];
  const requestFailures = [];
  const apiCalls = [];

  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', (err) => consoleErrors.push('pageerror: ' + err.message));
  page.on('requestfailed', (req) => requestFailures.push(req.url() + ' (failed)'));
  page.on('response', (res) => {
    const u = res.url();
    if (u.includes('/api/v1/')) {
      const ok = res.status() < 400;
      apiCalls.push({ url: u.replace(FRONTEND, ''), status: res.status(), ok });
      if (!ok) requestFailures.push(u + ' status=' + res.status());
    }
  });

  try {
    const resp = await page.goto(FRONTEND + r.url, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(800);
    await page.screenshot({ path: OUT + '/' + r.name + '.png', fullPage: false });
    const title = await page.title();
    const visibleHeading = await page.locator('h1').first().textContent().catch(() => '');
    report.runs.push({
      name: r.name, url: r.url,
      httpStatus: resp?.status(),
      title, visibleHeading,
      apiCount: apiCalls.length,
      failedApi: apiCalls.filter(c => !c.ok).map(c => c.url + ' → ' + c.status),
      consoleErrors,
      requestFailures,
    });
  } catch (err) {
    report.runs.push({ name: r.name, url: r.url, fatal: err.message, consoleErrors, requestFailures });
  } finally {
    await page.close();
  }
}

// ── Visit costs page and read the hero grand total ─────────
{
  const page = await context.newPage();
  await page.goto(FRONTEND + '/projects/1/costs', { waitUntil: 'networkidle' });
  await page.waitForSelector('.num-display', { state: 'visible', timeout: 15_000 });
  const heroText = await page.locator('.num-display').last().textContent();
  const heroNumber = heroText ? +(heroText.replace(/[^0-9]/g, '')) : null;
  report.boqMaxDisplayed = heroNumber;
  report.boqReference   = REFERENCE_TOTAL;
  report.boqDeltaPct    = heroNumber ? +(Math.abs(heroNumber - REFERENCE_TOTAL) / REFERENCE_TOTAL * 100).toFixed(3) : null;
  report.boqPass        = heroNumber ? Math.abs(heroNumber - REFERENCE_TOTAL) / REFERENCE_TOTAL < 0.01 : false;
  await page.close();
}

await browser.close();

writeFileSync(OUT + '/report.json', JSON.stringify(report, null, 2));

console.log('\n=== E2E CATCH-ALL ===');
for (const r of report.runs) {
  const status = r.fatal ? 'FATAL' : (r.failedApi?.length ? `FAIL(${r.failedApi.length})` : 'OK');
  console.log(`\n${status}  ${r.name}  ${r.url}  status=${r.httpStatus ?? '-'}  heading="${(r.visibleHeading || '').slice(0, 60)}"`);
  for (const f of r.failedApi.slice(0, 6)) console.log('  failed API: ' + f);
  for (const e of r.consoleErrors.slice(0, 4)) console.log('  console:    ' + e.slice(0, 100));
}
console.log('\n=== BOQ ROUND-TRIP ===');
console.log(`Reference total:    ₹${REFERENCE_TOTAL.toLocaleString('en-IN')}`);
console.log(`Hero grand total:  ₹${(report.boqMaxDisplayed || 0).toLocaleString('en-IN')}`);
console.log(`Delta:             ${report.boqDeltaPct}%`);
console.log(`PASS (±1%):        ${report.boqPass ? 'YES' : 'NO'}`);
console.log(`\nReport: ${OUT}/report.json`);
process.exit(report.boqPass ? 0 : 1);
