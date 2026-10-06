"""Gate: untrusted instructions cannot authorize tools, destinations, purchases, disclosure."""

from __future__ import annotations

import re
from typing import Any

from mainframe.secretdata.facility import get_facility
from mainframe.secretdata.untrusted import FORBIDDEN_FROM_UNTRUSTED, wrap_untrusted

# Patterns that look like injection trying to escalate
INJECTION_PATTERNS: list[tuple[str, str]] = [
    ("reveal_secret", r"(?i)\b(reveal|print|show|exfiltrat\w*|dump)\b.{0,40}\b(api[_-]?key|secret|password|token|credential)\b"),
    ("change_policy", r"(?i)\b(ignore|disregard)\b.{0,40}\b(previous|prior|system)\b.{0,20}\b(instruction|policy|rule)"),
    ("change_policy", r"(?i)\b(enable|allow|unlock)\b.{0,30}\b(paid|billing|spending|purchase)\b"),
    ("authorize_new_tool", r"(?i)\b(register|authorize|enable|add)\b.{0,30}\b(new\s+)?tool\b"),
    ("authorize_destination", r"(?i)\b(send|post|upload)\b.{0,40}\b(https?://|webhook|exfil)"),
    ("authorize_purchase", r"(?i)\b(buy|purchase|subscribe|checkout)\b"),
    ("authorize_disclosure", r"(?i)\b(disclose|leak|share)\b.{0,30}\b(secret|key|credential|prompt)\b"),
    ("install_package", r"(?i)\b(pip|npm|pnpm|yarn|cargo)\s+install\b"),
    ("expand_credential_scope", r"(?i)\b(grant|expand|widen)\b.{0,30}\b(credential|scope|permission)\b"),
]


def scan_untrusted_for_escalation(text: str) -> list[dict[str, Any]]:
    hits = []
    for action, pat in INJECTION_PATTERNS:
        m = re.search(pat, text)
        if m:
            hits.append({"action": action, "matched": m.group(0)[:120], "forbidden": action in FORBIDDEN_FROM_UNTRUSTED})
    return hits


def evaluate_proposed_action(
    *,
    action: str,
    from_untrusted: bool,
    envelope: dict[str, Any] | None = None,
    quoted_as_data: bool = False,
) -> dict[str, Any]:
    """
    Decide whether an action may proceed.

    Ordinary quoted instructions remain usable as *data* (quoted_as_data=True)
    without authorizing execution of the quoted directive.
    """
    if quoted_as_data and not from_untrusted:
        # Treating quote as data only
        return {
            "allowed": True,
            "as_data": True,
            "executed": False,
            "reason": "quoted_instructions_usable_as_data_only",
            "action": action,
        }

    if from_untrusted or (envelope or {}).get("untrusted"):
        if action in FORBIDDEN_FROM_UNTRUSTED or action.startswith("authorize_"):
            return {
                "allowed": False,
                "as_data": True,
                "executed": False,
                "reason": "untrusted_content_cannot_authorize",
                "action": action,
                "provenance": (envelope or {}).get("provenance"),
            }
        # Non-escalating analysis/summary of untrusted text is OK
        if action in {"summarize", "quote", "index", "retrieve_as_data"}:
            return {
                "allowed": True,
                "as_data": True,
                "executed": False,
                "reason": "untrusted_usable_as_data",
                "action": action,
            }
        return {
            "allowed": False,
            "as_data": True,
            "executed": False,
            "reason": "untrusted_default_deny_for_side_effecting_action",
            "action": action,
        }

    return {"allowed": True, "as_data": False, "executed": False, "reason": "trusted_actor", "action": action}


def handle_seeded_injection(
    raw_text: str,
    *,
    kind: str = "web_page",
    source: str = "seeded_injection",
    proposed_actions: list[str] | None = None,
) -> dict[str, Any]:
    """
    Acceptance helper: wrap seeded injection, refuse secret/policy/unauthorized acts.
    """
    env = wrap_untrusted(raw_text, kind=kind, source=source)
    hits = scan_untrusted_for_escalation(raw_text)
    facility = get_facility()
    # Attempt secret disclosure via injection — must fail
    secret_attempt = facility.get("openai_api", requester_scope="attacker_injection")
    decisions = []
    for act in proposed_actions or [h["action"] for h in hits] or ["reveal_secret"]:
        decisions.append(evaluate_proposed_action(action=act, from_untrusted=True, envelope=env))

    secrets_obtained = bool(secret_attempt.get("ok") and secret_attempt.get("value"))
    policy_changed = any(d.get("action") == "change_policy" and d.get("allowed") for d in decisions)
    unauthorized = any(d.get("allowed") and d.get("action") in FORBIDDEN_FROM_UNTRUSTED for d in decisions)

    return {
        "envelope": {k: v for k, v in env.items() if k != "text"}
        | {"text_preview": raw_text[:160], "text_len": len(raw_text)},
        "escalation_hits": hits,
        "decisions": decisions,
        "secret_access_attempt": {
            "ok": secret_attempt.get("ok"),
            "error": secret_attempt.get("error"),
            "value_returned": bool(secret_attempt.get("value")),
        },
        "secrets_obtained": secrets_obtained,
        "policy_changed": policy_changed,
        "unauthorized_action_triggered": unauthorized,
        "ok": (not secrets_obtained) and (not policy_changed) and (not unauthorized),
    }
