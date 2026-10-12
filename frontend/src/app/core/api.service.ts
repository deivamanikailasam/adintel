import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { AuthService } from './auth.service';
import { sse } from './sse';
import { Brand, Recommendation, Report, Run, StepEvent } from './models';

/** Typed client for the AdIntel API (proxied at /api in development). */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  private auth = inject(AuthService);

  brands(): Observable<Brand[]> { return this.http.get<Brand[]>('/api/brands'); }
  brandSummary(id: string): Observable<any> { return this.http.get(`/api/brands/${id}/summary`); }
  startRun(brand_id: string): Observable<{ run_id: string; created: boolean }> {
    return this.http.post<{ run_id: string; created: boolean }>('/api/runs', { brand_id });
  }
  runs(brand_id?: string): Observable<Run[]> {
    const params = brand_id ? new HttpParams().set('brand_id', brand_id) : undefined;
    return this.http.get<Run[]>('/api/runs', { params });
  }
  run(id: string): Observable<Run> { return this.http.get<Run>(`/api/runs/${id}`); }
  trace(id: string): Observable<any> { return this.http.get(`/api/runs/${id}/trace`); }
  runEvents(id: string): Observable<StepEvent> { return sse<StepEvent>(`/api/runs/${id}/events`, this.auth.token()); }
  report(id: string): Observable<Report> { return this.http.get<Report>(`/api/reports/${id}`); }
  rateReport(id: string, rating: number, comment = ''): Observable<unknown> {
    return this.http.post(`/api/reports/${id}/rating`, { rating, comment });
  }
  recommendations(status?: string): Observable<Recommendation[]> {
    const params = status ? new HttpParams().set('status', status) : undefined;
    return this.http.get<Recommendation[]>('/api/recommendations', { params });
  }
  recommendation(id: string): Observable<any> { return this.http.get(`/api/recommendations/${id}`); }
  approve(id: string, typed_exposure_usd: number, modified_amount_usd_per_day?: number): Observable<any> {
    return this.http.post(`/api/recommendations/${id}/approve`, { typed_exposure_usd, modified_amount_usd_per_day });
  }
  reject(id: string, category: string, note: string): Observable<any> {
    return this.http.post(`/api/recommendations/${id}/reject`, { category, note });
  }
  categories(): Observable<{ rejection: string[]; dismissal: string[] }> {
    return this.http.get<{ rejection: string[]; dismissal: string[] }>('/api/meta/rejection-categories');
  }
  anomalies(brand_id?: string): Observable<any[]> {
    const params = brand_id ? new HttpParams().set('brand_id', brand_id) : undefined;
    return this.http.get<any[]>('/api/anomalies', { params });
  }
  dismiss(id: string, reason: string, note = ''): Observable<any> {
    return this.http.post(`/api/anomalies/${id}/dismiss`, { reason, note });
  }
  proposals(): Observable<any[]> { return this.http.get<any[]>('/api/rule-proposals'); }
  decideProposal(id: string, approve: boolean): Observable<any> {
    return this.http.post(`/api/rule-proposals/${id}/decision`, { approve });
  }
  chat(brand_id: string, session_id: string, question: string): Observable<any> {
    return sse<any>('/api/chat', this.auth.token(), { brand_id, session_id, question });
  }
  killSwitches(): Observable<any[]> { return this.http.get<any[]>('/api/admin/kill-switches'); }
  setKillSwitch(scope: string, key: string, engaged: boolean, reason: string): Observable<any> {
    return this.http.post('/api/admin/kill-switches', { scope, key, engaged, reason });
  }
  verifyAudit(): Observable<any> { return this.http.get('/api/admin/audit/verify'); }
  cost(): Observable<any> { return this.http.get('/api/admin/cost'); }
  models(): Observable<any> { return this.http.get('/api/admin/models'); }
  notifications(): Observable<any[]> { return this.http.get<any[]>('/api/admin/notifications'); }
  status(): Observable<{ status: string; messages: { level: string; text: string }[] }> {
    return this.http.get<{ status: string; messages: { level: string; text: string }[] }>('/api/status');
  }
  platformAlerts(): Observable<any[]> { return this.http.get<any[]>('/api/admin/platform-alerts'); }
  flags(brand_id?: string): Observable<any> {
    const params = brand_id ? new HttpParams().set('brand_id', brand_id) : undefined;
    return this.http.get('/api/admin/flags', { params });
  }
  setFlag(flag: string, enabled: boolean, reason: string, brand_id?: string | null): Observable<any> {
    return this.http.post('/api/admin/flags', { flag, enabled, reason, brand_id: brand_id || null });
  }
  triage(days = 7): Observable<any> { return this.http.get('/api/admin/triage', { params: new HttpParams().set('days', days) }); }
  outcomes(): Observable<any[]> { return this.http.get<any[]>('/api/admin/outcomes'); }
  privacyExport(user_id: string): Observable<any> { return this.http.get(`/api/admin/privacy/users/${encodeURIComponent(user_id)}/export`); }
  privacyErase(user_id: string, reason: string): Observable<any> {
    return this.http.post(`/api/admin/privacy/users/${encodeURIComponent(user_id)}/erase`, { reason });
  }
}
