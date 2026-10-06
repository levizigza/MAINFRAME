"""Targeted fault-injection tests and published failure matrix."""

from __future__ import annotations

from mainframe.faults.accept import run_faults_accept
from mainframe.faults.matrix import publish_failure_matrix

__all__ = ["publish_failure_matrix", "run_faults_accept"]
