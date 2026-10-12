"""Exception hierarchy.

Every failure that the harness reacts to has its own type, so routing and degradation decisions are
made on types, never on parsing error strings.
"""

from __future__ import annotations


class AdIntelError(Exception):
    """Base class for all AdIntel errors."""


class ConfigError(AdIntelError):
    """Configuration is missing, inconsistent or unsafe (e.g. a floating model version)."""


class TenantIsolationViolation(AdIntelError):  # noqa: N818 - name is part of the documented contract
    """A query or output tried to cross a tenant boundary. Always a P1 security incident."""


class BudgetExceeded(AdIntelError):
    """The run's step/token/cost/wall-clock budget is exhausted."""


class KillSwitchEngaged(AdIntelError):
    """A global, tenant, brand or agent kill switch is on."""


class LLMError(AdIntelError):
    """Base class for model-call failures."""


class LLMTimeout(LLMError):
    """The provider did not answer within the call timeout."""


class LLMUnavailable(LLMError):
    """The provider is down or its circuit breaker is open."""


class LLMValidationError(LLMError):
    """The model output failed schema validation after all repair attempts."""


class PlatformError(AdIntelError):
    """An ad-platform API call failed."""


class PlatformUnavailable(PlatformError):
    """The ad platform is down, throttling or its circuit breaker is open."""


class SandboxViolation(AdIntelError):
    """Analyst code tried to do something outside the sandbox policy."""


class SandboxTimeout(AdIntelError):
    """Analyst code exceeded its CPU or wall-clock limit."""


class CheckpointCorrupted(AdIntelError):
    """A stored checkpoint failed its integrity check; the run must fail cleanly, not resume."""


class ApprovalError(AdIntelError):
    """An approval request failed one of the server-side checks."""

    def __init__(self, check: str, message: str) -> None:
        super().__init__(f"{check}: {message}")
        self.check = check
        self.message = message


class ExecutionError(AdIntelError):
    """The executor refused or failed to apply an approved change."""


class AuthError(AdIntelError):
    """Authentication or authorisation failed."""


class RateLimited(AdIntelError):
    """A per-tenant rate limit or quota was hit."""
