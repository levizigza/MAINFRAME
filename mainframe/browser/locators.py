"""Semantic locators — prefer Playwright get_by_role / get_by_label APIs."""

from __future__ import annotations

from typing import Any


def resolve_locator(page: Any, spec: dict[str, Any]) -> Any:
    kind = spec.get("kind") or "role"
    if kind == "role":
        role = spec.get("role")
        if not role:
            raise ValueError("role required for kind=role")
        name = spec.get("name")
        if name:
            return page.get_by_role(role, name=name)
        return page.get_by_role(role)
    if kind == "label":
        return page.get_by_label(spec["label"])
    if kind == "text":
        return page.get_by_text(spec["text"], exact=bool(spec.get("exact")))
    if kind == "test_id":
        return page.get_by_test_id(spec["test_id"])
    if kind == "css":
        return page.locator(spec["selector"])
    raise ValueError(f"unknown locator kind: {kind}")


def semantic_control_present(page: Any, *, role: str, name: str | None = None) -> dict[str, Any]:
    loc = page.get_by_role(role, name=name) if name else page.get_by_role(role)
    count = loc.count()
    return {
        "present": count > 0,
        "count": count,
        "evidence": "dom",
        "role": role,
        "name": name,
        "api": "get_by_role",
    }
