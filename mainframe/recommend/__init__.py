"""Recommended FreeForge configuration from accumulated local evidence."""

from mainframe.recommend.accept import run_recommend_accept
from mainframe.recommend.suite import run_recommend

__all__ = ["run_recommend", "run_recommend_accept"]
