import { Component, Input, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { DecimalPipe, JsonPipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';
import { ApiService } from '../core/api.service';
import { Run, StepEvent } from '../core/models';

/** Live timeline (SSE) + the explainability trace: decisions, steps, prompts, sources and audit. */
@Component({
  selector: 'app-run-detail',
  standalone: true,
  imports: [RouterLink, DecimalPipe, JsonPipe],
  template: `
    @if (run(); as r) {
      <div class="row"><h1>{{ r.brand_name }} · {{ r.period_start }} → {{ r.period_end }}</h1>
        <span class="badge {{ r.status }}">{{ r.status }}</span>
        @if (r.health === 'degraded') { <span class="badge degraded">degraded</span> }</div>
      @if (r.abort_reason) { <div class="panel error">✋ {{ r.abort_reason }}</div> }
      <p class="muted">Run {{ r.run_id }} · trigger {{ r.trigger }} ·
        @if (r.usage) { {{ r.usage.steps }} steps · {{ r.usage.tokens_in + r.usage.tokens_out }} tokens ·
          \${{ r.usage.cost_usd | number:'1.4-4' }} notional }
        @if (r.report_id) { · <a [routerLink]="['/reports', r.report_id]">report</a> }</p>
    }
    <h2>Live progress</h2>
    <div class="panel"><ol class="timeline" aria-live="polite" aria-label="Run progress">
      @for (e of events(); track $index) {
        <li><strong>{{ e.agent || e.kind }}</strong> <span class="muted">{{ e.summary }}</span>
          @if (e.cost_usd !== undefined) { <span class="muted">· {{ e.steps }} steps · \${{ e.cost_usd | number:'1.4-4' }}</span> }</li>
      } @empty { <li class="muted">Waiting for the worker…</li> }
    </ol></div>

    @if (trace(); as t) {
      <h2>Why — orchestrator decisions</h2>
      <div class="panel"><table><tr><th>Step</th><th>Next</th><th>Decided by</th><th>Reasoning</th></tr>
        @for (d of t.decisions; track $index) {
          <tr><td>{{ d.step }}</td><td>{{ d.next_action }}</td><td><span class="badge">{{ d.decided_by }}</span></td><td>{{ d.reasoning }}</td></tr>
        }</table></div>
      @if (t.degradations.length) {
        <h2>Degradations (disclosed in the report)</h2>
        <div class="panel"><ul>@for (d of t.degradations; track $index) { <li><strong>{{ d.code }}</strong> — {{ d.client_caveat || d.detail }}</li> }</ul></div>
      }
      @if (t.root_causes.length) {
        <h2>Root cause</h2>
        @for (rc of t.root_causes; track $index) {
          <div class="panel"><p>{{ rc.summary }} <span class="badge">confidence {{ rc.confidence }}</span></p>
            <ul>@for (h of rc.hypotheses; track $index) { <li><strong>{{ h.name }}</strong>: {{ h.verdict }} — {{ h.evidence }}</li> }</ul>
            @if (rc.queries_run.length) { <p class="muted">Sandboxed queries run:</p><pre>{{ rc.queries_run.join('\\n') }}</pre> }
          </div>
        }
      }
      <h2>Model calls ({{ t.llm_calls.length }})</h2>
      <div class="panel"><table><tr><th>Agent</th><th>Tier / model</th><th>Status</th><th>Tokens</th><th>Prompt</th></tr>
        @for (c of t.llm_calls; track c.call_id) {
          <tr><td>{{ c.agent }}</td><td>{{ c.tier }}<br><span class="muted">{{ c.model_id }}</span></td>
            <td><span class="badge {{ c.status === 'ok' ? 'ok' : 'degraded' }}">{{ c.status }}</span> #{{ c.attempt }}</td>
            <td>{{ c.tokens_in }} / {{ c.tokens_out }}</td>
            <td><button (click)="open.set(open() === c.call_id ? null : c.call_id)">{{ open() === c.call_id ? 'hide' : 'show' }}</button></td></tr>
          @if (open() === c.call_id) {
            <tr><td colspan="5"><p class="muted">Prompt (sha {{ c.prompt_hash.slice(0, 12) }}) — exactly what the model saw:</p>
              <pre>{{ c.prompt | json }}</pre><p class="muted">Response:</p><pre>{{ c.response }}</pre></td></tr>
          }
        }</table></div>
      <h2>Retrieved sources</h2>
      <div class="panel"><ul>@for (s of t.retrieved_sources; track s.chunk_id) { <li><strong>{{ s.doc_title }}</strong> — {{ s.heading }} <span class="muted">({{ s.doc_type }})</span></li> }
        @empty { <li class="muted">None</li> }</ul></div>
      <h2>Audit trail</h2>
      <div class="panel"><table><tr><th>#</th><th>Action</th><th>Actor</th><th>Hash</th></tr>
        @for (a of t.audit; track a.seq) { <tr><td>{{ a.seq }}</td><td>{{ a.action }}</td><td>{{ a.actor_id }}</td><td class="muted">{{ a.hash.slice(0, 16) }}…</td></tr> }
      </table></div>
    }
  `,
})
export class RunDetailComponent implements OnInit, OnDestroy {
  @Input() runId = '';
  private api = inject(ApiService);
  run = signal<Run | null>(null);
  events = signal<StepEvent[]>([]);
  trace = signal<any>(null);
  open = signal<string | null>(null);
  private sub?: Subscription;

  ngOnInit(): void {
    this.refresh();
    this.sub = this.api.runEvents(this.runId).subscribe({
      next: e => {
        if (e.kind !== 'keep-alive') this.events.update(xs => [...xs, e]);
        if (e.kind === 'run_finished') this.refresh();
      },
      complete: () => this.refresh(),
    });
  }

  refresh(): void {
    this.api.run(this.runId).subscribe(r => this.run.set(r));
    this.api.trace(this.runId).subscribe(t => this.trace.set(t));
  }

  ngOnDestroy(): void { this.sub?.unsubscribe(); }
}
