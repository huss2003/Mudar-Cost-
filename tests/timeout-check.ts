import { chromium } from '@playwright/test';

const BASE = process.env.BASE ?? 'http://localhost:5175';

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(`${BASE}/projects/1/plan`, { waitUntil: 'domcontentloaded' });
  // wait past the 12s project-load timeout I added
  await page.waitForTimeout(14_000);
  await page.screenshot({ path: 'tests/out/08-workspace-after-timeout.png', fullPage: false });
  // also screenshot the projects index with the API failing
  const idx = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await idx.goto(`${BASE}/projects`, { waitUntil: 'networkidle' });
  await idx.waitForTimeout(800);
  await idx.screenshot({ path: 'tests/out/09-projects-after-failure.png' });
  await browser.close();
  console.log('OK');
}
main().catch((e) => { console.error(e); process.exit(1); });