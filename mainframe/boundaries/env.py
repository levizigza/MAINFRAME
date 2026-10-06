"""Worker environment — model credentials must stay outside worker envs."""

from __future__ import annotations

import os
import re
from typing import Any

from mainframe.cost_gate import scrub_env_for_child

# Extra patterns beyond cost_gate scrub — model / broker credentials
_EXTRA_DENY = re.compile(
    r"(?i)(OPENAI|ANTHROPIC|GEMINI|GROQ|MISTRAL|HF_|HUGGING|OLLAMA_API|AWS_SECRET|"
    r"AZURE_|COHERE_|TOGETHER_|FIREWORKS_|REPLICATE_|MAINFRAME_CRED|BROKER_)"
)


def worker_env(
    base: dict[str, str] | None = None,
    *,
    allow_passthrough: list[str] | None = None,
) -> dict[str, Any]:
    """
    Build an environment for executable workers.

    Model and provider credentials are stripped — they must remain outside
    worker environments (broker / host only).
    """
    scrubbed = scrub_env_for_child(base if base is not None else dict(os.environ))
    allow = set(allow_passthrough or [])
    clean: dict[str, str] = {}
    removed: list[str] = []
    for k, v in scrubbed.items():
        if k in allow:
            clean[k] = v
            continue
        if _EXTRA_DENY.search(k):
            removed.append(k)
            continue
        clean[k] = v
    # Never inject credential files path into untrusted workers
    clean.pop("MAINFRAME_CREDENTIALS_DIR", None)
    return {
        "env": clean,
        "removed_keys": sorted(set(removed)),
        "credentials_outside_worker": True,
        "boundary": "environment_variables",
        "enforced": True,
    }


def assert_no_model_credentials(env: dict[str, str]) -> dict[str, Any]:
    leaked = [k for k in env if _EXTRA_DENY.search(k) or "API_KEY" in k.upper() or "SECRET" in k.upper()]
    # PATH etc. OK; filter false positives carefully
    leaked = [
        k
        for k in leaked
        if any(
            x in k.upper()
            for x in ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "OPENAI", "ANTHROPIC")
        )
    ]
    return {
        "ok": len(leaked) == 0,
        "leaked_keys": leaked,
        "credentials_outside_worker": len(leaked) == 0,
        "boundary": "environment_variables",
        "enforced": True,
    }
