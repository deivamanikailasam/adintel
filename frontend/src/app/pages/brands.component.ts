import { Component, inject } from '@angular/core';
import { AsyncPipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { ApiService } from '../core/api.service';

@Component({
  selector: 'app-brands',
  standalone: true,
  imports: [AsyncPipe, RouterLink],
  template: `
    <h1>Brands</h1>
    <div class="grid">
      @for (b of brands$ | async; track b.brand_id) {
        <a class="panel card" [routerLink]="['/brands', b.brand_id]">
          <div class="row"><strong>{{ b.name }}</strong>
            @if (b.last_run) { <span class="badge {{ b.last_run.status }}">{{ b.last_run.status }}</span> }
            @else { <span class="badge">no runs yet</span> }
          </div>
          <p class="muted">{{ b.platforms.join(' · ') }}</p>
          <p class="muted">{{ b.profile.vertical }} · {{ b.profile.timezone }}
            @if (b.last_run?.health === 'degraded') { · <span class="badge degraded">degraded</span> }</p>
        </a>
      } @empty { <p class="muted">No brands in your scope.</p> }
    </div>
  `,
  styles: [`.card { display: block; color: inherit; } .card:hover { border-color: var(--accent); }`],
})
export class BrandsComponent {
  brands$ = inject(ApiService).brands();
}
