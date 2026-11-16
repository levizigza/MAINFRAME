"""Pinned SWE-bench-style resolve protocol — local fixtures first; full suite later."""

from mainframe.swebench.accept import run_swebench_accept
from mainframe.swebench.runner import run_swe_slice

__all__ = ["run_swe_slice", "run_swebench_accept"]
