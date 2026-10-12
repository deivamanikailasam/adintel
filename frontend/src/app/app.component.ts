import { Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { ApiService } from './core/api.service';
import { AuthService } from './core/auth.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    <a class="skip" href="#main">Skip to content</a>
    @if (auth.loggedIn()) {
      <header class="top">
        <strong>AdIntel</strong>
        <nav aria-label="Main">
          <a routerLink="/brands" routerLinkActive="on">Brands</a>
          <a routerLink="/approvals" routerLinkActive="on">Approvals</a>
          <a routerLink="/chat" routerLinkActive="on">Chat</a>
          @if (auth.hasRole('senior_account_manager', 'head_of_performance', 'admin')) {
            <a routerLink="/admin" routerLinkActive="on">Governance</a>
          }
        </nav>
        <span class="who">{{ auth.me()?.email }} · {{ auth.me()?.roles?.join(', ') }}</span>
        <button (click)="auth.logout()">Sign out</button>
      </header>
    }
    @if (auth.loggedIn() && banner().length) {
      <div class="banner {{ level() }}" role="status" aria-live="polite">
        @for (m of banner(); track $index) { <div>{{ m.text }}</div> }
      </div>
    }
    <main id="main" tabindex="-1"><router-outlet /></main>
    <footer class="muted">AI drafts and analyses; a named human approves every change. Nothing spends money without approval.</footer>
  `,
  styles: [`
    .top { display: flex; gap: 1.5rem; align-items: center; padding: .7rem 1.5rem; background: #101828; color: white; }
    .top nav { display: flex; gap: 1rem; flex: 1; }
    .top a { color: #c7d2fe; } .top a.on { color: white; font-weight: 600; }
    .who { font-size: .85rem; color: #d0d5dd; }
    main { max-width: 1180px; margin: 1.5rem auto; padding: 0 1rem; }
    footer { text-align: center; padding: 2rem; }
    .skip { position: absolute; left: -999px; top: 0; background: #fff; padding: .5rem 1rem; z-index: 10; }
    .skip:focus { left: 1rem; }
    .banner { padding: .6rem 1.5rem; font-size: .92rem; }
    .banner.degraded { background: #fdf3e1; color: #7a4f0d; }
    .banner.down { background: #fdecea; color: #8a1f14; }
  `],
})
export class AppComponent implements OnInit, OnDestroy {
  auth = inject(AuthService);
  private api = inject(ApiService);
  banner = signal<{ level: string; text: string }[]>([]);
  level = signal('ok');
  private timer?: ReturnType<typeof setInterval>;

  ngOnInit(): void {
    void this.auth.loadMe().then(() => this.auth.startSessionWatch());
    this.poll();
    this.timer = setInterval(() => this.poll(), 60_000);
  }
  ngOnDestroy(): void { if (this.timer) clearInterval(this.timer); }
  private poll(): void {
    if (!this.auth.loggedIn()) return;
    this.api.status().subscribe({
      next: s => { this.banner.set(s.messages); this.level.set(s.status); },
      error: () => { /* the banner is best-effort; real errors surface where they happen */ },
    });
  }
}
