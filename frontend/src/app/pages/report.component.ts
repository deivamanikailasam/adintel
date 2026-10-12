import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { ApiService } from '../core/api.service';
import { Report } from '../core/models';

/** Report viewer. Model-written text is rendered with interpolation only (escaped) — never innerHTML. */
@Component({
  selector: 'app-report',
  standalone: true,
  template: `
    @if (r(); as rep) {
      <div class="row"><h1>{{ rep.title }}</h1><span class="badge {{ rep.status }}">{{ rep.status }}</span>
        <span class="badge">{{ rep.deterministic_template ? 'template' : rep.model_tier }}</span>
        @if (rep.grounding) { <span class="badge {{ rep.grounding.passed ? 'ok' : 'failed' }}">{{ rep.grounding.numbers_checked }} numbers checked</span> }</div>
      @for (s of rep.sections; track s.key) {
        <div class="panel prose"><h2>{{ s.title }}</h2>
          @for (p of paragraphs(s.body); track $index) { <p>{{ p }}</p> }</div>
      }
      <p class="muted">{{ rep.footer }}</p>
      @if ($any(rep).disclosure) { <p class="muted" role="note">{{ $any(rep).disclosure }}</p> }
      @if ($any(rep).provenance; as pv) {
        <p class="muted">Signed {{ pv.signed_at }} · key {{ pv.key_id }} · fingerprint {{ pv.sha256.slice(0, 16) }}…
          — anyone can check it at <code>/verify/reports/{{ rep.report_id }}</code></p>
      }
      <div class="row">Rate this report:
        @for (n of [1, 2, 3, 4, 5]; track n) { <button (click)="rate(n)">{{ n }}</button> }
        @if (rated()) { <span class="muted">thanks — ratings feed the eval flywheel</span> }</div>
    }
  `,
})
export class ReportComponent implements OnInit {
  @Input() reportId = '';
  private api = inject(ApiService);
  r = signal<Report | null>(null);
  rated = signal(false);
  ngOnInit(): void { this.api.report(this.reportId).subscribe(x => this.r.set(x)); }
  paragraphs(body: string): string[] { return body.split(/\n+/).filter(Boolean); }
  rate(n: number): void { this.api.rateReport(this.reportId, n).subscribe(() => this.rated.set(true)); }
}
