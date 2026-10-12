import { Routes } from '@angular/router';
import { authGuard } from './core/auth.guard';

export const routes: Routes = [
  { path: 'login', loadComponent: () => import('./pages/login.component').then(m => m.LoginComponent) },
  { path: '', canActivate: [authGuard], children: [
    { path: '', pathMatch: 'full', redirectTo: 'brands' },
    { path: 'brands', loadComponent: () => import('./pages/brands.component').then(m => m.BrandsComponent) },
    { path: 'brands/:brandId', loadComponent: () => import('./pages/brand-detail.component').then(m => m.BrandDetailComponent) },
    { path: 'runs/:runId', loadComponent: () => import('./pages/run-detail.component').then(m => m.RunDetailComponent) },
    { path: 'approvals', loadComponent: () => import('./pages/approvals.component').then(m => m.ApprovalsComponent) },
    { path: 'approvals/:recId', loadComponent: () => import('./pages/recommendation.component').then(m => m.RecommendationComponent) },
    { path: 'reports/:reportId', loadComponent: () => import('./pages/report.component').then(m => m.ReportComponent) },
    { path: 'chat', loadComponent: () => import('./pages/chat.component').then(m => m.ChatComponent) },
    { path: 'admin', loadComponent: () => import('./pages/admin.component').then(m => m.AdminComponent) },
  ]},
  { path: '**', redirectTo: '' },
];
