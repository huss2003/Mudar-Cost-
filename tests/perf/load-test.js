import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:80';
const TOKEN = __ENV.TOKEN || 'mock-token';

const headers = {
  'Authorization': `Bearer ${TOKEN}`,
  'Content-Type': 'application/json',
};

const errorRate = new Rate('errors');

export const options = {
  stages: [
    { duration: '30s', target: 10 },  // ramp up
    { duration: '1m', target: 25 },   // sustain
    { duration: '30s', target: 50 },  // peak
    { duration: '30s', target: 0 },   // ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'], // 95% under 2s
    errors: ['rate<0.1'],              // <10% errors
  },
};

// ── Warmup: trigger compute-quantities ────────────────────────────
export function setup() {
  // Create a test project and drawing via API
  const projRes = http.post(`${BASE_URL}/api/v1/projects`, JSON.stringify({
    name: 'Perf Test', client_name: 'K6', location: 'Mumbai',
  }), { headers });
  check(projRes, { 'project created': (r) => r.status === 201 });
  const projectId = projRes.json('id');

  // Trigger compute
  http.post(`${BASE_URL}/api/v1/projects/${projectId}/compute-quantities`, null, { headers });

  return { projectId };
}

// ── Main load test ────────────────────────────────────────────────
export default function (data) {
  const pid = data.projectId;

  // 1. GET BOQ
  const boqRes = http.get(`${BASE_URL}/api/v1/projects/${pid}/boq`, { headers });
  check(boqRes, { 'boq fetched': (r) => r.status === 200 });
  errorRate.add(boqRes.status !== 200);

  // 2. GET BOQ summary
  const summaryRes = http.get(`${BASE_URL}/api/v1/projects/${pid}/boq/summary`, { headers });
  check(summaryRes, { 'summary fetched': (r) => r.status === 200 });

  // 3. Get materials for a BOQ item
  const itemsRes = http.get(`${BASE_URL}/api/v1/projects/${pid}/boq`, { headers });
  if (itemsRes.status === 200) {
    const items = itemsRes.json();
    const trades = items?.trades || [];
    for (const trade of trades.slice(0, 2)) {
      for (const item of (trade.items || []).slice(0, 3)) {
        const matRes = http.get(
          `${BASE_URL}/api/v1/boq-items/${item.id}/materials`,
          { headers }
        );
        check(matRes, { 'materials fetched': (r) => r.status === 200 });

        // Select the first material
        const mats = matRes.json();
        if (Array.isArray(mats) && mats.length > 0) {
          const selectRes = http.post(
            `${BASE_URL}/api/v1/boq-items/${item.id}/select-material`,
            JSON.stringify({ material_id: mats[0].material_id }),
            { headers }
          );
          check(selectRes, { 'material selected': (r) => r.status === 200 });
        }
      }
    }
  }

  // 4. GET versions list
  const versRes = http.get(`${BASE_URL}/api/v1/projects/${pid}/versions`, { headers });
  check(versRes, { 'versions fetched': (r) => r.status === 200 });

  // 5. AI ask (mock mode — fast)
  const aiRes = http.post(`${BASE_URL}/api/v1/projects/${pid}/ask`,
    JSON.stringify({ question: 'What is the total cost?', stream: false }),
    { headers }
  );
  check(aiRes, { 'ai asked': (r) => r.status === 200 });

  sleep(1);
}

// ── Teardown ──────────────────────────────────────────────────────
export function teardown(data) {
  if (data?.projectId) {
    http.del(`${BASE_URL}/api/v1/projects/${data.projectId}`, null, { headers });
  }
}
