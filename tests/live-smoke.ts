// Live smoke test — runs against the dev server, screenshots every route,
// captures console errors, page errors, and failed network requests.
import { chromium } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';

async function main() {
  const BASE = process.env.BASE ?? 'http://localhost:5174';
  const OUT = 'tests/out';
  mkdirSync(OUT, { recursive: true });

  const routes = [
    { name: '00-root',            url: '/' },
    { name: '01-projects',        url: '/projects' },
    { name: '02-workspace-plan',       url: '/projects/1/plan' },
    { name: '03-workspace-quantities', url: '/projects/1/quantities' },
    { name: '04-workspace-materials',  url: '/projects/1/materials' },
    { name: '05-workspace-costs',      url: '/projects/1/costs' },
    { name: '06-workspace-ai',         url: '/projects/1/ai' },
    { name: '07-workspace-export',     url: '/projects/1/export' },
  ];

  const report: any = { base: BASE, runs: [] };
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });

  for (const r of routes) {
    const page = await context.newPage();
    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];
    const failedRequests: { url: string; status: number; failure?: string }[] = [];

    page.on('console', (msg) => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });
    page.on('pageerror', (err) => pageErrors.push(`${err.name}: ${err.message}`));
    page.on('requestfailed', (req) => failedRequests.push({ url: req.url(), status: 0, failure: req.failure()?.errorText }));
    page.on('response', (res) => { if (res.status() >= 400) failedRequests.push({ url: res.url(), status: res.status() }); });

    try {
      const res = await page.goto(`${BASE}${r.url}`, { waitUntil: 'networkidle', timeout: 15_000 });
      await page.waitForTimeout(500);
      await page.screenshot({ path: `${OUT}/${r.name}.png`, fullPage: false });
      report.runs.push({ name: r.name, url: r.url, status: res?.status() ?? null, title: await page.title().catch(() => ''), consoleErrors, pageErrors, failedRequests });
    } catch (e: any) {
      report.runs.push({ name: r.name, url: r.url, fatal: e.message, consoleErrors, pageErrors, failedRequests });
    } finally {
      await page.close();
    }
  }

  await browser.close();
  writeFileSync(`${OUT}/report.json`, JSON.stringify(report, null, 2));

  console.log('\n=== LIVE SMOKE SUMMARY ===');
  for (const r of report.runs) {
    console.log(`\n${r.name}  ${r.url}  status=${r.status ?? '-'}  title="${r.title ?? ''}"`);
    if (r.fatal) console.log(`  FATAL: ${r.fatal}`);
    if (r.pageErrors.length) { console.log(`  pageErrors: ${r.pageErrors.length}`); for (const e of r.pageErrors) console.log(`    - ${e}`); }
    if (r.consoleErrors.length) { console.log(`  consoleErrors: ${r.consoleErrors.length}`); for (const e of r.consoleErrors.slice(0, 5)) console.log(`    - ${e}`); }
    if (r.failedRequests.length) { console.log(`  failedRequests: ${r.failedRequests.length}`); for (const e of r.failedRequests.slice(0, 8)) console.log(`    - ${e.status} ${e.url}${e.failure ? ` (${e.failure})` : ''}`); }
  }
  console.log(`\nScreenshots + report in ${OUT}/`);
}

main().catch((e) => { console.error(e); process.exit(1); });