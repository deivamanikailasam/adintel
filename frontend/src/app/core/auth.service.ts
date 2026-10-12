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
