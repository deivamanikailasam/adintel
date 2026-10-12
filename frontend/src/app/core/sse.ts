import { Observable } from 'rxjs';

/**
 * Server-sent events over fetch (EventSource cannot send an Authorization header or a POST body).
 * Emits each `data:` payload parsed as JSON; completes when the server closes the stream.
 */
export function sse<T>(url: string, token: string | null, body?: unknown): Observable<T> {
  return new Observable<T>(subscriber => {
    const ctrl = new AbortController();
    const headers: Record<string, string> = { Accept: 'text/event-stream' };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    fetch(url, { method: body === undefined ? 'GET' : 'POST', headers, signal: ctrl.signal,
                 body: body === undefined ? undefined : JSON.stringify(body) })
      .then(async res => {
        if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = '';
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          let idx: number;
          while ((idx = buf.indexOf('\n\n')) >= 0) {
            const chunk = buf.slice(0, idx);
            buf = buf.slice(idx + 2);
            const data = chunk.split('\n').filter(l => l.startsWith('data: ')).map(l => l.slice(6)).join('\n');
            if (data) subscriber.next(JSON.parse(data) as T);
          }
        }
        subscriber.complete();
      })
      .catch(err => { if (!ctrl.signal.aborted) subscriber.error(err); });
    return () => ctrl.abort();
  });
}
