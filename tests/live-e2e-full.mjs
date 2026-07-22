import { chromium } from '@playwright/test';
import { writeFileSync, mkdirSync, readFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const OUT = 'tests/out/e2e-full';
mkdirSync(OUT, { recursive: true });

// Minimal valid PDF that some parsers can ingest.
const minimalPdf = Buffer.from(
  '%PDF-1.4\n' +
  '1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n' +
  '2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n' +
  '3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n' +
  'xref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000052 00000 n\n0000000100 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n150\n%%EOF\n',
);
const filePath = join(tmpdir(), 'gu-roundtrip.pdf');
writeFileSync(filePath, minimalPdf);

const BASE = 'https://auto-cost-engine.vercel.app';

const browser = await chromium.launch({ args: ['--no-sandbox'] });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });

// 1. Open Projects index
const idx = await ctx.newPage();
const apiCalls = [];
const pageErrors = [];
const uploadResponses = [];
idx.on('response', async (r) => {
  const u = r.url();
  if (u.includes('/api/')) {
    apiCalls.push({ url: u.replace(BASE, ''), status: r.status() });
    if (u.includes('/drawings') && r.request().method() === 'POST') {
      try { uploadResponses.push({ status: r.status(), body: (await r.text()).slice(0, 500) }); }
      catch { uploadResponses.push({ status: r.status(), body: '<unreadable>' }); }
    }
  }
});
idx.on('pageerror', (e) => pageErrors.push(String(e.message).slice(0, 200)));
idx.on('dialog', async (d) => {
  console.log('  DIALOG:', d.message());
  await d.dismiss();
});

console.log('=== Step 1: open /projects ===');
await idx.goto(BASE + '/projects', { waitUntil: 'domcontentloaded', timeout: 30000 });
await idx.waitForTimeout(1500);
await idx.screenshot({ path: `${OUT}/01-projects.png` });
console.log('  H1:', (await idx.locator('h1').first().textContent())?.slice(0, 60));

// 2. Upload the test PDF via the hidden file input
console.log('\n=== Step 2: upload PDF ===');
await idx.locator('input[type="file"]').first().setInputFiles(filePath);
// Wait up to 30s for upload+processing+nav; if nav never happens, log
// every upload response and the current URL so we know exactly what failed.
let navigated = false;
try {
  await idx.waitForURL(/\/projects\/\d+\/plan/, { timeout: 30_000 });
  navigated = true;
} catch (e) {}
await idx.waitForTimeout(2000);
console.log('  After upload URL:', idx.url(), '  navigated:', navigated);
console.log('  Upload POST responses:');
uploadResponses.forEach((r, i) => console.log(`    [${i}] ${r.status}  ${r.body.slice(0, 300)}`));
await idx.screenshot({ path: `${OUT}/02-after-upload.png` });
const planH1 = (await idx.locator('h1').first().textContent())?.slice(0, 60);
console.log('  H1:', planH1);

// Extract project id from URL — fall back to project 1 if never navigated
const m = idx.url().match(/\/projects\/(\d+)/);
const projectId = m ? Number(m[1]) : 1;
console.log('  Project ID:', projectId);

// 3. Visit every tab + verify it rendered without crash
const tabs = ['plan', 'quantities', 'materials', 'costs', 'ai', 'export'];
let stepIndex = 3;
const tabReport = {};
for (const tab of tabs) {
  console.log(`\n=== Step ${stepIndex}: /projects/${projectId}/${tab} ===`);
  const page = await ctx.newPage();
  const tabErrors = [];
  page.on('pageerror', (e) => tabErrors.push(String(e.message).slice(0, 200)));
  page.on('response', (r) => {
    const u = r.url();
    if (u.includes('/api/') && r.status() >= 400) tabErrors.push(`[${r.status()}] ${u.replace(BASE, '')}`);
  });
  try {
    const r = await page.goto(`${BASE}/projects/${projectId}/${tab}`, { timeout: 20000 });
    await page.waitForTimeout(2500);
    const h1 = (await page.locator('h1').first().textContent())?.slice(0, 80);
    await page.screenshot({ path: `${OUT}/03-tab-${tab}.png` });
    tabReport[tab] = {
      http: r?.status(),
      h1,
      ok: r?.status() === 200 && tabErrors.filter((e) => !e.includes('EventSource')).length === 0,
      errors: tabErrors.filter((e) => !e.includes('EventSource')),
    };
    console.log('  HTTP:', r?.status(), '  H1:', h1);
    if (tabErrors.length) {
      console.log('  Errors:');
      tabErrors.forEach((e) => console.log('    • ' + e));
    } else console.log('  ✓ page rendered clean');
  } catch (e) {
    tabReport[tab] = { ok: false, errors: [String(e.message).slice(0, 200)] };
    console.log('  ✖ ' + e.message);
  } finally { await page.close(); }
  stepIndex++;
}

await browser.close();

// Summary
console.log('\n=== FINAL VERDICT ===');
const clean = Object.values(tabReport).filter((r) => r.ok).length;
const total = Object.keys(tabReport).length;
console.log(`${clean}/${total} tabs rendered clean.`);
for (const [tab, r] of Object.entries(tabReport)) {
  console.log(`  ${r.ok ? '✓' : '✖'} ${tab.padEnd(11)} http=${r.http ?? '-'} h1="${r.h1 ?? ''}"${(r.errors?.length ? '  errors=' + r.errors.length : '')}`);
}
console.log('\nScreenshots + report in', OUT);
writeFileSync(`${OUT}/verdict.json`, JSON.stringify({ projectId, tabs: tabReport }, null, 2));
process.exit(clean === total ? 0 : 1);
