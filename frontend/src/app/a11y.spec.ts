/**
 * Automated accessibility audit (axe-core, WCAG 2.0/2.1 A + AA rules) of every page, rendered with realistic
 * data so tables, forms and badges are actually on screen. Any violation fails the build; the rule results
 * feed docs/16-frontend/accessibility-conformance-report.md.
 */
import { Type, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, NEVER } from 'rxjs';
import axe from 'axe-core';
import { ApiService } from './core/api.service';
import { AuthService } from './core/auth.service';
import { AdminComponent } from './pages/admin.component';
import { ApprovalsComponent } from './pages/approvals.component';
import { BrandDetailComponent } from './pages/brand-detail.component';
import { BrandsComponent } from './pages/brands.component';
import { ChatComponent } from './pages/chat.component';
import { LearningComponent } from './pages/learning.component';
import { LoginComponent } from './pages/login.component';
import { PrivacyComponent } from './pages/privacy.component';
import { RecommendationComponent } from './pages/recommendation.component';
import { ReportComponent } from './pages/report.component';
import { RunDetailComponent } from './pages/run-detail.component';
import { AppComponent } from './app.component';

const brand = { brand_id: 'urban-roast', name: 'Urban Roast Coffee', platforms: ['meta', 'google_ads'],
  profile: { tone_cluster: 'warm', timezone: 'America/New_York', vertical: 'coffee' },
  last_run: { run_id: 'run_1', status: 'awaiting_approval', health: 'ok', finished_at: '2026-10-12T06:00:00Z', path: 'full' } };
const rec = { recommendation_id: 'rec_1', brand_id: 'urban-roast', run_id: 'run_1', action_type: 'budget_shift', platform: 'meta',
  source_entity_id: 'as_ur_b', target_entity_id: 'as_ur_a', amount_usd_per_day: 200, daily_exposure_usd: 200,
  expected_impact: 'CPA back to normal in 5–7 days', expected_cpa_change_pct_low: -34, expected_cpa_change_pct_high: -22,
  rationale: 'Reverse the platform reallocation', citations: [{ chunk_id: 'c1', doc_title: 'Playbook', snippet: 'Shift budget back…' }],
  risk: 'medium', status: 'pending_approval', expires_at: '2026-10-14T06:00:00Z', constraint_checks: ['max_change', 'blackout'],
  created_at: '2026-10-12T06:00:00Z' };
const report = { report_id: 'rpt_1', brand_id: 'urban-roast', run_id: 'run_1', title: 'Urban Roast weekly report', status: 'released',
  model_tier: 'report:warm', deterministic_template: false, footer: 'Prepared by AdIntel', disclosure: 'Drafted with AI assistance.',
  grounding: { passed: true, numbers_checked: 12, ungrounded: [] },
  provenance: { signed_at: '2026-10-12T06:01:00Z', key_id: 'abcd1234abcd1234', sha256: 'f'.repeat(64) },
  sections: [{ key: 'summary', title: 'Summary', body: 'One area needs attention.' }, { key: 'performance', title: 'Performance', body: 'You invested $4,210.' }] };
const run = { run_id: 'run_1', brand_id: 'urban-roast', brand_name: 'Urban Roast Coffee', status: 'awaiting_approval', health: 'ok',
  trigger: 'schedule', period_start: '2026-10-05', period_end: '2026-10-11', created_at: '2026-10-12T02:00:00Z', path: 'full',
  usage: { steps: 12, tokens_in: 9000, tokens_out: 2000, cost_usd: 0.12 }, degradations: [], report_id: 'rpt_1', recommendation_ids: ['rec_1'] };

const DATA: Record<string, unknown> = {
  brands: [brand],
  brandSummary: { brand, runs: [run], open_anomalies: [{ anomaly_id: 'a1', metric: 'cpa', platform: 'meta', entity_name: 'Retargeting',
    observed: 41.2, expected: 28.1, deviation_pct: 46, severity: 'high', days: 4 }], latest_report: report, rules: { max_single_change_pct: 25 } },
  recommendations: [rec],
  proposals: [{ proposal_id: 'p1', brand_id: 'urban-roast', description: 'Q4 always spikes', status: 'proposed' }],
  recommendation: { recommendation: rec, approval_requirement: 'one account manager (≤ $500/day)', root_causes: [{ confidence: 0.81, summary: 'Budget moved to an expensive ad set' }],
    anomaly: { metric: 'cpa', observed: 41.2, expected: 28.1, lower: 24, upper: 32, days: 4 }, audit: [{ seq: 1, at: 'now', action: 'recommendation.created', actor_id: 'agent:optimizer' }] },
  categories: { rejection: ['wrong_diagnosis', 'other'], dismissal: ['seasonal'] },
  report, run,
  trace: { decisions: [{ step: 1, next_action: 'analyst', decided_by: 'rule:high_severity', reasoning: 'High severity anomaly' }],
    degradations: [], llm_calls: [], retrieved_sources: [], root_causes: [], audit: [] },
  runEvents: NEVER,
  killSwitches: [{ scope: 'brand', key: 'brightwave/urban-roast', engaged: false, reason: 'test', actor_id: 'u_admin' }],
  cost: { total_usd: 0.42, by_agent: { analyst: 0.2, optimizer: 0.12 } },
  models: { registry_version: '1', tiers: { frontier: { model_id: 'qwen', base_url: 'http://127.0.0.1:8081/v1', fallback: 'small', production_equivalent: 'Bedrock' } },
    health: { frontier: { ok: true } } },
  notifications: [{ created_at: 'now', kind: 'approval_needed', title: '1 recommendation awaiting approval', audience: 'account_manager' }],
  platformAlerts: [{ alert_id: 'am1', severity: 'P2', title: 'DLQ not empty', detail: '', status: 'firing', created_at: 'now' }],
  verifyAudit: { ok: true, entries: 42 },
  triage: { actions: ['Nothing needs attention this week.'], runs: { total: 3, by_status: { completed: 3 } }, decisions: { approved: 1 },
    rejection_reasons: {}, degradations: {}, average_approved_to_proposed_ratio: null, report_ratings: { count: 0, average: null, low: 0 },
    guardrail_blocks: 0, ai_cost_usd: 0.4, outcomes: {} },
  outcomes: [{ recommendation_id: 'rec_1', brand_id: 'urban-roast', executed_on: '2026-09-20', cpa_before: 40, cpa_after: 30,
    predicted_low_pct: -34, predicted_high_pct: -22, actual_pct: -25, verdict: 'within_range' }],
  flags: { defaults: { 'agent.optimizer': true }, effective: { 'agent.optimizer': true }, overrides: [] },
  status: { status: 'degraded', messages: [{ level: 'degraded', text: 'Deep analysis is running on a backup model.' }] },
};

const apiStub = new Proxy({}, { get: (_t, name: string) => () => (name === 'runEvents' ? NEVER : of(DATA[name] ?? {})) });
const authStub = { hasRole: () => true, loggedIn: signal(true), idleWarning: signal(true), stayActive: () => undefined, me: signal({ email: 'jordan@brightwave.example', roles: ['account_manager'] }),
  token: signal('x'), loadMe: () => Promise.resolve(), startSessionWatch: () => Promise.resolve(), takeLogoutReason: () => '',
  logout: () => undefined, login: () => Promise.resolve(), loginSso: () => Promise.resolve() };

const PAGES: [string, Type<unknown>, Record<string, string>?][] = [
  ['shell', AppComponent], ['login', LoginComponent], ['brands', BrandsComponent],
  ['brand detail', BrandDetailComponent, { brandId: 'urban-roast' }], ['approvals', ApprovalsComponent],
  ['recommendation', RecommendationComponent, { recId: 'rec_1' }], ['report', ReportComponent, { reportId: 'rpt_1' }],
  ['run detail', RunDetailComponent, { runId: 'run_1' }], ['chat', ChatComponent], ['governance', AdminComponent],
  ['learning', LearningComponent], ['privacy', PrivacyComponent],
];

describe('Accessibility audit (axe-core, WCAG 2.1 A/AA)', () => {
  for (const [name, cmp, inputs] of PAGES) {
    it(`${name} page has no WCAG A/AA violations`, async () => {
      TestBed.configureTestingModule({
        imports: [cmp],
        providers: [provideRouter([]), { provide: ApiService, useValue: apiStub }, { provide: AuthService, useValue: authStub }],
      });
      const f: ComponentFixture<unknown> = TestBed.createComponent(cmp);
      for (const [k, v] of Object.entries(inputs ?? {})) f.componentRef.setInput(k, v);
      f.detectChanges();
      await new Promise(r => setTimeout(r, 0));  // not whenStable(): the shell polls /status on an interval
      f.detectChanges();
      // page components render inside <main>; give axe a document-like landmark context
      const host = document.createElement('main');
      host.appendChild(f.nativeElement);
      document.body.appendChild(host);
      const res = await axe.run(host, {
        runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
        rules: { region: { enabled: false } },
      });
      host.remove();
      f.destroy();
      const msgs = res.violations.map(v => `${v.id} (${v.impact}): ${v.help} — ${v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | ')}`);
      expect(msgs).withContext(name).toEqual([]);
      expect(res.passes.length).toBeGreaterThan(0);
    });
  }
});
