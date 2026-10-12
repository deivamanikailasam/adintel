import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { AuthService } from '../core/auth.service';
import { LearningComponent } from './learning.component';

const TRIAGE = {
  actions: ['More than 20% of measured changes made CPA worse: pause the optimizer flag and review.'],
  runs: { total: 3, by_status: { completed: 2, awaiting_approval: 1 } }, decisions: { approved: 1 },
  rejection_reasons: {}, degradations: {}, average_approved_to_proposed_ratio: null,
  report_ratings: { count: 0, average: null, low: 0 }, guardrail_blocks: 0, ai_cost_usd: 0.42, outcomes: { worsened: 1 },
};
const FLAGS = {
  defaults: { 'agent.optimizer': true, 'agent.analyst': true },
  effective: { 'agent.optimizer': false, 'agent.analyst': true },
  overrides: [{ flag: 'agent.optimizer', brand_id: null, enabled: false, reason: 'pilot', actor_id: 'u_admin', updated_at: 'now' }],
};

describe('LearningComponent', () => {
  let http: HttpTestingController;
  const setup = (admin: boolean) => {
    TestBed.configureTestingModule({
      imports: [LearningComponent],
      providers: [provideHttpClient(), provideHttpClientTesting(), { provide: AuthService, useValue: { hasRole: () => admin } }],
    });
    http = TestBed.inject(HttpTestingController);
    const f = TestBed.createComponent(LearningComponent);
    f.detectChanges();
    http.expectOne(r => r.url === '/api/admin/triage').flush(TRIAGE);
    http.expectOne('/api/admin/outcomes').flush([
      { recommendation_id: 'rec_1', brand_id: 'urban-roast', executed_on: '2026-09-20', cpa_before: 40, cpa_after: 48,
        predicted_low_pct: -34, predicted_high_pct: -22, actual_pct: 20, verdict: 'worsened' },
    ]);
    http.expectOne(r => r.url === '/api/admin/flags').flush(FLAGS);
    f.detectChanges();
    return f;
  };
  afterEach(() => http.verify());

  it('shows triage actions, graded outcomes and effective flags', () => {
    const text = (setup(false).nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('pause the optimizer flag');
    expect(text).toContain('worsened');
    expect(text).toContain('agent.optimizer');
    expect(text).not.toContain('Apply'); // only admins can change flags
  });

  it('lets an admin change a flag with an audited reason', () => {
    const f = setup(true);
    const c = f.componentInstance;
    c.flag = 'agent.optimizer'; c.enabled = true; c.reason = 'pilot over'; c.flagBrand = 'urban-roast';
    c.save();
    const req = http.expectOne('/api/admin/flags');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ flag: 'agent.optimizer', enabled: true, reason: 'pilot over', brand_id: 'urban-roast' });
    req.flush({});
    http.expectOne(r => r.url === '/api/admin/flags' && r.method === 'GET').flush(FLAGS);
  });
});
