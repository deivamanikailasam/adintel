"""The degradation matrix: degrade visibly, never fail silently, never fabricate.

Every degradation is written to state as a code. It becomes a caveat block in the client report, a
run-health indicator in the UI and a metric (``adintel_degradations_total{code}``).

Three things never degrade: tenant isolation, the approval gate, and numeric grounding.
"""

from __future__ import annotations

from dataclasses import dataclass

from adintel.domain.enums import AgentName, DegradationCode, RunStatus
from adintel.domain.models import Degradation
from adintel.observability.metrics import DEGRADATIONS


@dataclass(frozen=True)
class MatrixRow:
    failure: str
    what_happens: str
    status: RunStatus | None
    caveat: str


MATRIX: dict[DegradationCode, MatrixRow] = {
    DegradationCode.PLATFORM_UNAVAILABLE: MatrixRow(
        "One ad platform down",
        "Continue with the rest; banner names the gap",
        RunStatus.DEGRADED,
        "Data from {detail} was unavailable tonight, so it is not included in this report.",
    ),
    DegradationCode.ALL_PLATFORMS_UNAVAILABLE: MatrixRow(
        "All platforms down",
        "Abort before analysis; retry at 06:00",
        RunStatus.FAILED,
        "No platform data could be retrieved; the report will be regenerated automatically.",
    ),
    DegradationCode.SCHEMA_DRIFT: MatrixRow(
        "Platform returned unknown fields",
        "Ignore them, propose a mapping for engineering review",
        RunStatus.DEGRADED,
        "Some new fields from {detail} were not yet recognised and were excluded.",
    ),
    DegradationCode.DQ_WARNINGS: MatrixRow(
        "Data quality only has warnings",
        "Anomaly + report allowed; Optimizer blocked",
        RunStatus.DEGRADED,
        "Data-quality warnings were found ({detail}); figures are shown but no changes are proposed.",
    ),
    DegradationCode.OPTIMIZER_BLOCKED_DQ: MatrixRow(
        "Optimizer blocked by data-quality warnings",
        "No recommendations",
        RunStatus.DEGRADED,
        "No budget changes are proposed this week because of data-quality warnings.",
    ),
    DegradationCode.INSUFFICIENT_HISTORY: MatrixRow(
        "Less than 28 days of history",
        "Skip anomaly detection; raw metrics only",
        RunStatus.DEGRADED,
        "There is not yet enough history to detect anomalies reliably; raw metrics are shown.",
    ),
    DegradationCode.ANOMALY_SKIPPED: MatrixRow(
        "Anomaly detection timed out or failed",
        "Metrics without an anomaly section",
        RunStatus.DEGRADED,
        "Anomaly detection could not complete tonight; this report shows metrics only.",
    ),
    DegradationCode.ANALYST_SKIPPED: MatrixRow(
        "Analyst timed out or failed",
        "Anomaly without root cause, so no Optimizer",
        RunStatus.DEGRADED,
        "The cause of the anomaly could not be determined tonight; the account team will review it.",
    ),
    DegradationCode.OPTIMIZER_SKIPPED: MatrixRow(
        "Optimizer timed out or failed",
        "Findings without recommendations",
        RunStatus.DEGRADED,
        "No recommendations could be prepared tonight; the account team will review the findings.",
    ),
    DegradationCode.FRONTIER_UNAVAILABLE: MatrixRow(
        "Frontier model outage",
        "Skip Analyst and Optimizer; small model writes a data summary",
        RunStatus.DEGRADED,
        "Advanced analysis was unavailable tonight; this is a data summary.",
    ),
    DegradationCode.REPORT_FALLBACK_FRONTIER: MatrixRow(
        "Fine-tuned report failed the number check", "Rewrite with frontier", RunStatus.DEGRADED, ""
    ),
    DegradationCode.REPORT_TEMPLATE: MatrixRow(
        "No model could write a grounded report",
        "Deterministic template report with exact figures",
        RunStatus.DEGRADED,
        "This week's report uses the standard summary format.",
    ),
    DegradationCode.VECTOR_SEARCH_UNAVAILABLE: MatrixRow(
        "Vector search down",
        "Optimizer needs at least one citation, so it produces nothing",
        RunStatus.DEGRADED,
        "Historical evidence was unavailable, so no recommendations are proposed.",
    ),
    DegradationCode.RERANKER_UNAVAILABLE: MatrixRow("Reranker down", "Use raw retrieval order", RunStatus.DEGRADED, ""),
    DegradationCode.NO_CITATIONS: MatrixRow(
        "Optimizer proposal without valid citations", "Proposal discarded", RunStatus.DEGRADED, ""
    ),
    DegradationCode.BUDGET_EXHAUSTED: MatrixRow(
        "Run budget hit",
        "Best-effort deterministic finalize",
        RunStatus.DEGRADED,
        "Tonight's analysis was shortened; the findings shown are complete but limited.",
    ),
    DegradationCode.STEP_LIMIT: MatrixRow(
        "Step limit hit (possible loop)",
        "Best-effort finalize; page — it signals an orchestration bug",
        RunStatus.DEGRADED,
        "Tonight's analysis was shortened; the findings shown are complete but limited.",
    ),
    DegradationCode.ORCHESTRATOR_RULE_FALLBACK: MatrixRow(
        "Orchestrator model failed", "Deterministic fallback rule chooses the next step", None, ""
    ),
    DegradationCode.CONSTRAINT_REJECTED: MatrixRow(
        "A proposal broke a brand constraint", "Proposal discarded, reason logged", None, ""
    ),
    DegradationCode.INJECTION_SUSPECTED: MatrixRow(
        "Model flagged prompt injection in data",
        "Output quarantined; security paged",
        RunStatus.HELD,
        "Part of tonight's output is held for review by the account team.",
    ),
}


def degrade(code: DegradationCode, agent: AgentName, detail: str = "") -> Degradation:
    row = MATRIX[code]
    DEGRADATIONS.labels(code=str(code)).inc()
    return Degradation(
        code=code, agent=agent, detail=detail, client_caveat=row.caveat.format(detail=detail) if row.caveat else ""
    )
