import { chromium } from '@playwright/test';
import { writeFileSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const OUT = 'tests/out/live-upload';
mkdirSync(OUT, { recursive: true });

// Minimal valid PDF that browsers will accept
const fakePdf = Buffer.from(
  '%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 100 100]>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000052 00000 n\n0000000100 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n150\n%%EOF\n',
);
const filePath = join(tmpdir(), 'gu-test.pdf');
writeFileSync(filePath, fakePdf);

const browser = await chromium.launch({ args: ['--no-sandbox'] });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();

const apiCalls = [];
const failures = [];
page.on('response', (r) => {
  const u = r.url();
  if (u.includes('/api/') || u.includes('/functions/')) {
    apiCalls.push({ url: u, status: r.status() });
    if (r.status() >= 400) failures.push(`${r.status()} ${u}`);
  }
});
page.on('dialog', async (d) => { console.log('ALERT:', d.message()); await d.dismiss(); });
page.on('pageerror', (e) => failures.push(`PAGE ERROR: ${e.message}`));

console.log('Loading /projects ...');
await page.goto('https://auto-cost-engine.vercel.app/projects', { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForTimeout(1500);
await page.screenshot({ path: `${OUT}/01-projects-page.png` });

console.log('Setting file on hidden input ...');
const fileInput = await page.locator('input[type="file"]').first();
// fileChooser is what the dropzone triggers; Playwright's setInputFiles bypasses it
await fileInput.setInputFiles(filePath);

console.log('Waiting 8s for upload+processing ...');
await page.waitForTimeout(8000);
await page.screenshot({ path: `${OUT}/02-after-upload.png` });

const url = page.url();
const heading = await page.locator('h1').first().textContent().catch(() => '<no h1>');
const bodySnippet = (await page.locator('body').innerText().catch(() => '')).slice(0, 600);

console.log('\nAfter upload:');
console.log('  URL:    ', url);
console.log('  H1:     ', (heading || '').slice(0, 60));
console.log('  Body:   ', bodySnippet.slice(0, 300));

console.log('\nAll /api calls:');
apiCalls.forEach((c) => console.log(`  ${c.status}  ${c.url.replace('https://auto-cost-engine.vercel.app', '')}`));

console.log('\nFailures:');
if (failures.length === 0) console.log('  (none)');
else failures.forEach((f) => console.log(`  ${f}`));

console.log('\nScreenshots:');
console.log('  tests/out/live-upload/01-projects-page.png');
console.log('  tests/out/live-upload/02-after-upload.png');

await browser.close();
