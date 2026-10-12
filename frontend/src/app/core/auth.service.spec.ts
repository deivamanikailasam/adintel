import { TestBed, fakeAsync, tick } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { Component } from '@angular/core';

@Component({ standalone: true, template: '' })
class Blank {}
import { AuthService, tokenExpiry } from './auth.service';

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

  it('signs out when the token expires (no refresh token for dev login)', fakeAsync(() => {
    auth.token.set(jwt(Math.floor(Date.now() / 1000) + 5));
    void auth.startSessionWatch();
    http.expectOne('/api/auth/config').flush({ session: { idle_timeout_minutes: 30 } });
    tick(6_000);
    expect(auth.loggedIn()).toBeFalse();
    expect(auth.takeLogoutReason()).toContain('expired');
  }));
});
