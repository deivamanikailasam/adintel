"""Domain models.

These are the nouns of the system. They are deliberately plain Pydantic models with no behaviour
beyond validation, so the same objects travel through state, storage, the API and evals.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from adintel.core.clock import utcnow
from adintel.core.ids import new_id
from adintel.domain.enums import (
    ActionType,
    AgentName,
    DegradationCode,
    DQVerdict,
    Metric,
    NextAction,
    Platform,
    RecommendationStatus,
    RiskLevel,
    Role,
    Severity,
)


class Model(BaseModel):
    model_config = ConfigDict(use_enum_values=False, extra="forbid")


# --------------------------------------------------------------------------------------------------
# Tenancy and people
# --------------------------------------------------------------------------------------------------
class Tenant(Model):
    tenant_id: str
    name: str
    active: bool = True


class BrandProfile(Model):
    tone_cluster: str = "neutral"  # selects the report LoRA adapter
    timezone: str = "America/New_York"
    vertical: str = "general"
    currency: str = "USD"
    voice_notes: str = ""


class Brand(Model):
    tenant_id: str
    brand_id: str
    name: str
    platforms: list[Platform]
    assigned_am: str | None = None  # user_id of the brand's account manager
    profile: BrandProfile = Field(default_factory=BrandProfile)
    active: bool = True


class User(Model):
    tenant_id: str
    user_id: str
    email: str
    name: str
    roles: list[Role]
    approval_limit_usd: float = 0.0  # max daily exposure this person may approve alone
    brand_ids: list[str] = Field(default_factory=list)  # empty = all brands in tenant


# --------------------------------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------------------------------
class MetricRow(Model):
    """One normalised daily row for one entity (campaign or ad set) on one platform, in USD."""

    tenant_id: str
    brand_id: str
    platform: Platform
    date: date
    campaign_id: str
    campaign_name: str
    entity_id: str  # ad set / ad group id (the level budgets are moved at)
    entity_name: str
    entity_type: str = "ad_set"
    impressions: int
    clicks: int
    spend: float
    conversions: float
    revenue: float
    daily_budget: float | None = None
    currency_original: str = "USD"


class PlatformFetch(Model):
    platform: Platform
    ok: bool
    rows: int = 0
    latency_ms: float = 0.0
    error: str | None = None
    unmapped_fields: list[str] = Field(default_factory=list)
    raw_spend_total_usd: float = 0.0
    duplicates: int = 0
    currencies: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------------------------------
# Run artefacts
# --------------------------------------------------------------------------------------------------
class Degradation(Model):
    code: DegradationCode
    agent: AgentName
    detail: str
    client_caveat: str  # the plain-English sentence that appears in the report
    at: datetime = Field(default_factory=utcnow)


class TraceEvent(Model):
    step: int
    agent: AgentName
    status: str  # ok | degraded | skipped | failed
    summary: str
    started_at: datetime
    duration_ms: float
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    llm_call_ids: list[str] = Field(default_factory=list)


class DQCheck(Model):
    name: str
    passed: bool
    critical: bool
    detail: str


class DQResult(Model):
    verdict: DQVerdict
    checks: list[DQCheck]
    summary: str


class Anomaly(Model):
    anomaly_id: str = Field(default_factory=lambda: new_id("anom"))
    platform: Platform
    entity_id: str
    entity_name: str
    campaign_id: str
    metric: Metric
    direction: str  # up | down
    observed: float
    expected: float
    lower: float
    upper: float
    deviation_pct: float
    days: int  # consecutive days outside the band
    severity: Severity
    spend_at_risk_weekly: float
    iforest_confirmed: bool
    method: str = "stl+iforest"
    series_hash: str = ""


class Hypothesis(Model):
    name: str
    verdict: str  # confirmed | ruled_out | inconclusive
    evidence: str


class RootCause(Model):
    anomaly_id: str
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    hypotheses: list[Hypothesis]
    evidence_chunk_ids: list[str] = Field(default_factory=list)
    queries_run: list[str] = Field(default_factory=list)
    injection_suspected: bool = False


class Citation(Model):
    chunk_id: str
    doc_title: str
    snippet: str


class Recommendation(Model):
    recommendation_id: str = Field(default_factory=lambda: new_id("rec"))
    tenant_id: str
    brand_id: str
    run_id: str
    anomaly_id: str | None
    action_type: ActionType
    platform: Platform
    source_entity_id: str | None = None
    target_entity_id: str
    amount_usd_per_day: float  # signed for budget_change; positive for shifts
    daily_exposure_usd: float  # computed in code, never by the model
    expected_impact: str
    expected_cpa_change_pct_low: float | None = None
    expected_cpa_change_pct_high: float | None = None
    rationale: str
    citations: list[Citation]
    risk: RiskLevel
    irreversible: bool = False
    entity_snapshot_hash: str
    status: RecommendationStatus = RecommendationStatus.PENDING_APPROVAL
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime
    constraint_checks: list[str] = Field(default_factory=list)


class ReportSection(Model):
    key: str  # summary | performance | anomalies | recommendations | caveats | next_steps
    title: str
    body: str


class GroundingResult(Model):
    passed: bool
    numbers_checked: int
    ungrounded: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)  # warnings only


class Report(Model):
    report_id: str = Field(default_factory=lambda: new_id("rpt"))
    title: str
    sections: list[ReportSection]
    facts: dict[str, Any]  # the numbers the prose is allowed to use
    model_tier: str
    adapter_sha256: str | None = None
    grounding: GroundingResult | None = None
    deterministic_template: bool = False


class GuardrailFinding(Model):
    check: str
    severity: str  # block | warn
    detail: str


class GuardrailVerdict(Model):
    passed: bool
    findings: list[GuardrailFinding]
    classifier_used: bool
    classifier_category: str | None = None


class OrchestratorDecision(Model):
    step: int
    next_action: NextAction
    decided_by: str  # rule:<name> | model | fallback_rule
    reasoning: str
    at: datetime = Field(default_factory=utcnow)


# --------------------------------------------------------------------------------------------------
# Governance artefacts
# --------------------------------------------------------------------------------------------------
class BlackoutWindow(Model):
    start: datetime
    end: datetime
    reason: str


class BrandRules(Model):
    """Brand constraints (pure code, applied after the model) plus procedural memory."""

    tenant_id: str
    brand_id: str
    max_single_change_pct: float = 25.0
    min_daily_budget_usd: float = 10.0
    allowed_actions: list[ActionType] = Field(
        default_factory=lambda: [ActionType.BUDGET_SHIFT, ActionType.BUDGET_CHANGE, ActionType.PAUSE_ENTITY]
    )
    blackout_windows: list[BlackoutWindow] = Field(default_factory=list)
    protected_entity_ids: list[str] = Field(default_factory=list)
    suppressions: list[Suppression] = Field(default_factory=list)
    anomaly_min_severity_to_alert: Severity = Severity.MEDIUM
    version: int = 1


class Suppression(Model):
    """A human-approved procedural-memory rule, e.g. 'Q4 always spikes, don't flag it'."""

    rule_id: str = Field(default_factory=lambda: new_id("rule"))
    description: str
    metric: Metric | None = None
    entity_id: str | None = None
    month: int | None = None  # 1-12; suppress in this month only
    approved_by: str
    approved_at: datetime


BrandRules.model_rebuild()


class Approval(Model):
    approval_id: str = Field(default_factory=lambda: new_id("apr"))
    tenant_id: str
    recommendation_id: str
    approver_id: str
    second_approver_id: str | None = None
    typed_exposure_usd: float
    modified_amount_usd_per_day: float | None = None
    approved_at: datetime = Field(default_factory=utcnow)
    second_approved_at: datetime | None = None
    snapshot_hash: str
    signature: str = ""


class Execution(Model):
    execution_id: str = Field(default_factory=lambda: new_id("exe"))
    tenant_id: str
    brand_id: str
    recommendation_id: str
    approval_id: str
    platform: Platform
    request: dict[str, Any]
    status: str  # succeeded | failed | refused
    platform_response: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    attempts: int = 1
    executed_at: datetime = Field(default_factory=utcnow)
