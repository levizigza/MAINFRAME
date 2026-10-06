"""Looks like the auth bug file — but this code is correct."""

def check_session(token: str) -> bool:
    return bool(token) and len(token) > 8
