"""Lightweight dependency + test map (cached locally; no graph service)."""

from mainframe.depmap.accept import run_depmap_accept
from mainframe.depmap.cache import get_or_build
from mainframe.depmap.plan import plan_verification

__all__ = ["get_or_build", "plan_verification", "run_depmap_accept"]
