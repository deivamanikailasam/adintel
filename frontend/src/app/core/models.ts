export type Role = 'viewer' | 'account_manager' | 'senior_account_manager' | 'head_of_performance' | 'admin';

export interface Me { user_id: string; tenant_id: string; email: string; roles: Role[]; brand_ids: string[]; senior: boolean; }

export interface RunSummary { run_id: string; status: string; health?: string; finished_at?: string; path?: string; }

export interface Brand {
  brand_id: string; name: string; platforms: string[]; assigned_am?: string;
  profile: { tone_cluster: string; timezone: string; vertical: string };
  last_run: RunSummary | null;
}

export interface Run {
  run_id: string; brand_id: string; brand_name: string; status: string; health?: string; trigger: string;
  period_start: string; period_end: string; created_at: string; finished_at?: string; path?: string;
  usage?: { steps: number; tokens_in: number; tokens_out: number; cost_usd: number };
  degradations?: string[]; abort_reason?: string; report_id?: string; recommendation_ids?: string[];
}

export interface Citation { chunk_id: string; doc_title: string; snippet: string; }

export interface Recommendation {
  recommendation_id: string; brand_id: string; run_id: string; anomaly_id?: string; action_type: string;
  platform: string; source_entity_id?: string; target_entity_id: string; amount_usd_per_day: number;
  daily_exposure_usd: number; expected_impact: string; expected_cpa_change_pct_low?: number;
  expected_cpa_change_pct_high?: number; rationale: string; citations: Citation[]; risk: string;
  status: string; created_at: string; expires_at: string; constraint_checks: string[];
}

export interface ReportSection { key: string; title: string; body: string; }
export interface Report {
  report_id: string; brand_id: string; run_id: string; title: string; sections: ReportSection[]; status: string;
  model_tier: string; deterministic_template: boolean; footer: string;
  grounding?: { passed: boolean; numbers_checked: number; ungrounded: string[] };
}

export interface StepEvent { kind: string; agent?: string; summary?: string; status?: string; steps?: number; cost_usd?: number; at?: string; }
