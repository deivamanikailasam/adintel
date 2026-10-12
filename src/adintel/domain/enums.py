"""Enumerations shared across the system. String enums so they serialise cleanly to Mongo and JSON."""

from __future__ import annotations

from enum import StrEnum


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    DEGRADED = "degraded"
    FAILED = "failed"
    ABORTED_DATA_QUALITY = "aborted_data_quality"
    KILLED = "killed"
    HELD = "held"  # output blocked by the guardrail or grounding; awaiting human review

    @property
    def terminal(self) -> bool:
        return self not in (RunStatus.PENDING, RunStatus.RUNNING)


class DQVerdict(StrEnum):
    TRUSTWORTHY = "trustworthy"
    DEGRADED = "degraded"  # usable with a disclosed caveat; Optimizer blocked
    UNTRUSTWORTHY = "untrustworthy"  # hard stop


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return ["low", "medium", "high", "critical"].index(self.value)


class AgentName(StrEnum):
    INGESTION = "ingestion"
    DATA_QUALITY = "data_quality"
    ORCHESTRATOR = "orchestrator"
    ANOMALY = "anomaly"
    ANALYST = "analyst"
    OPTIMIZER = "optimizer"
    REPORT = "report"
    GUARDRAIL = "guardrail"
    FINALIZE = "finalize"
    CHAT = "chat"


class NextAction(StrEnum):
    """Hops the Orchestrator may choose. Anything else from a model is rejected."""

    ANOMALY = "anomaly"
    ANALYST = "analyst"
    OPTIMIZER = "optimizer"
    REPORT = "report"
    GUARDRAIL = "guardrail"  # i.e. "the run is complete"


class Platform(StrEnum):
    GOOGLE_ADS = "google_ads"
    META = "meta"
    TIKTOK = "tiktok"
    LINKEDIN = "linkedin"
    AMAZON_ADS = "amazon_ads"


class Metric(StrEnum):
    SPEND = "spend"
    IMPRESSIONS = "impressions"
    CLICKS = "clicks"
    CONVERSIONS = "conversions"
    REVENUE = "revenue"
    CPA = "cpa"
    ROAS = "roas"
    CTR = "ctr"
    CPC = "cpc"


class ActionType(StrEnum):
    BUDGET_SHIFT = "budget_shift"  # move daily budget from one entity to another
    BUDGET_CHANGE = "budget_change"  # raise/lower one entity's daily budget
    PAUSE_ENTITY = "pause_entity"
    BID_CHANGE = "bid_change"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RecommendationStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    AWAITING_SECOND_APPROVAL = "awaiting_second_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    QUARANTINED = "quarantined"
    EXECUTING = "executing"
    EXECUTED = "executed"
    EXECUTION_FAILED = "execution_failed"


class Role(StrEnum):
    VIEWER = "viewer"
    ACCOUNT_MANAGER = "account_manager"
    SENIOR_ACCOUNT_MANAGER = "senior_account_manager"
    HEAD_OF_PERFORMANCE = "head_of_performance"
    ADMIN = "admin"


class DegradationCode(StrEnum):
    PLATFORM_UNAVAILABLE = "platform_unavailable"
    ALL_PLATFORMS_UNAVAILABLE = "all_platforms_unavailable"
    SCHEMA_DRIFT = "schema_drift"
    DQ_WARNINGS = "dq_warnings"
    INSUFFICIENT_HISTORY = "insufficient_history"
    ANOMALY_SKIPPED = "anomaly_skipped"
    ANALYST_SKIPPED = "analyst_skipped"
    OPTIMIZER_SKIPPED = "optimizer_skipped"
    OPTIMIZER_BLOCKED_DQ = "optimizer_blocked_dq"
    FRONTIER_UNAVAILABLE = "frontier_unavailable"
    REPORT_FALLBACK_FRONTIER = "report_fallback_frontier"
    REPORT_TEMPLATE = "report_template"
    VECTOR_SEARCH_UNAVAILABLE = "vector_search_unavailable"
    RERANKER_UNAVAILABLE = "reranker_unavailable"
    NO_CITATIONS = "no_citations"
    BUDGET_EXHAUSTED = "budget_exhausted"
    STEP_LIMIT = "step_limit"
    ORCHESTRATOR_RULE_FALLBACK = "orchestrator_rule_fallback"
    CONSTRAINT_REJECTED = "constraint_rejected"
    INJECTION_SUSPECTED = "injection_suspected"


class AuditAction(StrEnum):
    RUN_STARTED = "run.started"
    RUN_FINISHED = "run.finished"
    RUN_DUPLICATE = "run.duplicate"
    ORCHESTRATOR_DECISION = "orchestrator.decision"
    AGENT_STEP = "agent.step"
    RECOMMENDATION_CREATED = "recommendation.created"
    RECOMMENDATION_APPROVED = "recommendation.approved"
    RECOMMENDATION_SECOND_APPROVAL = "recommendation.second_approval"
    RECOMMENDATION_REJECTED = "recommendation.rejected"
    RECOMMENDATION_EXPIRED = "recommendation.expired"
    RECOMMENDATION_QUARANTINED = "recommendation.quarantined"
    APPROVAL_DENIED = "approval.denied"
    EXECUTION_STARTED = "execution.started"
    EXECUTION_SUCCEEDED = "execution.succeeded"
    EXECUTION_FAILED = "execution.failed"
    EXECUTION_REFUSED = "execution.refused"
    RECONCILIATION_MISMATCH = "reconciliation.mismatch"
    GUARDRAIL_BLOCK = "guardrail.block"
    KILL_SWITCH_CHANGED = "kill_switch.changed"
    RULE_PROPOSED = "brand_rule.proposed"
    RULE_APPROVED = "brand_rule.approved"
    ANOMALY_DISMISSED = "anomaly.dismissed"
    SECURITY_INCIDENT = "security.incident"
    REPORT_RELEASED = "report.released"
    DATA_ACCESS = "data.access"
