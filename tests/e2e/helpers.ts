/**
 * auto-cost-engine E2E Tests — Shared helpers & utilities
 *
 * Provides reusable functions for:
 * - Keycloak token acquisition (direct grant & browser redirect)
 * - Project creation via DB
 * - DXF upload via API
 * - BOQ computation & polling
 * - Material operations
 * - AI queries & anomaly detection
 * - Proposal generation
 */

import { APIRequestContext, Page } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const KEYCLOAK_BASE = process.env.KEYCLOAK_URL || 'http://localhost:8080';
export const KEYCLOAK_REALM = 'jasfo';
export const KEYCLOAK_CLIENT = 'estimation-web';
export const KEYCLOAK_USER = process.env.KEYCLOAK_USER || 'test@jasfo.com';
export const KEYCLOAK_PASS = process.env.KEYCLOAK_PASS || 'test1234';

export const API_BASE = '/api/v1';
export const DB_HOST = process.env.DB_HOST || 'localhost';
export const DB_PORT = process.env.DB_PORT || '5432';
export const DB_NAME = process.env.DB_NAME || 'estimation';
export const DB_USER = process.env.DB_USER || 'estimation';
export const DB_PASS = process.env.DB_PASS || 'estimation_secret_2024';

// Resolve project root from the current module's location
// helpers.ts lives in tests/e2e/, project root is two levels up
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
export const PROJECT_ROOT = path.resolve(__dirname, '..', '..');
export const FIXTURE_DXF = path.join(
  PROJECT_ROOT,
  'backend',
  'tests',
  'fixtures',
  'sample_floor_plan.dxf',
);

// ---------------------------------------------------------------------------
// Keycloak helpers
// ---------------------------------------------------------------------------

/**
 * Obtain tokens via Keycloak direct grant (resource owner password flow).
 * Returns { access_token, refresh_token } or throws.
 */
export async function getKeycloakTokenDirect(): Promise<{
  access_token: string;
  refresh_token: string;
}> {
  const url = `${KEYCLOAK_BASE}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token`;
  const body = new URLSearchParams({
    grant_type: 'password',
    client_id: KEYCLOAK_CLIENT,
    username: KEYCLOAK_USER,
    password: KEYCLOAK_PASS,
  });

  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Keycloak direct grant failed (${resp.status}): ${text}`);
  }

  const json = await resp.json();
  return {
    access_token: json.access_token,
    refresh_token: json.refresh_token || '',
  };
}

/**
 * Decode a JWT payload without verification (for extracting user info).
 */
export function decodeJwt(token: string): Record<string, unknown> {
  const parts = token.split('.');
  if (parts.length !== 3) throw new Error('Invalid JWT format');
  return JSON.parse(Buffer.from(parts[1], 'base64').toString('utf-8'));
}

/**
 * Build the auth-storage JSON that the Zustand persist middleware expects.
 */
export function buildAuthStorage(token: string, refreshToken: string): string {
  const payload = decodeJwt(token);
  const realmAccess = (payload.realm_access as { roles?: string[] }) || {};
  const user = {
    sub: payload.sub || '',
    email: payload.email || '',
    name: payload.name || payload.preferred_username || payload.email || '',
    roles: realmAccess.roles || [],
  };
  const store = {
    state: {
      token,
      refreshToken,
      user,
      isAuthenticated: true,
    },
    version: 0,
  };
  return JSON.stringify(store);
}

/**
 * Inject Keycloak tokens into the browser's localStorage (bypasses the
 * full redirect flow).  Also sets the Authorization header for axios.
 */
export async function injectKeycloakSession(
  page: Page,
  token: string,
  refreshToken: string,
): Promise<void> {
  const storage = buildAuthStorage(token, refreshToken);
  await page.evaluate(
    ({ key, val }) => {
      localStorage.setItem(key, val);
    },
    { key: 'auth-storage', val: storage },
  );
}

// ---------------------------------------------------------------------------
// Database helpers
// ---------------------------------------------------------------------------

/**
 * Create a test project in the database.  Uses the PostgreSQL running on
 * the host (localhost:5432) which is the same DB the docker-compose stack
 * exposes.  Returns the project ID.
 *
 * Falls back to trying project_id=1 if psql isn't available or the insert
 * fails.
 */
export async function ensureTestProject(): Promise<number> {
  // First try creating via psql
  try {
    const { execSync } = await import('child_process');
    const sql = [
      'INSERT INTO projects (id, name, status, created_by, is_deleted)',
      "VALUES (9999, 'E2E Test Project', 'draft', 1, false)",
      'ON CONFLICT (id) DO UPDATE SET is_deleted = false',
      'RETURNING id',
    ].join(' ');
    const cmd = [
      'psql',
      '-h', DB_HOST,
      '-p', DB_PORT,
      '-U', DB_USER,
      '-d', DB_NAME,
      '-tAc', sql,
    ].join(' ');

    const out = execSync(cmd, {
      env: { ...process.env, PGPASSWORD: DB_PASS },
      timeout: 10000,
    });
    const id = parseInt(out.toString().trim(), 10);
    if (!isNaN(id)) return id;
  } catch {
    // psql might not be installed — try project 1
  }

  // Fallback: try project 1 (may exist from dev/seed data)
  return 1;
}

// ---------------------------------------------------------------------------
// API helpers (via Playwright's APIRequestContext)
// ---------------------------------------------------------------------------

/** Upload a DXF file and return the drawing ID + job_id. */
export async function uploadDxf(
  api: APIRequestContext,
  projectId: number,
  dxfPath: string,
): Promise<{ drawingId: number; jobId: string | null }> {
  const fs = await import('fs');
  const fileBuffer = fs.readFileSync(dxfPath);
  const fileName = path.basename(dxfPath);

  const resp = await api.post(`${API_BASE}/drawings`, {
    multipart: {
      file: {
        name: fileName,
        mimeType: 'application/dxf',
        buffer: fileBuffer,
      },
    },
    params: { project_id: projectId },
  });

  if (!resp.ok()) {
    const err = await resp.text();
    throw new Error(`DXF upload failed (${resp.status()}): ${err}`);
  }

  const body = await resp.json();
  return { drawingId: body.drawing_id, jobId: body.job_id || null };
}

/** Poll drawing status until it's 'processed' or 'analyzed'. */
export async function waitForDrawingReady(
  api: APIRequestContext,
  drawingId: number,
  timeoutMs = 120_000,
  intervalMs = 3000,
): Promise<string> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const resp = await api.get(`${API_BASE}/drawings/${drawingId}/status`);
    if (!resp.ok()) {
      throw new Error(`Status check failed: ${await resp.text()}`);
    }
    const body = await resp.json();
    const status: string = body.status || '';
    if (['analyzed', 'processed', 'completed'].includes(status)) {
      return status;
    }
    if (['failed', 'error'].includes(status)) {
      throw new Error(`Drawing processing failed: ${JSON.stringify(body)}`);
    }
    await sleep(intervalMs);
  }
  throw new Error(`Drawing ${drawingId} not ready after ${timeoutMs}ms`);
}

/** Fetch detected objects for a drawing. */
export async function getDrawingObjects(
  api: APIRequestContext,
  drawingId: number,
): Promise<unknown[]> {
  const resp = await api.get(`${API_BASE}/drawings/${drawingId}/objects`);
  if (!resp.ok()) throw new Error(`Objects fetch failed: ${await resp.text()}`);
  return resp.json() as unknown as unknown[];
}

/** Compute BOQ for a project and poll until done. */
export async function computeBoq(
  api: APIRequestContext,
  projectId: number,
  timeoutMs = 120_000,
  intervalMs = 3000,
): Promise<void> {
  // Dispatch computation
  const resp = await api.post(
    `${API_BASE}/projects/${projectId}/compute-quantities`,
  );
  if (!resp.ok()) {
    throw new Error(`BOQ compute dispatch failed: ${await resp.text()}`);
  }

  // Poll BOQ until items appear
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const boqResp = await api.get(`${API_BASE}/projects/${projectId}/boq`);
    if (!boqResp.ok()) {
      // 404 is fine while BOQ is being computed
      await sleep(intervalMs);
      continue;
    }
    const boq = await boqResp.json();
    if (boq.groups && boq.groups.length > 0) {
      return; // done
    }
    if (boq.status === 'not_computed') {
      await sleep(intervalMs);
      continue;
    }
    // Any other shape — done
    return;
  }
  throw new Error(`BOQ computation not finished after ${timeoutMs}ms`);
}

/** Fetch available materials for a BOQ item. */
export async function getBoqItemMaterials(
  api: APIRequestContext,
  boqItemId: number,
): Promise<unknown[]> {
  const resp = await api.get(`${API_BASE}/boq-items/${boqItemId}/materials`);
  if (!resp.ok()) {
    throw new Error(`Materials fetch failed: ${await resp.text()}`);
  }
  return resp.json() as unknown as unknown[];
}

/** Select a material for a BOQ item. */
export async function selectBoqItemMaterial(
  api: APIRequestContext,
  boqItemId: number,
  materialId: number,
): Promise<void> {
  const resp = await api.post(
    `${API_BASE}/boq-items/${boqItemId}/select-material`,
    { data: { material_id: materialId } },
  );
  if (!resp.ok()) {
    throw new Error(`Material selection failed: ${await resp.text()}`);
  }
}

/** Ask AI a question about the project. */
export async function askAi(
  api: APIRequestContext,
  projectId: number,
  question: string,
): Promise<Record<string, unknown>> {
  const resp = await api.post(`${API_BASE}/projects/${projectId}/ask`, {
    data: { question, stream: false },
  });
  if (!resp.ok()) {
    throw new Error(`AI ask failed: ${await resp.text()}`);
  }
  return (await resp.json()) as Record<string, unknown>;
}

/** Detect anomalies for a project. */
export async function detectAnomalies(
  api: APIRequestContext,
  projectId: number,
): Promise<Record<string, unknown>> {
  const resp = await api.post(
    `${API_BASE}/projects/${projectId}/anomalies`,
  );
  if (!resp.ok()) {
    throw new Error(`Anomaly detection failed: ${await resp.text()}`);
  }
  return (await resp.json()) as Record<string, unknown>;
}

/** Generate a proposal PDF for a project. */
export async function generateProposal(
  api: APIRequestContext,
  projectId: number,
): Promise<Buffer> {
  const resp = await api.post(
    `${API_BASE}/projects/${projectId}/proposal`,
  );
  if (!resp.ok()) {
    throw new Error(`Proposal generation failed: ${await resp.text()}`);
  }
  return Buffer.from(await resp.body());
}

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Build an authorized API context using the stored token. */
export async function getAuthorizedApiContext(
  page: Page,
): Promise<APIRequestContext> {
  const token = await page.evaluate(() => {
    const raw = localStorage.getItem('auth-storage');
    if (!raw) return null;
    try {
      return JSON.parse(raw).state?.token || null;
    } catch {
      return null;
    }
  });

  const { request } = await import('@playwright/test');
  const ctx = await request.newContext({
    baseURL: 'http://localhost:5173',
    extraHTTPHeaders: token
      ? { Authorization: `Bearer ${token}` }
      : {},
  });
  return ctx;
}
