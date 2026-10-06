"""Local secret facility — Windows DPAPI when available; never put secrets in config."""

from __future__ import annotations

import base64
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state

SECRET_ROOT = STATE_DIR / "secrets"
INDEX_PATH = SECRET_ROOT / "index.json"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure() -> None:
    ensure_state()
    SECRET_ROOT.mkdir(parents=True, exist_ok=True)
    if not INDEX_PATH.is_file():
        INDEX_PATH.write_text(
            json.dumps(
                {
                    "facility": "local_dpapi_or_file",
                    "note": "Secrets stay here — never in config.json, logs, or exports.",
                    "entries": {},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def dpapi_available() -> bool:
    return sys.platform == "win32"


def protect_bytes(plain: bytes) -> dict[str, Any]:
    """Encrypt with Windows DPAPI (user scope) when available."""
    if not dpapi_available():
        return {
            "ok": True,
            "mechanism": "plaintext_file_fallback",
            "blob_b64": base64.b64encode(plain).decode("ascii"),
            "dpapi": False,
        }
    import ctypes
    from ctypes import wintypes as w

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", w.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    CryptProtectData = crypt32.CryptProtectData
    CryptProtectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        w.LPCWSTR,
        ctypes.POINTER(DATA_BLOB),
        w.LPVOID,
        w.LPVOID,
        w.DWORD,
        ctypes.POINTER(DATA_BLOB),
    ]
    CryptProtectData.restype = w.BOOL

    in_buf = ctypes.create_string_buffer(plain)
    blob_in = DATA_BLOB(len(plain), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    ok = CryptProtectData(ctypes.byref(blob_in), "MAINFRAME", None, None, None, 0, ctypes.byref(blob_out))
    if not ok:
        return {
            "ok": False,
            "error": f"CryptProtectData failed ({ctypes.get_last_error()})",
            "dpapi": True,
        }
    try:
        encrypted = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)
    return {
        "ok": True,
        "mechanism": "windows_dpapi",
        "blob_b64": base64.b64encode(encrypted).decode("ascii"),
        "dpapi": True,
        "zero_fee": True,
    }


def unprotect_bytes(blob_b64: str, *, dpapi: bool) -> dict[str, Any]:
    raw = base64.b64decode(blob_b64.encode("ascii"))
    if not dpapi:
        return {"ok": True, "plain": raw, "mechanism": "plaintext_file_fallback"}
    import ctypes
    from ctypes import wintypes as w

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", w.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    CryptUnprotectData = crypt32.CryptUnprotectData
    CryptUnprotectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        ctypes.POINTER(w.LPWSTR),
        ctypes.POINTER(DATA_BLOB),
        w.LPVOID,
        w.LPVOID,
        w.DWORD,
        ctypes.POINTER(DATA_BLOB),
    ]
    CryptUnprotectData.restype = w.BOOL

    in_buf = ctypes.create_string_buffer(raw)
    blob_in = DATA_BLOB(len(raw), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    ok = CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out))
    if not ok:
        return {"ok": False, "error": f"CryptUnprotectData failed ({ctypes.get_last_error()})"}
    try:
        plain = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)
    return {"ok": True, "plain": plain, "mechanism": "windows_dpapi"}


class LocalSecretFacility:
    """Appropriate local secret facility for MAINFRAME credentials."""

    def __init__(self, root: Path | None = None) -> None:
        _ensure()
        self.root = root or SECRET_ROOT
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "index.json"
        if not self.index_path.is_file():
            self.index_path.write_text(
                json.dumps({"facility": "local_dpapi_or_file", "entries": {}}, indent=2) + "\n",
                encoding="utf-8",
            )

    def _index(self) -> dict[str, Any]:
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, Any]) -> None:
        self.index_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def store(self, secret_id: str, value: str, *, scopes: list[str] | None = None) -> dict[str, Any]:
        protected = protect_bytes(value.encode("utf-8"))
        if not protected.get("ok"):
            return protected
        path = self.root / f"{secret_id}.sealed"
        path.write_text(protected["blob_b64"] + "\n", encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        idx = self._index()
        entries = dict(idx.get("entries") or {})
        entries[secret_id] = {
            "present": True,
            "path": path.name,
            "scopes": list(scopes or ["default"]),
            "mechanism": protected.get("mechanism"),
            "dpapi": bool(protected.get("dpapi")),
            "updated_at": _utc(),
            "never_in_config": True,
        }
        idx["entries"] = entries
        self._save(idx)
        return {
            "ok": True,
            "secret_id": secret_id,
            "mechanism": protected.get("mechanism"),
            "scopes": entries[secret_id]["scopes"],
            "value_returned": False,
        }

    def get(self, secret_id: str, *, requester_scope: str) -> dict[str, Any]:
        idx = self._index()
        meta = (idx.get("entries") or {}).get(secret_id)
        if not meta or not meta.get("present"):
            return {"ok": False, "error": "missing_secret", "secret_id": secret_id}
        allowed = set(meta.get("scopes") or ["default"])
        if requester_scope not in allowed and "*" not in allowed:
            return {
                "ok": False,
                "error": "scope_denied",
                "secret_id": secret_id,
                "requester_scope": requester_scope,
                "allowed_scopes": sorted(allowed),
                "value": None,
            }
        path = self.root / meta["path"]
        if not path.is_file():
            return {"ok": False, "error": "missing_blob"}
        blob = path.read_text(encoding="utf-8").strip()
        opened = unprotect_bytes(blob, dpapi=bool(meta.get("dpapi")))
        if not opened.get("ok"):
            return opened
        return {
            "ok": True,
            "secret_id": secret_id,
            "value": opened["plain"].decode("utf-8"),
            "scope_used": requester_scope,
            "mechanism": opened.get("mechanism"),
        }

    def has(self, secret_id: str) -> bool:
        meta = (self._index().get("entries") or {}).get(secret_id) or {}
        return bool(meta.get("present")) and (self.root / meta.get("path", "")).is_file()

    def status(self) -> dict[str, Any]:
        idx = self._index()
        return {
            "facility": "windows_dpapi" if dpapi_available() else "plaintext_file_fallback",
            "dpapi_available": dpapi_available(),
            "root": str(self.root),
            "entries": {
                sid: {
                    "present": self.has(sid),
                    "scopes": meta.get("scopes"),
                    "mechanism": meta.get("mechanism"),
                    "never_in_config": True,
                }
                for sid, meta in (idx.get("entries") or {}).items()
            },
        }


_FACILITY: LocalSecretFacility | None = None


def get_facility() -> LocalSecretFacility:
    global _FACILITY
    if _FACILITY is None:
        _FACILITY = LocalSecretFacility()
    return _FACILITY
