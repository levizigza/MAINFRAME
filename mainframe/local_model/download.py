"""Explicit model downloads — never silent, never automatic."""

from __future__ import annotations

import shutil
from typing import Any

from mainframe.local_model.catalog import candidate_by_id
from mainframe.local_model.cloud_guard import is_cloud_model_name
from mainframe.local_model.select import select_candidate


def download_plan(candidate_id: str | None = None) -> dict[str, Any]:
    """Return explicit user-run commands; does not pull weights."""
    if candidate_id:
        c = candidate_by_id(candidate_id)
        if not c:
            return {"ok": False, "error": f"Unknown candidate {candidate_id!r}", "auto_download": False}
        selected = c
        reason = "user_specified"
    else:
        sel = select_candidate()
        selected = sel.get("selected")
        reason = sel.get("selection_reason")
        if not selected:
            return {
                "ok": False,
                "error": "No RAM-fitting candidate from doctor measurements.",
                "selection": sel,
                "auto_download": False,
            }

    name = selected.get("resolved_ollama_name") or selected["ollama_name"]
    if is_cloud_model_name(name):
        return {
            "ok": False,
            "error": f"Refusing cloud model {name!r}",
            "auto_download": False,
        }

    ollama_bin = shutil.which("ollama")
    commands = [
        {
            "step": 1,
            "title": "Ensure Ollama is installed and running locally",
            "argv": ["ollama", "serve"],
            "note": "Loopback only; set OLLAMA_NO_CLOUD=1 for local-only daemon.",
            "run_automatically": False,
        },
        {
            "step": 2,
            "title": "Explicit pull (user must confirm)",
            "argv": ["ollama", "pull", name],
            "note": f"Downloads weights for {name}. License: {selected.get('license')}",
            "run_automatically": False,
        },
        {
            "step": 3,
            "title": "Optional llama.cpp path (manual GGUF)",
            "argv": None,
            "gguf_hint": selected.get("gguf_hint"),
            "note": "Place GGUF yourself; point llama-server at the file. MAINFRAME never fetches GGUF.",
            "run_automatically": False,
        },
    ]
    return {
        "ok": True,
        "auto_download": False,
        "executed": False,
        "candidate": selected,
        "selection_reason": reason,
        "ollama_cli_present": bool(ollama_bin),
        "commands": commands,
        "confirm_required": True,
        "message": (
            "Download is explicit. Re-run with --confirm-pull only after reviewing "
            "license and disk/RAM fit. No silent pull."
        ),
    }


def confirm_pull(candidate_id: str | None = None, *, confirm: bool = False) -> dict[str, Any]:
    """Optionally run `ollama pull` only when confirm=True."""
    plan = download_plan(candidate_id)
    if not plan.get("ok"):
        return plan
    if not confirm:
        return {
            **plan,
            "executed": False,
            "message": "Not executed — pass confirm=True / --confirm-pull to run ollama pull.",
        }

    import subprocess

    name = plan["candidate"].get("resolved_ollama_name") or plan["candidate"]["ollama_name"]
    if is_cloud_model_name(name):
        return {"ok": False, "executed": False, "error": "Cloud model refused."}
    if not shutil.which("ollama"):
        return {
            **plan,
            "ok": False,
            "executed": False,
            "error": "ollama CLI not on PATH; install locally then retry.",
        }

    # Explicit user-confirmed pull — still local registry, may need network once.
    proc = subprocess.run(
        ["ollama", "pull", name],
        capture_output=True,
        text=True,
        timeout=3600,
    )
    return {
        **plan,
        "executed": True,
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
        "message": "Explicit ollama pull finished." if proc.returncode == 0 else "Pull failed.",
    }
