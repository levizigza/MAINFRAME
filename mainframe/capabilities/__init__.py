"""Scoped capabilities — grants, authorization, revoke, emergency stop."""

from __future__ import annotations

from mainframe.capabilities.accept import run_capabilities_accept
from mainframe.capabilities.authorize import authorize_action
from mainframe.capabilities.store import CapabilityStore

__all__ = ["CapabilityStore", "authorize_action", "run_capabilities_accept"]
