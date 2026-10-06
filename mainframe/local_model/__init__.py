"""Optional local-model adapter (Ollama native / llama.cpp) — not required."""

from __future__ import annotations

from mainframe.local_model.accept import run_local_model_accept
from mainframe.local_model.bench import run_benchmarks
from mainframe.local_model.download import confirm_pull, download_plan
from mainframe.local_model.protocol import verify_protocol
from mainframe.local_model.select import select_candidate
from mainframe.local_model.status import local_model_status, run_with_optional_model

__all__ = [
    "confirm_pull",
    "download_plan",
    "local_model_status",
    "run_benchmarks",
    "run_local_model_accept",
    "run_with_optional_model",
    "select_candidate",
    "verify_protocol",
]
