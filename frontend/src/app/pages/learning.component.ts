import { Component, OnInit, inject, signal } from '@angular/core';
import { DecimalPipe, KeyValuePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../core/api.service';
import { AuthService } from '../core/auth.service';

/** Learning loop and rollout: weekly triage, 14-day outcomes of executed changes, feature flags. */
@Component({
  selector: 'app-learning',
  standalone: true,
  imports: [FormsModule, DecimalPipe, KeyValuePipe],
  template: `
    <h1>Learning &amp; rollout</h1>
    <p class="muted">What the system learned from last week, whether approved changes worked, and which capabilities are switched on.</p>

    <h2>Weekly triage</h2>
    <div class="panel">
      <div class="row"><label>Window
        <select [(ngModel)]="days" name="days" (ngModelChange)="loadTriage()">
          <option [ngValue]="7">7 days</option><option [ngValue]="14">14 days</option><option [ngValue]="30">30 days</option>
        </select></label></div>
      @if (triage(); as t) {
        <h3>Suggested actions</h3>
        <ul class="actions">@for (a of t.actions; track $index) { <li>{{ a }}</li> }</ul>
        <div class="grid">
          <div><strong>{{ t.runs.total }}</strong> runs
            <table>@for (kv of t.runs.by_status | keyvalue; track kv.key) { <tr><td><span class="badge {{ kv.key }}">{{ kv.key }}</span></td><td>{{ kv.value }}</td></tr> }</table></div>
          <div><strong>Human decisions</strong>
            <table>@for (kv of t.decisions | keyvalue; track kv.key) { <tr><td>{{ kv.key }}</td><td>{{ kv.value }}</td></tr> }</table>
            <p class="muted">Approved ÷ proposed: {{ t.average_approved_to_proposed_ratio ?? '—' }}</p></div>
          <div><strong>Rejection reasons</strong>
            <table>@for (kv of t.rejection_reasons | keyvalue; track kv.key) { <tr><td>{{ kv.key }}</td><td>{{ kv.value }}</td></tr> } @empty { <tr><td class="muted">none</td></tr> }</table></div>
          <div><strong>Degradations</strong>
            <table>@for (kv of t.degradations | keyvalue; track kv.key) { <tr><td>{{ kv.key }}</td><td>{{ kv.value }}</td></tr> } @empty { <tr><td class="muted">none</td></tr> }</table></div>
        </div>
        <p class="muted">Report ratings: {{ t.report_ratings.count }} (average {{ t.report_ratings.average ?? '—' }}, {{ t.report_ratings.low }} rated ≤ 2) ·
          Guardrail blocks: {{ t.guardrail_blocks }} · AI cost: \${{ t.ai_cost_usd | number:'1.2-2' }}</p>
      }
    </div>

    <h2>Did approved changes work? (14 days after execution)</h2>
    <div class="panel">
      <table><tr><th>Recommendation</th><th>Brand</th><th>Executed</th><th>CPA before → after</th><th>Predicted</th><th>Actual</th><th>Verdict</th></tr>
        @for (o of outcomes(); track o.recommendation_id) {
          <tr><td class="muted">{{ o.recommendation_id }}</td><td>{{ o.brand_id }}</td><td>{{ o.executed_on }}</td>
            <td>{{ o.cpa_before ?? '—' }} → {{ o.cpa_after ?? '—' }}</td>
            <td>{{ o.predicted_low_pct ?? '—' }}% to {{ o.predicted_high_pct ?? '—' }}%</td>
            <td>{{ o.actual_pct === null ? '—' : (o.actual_pct | number:'1.1-1') + '%' }}</td>
            <td><span class="badge {{ verdictClass(o.verdict) }}">{{ o.verdict }}</span></td></tr>
        } @empty { <tr><td colspan="7" class="muted">No change has been executed long enough ago to measure yet.</td></tr> }
      </table>
    </div>

    <h2>Feature flags</h2>
    <div class="panel">
      <p class="muted">A flag is a planned rollout dial, not an emergency brake (that is the kill switch). A disabled agent is skipped visibly and the client report says what was not done.</p>
      <div class="row"><label>Show effective values for brand <input [(ngModel)]="brand" name="brand" placeholder="(tenant-wide)" (change)="loadFlags()"></label></div>
      @if (flags(); as f) {
        <table><tr><th>Flag</th><th>Default</th><th>Effective</th></tr>
          @for (kv of f.effective | keyvalue; track kv.key) {
            <tr><td>{{ kv.key }}</td><td>{{ f.defaults[$any(kv.key)] ? 'on' : 'off' }}</td>
              <td><span class="badge {{ kv.value ? 'ok' : 'failed' }}">{{ kv.value ? 'on' : 'off' }}</span></td></tr> }
        </table>
        @if (f.overrides.length) {
          <h3>Overrides</h3>
          <table><tr><th>Flag</th><th>Scope</th><th>Value</th><th>Reason</th><th>By</th><th>When</th></tr>
            @for (o of f.overrides; track o.flag + (o.brand_id || '*')) {
              <tr><td>{{ o.flag }}</td><td>{{ o.brand_id || 'tenant' }}</td><td>{{ o.enabled ? 'on' : 'off' }}</td>
                <td>{{ o.reason }}</td><td>{{ o.actor_id }}</td><td class="muted">{{ o.updated_at }}</td></tr> }
          </table>
        }
        @if (auth.hasRole('admin')) {
          <form class="row change" (ngSubmit)="save()">
            <select [(ngModel)]="flag" name="flag">@for (kv of f.defaults | keyvalue; track kv.key) { <option [value]="kv.key">{{ kv.key }}</option> }</select>
            <input [(ngModel)]="flagBrand" name="flagBrand" placeholder="brand id (blank = tenant-wide)">
            <label><input type="checkbox" [(ngModel)]="enabled" name="enabled"> enabled</label>
            <input [(ngModel)]="reason" name="reason" placeholder="reason (audited)" required>
            <button class="primary" [disabled]="!reason || !flag">Apply</button>
          </form>
          @if (error()) { <p class="error">{{ error() }}</p> }
        }
      }
    </div>
  `,
  styles: [`.actions li { margin: .3rem 0; } h3 { font-size: .95rem; margin: 1rem 0 .4rem; } .change { margin-top: 1rem; }`],
})
export class LearningComponent implements OnInit {
  private api = inject(ApiService);
  auth = inject(AuthService);
  triage = signal<any>(null);
  outcomes = signal<any[]>([]);
  flags = signal<any>(null);
  error = signal('');
  days = 7; brand = ''; flag = 'agent.optimizer'; flagBrand = ''; enabled = false; reason = '';

  ngOnInit(): void {
    this.loadTriage();
    this.api.outcomes().subscribe(o => this.outcomes.set(o));
    this.loadFlags();
  }
  loadTriage(): void { this.api.triage(this.days).subscribe(t => this.triage.set(t)); }
  loadFlags(): void { this.api.flags(this.brand || undefined).subscribe(f => this.flags.set(f)); }
  verdictClass(v: string): string {
    return { within_range: 'ok', better_than_expected: 'ok', improved_less_than_expected: 'degraded', worsened: 'failed' }[v] ?? '';
  }
  save(): void {
    this.error.set('');
    this.api.setFlag(this.flag, this.enabled, this.reason, this.flagBrand).subscribe({
      next: () => { this.reason = ''; this.loadFlags(); },
      error: e => this.error.set(e?.error?.detail ?? 'could not change the flag'),
    });
  }
}
