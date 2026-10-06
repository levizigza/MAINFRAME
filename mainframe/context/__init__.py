"""Progressive context assembly — contract, overview, symbols, ranges, diagnostics."""

from mainframe.context.accept import run_context_accept
from mainframe.context.assemble import assemble_context
from mainframe.context.docs_cache import installed_api_excerpt, record_fetched_excerpt

__all__ = [
    "assemble_context",
    "installed_api_excerpt",
    "record_fetched_excerpt",
    "run_context_accept",
]
