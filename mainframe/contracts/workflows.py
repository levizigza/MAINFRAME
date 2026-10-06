"""Known repeated workflows: I/O schemas + executable assertions."""

from __future__ import annotations

from typing import Any, Callable

# Workflow id → contract template pieces
WorkflowHandler = Callable[[dict[str, Any]], dict[str, Any]]

WORKFLOWS: dict[str, dict[str, Any]] = {
    "workspace_checksum": {
        "kind": "automation",
        "match": [
            r"(?i)\b(workspace[- ]?checksum|checksum\s+(?:the\s+)?workspace)\b",
            r"(?i)\brun\s+checksum\b",
        ],
        "desired_behavior": "Compute stable SHA-256 over configured workspace paths.",
        "scope": {"paths": ["mainframe/", "docs/", ".cursor/rules/", "README.md", "LICENSE"]},
        "constraints": ["read-only", "no_network", "deterministic"],
        "invariants": [
            {"id": "same_inputs_same_hash", "type": "determinism"},
        ],
        "acceptance_checks": [
            {"id": "has_sha256", "type": "output_field", "field": "sha256"},
            {"id": "has_file_count", "type": "output_field", "field": "file_count"},
        ],
        "permitted_side_effects": ["none"],
        "input_schema": {
            "type": "object",
            "properties": {
                "include": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "required": ["sha256", "file_count"],
            "properties": {
                "sha256": {"type": "string", "minLength": 64, "maxLength": 64},
                "file_count": {"type": "integer", "minimum": 0},
                "files": {"type": "array"},
            },
        },
        "executable_assertions": [
            {"id": "sha256_hex", "type": "regex", "field": "sha256", "pattern": r"^[a-f0-9]{64}$"},
            {"id": "file_count_nonneg", "type": "min", "field": "file_count", "value": 0},
        ],
        "automation_task": "workspace-checksum",
        "start_without_clarification": True,
    },
    "echo_message": {
        "kind": "automation",
        "match": [r"(?i)\becho\b.+\bmessage\b", r"(?i)\brun\s+echo\b"],
        "desired_behavior": "Echo a message via deterministic automation task.",
        "scope": {"task": "echo"},
        "constraints": ["deterministic", "no_network"],
        "invariants": [],
        "acceptance_checks": [
            {"id": "message_echoed", "type": "output_field", "field": "message"},
        ],
        "permitted_side_effects": ["none"],
        "input_schema": {
            "type": "object",
            "required": ["message"],
            "properties": {"message": {"type": "string"}},
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "required": ["message"],
            "properties": {"message": {"type": "string"}},
        },
        "executable_assertions": [
            {"id": "message_present", "type": "output_field", "field": "message"},
        ],
        "automation_task": "echo",
        "default_inputs": {"message": "MAINFRAME ready"},
        "start_without_clarification": True,
    },
}


def match_workflow(text: str) -> str | None:
    import re

    for wid, spec in WORKFLOWS.items():
        for pat in spec.get("match") or []:
            if re.search(pat, text):
                return wid
    return None


def get_workflow(workflow_id: str) -> dict[str, Any] | None:
    return WORKFLOWS.get(workflow_id)
