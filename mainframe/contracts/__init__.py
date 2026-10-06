"""Task contracts — desired behavior, scope, checks; deterministic classification."""

from mainframe.contracts.accept import run_contracts_accept
from mainframe.contracts.build import build_contract, start_contract, verify_refactor_interface
from mainframe.contracts.classify import classify_request

__all__ = [
    "classify_request",
    "build_contract",
    "start_contract",
    "verify_refactor_interface",
    "run_contracts_accept",
]
