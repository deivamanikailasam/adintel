import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../core/api.service';
import { Brand } from '../core/models';

interface Turn { role: 'user' | 'assistant'; text: string; meta?: string; blocked?: boolean; }

/** Streaming chat (SSE). Answers are about one brand; chat cannot change anything. */
@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [FormsModule],
  template: `
    <h1>Ask about a brand</h1>
    <div class="row"><select [(ngModel)]="brand" name="brand" aria-label="Brand">@for (b of brands(); track b.brand_id) { <option [value]="b.brand_id">{{ b.name }}</option> }</select>
      <span class="muted">Session {{ session }}</span></div>
    <div class="panel log" role="log" aria-live="polite" [attr.aria-busy]="busy()">
      @for (t of turns(); track $index) {
        <div class="turn {{ t.role }}"><strong>{{ t.role === 'user' ? 'You' : 'AdIntel' }}</strong>
          @if (t.meta) { <span class="muted">({{ t.meta }})</span> }
          <p [class.error]="t.blocked" [attr.role]="t.blocked ? 'alert' : null">{{ t.text }}</p></div>
      } @empty { <p class="muted">Try "What was spend last week?" (fast path) or "Why did retargeting costs rise after the budget increase?" (frontier + RAG).</p> }
    </div>
    <form class="row" (ngSubmit)="ask()"><input [(ngModel)]="q" name="q" aria-label="Your question" style="flex: 1" placeholder="Ask a question" maxlength="2000">
      <button class="primary" [disabled]="busy() || !q">Send</button></form>
  `,
  styles: [`.log { min-height: 300px; } .turn { margin: .6rem 0; } .turn p { margin: .2rem 0; white-space: pre-wrap; }`],
})
export class ChatComponent implements OnInit {
  private api = inject(ApiService);
  brands = signal<Brand[]>([]);
  turns = signal<Turn[]>([]);
  busy = signal(false);
  brand = '';
  q = '';
  session = Math.random().toString(36).slice(2, 10);

  ngOnInit(): void { this.api.brands().subscribe(b => { this.brands.set(b); this.brand = b[0]?.brand_id ?? ''; }); }

  ask(): void {
    const question = this.q.trim();
    if (!question) return;
    this.q = '';
    this.busy.set(true);
    this.turns.update(t => [...t, { role: 'user', text: question }, { role: 'assistant', text: '' }]);
    const patch = (fn: (t: Turn) => Turn) => this.turns.update(ts => [...ts.slice(0, -1), fn(ts[ts.length - 1])]);
    this.api.chat(this.brand, this.session, question).subscribe({
      next: ev => {
        if (ev.type === 'meta') patch(t => ({ ...t, meta: `${ev.route} · ${ev.cached ? 'cached' : ev.tier}` }));
        if (ev.type === 'token') patch(t => ({ ...t, text: t.text + ev.text }));
        if (ev.type === 'blocked') patch(t => ({ ...t, text: ev.replacement, blocked: true }));
        if (ev.type === 'error') patch(t => ({ ...t, text: ev.message, blocked: true }));
      },
      complete: () => this.busy.set(false),
      error: () => { patch(t => ({ ...t, text: 'Connection lost.', blocked: true })); this.busy.set(false); },
    });
  }
}
