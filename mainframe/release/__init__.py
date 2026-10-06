"""Minimal local release packaging — no hosted CI, signing, or cloud storage required."""

from mainframe.release.accept import run_release_accept
from mainframe.release.suite import run_release_package

__all__ = ["run_release_package", "run_release_accept"]
