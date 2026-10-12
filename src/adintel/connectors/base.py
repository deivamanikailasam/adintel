from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from adintel.domain.enums import Platform
from adintel.security.secrets import Credential


@dataclass
class RawFetch:
    platform: Platform
    rows: list[dict[str, Any]]
    account_currency: str = "USD"
    api_version: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


class PlatformConnector(ABC):
    platform: Platform

    @abstractmethod
    def fetch(self, cred: Credential, brand_id: str, start: date, end: date) -> RawFetch:
        """Read-only performance report for ``[start, end]`` in the platform's native field shape."""

    @abstractmethod
    def get_entity(self, cred: Credential, brand_id: str, entity_id: str) -> dict[str, Any]:
        """Live state of one entity (ad set / ad group): ``daily_budget`` (USD), ``status``, ``name``."""

    @abstractmethod
    def apply_change(self, cred: Credential, brand_id: str, change: dict[str, Any]) -> dict[str, Any]:
        """Mutate the platform. Must refuse anything but a ``write``-scope credential."""


def get_connector(platform: Platform) -> PlatformConnector:
    from adintel.config import get_settings

    s = get_settings()
    mode = s.connector_modes.get(str(platform), s.connectors)
    if mode == "csv":
        from adintel.connectors.csv_files import CsvConnector

        return CsvConnector(platform)
    if mode == "live":
        from adintel.connectors.live import LiveConnector

        return LiveConnector(platform)
    from adintel.connectors.synthetic import SyntheticConnector

    return SyntheticConnector(platform)
