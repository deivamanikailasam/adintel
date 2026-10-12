import { Component, OnInit, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService } from '../core/auth.service';

@Component({
  selector: 'app-callback',
  standalone: true,
  template: `<div class="panel">@if (error()) { <p class="error" role="alert">{{ error() }}</p> } @else { <p>Signing you in…</p> }</div>`,
})
export class CallbackComponent implements OnInit {
  private auth = inject(AuthService);
  private router = inject(Router);
  error = signal('');

  async ngOnInit(): Promise<void> {
    const q = new URLSearchParams(location.search);
    try {
      await this.auth.completeSso(q.get('code') ?? '', q.get('state') ?? '');
      await this.router.navigateByUrl('/brands');
    } catch (e: any) {
      this.error.set(`Sign-in failed: ${e?.message ?? e}. Is your user provisioned in AdIntel?`);
    }
  }
}
