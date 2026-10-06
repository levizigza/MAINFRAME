"""Visual page interpretation — only through eligible local inference routes."""

from __future__ import annotations

from typing import Any

from mainframe.eligibility import decide_provider


def interpret_page_visually(
    *,
    dom_evidence: dict[str, Any],
    screenshot_path: str | None = None,
    provider_id: str = "ollama_local",
    endpoint: str | None = "http://127.0.0.1:11434",
) -> dict[str, Any]:
    """
    DOM evidence is required first. Visual model interpretation is optional and
    refuses when no eligible route is available.
    """
    if not dom_evidence.get("summary") and not dom_evidence.get("present") is not None:
        return {
            "ok": False,
            "refused": True,
            "reason": "dom_evidence_required_first",
            "visual_used": False,
        }
    decision = decide_provider(provider_id, endpoint)
    if not decision.eligible:
        return {
            "ok": False,
            "paused": True,
            "refused": True,
            "visual_used": False,
            "dom_first": True,
            "eligibility": decision.to_dict(),
            "message": "Visual interpretation disabled; use DOM tools.",
        }
    return {
        "ok": True,
        "visual_used": False,
        "dom_first": True,
        "eligible_route_available": True,
        "screenshot_path": screenshot_path,
        "note": "Acceptance uses DOM; visual route gated and not invoked without explicit ask.",
    }
