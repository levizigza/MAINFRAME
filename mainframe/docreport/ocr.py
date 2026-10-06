"""Optional local Tesseract OCR — probed honestly; never invents OCR success."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any


def tesseract_probe() -> dict[str, Any]:
    exe = shutil.which("tesseract")
    if not exe:
        return {"available": False, "path": None, "version": None, "reason": "tesseract_not_on_path"}
    try:
        proc = subprocess.run(
            [exe, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        first = (proc.stdout or proc.stderr or "").splitlines()
        version = first[0].strip() if first else None
        return {"available": True, "path": exe, "version": version}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "path": exe, "version": None, "reason": str(exc)}


def ocr_image(path: Path, *, lang: str = "eng") -> dict[str, Any]:
    """Run Tesseract if available; otherwise return explicit unavailable status."""
    path = Path(path)
    probe = tesseract_probe()
    if not probe.get("available"):
        return {
            "ok": False,
            "error": "ocr_unavailable",
            "probe": probe,
            "path": str(path),
            "text": None,
            "page": 1,
        }
    try:
        proc = subprocess.run(
            [probe["path"], str(path), "stdout", "-l", lang],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "error": "ocr_failed",
            "detail": str(exc),
            "path": str(path),
            "text": None,
            "page": 1,
        }
    if proc.returncode != 0:
        return {
            "ok": False,
            "error": "ocr_nonzero_exit",
            "returncode": proc.returncode,
            "stderr": (proc.stderr or "")[:500],
            "path": str(path),
            "text": None,
            "page": 1,
        }
    return {
        "ok": True,
        "path": str(path),
        "text": proc.stdout or "",
        "page": 1,
        "engine": "tesseract",
        "version": probe.get("version"),
        "lang": lang,
    }
