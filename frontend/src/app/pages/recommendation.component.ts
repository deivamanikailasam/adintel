import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../core/api.service';
import { AuthService } from '../core/auth.service';

/** The approval screen: fast and evidence-rich, so the gate is used properly rather than rubber-stamped. */
@Component({
  selector: 'app-recommendation',
  standalone: true,
  imports: [FormsModule, RouterLink, DatePipe, DecimalPipe],
  template: `
    @if (d(); as x) {
      @let r = x.recommendation;
      <div class="row"><h1>{{ r.action_type.replace('_', ' ') }} · {{ r.brand_id }}</h1>
        <span class="badge {{ r.status }}">{{ r.status }}</span><span class="badge">risk {{ r.risk }}</span></div>
      <div class="panel">
        <p><strong>Proposal:</strong> move <strong>\${{ r.amount_usd_per_day | number:'1.2-2' }}/day</strong>
          @if (r.source_entity_id) { from <code>{{ r.source_entity_id }}</code> } to <code>{{ r.target_entity_id }}</code> on {{ r.platform }}.</p>
        <p><strong>Why:</strong> {{ r.rationale }}</p>
        <p><strong>Expected:</strong> {{ r.expected_impact }}
          @if (r.expected_cpa_change_pct_low !== null) { (CPA {{ r.expected_cpa_change_pct_low }}% to {{ r.expected_cpa_change_pct_high }}%) }</p>
        <p class="muted">Exposure computed by code: \${{ r.daily_exposure_usd | number:'1.2-2' }}/day · expires {{ r.expires_at | date:'medium' }} ·
          checks passed: {{ r.constraint_checks.join(', ') }} · <a [routerLink]="['/runs', r.run_id]">full trace →</a></p>
        <p class="muted">Who may approve: {{ x.approval_requirement }}</p>
      </div>
      <h2>Evidence</h2>
      <div class="panel">
        @for (rc of x.root_causes; track $index) { <p><strong>Root cause</strong> (confidence {{ rc.confidence }}): {{ rc.summary }}</p> }
        @if (x.anomaly) { <p><strong>Anomaly:</strong> {{ x.anomaly.metric }} {{ x.anomaly.observed | number:'1.2-2' }} vs expected
          {{ x.anomaly.expected | number:'1.2-2' }} (normal {{ x.anomaly.lower | number:'1.2-2' }}–{{ x.anomaly.upper | number:'1.2-2' }}) for {{ x.anomaly.days }} days</p> }
        <ul>@for (c of r.citations; track c.chunk_id) { <li><strong>{{ c.doc_title }}</strong>: <span class="muted">{{ c.snippet }}</span></li> }</ul>
      </div>
      @if (['pending_approval', 'awaiting_second_approval'].includes(r.status) && auth.hasRole('account_manager', 'senior_account_manager', 'head_of_performance')) {
        <h2>Decide</h2>
        <div class="panel">
          <div class="row">
            <label>Type the daily exposure to confirm: $ <input type="number" step="0.01" [(ngModel)]="typed" name="typed"></label>
            <label>Reduce amount (optional): $ <input type="number" step="0.01" [(ngModel)]="modified" name="modified"></label>
            <button class="primary" (click)="approve(r.recommendation_id)" [disabled]="typed === null">Approve</button>
          </div>
          <div class="row" style="margin-top: .8rem">
            <select [(ngModel)]="category" name="category" aria-label="Rejection reason">@for (c of categories(); track c) { <option [value]="c">{{ c }}</option> }</select>
            <input [(ngModel)]="note" name="note" aria-label="Rejection note" placeholder="What would you have done instead?" style="flex: 1">
            <button class="danger" (click)="reject(r.recommendation_id)">Reject</button>
          </div>
          @if (msg()) { <p [class.error]="msgError()">{{ msg() }}</p> }
        </div>
      }
      <h2>History</h2>
      <div class="panel"><ul>@for (a of x.audit; track a.seq) { <li>{{ a.at }} · {{ a.action }} · {{ a.actor_id }}
        @if (a.details?.check) { <span class="error">failed check: {{ a.details.check }}</span> }</li> }</ul></div>
    }
  `,
})
export class RecommendationComponent implements OnInit {
  @Input() recId = '';
  private api = inject(ApiService);
  auth = inject(AuthService);
  d = signal<any>(null);
  categories = signal<string[]>([]);
  typed: number | null = null;
  modified: number | null = null;
  category = 'right_diagnosis_wrong_action';
  note = '';
  msg = signal('');
  msgError = signal(false);

  ngOnInit(): void {
    this.load();
    this.api.categories().subscribe(c => this.categories.set(c.rejection));
  }

  load(): void { this.api.recommendation(this.recId).subscribe(x => this.d.set(x)); }

  approve(id: string): void {
    this.api.approve(id, Number(this.typed), this.modified ? Number(this.modified) : undefined).subscribe({
      next: r => { this.msgError.set(false); this.msg.set(`Done: ${r.status}${r.queued_for_execution ? ' — queued for the executor' : ''}`); this.load(); },
      error: e => { this.msgError.set(true); this.msg.set(`Refused (${e.error?.detail?.check}): ${e.error?.detail?.message ?? e.message}`); this.load(); },
    });
  }

  reject(id: string): void {
    this.api.reject(id, this.category, this.note).subscribe({
      next: () => { this.msg.set('Rejected — the reason feeds the weekly triage.'); this.load(); },
      error: e => { this.msgError.set(true); this.msg.set(e.error?.detail?.message ?? 'Failed'); },
    });
  }
}
