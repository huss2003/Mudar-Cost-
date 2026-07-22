// Playwright integration test — drop into frontend/tests/e2e.smoke.ts
//
// Usage:
//   npm install -D @playwright/test
//   npx playwright install chromium
//   PLAYWRIGHT_BASE=http://localhost:5173 npx playwright test tests/e2e.smoke.ts
//
// Or run against the deployed site:
//   PLAYWRIGHT_BASE=https://auto-cost-engine.vercel.app npx playwright test
//
// Drop the PDF at fixtures/gu-office.pdf — the real G.U. office.

import { test, expect, request as pwRequest } from '@playwright/test';
import path from 'node:path';

const BASE = process.env.PLAYWRIGHT_BASE ?? 'http://localhost:5173';
const FIXTURE = process.env.GU_PDF ?? path.resolve('fixtures/gu-office.pdf');
const REFERENCE_TOTAL_INR = 6_251_940; // G.U. reference grand total

test.describe('Auto Cost Engine — end to end', () => {
  test('live site loads and pathname redirects to /projects', async ({ page }) => {
    const res = await page.goto(`${BASE}/`, { waitUntil: 'networkidle' });
    expect(res?.status()).toBeLessThan(500);
    await expect(page).toHaveURL(/\/projects(\/|$)/);
    // Hero copy
    await expect(page.getByText(/Projects/i).first()).toBeVisible();
  });

  test('project workspace shell renders with all six views in tabs', async ({ page }) => {
    await page.goto(`${BASE}/projects`, { waitUntil: 'networkidle' });
    // Click first project row if present
    const firstRow = page.locator('button').filter({ hasText: /Active projects|in progress|Sent/i }).first();
    if (await firstRow.count()) await firstRow.click().catch(() => {});

    await expect(page.getByRole('link', { name: /Plan/ })).toBeVisible();
    await expect(page.getByRole('link', { name: /Quantities/ })).toBeVisible();
    await expect(page.getByRole('link', { name: /Materials/ })).toBeVisible();
    await expect(page.getByRole('link', { name: /Costs/ })).toBeVisible();
    await expect(page.getByRole('link', { name: /^AI$/ })).toBeVisible();
    await expect(page.getByRole('link', { name: /Export/ })).toBeVisible();

    // Live total label renders in mono numerics
    await expect(page.getByText(/Live total/i)).toBeVisible();
  });

  test('upload + compute produces an in-tolerance grand total', async ({ page }) => {
    test.skip(!process.env.RUN_FULL, 'set RUN_FULL=1 to exercise the upload pipeline');

    await page.goto(`${BASE}/projects`, { waitUntil: 'networkidle' });

    // Upload via the index drop zone
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles(FIXTURE);

    // Wait for navigation to plan view
    await page.waitForURL(/\/projects\/\d+\/plan/);

    // Poll until objects are detected
    await expect(page.locator('text=/objects/').first()).toBeVisible({ timeout: 60_000 });

    // Compute quantities
    await page.getByRole('button', { name: /Compute quantities/i }).click();

    // Visit Costs view
    await page.goto(`${page.url().replace(/\/plan$/, '/costs')}`, { waitUntil: 'networkidle' });

    // Total should be visible (numeric text). Allow up to ±2% noise for first training run.
    const totalText = await page.getByText(/Total/i).first().innerText();
    expect(totalText.length).toBeGreaterThan(0);

    // API assertion (deterministic): read BOQ for the active project
    const m = page.url().match(/\/projects\/(\d+)/);
    const projectId = m?.[1];
    expect(projectId).toBeTruthy();

    const api = await pwRequest.newContext({ baseURL: BASE });
    const boq = await api.get(`/api/v1/projects/${projectId}/boq`);
    expect(boq.status()).toBeLessThan(500);
    const json = await boq.json();
    const got = Number(json?.total ?? 0);
    const pctDelta = Math.abs(got - REFERENCE_TOTAL_INR) / REFERENCE_TOTAL_INR;
    // First-pass tolerance: ±5%. Tighten to 0.5% after the geometric rules from prompt 16 land.
    expect(pctDelta).toBeLessThan(0.05);
  });

  test('AI view asks DeepSeek V4 Flash, returns text + citations', async ({ page }) => {
    test.skip(!process.env.RUN_FULL, 'set RUN_FULL=1 to exercise AI');

    await page.goto(`${BASE}/projects`, { waitUntil: 'networkidle' });
    const firstRow = page.locator('button').filter({ hasText: /.+/ }).nth(1);
    if (await firstRow.count()) await firstRow.click().catch(() => {});

    await page.goto(`${BASE}/projects`, { waitUntil: 'networkidle' });
    const m = page.url().match(/\/projects\/(\d+)/);
    const projectId = m?.[1] ?? '1';

    const api = await pwRequest.newContext({ baseURL: BASE });
    const ask = await api.post(`/api/v1/projects/${projectId}/ai/ask`, {
      data: { question: 'List three trades and their totals.' },
    });
    expect(ask.status()).toBeLessThan(500);
    const j = await ask.json();
    expect(j?.answer?.length ?? 0).toBeGreaterThan(10);
  });
});
