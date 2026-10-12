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

  async login(email: string): Promise<void> {
    const r = await firstValueFrom(this.http.post<{ access_token: string }>('/api/auth/dev-login', { email }));
    sessionStorage.setItem(KEY, r.access_token);
    this.token.set(r.access_token);
    await this.loadMe();
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
    location.assign(`${cfg.oidc.issuer}/protocol/openid-connect/auth?${params}`);
  }

  async completeSso(code: string, state: string): Promise<void> {
    const saved = JSON.parse(sessionStorage.getItem('adintel.pkce') ?? '{}');
    sessionStorage.removeItem('adintel.pkce');
    if (!saved.state || saved.state !== state) throw new Error('state mismatch');
    const body = new URLSearchParams({ grant_type: 'authorization_code', code, client_id: saved.client_id,
      redirect_uri: `${location.origin}/auth/callback`, code_verifier: saved.verifier });
    const res = await fetch(`${saved.issuer}/protocol/openid-connect/token`, { method: 'POST', body,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' } });
    if (!res.ok) throw new Error(`token exchange failed: ${res.status}`);
    const tok = await res.json();
    sessionStorage.setItem(KEY, tok.access_token);
    this.token.set(tok.access_token);
    await this.loadMe();
  }

  hasRole(...roles: string[]): boolean {
    const me = this.me();
    return !!me && (me.roles.some(r => roles.includes(r)) || me.roles.includes('admin'));
  }

  logout(): void {
    sessionStorage.removeItem(KEY);
    this.token.set(null);
    this.me.set(null);
    this.router.navigateByUrl('/login');
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
