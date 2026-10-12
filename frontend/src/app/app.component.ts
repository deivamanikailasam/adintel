import { Component, OnInit, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthService } from './core/auth.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    @if (auth.loggedIn()) {
      <header class="top">
        <strong>AdIntel</strong>
        <nav>
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
    <main><router-outlet /></main>
    <footer class="muted">AI drafts and analyses; a named human approves every change. Nothing spends money without approval.</footer>
  `,
  styles: [`
    .top { display: flex; gap: 1.5rem; align-items: center; padding: .7rem 1.5rem; background: #101828; color: white; }
    .top nav { display: flex; gap: 1rem; flex: 1; }
    .top a { color: #c7d2fe; } .top a.on { color: white; font-weight: 600; }
    .who { font-size: .85rem; color: #d0d5dd; }
    main { max-width: 1180px; margin: 1.5rem auto; padding: 0 1rem; }
    footer { text-align: center; padding: 2rem; }
  `],
})
export class AppComponent implements OnInit {
  auth = inject(AuthService);
  ngOnInit(): void { void this.auth.loadMe(); }
}
