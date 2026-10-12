import { Routes } from '@angular/router';
import { authGuard } from './core/auth.guard';

export const routes: Routes = [
  { path: 'auth/callback', title: 'Signing in · AdIntel', loadComponent: () => import('./pages/callback.component').then(m => m.CallbackComponent) },
  { path: 'login', title: 'Sign in · AdIntel', loadComponent: () => import('./pages/login.component').then(m => m.LoginComponent) },
  { path: '', canActivate: [authGuard], children: [
    { path: '', pathMatch: 'full', redirectTo: 'brands' },
    { path: 'brands', title: 'Brands · AdIntel', loadComponent: () => import('./pages/brands.component').then(m => m.BrandsComponent) },
    { path: 'brands/:brandId', title: 'Brand · AdIntel', loadComponent: () => import('./pages/brand-detail.component').then(m => m.BrandDetailComponent) },
    { path: 'runs/:runId', title: 'Run · AdIntel', loadComponent: () => import('./pages/run-detail.component').then(m => m.RunDetailComponent) },
    { path: 'approvals', title: 'Approvals · AdIntel', loadComponent: () => import('./pages/approvals.component').then(m => m.ApprovalsComponent) },
    { path: 'approvals/:recId', title: 'Review recommendation · AdIntel', loadComponent: () => import('./pages/recommendation.component').then(m => m.RecommendationComponent) },
    { path: 'reports/:reportId', title: 'Report · AdIntel', loadComponent: () => import('./pages/report.component').then(m => m.ReportComponent) },
    { path: 'chat', title: 'Ask about a brand · AdIntel', loadComponent: () => import('./pages/chat.component').then(m => m.ChatComponent) },
    { path: 'admin', title: 'Governance · AdIntel', loadComponent: () => import('./pages/admin.component').then(m => m.AdminComponent) },
    { path: 'admin/learning', title: 'Learning & rollout · AdIntel', loadComponent: () => import('./pages/learning.component').then(m => m.LearningComponent) },
    { path: 'admin/privacy', title: 'Privacy requests · AdIntel', loadComponent: () => import('./pages/privacy.component').then(m => m.PrivacyComponent) },
  ]},
  { path: '**', redirectTo: '' },
];
