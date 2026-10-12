import { Component, OnInit, inject, signal } from '@angular/core';
import { DecimalPipe, JsonPipe, KeyValuePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../core/api.service';
import { AuthService } from '../core/auth.service';

/** Governance console: kill switches, audit chain, notional cost, model registry health, notifications. */
@Component({
  selector: 'app-admin',
  standalone: true,
  imports: [FormsModule, DecimalPipe, JsonPipe, KeyValuePipe],
  template: `
    <h1>Governance</h1>
    <div class="grid">
      <div class="panel"><h2>Audit chain</h2>
        @if (audit(); as a) { <p><span class="badge {{ a.ok ? 'ok' : 'failed' }}">{{ a.ok ? 'verified' : 'BROKEN at #' + a.broken_at_seq }}</span> {{ a.entries }} entries</p> }
        <button (click)="verify()">Verify now</button></div>
      <div class="panel"><h2>Today's notional AI cost</h2>
        @if (cost(); as c) { <p><strong>\${{ c.total_usd | number:'1.4-4' }}</strong></p>
          <table>@for (kv of c.by_agent | keyvalue; track kv.key) { <tr><td>{{ kv.key }}</td><td>\${{ $any(kv.value) | number:'1.4-4' }}</td></tr> }</table> }</div>
    </div>
    <h2>Kill switches</h2>
    <div class="panel">
      @if (auth.hasRole('admin')) {
        <form class="row" (ngSubmit)="flip()">
          <select [(ngModel)]="scope" name="scope"><option>global</option><option>tenant</option><option>brand</option><option>agent</option></select>
          <input [(ngModel)]="key" name="key" placeholder="brand id / agent name / *">
          <input [(ngModel)]="reason" name="reason" placeholder="reason (audited)" required>
          <label><input type="checkbox" [(ngModel)]="engaged" name="engaged"> engaged</label>
          <button class="danger" [disabled]="!reason">Apply</button></form>
      }
      <table><tr><th>Scope</th><th>Key</th><th>Engaged</th><th>Reason</th><th>By</th></tr>
        @for (k of switches(); track k.scope + k.key) { <tr><td>{{ k.scope }}</td><td>{{ k.key }}</td>
          <td><span class="badge {{ k.engaged ? 'failed' : 'ok' }}">{{ k.engaged }}</span></td><td>{{ k.reason }}</td><td>{{ k.actor_id }}</td></tr> }
      </table></div>
    <h2>Model registry</h2>
    <div class="panel">@if (models(); as m) {
      <table><tr><th>Tier</th><th>Model</th><th>Endpoint</th><th>Health</th><th>Fallback</th><th>Production equivalent</th></tr>
        @for (kv of m.tiers | keyvalue; track kv.key) { <tr><td>{{ kv.key }}</td><td>{{ $any(kv.value).model_id }}</td><td class="muted">{{ $any(kv.value).base_url }}</td>
          <td><span class="badge {{ m.health[$any(kv.key)]?.ok ? 'ok' : 'failed' }}">{{ m.health[$any(kv.key)]?.ok ? 'up' : 'down' }}</span></td>
          <td>{{ $any(kv.value).fallback || '— (fail closed)' }}</td><td class="muted">{{ $any(kv.value).production_equivalent }}</td></tr> }
      </table><p class="muted">Registry version {{ m.registry_version }}</p> }</div>
    <h2>Notifications</h2>
    <div class="panel"><table><tr><th>When</th><th>Severity / kind</th><th>Title</th><th>Audience</th></tr>
      @for (n of notes(); track $index) { <tr><td class="muted">{{ n.created_at }}</td><td>{{ n.severity || n.kind }}</td><td>{{ n.title }}</td><td>{{ n.audience }}</td></tr> }
    </table></div>
  `,
})
export class AdminComponent implements OnInit {
  private api = inject(ApiService);
  auth = inject(AuthService);
  audit = signal<any>(null);
  cost = signal<any>(null);
  models = signal<any>(null);
  switches = signal<any[]>([]);
  notes = signal<any[]>([]);
  scope = 'brand'; key = ''; reason = ''; engaged = true;

  ngOnInit(): void {
    this.api.killSwitches().subscribe(s => this.switches.set(s));
    this.api.cost().subscribe(c => this.cost.set(c));
    this.api.models().subscribe(m => this.models.set(m));
    this.api.notifications().subscribe(n => this.notes.set(n));
    if (this.auth.hasRole('admin')) this.verify();
  }
  verify(): void { this.api.verifyAudit().subscribe(a => this.audit.set(a)); }
  flip(): void {
    this.api.setKillSwitch(this.scope, this.key || '*', this.engaged, this.reason)
      .subscribe(() => this.api.killSwitches().subscribe(s => this.switches.set(s)));
  }
}
