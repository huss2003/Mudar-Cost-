import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './.',
  timeout: 180000,            // 3 min per test (covers Celery polling)
  expect: { timeout: 30000 }, // 30s for individual assertions
  fullyParallel: false,       // run tests sequentially (shared state)
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,                 // one worker to keep test order
  reporter: [
    ['html', { outputFolder: 'playwright-report' }],
    ['list'],
  ],
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:5173',
    headless: !process.env.HEADED && !process.env.DEBUG,
    viewport: { width: 1440, height: 900 },
    ignoreHTTPSErrors: true,
    screenshot: 'only-on-failure',
    trace: 'on-first-retry',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
