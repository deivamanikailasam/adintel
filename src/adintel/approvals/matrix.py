"""Approval authority matrix (autonomy level L2: AI proposes, a named human approves, the system executes).

| Daily exposure | Who can approve | Second approver? |
|----------------|-----------------|------------------|
| < $50, low risk | Any account manager | No |
| $50–$500, low/medium | The brand's assigned AM (or a senior AM / Head of Performance) | No |
| $500–$2,000 | Senior AM or Head of Performance | No |
| > $2,000 | Head of Performance | **Yes** |
| Any, high risk or irreversible | Head of Performance | **Yes** |
| Any, during a blackout window | **Blocked** | — |

On top of the role, the approver's personal ``approval_limit_usd`` must cover the exposure.
"""

from __future__ import annotations

from dataclasses import dataclass

from adintel.domain.enums import RiskLevel, Role
from adintel.domain.models import Recommendation, User

SECOND_APPROVER_THRESHOLD = 2000.0


@dataclass(frozen=True)
class Requirement:
    roles: frozenset[Role]
    assigned_am_only: bool
    second_approver: bool
    description: str


def requirement(rec: Recommendation, exposure: float) -> Requirement:
    senior = frozenset({Role.SENIOR_ACCOUNT_MANAGER, Role.HEAD_OF_PERFORMANCE})
    if rec.risk == RiskLevel.HIGH or rec.irreversible:
        return Requirement(
            frozenset({Role.HEAD_OF_PERFORMANCE}), False, True, "high risk: Head of Performance + second approver"
        )
    if exposure > SECOND_APPROVER_THRESHOLD:
        return Requirement(
            frozenset({Role.HEAD_OF_PERFORMANCE}), False, True, "> $2,000/day: Head of Performance + second approver"
        )
    if exposure >= 500:
        return Requirement(senior, False, False, "$500–$2,000/day: senior AM or Head of Performance")
    if exposure >= 50:
        return Requirement(
            frozenset({Role.ACCOUNT_MANAGER}) | senior, True, False, "$50–$500/day: the brand's assigned AM"
        )
    return Requirement(frozenset({Role.ACCOUNT_MANAGER}) | senior, False, False, "< $50/day: any account manager")


def can_approve(user: User, rec: Recommendation, exposure: float, assigned_am: str | None) -> tuple[bool, str]:
    req = requirement(rec, exposure)
    if not set(user.roles) & req.roles:
        return False, f"role not sufficient ({req.description})"
    is_senior = bool(set(user.roles) & {Role.SENIOR_ACCOUNT_MANAGER, Role.HEAD_OF_PERFORMANCE})
    if req.assigned_am_only and not is_senior and user.user_id != assigned_am:
        return False, "only the brand's assigned account manager (or a senior) may approve this exposure"
    if user.brand_ids and rec.brand_id not in user.brand_ids and not is_senior:
        return False, "approver is not assigned to this brand"
    if user.approval_limit_usd + 0.005 < exposure:
        return False, f"approval limit ${user.approval_limit_usd:,.2f}/day is below the exposure ${exposure:,.2f}/day"
    return True, req.description
