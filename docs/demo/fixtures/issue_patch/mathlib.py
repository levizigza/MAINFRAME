"""Intentionally wrong multiply — failing test fixture for mock repair."""


def multiply(a: int, b: int) -> int:
    return a + b  # BUG: should multiply
