"""Hosted provider adapters — investigated candidates; live only if verified free."""

from __future__ import annotations

from mainframe.providers.accept import run_providers_accept
from mainframe.providers.broker import get_broker
from mainframe.providers.dispatch import list_adapters, live_or_pause, run_protocol_fixture
from mainframe.providers.investigation import investigation_report

__all__ = [
    "get_broker",
    "investigation_report",
    "list_adapters",
    "live_or_pause",
    "run_protocol_fixture",
    "run_providers_accept",
]
