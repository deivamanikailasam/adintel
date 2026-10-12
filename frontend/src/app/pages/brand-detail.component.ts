import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { Router, RouterLink } from '@angular/router';
import { ApiService } from '../core/api.service';
import { AuthService } from '../core/auth.service';

@Component({
  selector: 'app-brand-detail',
  standalone: true,
  imports: [RouterLink, DatePipe, DecimalPipe],
  template: `
    @if (summary(); as s) {
      <div class="row"><h1>{{ s.brand.name }}</h1>
        @if (auth.hasRole('account_manager', 'senior_account_manager', 'head_of_performance')) {
          <button class="primary" (click)="runNow()" [disabled]="busy()">Run now</button>
        }
        @if (error()) { <span class="error">{{ error() }}</span> }
      </div>
      <p class="muted">{{ s.brand.platforms.join(' · ') }} · tone "{{ s.brand.profile.tone_cluster }}" ·
        max change {{ s.rules?.max_single_change_pct }}% · {{ s.rules?.suppressions?.length || 0 }} learned rule(s)</p>

      <h2>Open anomalies</h2>
      <div class="panel"><table>
        <tr><th>Campaign</th><th>Metric</th><th>Observed vs expected</th><th>Normal range</th><th>Severity</th><th></th></tr>
        @for (a of s.open_anomalies; track a.anomaly_id) {
          <tr><td>{{ a.entity_name }} <span class="muted">({{ a.platform }})</span></td><td>{{ a.metric }}</td>
            <td>{{ a.observed | number:'1.2-2' }} vs {{ a.expected | number:'1.2-2' }} ({{ a.deviation_pct }}%, {{ a.days }}d)</td>
            <td>{{ a.lower | number:'1.2-2' }} – {{ a.upper | number:'1.2-2' }}</td>
            <td><span class="badge">{{ a.severity }}</span></td>
            <td><select #r><option value="planned_promo">planned promo</option><option value="seasonal">seasonal</option>
                <option value="noise">noise</option><option value="known_tracking_change">tracking change</option></select>
                <button (click)="dismiss(a.anomaly_id, r.value)">Dismiss</button></td></tr>
        } @empty { <tr><td colspan="6" class="muted">None</td></tr> }
      </table></div>

      <h2>Runs</h2>
      <div class="panel"><table>
        <tr><th>Run</th><th>Status</th><th>Path</th><th>Period</th><th>Steps</th><th>Notional cost</th><th>Created</th></tr>
        @for (r of s.runs; track r.run_id) {
          <tr><td><a [routerLink]="['/runs', r.run_id]">{{ r.run_id }}</a></td>
            <td><span class="badge {{ r.status }}">{{ r.status }}</span></td><td>{{ r.path || '—' }}</td>
            <td>{{ r.period_start }} → {{ r.period_end }}</td><td>{{ r.usage?.steps ?? '—' }}</td>
            <td>{{ r.usage ? ('$' + (r.usage.cost_usd | number:'1.4-4')) : '—' }}</td>
            <td>{{ r.created_at | date:'short' }}</td></tr>
        }
      </table></div>
      @if (s.latest_report) { <p><a [routerLink]="['/reports', s.latest_report.report_id]">Latest report →</a></p> }
    }
  `,
})
export class BrandDetailComponent implements OnInit {
  @Input() brandId = '';
  private api = inject(ApiService);
  private router = inject(Router);
  auth = inject(AuthService);
  summary = signal<any>(null);
  busy = signal(false);
  error = signal('');

  ngOnInit(): void { this.load(); }
  load(): void { this.api.brandSummary(this.brandId).subscribe(s => this.summary.set(s)); }

  runNow(): void {
    this.busy.set(true);
    this.api.startRun(this.brandId).subscribe({
      next: r => this.router.navigate(['/runs', r.run_id]),
      error: e => { this.error.set(e.status === 423 ? 'Kill switch engaged' : e.error?.detail ?? 'Could not start'); this.busy.set(false); },
    });
  }

  dismiss(id: string, reason: string): void { this.api.dismiss(id, reason).subscribe(() => this.load()); }
}
