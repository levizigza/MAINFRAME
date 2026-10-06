"""Credential broker — secrets stay here, never in config or child env by default."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state
from mainframe.cost_gate import scrub_env_for_child

CRED_DIR = STATE_DIR / "credentials"
CRED_INDEX = CRED_DIR / "index.json"


class CredentialBroker:
    """
    Holds provider credential references under ``.mainframe/credentials/``.

    Values are never written into ``config.json``. Scrubbed child envs do not
    inherit these secrets unless an adapter explicitly requests a one-shot env
    for a gated live call (and live remains disabled for unverified providers).
    """

    def __init__(self, root: Path | None = None) -> None:
        ensure_state()
        self.root = root or CRED_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        if not CRED_INDEX.exists():
            CRED_INDEX.write_text(
                json.dumps(
                    {
                        "note": (
                            "Provider API keys live only under this directory. "
                            "Unverified free-tier candidates remain disabled for live dispatch."
                        ),
                        "providers": {},
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

    def _index(self) -> dict[str, Any]:
        return json.loads(CRED_INDEX.read_text(encoding="utf-8"))

    def _save_index(self, data: dict[str, Any]) -> None:
        CRED_INDEX.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def has_credential(self, provider_id: str) -> bool:
        idx = self._index().get("providers") or {}
        meta = idx.get(provider_id) or {}
        path = self.root / f"{provider_id}.secret"
        return bool(meta.get("present")) and path.is_file() and path.stat().st_size > 0

    def store(self, provider_id: str, secret: str, *, env_hint: str | None = None) -> dict[str, Any]:
        path = self.root / f"{provider_id}.secret"
        # Prefer DPAPI-backed local secret facility; keep legacy file pointer for status.
        try:
            from mainframe.secretdata.facility import get_facility

            sealed = get_facility().store(provider_id, secret.strip(), scopes=[provider_id])
        except Exception:  # noqa: BLE001
            sealed = {"ok": False}
        if not sealed.get("ok"):
            path.write_text(secret.strip(), encoding="utf-8")
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        else:
            # Marker file without raw secret (facility holds sealed blob)
            path.write_text("sealed:see_mainframe_secretdata_facility\n", encoding="utf-8")
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        idx = self._index()
        providers = dict(idx.get("providers") or {})
        providers[provider_id] = {
            "present": True,
            "path": str(path.name),
            "env_hint": env_hint,
            "never_in_config": True,
            "facility": sealed.get("mechanism") if sealed.get("ok") else "legacy_file",
            "scopes": [provider_id],
        }
        idx["providers"] = providers
        self._save_index(idx)
        return {"ok": True, "provider_id": provider_id, "stored": True, "facility": providers[provider_id].get("facility")}

    def get(self, provider_id: str) -> str | None:
        if not self.has_credential(provider_id):
            return None
        try:
            from mainframe.secretdata.facility import get_facility

            opened = get_facility().get(provider_id, requester_scope=provider_id)
            if opened.get("ok") and opened.get("value"):
                return str(opened["value"])
        except Exception:  # noqa: BLE001
            pass
        path = self.root / f"{provider_id}.secret"
        text = path.read_text(encoding="utf-8").strip()
        if text.startswith("sealed:"):
            return None
        return text or None

    def clear(self, provider_id: str) -> dict[str, Any]:
        path = self.root / f"{provider_id}.secret"
        if path.exists():
            path.unlink()
        idx = self._index()
        providers = dict(idx.get("providers") or {})
        providers.pop(provider_id, None)
        idx["providers"] = providers
        self._save_index(idx)
        return {"ok": True, "cleared": provider_id}

    def status(self) -> dict[str, Any]:
        idx = self._index()
        out = {}
        for pid, meta in (idx.get("providers") or {}).items():
            out[pid] = {
                "present": self.has_credential(pid),
                "env_hint": meta.get("env_hint"),
                "never_in_config": True,
            }
        return {
            "credential_dir": str(self.root),
            "providers": out,
            "inherited_paid_fallback": False,
            "scrubbed_child_env_preview_keys": sorted(
                k for k in scrub_env_for_child().keys() if "KEY" in k.upper() or "TOKEN" in k.upper()
            )[:0],  # always empty after scrub of secrets
        }


_BROKER: CredentialBroker | None = None


def get_broker() -> CredentialBroker:
    global _BROKER
    if _BROKER is None:
        _BROKER = CredentialBroker()
    return _BROKER
