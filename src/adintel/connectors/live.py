"""Live connector placeholder.

Real Google Ads / Meta Marketing / TikTok Business / LinkedIn Marketing / Amazon Ads clients plug in
here behind the same interface. They are intentionally not implemented in the local build: they need
OAuth app registration per agency. The promotion guide (docs/14-production) lists the steps; the
nightly contract tests (tests/contract/) run against read-only sandbox accounts once configured.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from adintel.connectors.base import PlatformConnector, RawFetch
from adintel.core.errors import PlatformUnavailable
from adintel.domain.enums import Platform
from adintel.security.secrets import Credential


class LiveConnector(PlatformConnector):
    def __init__(self, platform: Platform) -> None:
        self.platform = platform

    def _todo(self) -> PlatformUnavailable:
        return PlatformUnavailable(f"live connector for {self.platform} is not configured in this deployment")

    def fetch(self, cred: Credential, brand_id: str, start: date, end: date) -> RawFetch:
        raise self._todo()

    def get_entity(self, cred: Credential, brand_id: str, entity_id: str) -> dict[str, Any]:
        raise self._todo()

    def apply_change(self, cred: Credential, brand_id: str, change: dict[str, Any]) -> dict[str, Any]:
        raise self._todo()
