"""Ad-platform connectors. Reads are used by the agent worker; writes only by the executor."""

from adintel.connectors.base import PlatformConnector, RawFetch, get_connector

__all__ = ["PlatformConnector", "RawFetch", "get_connector"]
