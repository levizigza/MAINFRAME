"""Local model candidates — licenses, tags, tool/template notes (no downloads)."""

from __future__ import annotations

from typing import Any

# Maps doctor MODEL_CATALOG ids → pull metadata.
# Licenses are for the *weights* as commonly published on Ollama library pages;
# always re-verify via /api/show after pull.
CANDIDATES: list[dict[str, Any]] = [
    {
        "id": "tinyllama-1.1b-q4",
        "ollama_name": "tinyllama:1.1b",
        "gguf_hint": "TinyLlama-1.1B-Chat-v1.0 Q4_K_M (user-supplied path)",
        "license": "Apache-2.0 (TinyLlama weights; verify after pull)",
        "chat_template": "ChatML-style via Ollama Modelfile TEMPLATE (server-applied on /api/chat)",
        "tools_supported": False,
        "tools_note": "TinyLlama typically lacks reliable native tool calling.",
        "coding_quality": "not_assumed — CPU fit ≠ coding quality",
        "size_class": "small",
        "doctor_id": "tinyllama-1.1b-q4",
    },
    {
        "id": "qwen2.5-3b-instruct-q4",
        "ollama_name": "qwen2.5:3b-instruct",
        "gguf_hint": "Qwen2.5-3B-Instruct Q4_K_M (user-supplied path)",
        "license": "Apache-2.0 (Qwen2.5; verify after pull)",
        "chat_template": "Qwen chat template via Ollama Modelfile (server-applied on /api/chat)",
        "tools_supported": True,
        "tools_note": "Tool calling depends on model+Ollama version; verify via protocol probe.",
        "coding_quality": "not_assumed — measure locally; no frontier parity claim",
        "size_class": "small",
        "doctor_id": "qwen2.5-3b-instruct-q4",
    },
    {
        "id": "llama3.2-3b-instruct-q4",
        "ollama_name": "llama3.2:3b-instruct",
        "gguf_hint": "Llama-3.2-3B-Instruct Q4_K_M (user-supplied path)",
        "license": "Llama 3.2 Community License (Meta; verify after pull)",
        "chat_template": "Llama 3 instruct template via Ollama Modelfile",
        "tools_supported": True,
        "tools_note": "Verify tools via /api/chat tool round-trip after pull.",
        "coding_quality": "not_assumed",
        "size_class": "small",
        "doctor_id": "llama3.2-3b-instruct-q4",
    },
    {
        "id": "qwen2.5-7b-instruct-q4",
        "ollama_name": "qwen2.5:7b-instruct",
        "gguf_hint": "Qwen2.5-7B-Instruct Q4_K_M (user-supplied path)",
        "license": "Apache-2.0 (Qwen2.5; verify after pull)",
        "chat_template": "Qwen chat template via Ollama Modelfile",
        "tools_supported": True,
        "tools_note": "Often needs more RAM than small-laptop inference budget.",
        "coding_quality": "not_assumed",
        "size_class": "medium",
        "doctor_id": "qwen2.5-7b-instruct-q4",
    },
    {
        "id": "llama3.1-8b-instruct-q4",
        "ollama_name": "llama3.1:8b-instruct",
        "gguf_hint": "Llama-3.1-8B-Instruct Q4_K_M (user-supplied path)",
        "license": "Llama 3.1 Community License (Meta; verify after pull)",
        "chat_template": "Llama 3 instruct template via Ollama Modelfile",
        "tools_supported": True,
        "tools_note": "Often exceeds safe budget on 16 GiB systems.",
        "coding_quality": "not_assumed",
        "size_class": "medium",
        "doctor_id": "llama3.1-8b-instruct-q4",
    },
]


def candidate_by_id(cid: str) -> dict[str, Any] | None:
    for c in CANDIDATES:
        if c["id"] == cid or c["ollama_name"] == cid or c["doctor_id"] == cid:
            return dict(c)
    return None


def catalog_public() -> list[dict[str, Any]]:
    return [dict(c) for c in CANDIDATES]
