// k6 load test — the Monday 06:00–08:00 profile: 50 concurrent runs + 30 chat sessions.
// Measures latency AND the cost of a busy morning (notional cost from /admin/cost).
//   k6 run tests/load/monday_peak.js -e BASE=http://localhost:8000
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend } from 'k6/metrics';

const BASE = __ENV.BASE || 'http://localhost:8000';
const firstToken = new Trend('chat_first_token_ms');

export const options = {
  scenarios: {
    runs: { executor: 'constant-vus', vus: 50, duration: '10m', exec: 'runs' },
    chat: { executor: 'constant-vus', vus: 30, duration: '10m', exec: 'chat' },
  },
  thresholds: {
    'http_req_failed': ['rate<0.01'],
    'http_req_duration{kind:api}': ['p(95)<500'],
    'chat_first_token_ms': ['p(95)<2500'],   // SLO: chat p95 first token < 2.5 s
  },
};

export function setup() {
  const login = (email) => http.post(`${BASE}/auth/dev-login`, JSON.stringify({ email }),
    { headers: { 'Content-Type': 'application/json' } }).json('access_token');
  return { am: login('jordan@brightwave.example'), admin: login('admin@brightwave.example') };
}

const brands = ['urban-roast', 'fitely'];

export function runs(data) {
  const h = { headers: { Authorization: `Bearer ${data.am}`, 'Content-Type': 'application/json' }, tags: { kind: 'api' } };
  const brand = brands[__VU % brands.length];
  const r = http.post(`${BASE}/runs`, JSON.stringify({ brand_id: brand }), h);
  check(r, { 'run accepted': (x) => x.status === 202 || x.status === 429 });
  http.get(`${BASE}/brands/${brand}/summary`, h);
  sleep(5);
}

export function chat(data) {
  const h = { headers: { Authorization: `Bearer ${data.am}`, 'Content-Type': 'application/json' } };
  const t0 = Date.now();
  const r = http.post(`${BASE}/chat`, JSON.stringify({
    brand_id: brands[__VU % brands.length], session_id: `load-${__VU}`, question: 'What was spend last week?' }), h);
  firstToken.add(r.timings.waiting || (Date.now() - t0));
  check(r, { 'chat ok': (x) => x.status === 200 });
  sleep(3);
}

export function teardown(data) {
  const c = http.get(`${BASE}/admin/cost`, { headers: { Authorization: `Bearer ${data.admin}` } }).json();
  console.log(`notional AI cost of this busy morning: $${c.total_usd}`);
}
