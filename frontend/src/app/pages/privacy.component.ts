import { Component, inject, signal } from '@angular/core';
import { KeyValuePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../core/api.service';

/** Data-subject requests for agency staff: export everything held about a user, or erase (pseudonymise) them. */
@Component({
  selector: 'app-privacy',
  standalone: true,
  imports: [FormsModule, KeyValuePipe],
  template: `
    <h1>Privacy requests</h1>
    <p class="muted">Both actions are written to the audit log. Erasure removes the person's name, email, roles,
      chats and free-text notes; approvals keep the opaque user id because the agency must keep a record of who
      authorised spending client money. Also disable the person in the identity provider.</p>
    <div class="panel">
      <div class="row"><input [(ngModel)]="userId" name="userId" aria-label="User id" placeholder="user id, e.g. u_jordan">
        <button (click)="export()" [disabled]="!userId">Export their data</button></div>
      @if (exported(); as x) {
        <p>Export for <strong>{{ x.profile.email }}</strong>:</p>
        <table>@for (kv of counts(x) | keyvalue; track kv.key) { <tr><td>{{ kv.key }}</td><td>{{ kv.value }}</td></tr> }</table>
        <button (click)="download(x)">Download JSON</button>
      }
    </div>
    <div class="panel">
      <h2>Erase a user</h2>
      <div class="row">
        <input [(ngModel)]="reason" name="reason" aria-label="Reason or ticket" placeholder="reason / ticket (audited)">
        <input [(ngModel)]="confirm" name="confirm" aria-label="Confirm user id" placeholder="type the user id again to confirm">
        <button class="danger" (click)="erase()" [disabled]="!userId || !reason || confirm !== userId">Erase</button>
      </div>
      @if (erased(); as e) { <p class="badge ok">done</p> <table>@for (kv of e | keyvalue; track kv.key) { <tr><td>{{ kv.key }}</td><td>{{ kv.value }}</td></tr> }</table> }
    </div>
    @if (error()) { <p class="error">{{ error() }}</p> }
  `,
})
export class PrivacyComponent {
  private api = inject(ApiService);
  userId = ''; reason = ''; confirm = '';
  exported = signal<any>(null);
  erased = signal<any>(null);
  error = signal('');

  counts(x: any): Record<string, number> {
    return Object.fromEntries(Object.entries(x).filter(([, v]) => Array.isArray(v)).map(([k, v]) => [k, (v as unknown[]).length]));
  }
  export(): void {
    this.error.set(''); this.erased.set(null);
    this.api.privacyExport(this.userId).subscribe({ next: x => this.exported.set(x), error: e => this.fail(e) });
  }
  erase(): void {
    this.error.set(''); this.exported.set(null);
    this.api.privacyErase(this.userId, this.reason).subscribe({
      next: r => { this.erased.set(r); this.confirm = ''; },
      error: e => this.fail(e),
    });
  }
  download(x: any): void {
    const url = URL.createObjectURL(new Blob([JSON.stringify(x, null, 2)], { type: 'application/json' }));
    const a = document.createElement('a');
    a.href = url; a.download = `privacy-export-${x.user_id}.json`; a.click();
    URL.revokeObjectURL(url);
  }
  private fail(e: any): void { this.error.set(e?.error?.detail ?? `request failed (${e?.status ?? 'network'})`); }
}
