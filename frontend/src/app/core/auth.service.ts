import { Injectable, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { Me } from './models';

const KEY = 'adintel.token';

/** Holds the JWT in sessionStorage (cleared when the tab closes). In production, Cognito hosted UI. */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private http = inject(HttpClient);
  private router = inject(Router);
  readonly token = signal<string | null>(sessionStorage.getItem(KEY));
  readonly me = signal<Me | null>(null);
  readonly loggedIn = computed(() => !!this.token());
  /** Refresh token is kept in memory only: a reload signs in again silently through the IdP session. */
  private refreshToken: string | null = null;
  private idToken: string | null = null;
  private idleTimer?: ReturnType<typeof setTimeout>;
  private expiryTimer?: ReturnType<typeof setTimeout>;
  private idleMinutes = 30;
  private watching = false;

  /** Idle sign-out and token-expiry handling; called once a session exists. */
  async startSessionWatch(): Promise<void> {
    if (this.watching || !this.token()) return;
    this.watching = true;
    try {
      const cfg = await firstValueFrom(this.http.get<any>('/api/auth/config'));
      this.idleMinutes = cfg?.session?.idle_timeout_minutes ?? 30;
    } catch { /* keep the default */ }
    const reset = () => {
      clearTimeout(this.idleTimer);
      this.idleTimer = setTimeout(() => this.logout(`Signed out after ${this.idleMinutes} minutes of inactivity.`),
        this.idleMinutes * 60_000);
    };
    for (const ev of ['mousemove', 'keydown', 'click', 'scroll', 'touchstart']) addEventListener(ev, reset, { passive: true });
    reset();
    this.scheduleExpiry();
  }

  private scheduleExpiry(): void {
    clearTimeout(this.expiryTimer);
    const exp = tokenExpiry(this.token());
    if (!exp) return;
    const ms = exp * 1000 - Date.now();
    if (this.refreshToken && ms > 90_000) {
      this.expiryTimer = setTimeout(() => void this.refresh(), ms - 60_000);  // refresh a minute early
    } else {
      this.expiryTimer = setTimeout(() => this.logout('Your session expired. Please sign in again.'), Math.max(ms, 0));
    }
  }

  private async refresh(): Promise<void> {
    const saved = JSON.parse(sessionStorage.getItem('adintel.oidc') ?? '{}');
    try {
      const res = await fetch(saved.token_endpoint, { method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ grant_type: 'refresh_token', refresh_token: this.refreshToken ?? '', client_id: saved.client_id }) });
      if (!res.ok) throw new Error(String(res.status));
      const tok = await res.json();
      this.store(tok);
      this.scheduleExpiry();
    } catch {
      this.logout('Your session could not be renewed. Please sign in again.');
    }
  }

  private store(tok: { access_token: string; refresh_token?: string; id_token?: string }): void {
    sessionStorage.setItem(KEY, tok.access_token);
    this.token.set(tok.access_token);
    this.refreshToken = tok.refresh_token ?? this.refreshToken;
    this.idToken = tok.id_token ?? this.idToken;
  }

  async login(email: string): Promise<void> {
    const r = await firstValueFrom(this.http.post<{ access_token: string }>('/api/auth/dev-login', { email }));
    sessionStorage.setItem(KEY, r.access_token);
    this.token.set(r.access_token);
    await this.loadMe();
    void this.startSessionWatch();
  }

  async loadMe(): Promise<void> {
    if (!this.token()) return;
    try { this.me.set(await firstValueFrom(this.http.get<Me>('/api/me'))); }
    catch { this.logout(); }
  }

  /** OIDC authorization-code flow with PKCE (Keycloak locally; Cognito/Entra/Okta in production). */
  async loginSso(): Promise<void> {
    const cfg = await firstValueFrom(this.http.get<any>('/api/auth/config'));
    if (!cfg.oidc) throw new Error('SSO is not enabled on this server');
    const verifier = randomString(64);
    const state = randomString(24);
    sessionStorage.setItem('adintel.pkce', JSON.stringify({ verifier, state, ...cfg.oidc }));
    const challenge = await sha256url(verifier);
    const params = new URLSearchParams({ client_id: cfg.oidc.client_id, response_type: 'code', scope: 'openid email profile',
      redirect_uri: `${location.origin}/auth/callback`, state, code_challenge: challenge, code_challenge_method: 'S256' });
    location.assign(`${cfg.oidc.authorization_endpoint}?${params}`);
  }

  async completeSso(code: string, state: string): Promise<void> {
    const saved = JSON.parse(sessionStorage.getItem('adintel.pkce') ?? '{}');
    sessionStorage.removeItem('adintel.pkce');
    if (!saved.state || saved.state !== state) throw new Error('state mismatch');
    const body = new URLSearchParams({ grant_type: 'authorization_code', code, client_id: saved.client_id,
      redirect_uri: `${location.origin}/auth/callback`, code_verifier: saved.verifier });
    const res = await fetch(saved.token_endpoint, { method: 'POST', body,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' } });
    if (!res.ok) throw new Error(`token exchange failed: ${res.status}`);
    const tok = await res.json();
    sessionStorage.setItem('adintel.oidc', JSON.stringify({ issuer: saved.issuer, client_id: saved.client_id,
      token_endpoint: saved.token_endpoint, end_session_endpoint: saved.end_session_endpoint, logout_style: saved.logout_style }));
    this.store(tok);
    await this.loadMe();
    void this.startSessionWatch();
  }

  hasRole(...roles: string[]): boolean {
    const me = this.me();
    return !!me && (me.roles.some(r => roles.includes(r)) || me.roles.includes('admin'));
  }

  /** Signs out locally and, after SSO, at the identity provider too (RP-initiated logout). */
  logout(reason?: string): void {
    clearTimeout(this.idleTimer);
    clearTimeout(this.expiryTimer);
    const oidc = JSON.parse(sessionStorage.getItem('adintel.oidc') ?? 'null');
    const idToken = this.idToken;
    sessionStorage.removeItem(KEY);
    sessionStorage.removeItem('adintel.oidc');
    if (reason) sessionStorage.setItem('adintel.logout_reason', reason);
    this.token.set(null);
    this.me.set(null);
    this.refreshToken = this.idToken = null;
    this.watching = false;
    const url = oidc?.end_session_endpoint ? logoutUrl(oidc, idToken, `${location.origin}/login`) : null;
    if (url) {
      location.assign(url);
      return;
    }
    this.router.navigateByUrl('/login');
  }

  /** Why the last session ended (shown once on the sign-in page). */
  takeLogoutReason(): string {
    const r = sessionStorage.getItem('adintel.logout_reason') ?? '';
    sessionStorage.removeItem('adintel.logout_reason');
    return r;
  }
}

function randomString(n: number): string {
  const bytes = crypto.getRandomValues(new Uint8Array(n));
  return Array.from(bytes, b => ('0' + (b % 62).toString(36)).slice(-1)).join('').slice(0, n) + Date.now().toString(36);
}

async function sha256url(input: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input));
  return btoa(String.fromCharCode(...new Uint8Array(digest))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/** The `exp` claim (seconds) of a JWT, without verifying it — the server verifies; this only schedules. */
export function tokenExpiry(token: string | null): number | null {
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    return typeof payload.exp === 'number' ? payload.exp : null;
  } catch { return null; }
}

/** IdP logout URL: standard OIDC RP-initiated logout, or Cognito's /logout (no id_token_hint). */
export function logoutUrl(
  oidc: { end_session_endpoint: string; client_id: string; logout_style?: string },
  idToken: string | null, returnTo: string,
): string | null {
  if (oidc.logout_style === 'cognito') {
    return `${oidc.end_session_endpoint}?${new URLSearchParams({ client_id: oidc.client_id, logout_uri: returnTo })}`;
  }
  if (!idToken) return null;  // without an id_token the IdP can't identify the session; local sign-out only
  return `${oidc.end_session_endpoint}?${new URLSearchParams({ client_id: oidc.client_id, id_token_hint: idToken, post_logout_redirect_uri: returnTo })}`;
}
