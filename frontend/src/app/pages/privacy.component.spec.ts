import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { PrivacyComponent } from './privacy.component';

describe('PrivacyComponent', () => {
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [PrivacyComponent], providers: [provideHttpClient(), provideHttpClientTesting()] });
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());

  it('exports a user and summarises what is held', () => {
    const f = TestBed.createComponent(PrivacyComponent);
    f.componentInstance.userId = 'u_jordan';
    f.componentInstance.export();
    http.expectOne('/api/admin/privacy/users/u_jordan/export').flush({
      user_id: 'u_jordan', profile: { email: 'jordan@brightwave.example' }, approvals: [{}], feedback: [{}, {}],
    });
    f.detectChanges();
    const text = (f.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('jordan@brightwave.example');
    expect(f.componentInstance.counts(f.componentInstance.exported())).toEqual({ approvals: 1, feedback: 2 });
  });

  it('only erases after the user id is typed again, and shows server refusals', () => {
    const f = TestBed.createComponent(PrivacyComponent);
    const c = f.componentInstance;
    c.userId = 'u_admin'; c.reason = 'ticket 42'; c.confirm = 'u_other';
    f.detectChanges();
    const button = (f.nativeElement as HTMLElement).querySelector('button.danger') as HTMLButtonElement;
    expect(button.disabled).toBeTrue();
    c.confirm = 'u_admin';
    c.erase();
    http.expectOne('/api/admin/privacy/users/u_admin/erase').flush(
      { detail: 'ask another admin to erase your own account' }, { status: 409, statusText: 'Conflict' });
    expect(c.error()).toContain('another admin');
  });
});
