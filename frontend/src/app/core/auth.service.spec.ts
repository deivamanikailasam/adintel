import { TestBed, fakeAsync, tick } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { Component } from '@angular/core';

@Component({ standalone: true, template: '' })
class Blank {}
import { AuthService, logoutUrl, tokenExpiry } from './auth.service';

function jwt(exp: number): string {
  const b64 = (o: object) => btoa(JSON.stringify(o)).replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_');
  return `${b64({ alg: 'HS256' })}.${b64({ sub: 'u', exp })}.sig`;
}

describe('AuthService session handling', () => {
  let auth: AuthService;
  let http: HttpTestingController;
  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([{ path: 'login', component: Blank }])] });
    auth = TestBed.inject(AuthService);
    http = TestBed.inject(HttpTestingController);
  });

  it('reads the exp claim without trusting it', () => {
    expect(tokenExpiry(jwt(1_900_000_000))).toBe(1_900_000_000);
    expect(tokenExpiry('garbage')).toBeNull();
    expect(tokenExpiry(null)).toBeNull();
  });

  it('signs out after the configured idle time and says why', fakeAsync(() => {
    auth.token.set(jwt(Math.floor(Date.now() / 1000) + 3600));
    void auth.startSessionWatch();
    http.expectOne('/api/auth/config').flush({ session: { idle_timeout_minutes: 1 } });
    tick(59_000);
    expect(auth.loggedIn()).toBeTrue();
    tick(2_000);
    expect(auth.loggedIn()).toBeFalse();
    expect(auth.takeLogoutReason()).toContain('inactivity');
    expect(auth.takeLogoutReason()).toBe('');  // shown once
  }));

  it('warns a minute before idle sign-out and lets the user stay signed in (WCAG 2.2.1)', fakeAsync(() => {
    auth.token.set(jwt(Math.floor(Date.now() / 1000) + 7200));
    void auth.startSessionWatch();
    http.expectOne('/api/auth/config').flush({ session: { idle_timeout_minutes: 2 } });
    tick(60_500);
    expect(auth.idleWarning()).toBeTrue();
    auth.stayActive();
    expect(auth.idleWarning()).toBeFalse();
    tick(100_000);
    expect(auth.loggedIn()).toBeTrue();  // extended
    tick(30_000);
    expect(auth.loggedIn()).toBeFalse();  // and still ends if they really leave
    auth.takeLogoutReason();
  }));

  it('signs out when the token expires (no refresh token for dev login)', fakeAsync(() => {
    auth.token.set(jwt(Math.floor(Date.now() / 1000) + 5));
    void auth.startSessionWatch();
    http.expectOne('/api/auth/config').flush({ session: { idle_timeout_minutes: 30 } });
    tick(6_000);
    expect(auth.loggedIn()).toBeFalse();
    expect(auth.takeLogoutReason()).toContain('expired');
  }));
});

describe('logoutUrl', () => {
  const back = 'https://adintel.example/login';
  it('uses standard RP-initiated logout for Keycloak, Okta and Entra ID', () => {
    const u = new URL(logoutUrl({ end_session_endpoint: 'https://idp.example/logout', client_id: 'spa' }, 'idtok', back)!);
    expect(u.searchParams.get('id_token_hint')).toBe('idtok');
    expect(u.searchParams.get('post_logout_redirect_uri')).toBe(back);
  });
  it('uses client_id + logout_uri for Cognito', () => {
    const u = new URL(logoutUrl({ end_session_endpoint: 'https://auth.example/logout', client_id: 'spa', logout_style: 'cognito' }, null, back)!);
    expect(u.searchParams.get('logout_uri')).toBe(back);
    expect(u.searchParams.has('id_token_hint')).toBeFalse();
  });
  it('falls back to local sign-out without an id token', () => {
    expect(logoutUrl({ end_session_endpoint: 'https://idp.example/logout', client_id: 'spa' }, null, back)).toBeNull();
  });
});
