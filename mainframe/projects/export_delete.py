"""Project export and deletion — preview first; no credentials; honest erasure."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.projects.registry import get_project, load_registry, project_home, save_registry, safe_project_id

# Keys / substrings that must never appear in exports
_CREDENTIAL_KEYS = {
    "password",
    "api_key",
    "apikey",
    "secret",
    "token",
    "credential",
    "authorization",
    "private_key",
    "access_key",
    "refresh_token",
    "client_secret",
    "bearer",
}


ERASURE_DISCLAIMER = (
    "Deletion removes FreeForge-managed project files and marks the registry entry deleted. "
    "This storage system cannot guarantee secure erasure. Backups, Recycle Bin, Volume Shadow "
    "Copy, SSD wear-leveling remaps, OneDrive/cloud replicas, and OS caches may retain copies."
)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_credential_key(key: str) -> bool:
    k = key.casefold().replace("-", "_")
    return any(part in k for part in _CREDENTIAL_KEYS)


def scrub_credentials(obj: Any) -> Any:
    """Recursively strip credential fields from export payloads."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if _is_credential_key(str(k)):
                out[k] = "[REDACTED_CREDENTIAL]"
            else:
                out[k] = scrub_credentials(v)
        return out
    if isinstance(obj, list):
        return [scrub_credentials(x) for x in obj]
    if isinstance(obj, str):
        # Heuristic: long bearer-like tokens
        if obj.lower().startswith("sk-") or obj.lower().startswith("ghp_"):
            return "[REDACTED_CREDENTIAL]"
        return obj
    return obj


def preview_affected_records(project_id: str) -> dict[str, Any]:
    """Preview what export or delete would touch — before any mutation."""
    rec = get_project(project_id)
    if not rec:
        return {"ok": False, "error": "project_not_found"}
    home = project_home(project_id)
    counts: dict[str, int] = {}
    samples: list[dict[str, str]] = []
    for area in ("workspace", "artifacts", "memory", "cache", "secrets", "browser_profile", "grants", "exports"):
        root = home / area
        n = 0
        if root.is_dir():
            for p in root.rglob("*"):
                if p.is_file():
                    n += 1
                    if len(samples) < 40:
                        samples.append(
                            {
                                "area": area,
                                "path": str(p.relative_to(home)).replace("\\", "/"),
                            }
                        )
        counts[area] = n

    # Secrets are listed by metadata only — never values
    secret_meta = []
    secrets_index = home / "secrets" / "index.json"
    if secrets_index.is_file():
        try:
            idx = json.loads(secrets_index.read_text(encoding="utf-8"))
            for sid, meta in (idx.get("entries") or {}).items():
                secret_meta.append(
                    {
                        "secret_id": sid,
                        "present": bool(meta.get("present")),
                        "scopes": meta.get("scopes"),
                        "value_included": False,
                    }
                )
        except (OSError, json.JSONDecodeError):
            pass

    return {
        "ok": True,
        "project_id": rec["project_id"],
        "home": str(home),
        "record_counts": counts,
        "sample_paths": samples,
        "secret_refs": secret_meta,
        "credentials_in_preview": False,
        "secure_erasure_guaranteed": False,
        "erasure_disclaimer": ERASURE_DISCLAIMER,
    }


def export_project(project_id: str, *, dest: Path | None = None) -> dict[str, Any]:
    """
    Export project metadata + non-secret artifacts.
    Credentials and sealed secret blobs are omitted.
    """
    rec = get_project(project_id)
    if not rec:
        return {"ok": False, "error": "project_not_found"}
    preview = preview_affected_records(project_id)
    home = project_home(project_id)
    stamp = _utc().replace(":", "").replace("+", "_").replace(".", "_")
    out_dir = dest or (home / "exports" / f"export_{stamp}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Scrubbed project record (no secret paths contents)
    safe_rec = scrub_credentials(dict(rec))
    # Never copy sealed secrets or token secret hashes into export
    manifest = {
        "exported_at": _utc(),
        "project": safe_rec,
        "preview": {
            "record_counts": preview.get("record_counts"),
            "secret_refs": preview.get("secret_refs"),
        },
        "credentials_included": False,
        "secrets_included": False,
        "permission_token_secrets_included": False,
        "secure_erasure_guaranteed": False,
        "note": "Export omits secrets/, sealed blobs, and raw permission token secrets.",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    # Copy artifacts and workspace text-ish files only (skip secrets/browser sealed)
    copied = []
    for area in ("artifacts", "workspace"):
        src = home / area
        if not src.is_dir():
            continue
        dst = out_dir / area
        for p in src.rglob("*"):
            if not p.is_file():
                continue
            # Skip anything that looks sealed/credential
            if p.suffix in {".sealed", ".key", ".pem"} or "secret" in p.name.casefold():
                continue
            rel = p.relative_to(src)
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            raw = p.read_bytes()
            # Skip only obvious private-key material; scrub credential fields instead of omitting notes
            if b"BEGIN RSA PRIVATE KEY" in raw or b"BEGIN OPENSSH PRIVATE KEY" in raw:
                continue
            text_try = None
            try:
                text_try = raw.decode("utf-8")
            except UnicodeDecodeError:
                # Copy small non-text artifacts as-is only under artifacts/
                if area == "artifacts" and len(raw) < 2_000_000:
                    target.write_bytes(raw)
                    copied.append(f"{area}/{rel.as_posix()}")
                continue
            # Prefer structured scrub when content is JSON
            written = text_try
            try:
                parsed = json.loads(text_try)
                written = json.dumps(scrub_credentials(parsed), indent=2) + "\n"
            except json.JSONDecodeError:
                body = scrub_credentials({"body": text_try}).get("body", text_try)
                written = body if isinstance(body, str) else text_try
            if isinstance(written, str):
                low = written.casefold()
                for marker in ("sk-live-", "sk-secret-", "ghp_", "begin rsa private"):
                    if marker in low:
                        written = "[REDACTED_CREDENTIAL]\n"
                        break
            target.write_text(written if isinstance(written, str) else text_try, encoding="utf-8")
            copied.append(f"{area}/{rel.as_posix()}")

    # Verify no credential values in manifest dump
    blob = (out_dir / "manifest.json").read_text(encoding="utf-8")
    has_cred = any(
        x in blob.casefold()
        for x in ("sk-live", "sk-secret", "ghp_", "BEGIN RSA PRIVATE")
    )

    return {
        "ok": True,
        "project_id": rec["project_id"],
        "export_dir": str(out_dir),
        "copied": copied,
        "credentials_included": False,
        "credentials_detected_in_manifest": has_cred,
        "secrets_included": False,
        "preview": preview,
        "secure_erasure_guaranteed": False,
    }


def delete_project(project_id: str, *, confirm: bool = False, preview_only: bool = False) -> dict[str, Any]:
    preview = preview_affected_records(project_id)
    if not preview.get("ok"):
        return preview
    if preview_only or not confirm:
        return {
            "ok": True,
            "deleted": False,
            "preview_only": True,
            "preview": preview,
            "secure_erasure_guaranteed": False,
            "erasure_disclaimer": ERASURE_DISCLAIMER,
            "note": "Pass confirm=True to apply best-effort deletion after reviewing preview.",
        }

    pid = safe_project_id(project_id)
    home = project_home(pid)
    # Remove secrets and tokens first (best-effort)
    errors: list[str] = []
    try:
        if home.is_dir():
            shutil.rmtree(home, ignore_errors=False)
    except OSError as exc:
        errors.append(str(exc))
        # Partial cleanup
        shutil.rmtree(home, ignore_errors=True)

    reg = load_registry()
    if pid in (reg.get("projects") or {}):
        reg["projects"][pid]["deleted"] = True
        reg["projects"][pid]["deleted_at"] = _utc()
        reg["projects"][pid]["workspace"] = None
        # Strip lingering path strings that might point at removed trees
        reg["projects"][pid]["paths"] = {}
        save_registry(reg)

    return {
        "ok": errors == [],
        "deleted": True,
        "project_id": pid,
        "preview": preview,
        "errors": errors,
        "secure_erasure_guaranteed": False,
        "erasure_disclaimer": ERASURE_DISCLAIMER,
        "credentials_exported": False,
    }
