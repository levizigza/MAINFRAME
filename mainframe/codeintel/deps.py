"""Resolve dependency APIs against installed versions (no model)."""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Any

from mainframe.codeintel.provenance import evidence


def installed_version(distribution_name: str) -> str | None:
    try:
        return importlib.metadata.version(distribution_name)
    except importlib.metadata.PackageNotFoundError:
        return None


def resolve_module(module_name: str, *, extra_sys_path: list[str] | None = None) -> dict[str, Any]:
    """Import or locate a module; report installed version when applicable."""
    added: list[str] = []
    try:
        if extra_sys_path:
            for p in extra_sys_path:
                if p not in sys.path:
                    sys.path.insert(0, p)
                    added.append(p)
        spec = importlib.util.find_spec(module_name)
        if spec is None:
            return {
                "ok": False,
                "module": module_name,
                "error": "module_not_found",
                "evidence": evidence(
                    "installed_api_fact",
                    tool="importlib.util.find_spec",
                    detail="Module not found on sys.path",
                ),
                "model_service_used": False,
            }
        mod = importlib.import_module(module_name)
        dist = _guess_distribution(module_name)
        ver = installed_version(dist) if dist else None
        origin = getattr(spec, "origin", None)
        return {
            "ok": True,
            "module": module_name,
            "distribution": dist,
            "installed_version": ver,
            "origin": origin,
            "file": str(Path(origin)).replace("\\", "/") if origin and origin != "built-in" else origin,
            "evidence": evidence(
                "installed_api_fact",
                tool="importlib",
                detail=f"Resolved {module_name} version={ver}",
            ),
            "model_service_used": False,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "module": module_name,
            "error": f"{type(exc).__name__}: {exc}",
            "evidence": evidence("installed_api_fact", tool="importlib", detail=str(exc)),
            "model_service_used": False,
        }
    finally:
        for p in added:
            try:
                sys.path.remove(p)
            except ValueError:
                pass


def _guess_distribution(module_name: str) -> str | None:
    top = module_name.split(".")[0]
    # Common cases: module name == distribution name
    if installed_version(top):
        return top
    # stdlib — no distribution version; mark as stdlib
    if top in sys.stdlib_module_names:
        return None
    return top


def list_public_api(module_name: str, *, extra_sys_path: list[str] | None = None) -> dict[str, Any]:
    info = resolve_module(module_name, extra_sys_path=extra_sys_path)
    if not info.get("ok"):
        return info
    mod = importlib.import_module(module_name)
    names = [n for n in dir(mod) if not n.startswith("_")]
    return {
        **info,
        "public_names": sorted(names),
        "evidence": evidence(
            "installed_api_fact",
            tool="dir()+importlib",
            detail=f"{len(names)} public names",
        ),
    }


def check_callable(
    module_name: str,
    attr_path: str,
    *,
    extra_sys_path: list[str] | None = None,
) -> dict[str, Any]:
    """
    Accept/reject a proposed call target against the installed module.

    ``attr_path`` may be dotted (e.g. ``JSONDecoder.decode``).
    """
    info = resolve_module(module_name, extra_sys_path=extra_sys_path)
    if not info.get("ok"):
        return {
            "ok": True,
            "accepted": False,
            "reason": "module_not_installed_or_unresolvable",
            "module": module_name,
            "attr": attr_path,
            "proposed_call_rejected": True,
            "evidence": info.get("evidence"),
            "model_service_used": False,
        }

    mod = importlib.import_module(module_name)
    obj: Any = mod
    parts = attr_path.split(".")
    walked: list[str] = []
    try:
        for part in parts:
            if not hasattr(obj, part):
                return {
                    "ok": True,
                    "accepted": False,
                    "reason": "attribute_absent_from_installed_module",
                    "module": module_name,
                    "attr": attr_path,
                    "missing_part": part,
                    "walked": walked,
                    "installed_version": info.get("installed_version"),
                    "proposed_call_rejected": True,
                    "signature": None,
                    "evidence": evidence(
                        "installed_api_fact",
                        tool="hasattr/importlib",
                        detail=f"{module_name}.{'.'.join(walked+[part])} absent",
                    ),
                    "model_service_used": False,
                }
            obj = getattr(obj, part)
            walked.append(part)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": True,
            "accepted": False,
            "reason": f"resolve_error:{type(exc).__name__}",
            "proposed_call_rejected": True,
            "error": str(exc),
            "model_service_used": False,
        }

    sig = None
    sig_evidence = evidence("installed_api_fact", tool="inspect.signature", detail="unavailable")
    try:
        if callable(obj):
            sig = str(inspect.signature(obj))
            sig_evidence = evidence(
                "installed_api_fact",
                tool="inspect.signature",
                detail=sig,
            )
    except (TypeError, ValueError):
        pass

    return {
        "ok": True,
        "accepted": True,
        "reason": "attribute_present_on_installed_module",
        "module": module_name,
        "attr": attr_path,
        "installed_version": info.get("installed_version"),
        "origin": info.get("origin"),
        "callable": callable(obj),
        "signature": sig,
        "proposed_call_rejected": False,
        "evidence": sig_evidence,
        "model_service_used": False,
    }
