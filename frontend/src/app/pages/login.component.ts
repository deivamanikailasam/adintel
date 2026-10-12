import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../core/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [FormsModule],
  template: `
    <div class="panel login">
      <h1>Sign in to AdIntel</h1>
      @if (notice) { <p class="muted" role="status">{{ notice }}</p> }
      <p class="muted">Local development login (seeded users, no password). Production uses Cognito SSO.</p>
      <form (ngSubmit)="submit()">
        <select [(ngModel)]="email" name="email" aria-label="Seeded user">
          @for (u of users; track u.email) { <option [value]="u.email">{{ u.label }}</option> }
        </select>
        <button class="primary" type="submit" [disabled]="busy()">Sign in</button>
      </form>
      <p><button (click)="sso()">Sign in with SSO (Keycloak / your identity provider)</button></p>
      @if (error()) { <p class="error">{{ error() }}</p> }
    </div>
  `,
  styles: [`.login { max-width: 520px; margin: 4rem auto; } form { display: flex; gap: .6rem; } select { flex: 1; }`],
})
export class LoginComponent {
  private auth = inject(AuthService);
  private router = inject(Router);
  users = [
    { email: 'jordan@brightwave.example', label: 'Jordan Lee — Account manager (Urban Roast, Fitely), $500/day' },
    { email: 'priya@brightwave.example', label: 'Priya Shah — Account manager (NorthPeak, Cobalt), $500/day' },
    { email: 'sam@brightwave.example', label: 'Sam Ortiz — Senior AM, $2,000/day' },
    { email: 'hana@brightwave.example', label: 'Hana Kim — Head of Performance' },
    { email: 'alex@brightwave.example', label: 'Alex Rivera — Head of Performance (second approver)' },
    { email: 'admin@brightwave.example', label: 'Ali Admin — Admin (kill switches, audit)' },
    { email: 'viewer@brightwave.example', label: 'Vic Viewer — read only' },
    { email: 'am@acme.example', label: 'Acme AM — a different agency (isolation demo)' },
  ];
  email = this.users[0].email;
  busy = signal(false);
  error = signal('');
  notice = this.auth.takeLogoutReason();

  async sso(): Promise<void> {
    try { await this.auth.loginSso(); } catch (e: any) { this.error.set(e?.message ?? 'SSO unavailable'); }
  }

  async submit(): Promise<void> {
    this.busy.set(true);
    this.error.set('');
    try { await this.auth.login(this.email); await this.router.navigateByUrl('/brands'); }
    catch { this.error.set('Login failed — is the API running on :8000 and seeded (adintel seed)?'); }
    finally { this.busy.set(false); }
  }
}
