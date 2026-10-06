"""Token estimation and optional actual usage when local inference is available."""

from __future__ import annotations

from typing import Any


def estimate_tokens(text: str) -> int:
    """Deterministic estimate (~4 chars/token). No model required."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def estimate_obj_tokens(obj: Any) -> int:
    import json

    try:
        return estimate_tokens(json.dumps(obj, ensure_ascii=False, default=str))
    except TypeError:
        return estimate_tokens(str(obj))


def report_token_use(
    assembled_text: str,
    *,
    probe_inference: bool = True,
) -> dict[str, Any]:
    """
    Always report estimated tokens. When eligible local inference is available,
    also report an actual tokenizer count if the adapter exposes one; otherwise
    note that actual is unavailable without inventing numbers.
    """
    estimated = estimate_tokens(assembled_text)
    actual: int | None = None
    inference_status = "not_probed"
    detail = None

    if probe_inference:
        try:
            from mainframe.ai import probe_free_inference

            probe = probe_free_inference(timeout_s=0.8)
            inference_status = probe.status
            detail = probe.detail
            if probe.status == "available":
                # Ollama does not expose a free tokenizer API reliably; use
                # measured byte-equivalent actual via /api/tokenize when present.
                actual = _try_ollama_token_count(assembled_text)
        except Exception as exc:  # noqa: BLE001
            inference_status = "probe_error"
            detail = str(exc)

    return {
        "estimated_tokens": estimated,
        "actual_tokens": actual,
        "actual_available": actual is not None,
        "inference_status": inference_status,
        "inference_detail": detail,
        "model_service_required": False,
    }


def _try_ollama_token_count(text: str) -> int | None:
    """Best-effort local count; returns None if unavailable (never invents)."""
    try:
        from mainframe.config import load_config
        from mainframe.eligibility import sanitize_loopback_base
        import json
        import urllib.request

        cfg = load_config()
        base, rewritten = sanitize_loopback_base(
            str(cfg.get("ai", {}).get("ollama_base_url", "http://127.0.0.1:11434"))
        )
        if rewritten:
            return None
        # Many Ollama builds lack /api/tokenize — try and accept failure honestly
        req = urllib.request.Request(
            f"{base.rstrip('/')}/api/tokenize",
            data=json.dumps({"model": "llama3.2", "prompt": text[:8000]}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=1.5) as resp:  # noqa: S310 — loopback only
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        tokens = payload.get("tokens")
        if isinstance(tokens, list):
            return len(tokens)
        if isinstance(payload.get("count"), int):
            return int(payload["count"])
    except Exception:
        return None
    return None
