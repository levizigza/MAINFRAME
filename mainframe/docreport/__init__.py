"""Local document → report: ingest, extract, validate, dedupe, CSV + readable report."""

from __future__ import annotations

from mainframe.docreport.accept import run_docreport_accept
from mainframe.docreport.pipeline import run_pipeline

__all__ = ["run_pipeline", "run_docreport_accept"]
