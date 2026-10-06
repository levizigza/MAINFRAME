"""Egress gate — what may leave the device; free hosted ≠ confidential-safe."""

from __future__ import annotations

from typing import Any

from mainframe.projects.registry import get_project


def may_leave_device(
    project_id: str,
    *,
    data_class: str,
    provider_id: str | None = None,
) -> dict[str, Any]:
    rec = get_project(project_id)
    if not rec:
        return {"ok": False, "allowed": False, "error": "project_not_found"}

    eg = rec.get("egress") or {}
    if data_class in {"secrets", "permission_grants", "browser_cookies"}:
        return {
            "ok": True,
            "allowed": False,
            "reason": "never_leave_device",
            "data_class": data_class,
            "free_hosted_inference_ok_for_confidential": False,
        }

    if rec.get("local_only") or not eg.get("leave_device"):
        return {
            "ok": True,
            "allowed": False,
            "reason": "project_forbids_leave_device",
            "confidentiality": rec.get("confidentiality"),
            "data_class": data_class,
            "free_hosted_inference_ok_for_confidential": False,
        }

    allowed_classes = set(eg.get("allowed_data_classes_off_device") or [])
    if data_class not in allowed_classes:
        return {
            "ok": True,
            "allowed": False,
            "reason": "data_class_not_in_egress_policy",
            "data_class": data_class,
            "allowed_classes": sorted(allowed_classes),
            "free_hosted_inference_ok_for_confidential": False,
        }

    if provider_id:
        providers = set(eg.get("eligible_providers_may_receive") or [])
        # Free hosted inference is never auto-approved for confidential material
        if rec.get("confidentiality") in {"confidential", "local_only"}:
            return {
                "ok": True,
                "allowed": False,
                "reason": "confidential_blocks_off_device_providers",
                "free_hosted_inference_ok_for_confidential": False,
                "provider_id": provider_id,
            }
        if provider_id.startswith("hosted_") or provider_id in {
            "openai_api",
            "anthropic_api",
            "groq_cloud",
            "mistral_api",
            "google_gemini_api",
        }:
            return {
                "ok": True,
                "allowed": False,
                "reason": "free_hosted_inference_not_auto_suitable",
                "free_hosted_inference_ok_for_confidential": False,
                "provider_id": provider_id,
                "note": "Eligible free hosted routes still require explicit non-confidential approval; never auto for confidential.",
            }
        if provider_id not in providers:
            return {
                "ok": True,
                "allowed": False,
                "reason": "provider_not_in_egress_allowlist",
                "provider_id": provider_id,
                "allowed_providers": sorted(providers),
            }

    return {
        "ok": True,
        "allowed": True,
        "data_class": data_class,
        "provider_id": provider_id,
        "free_hosted_inference_ok_for_confidential": False,
    }


def local_only_inference_gate(project_id: str, *, available_local_models: list[str] | None = None) -> dict[str, Any]:
    """
    Local-only projects pause when no approved local model is available.
    Deterministic automation remains usable (caller decides).
    """
    rec = get_project(project_id)
    if not rec:
        return {"ok": False, "error": "project_not_found", "paused": True}
    if not rec.get("local_only") and rec.get("confidentiality") != "local_only":
        return {
            "ok": True,
            "paused": False,
            "local_only": False,
            "note": "Project is not local-only; still subject to egress policy.",
        }

    approved = set(rec.get("approved_local_models") or ["ollama_local"])
    available = set(available_local_models or [])
    intersection = approved & available
    if not intersection:
        return {
            "ok": True,
            "paused": True,
            "local_only": True,
            "reason": "no_approved_local_model",
            "approved_local_models": sorted(approved),
            "available_local_models": sorted(available),
            "note": "AI steps pause; deterministic automation may continue.",
            "fallback_used": False,
            "hosted_used": False,
        }
    return {
        "ok": True,
        "paused": False,
        "local_only": True,
        "approved_model": sorted(intersection)[0],
        "fallback_used": False,
        "hosted_used": False,
    }
