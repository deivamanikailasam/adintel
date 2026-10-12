import { Component, inject } from '@angular/core';
import { AsyncPipe, DatePipe, DecimalPipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { ApiService } from '../core/api.service';

@Component({
  selector: 'app-approvals',
  standalone: true,
  imports: [AsyncPipe, RouterLink, DatePipe, DecimalPipe],
  template: `
    <h1>Approval queue</h1>
    <p class="muted">Evidence is one click away. Nothing executes until a named person with enough authority types the exact exposure.</p>
    <div class="panel"><table>
      <tr><th>Brand</th><th>Action</th><th>Daily exposure</th><th>Risk</th><th>Status</th><th>Expires</th><th></th></tr>
      @for (r of recs$ | async; track r.recommendation_id) {
        <tr><td>{{ r.brand_id }}</td><td>{{ r.action_type }} · {{ r.platform }}</td>
          <td>\${{ r.daily_exposure_usd | number:'1.2-2' }}/day</td><td><span class="badge">{{ r.risk }}</span></td>
          <td><span class="badge {{ r.status }}">{{ r.status }}</span></td><td>{{ r.expires_at | date:'short' }}</td>
          <td><a [routerLink]="['/approvals', r.recommendation_id]">Review →</a></td></tr>
      } @empty { <tr><td colspan="7" class="muted">Nothing awaiting approval.</td></tr> }
    </table></div>
    <h2>Learned-rule proposals</h2>
    <div class="panel"><ul>
      @for (p of proposals$ | async; track p.proposal_id) { <li>{{ p.description }} <span class="muted">(needs a senior AM or Head of Performance)</span></li> }
      @empty { <li class="muted">None</li> }
    </ul></div>
  `,
})
export class ApprovalsComponent {
  private api = inject(ApiService);
  recs$ = this.api.recommendations();
  proposals$ = this.api.proposals();
}
