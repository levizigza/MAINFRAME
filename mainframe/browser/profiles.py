"""Per-project browser profiles — isolate session storage; never export credentials."""

from __future__ import annotations

import re
from pathlib import Path

from mainframe.config import STATE_DIR, ensure_state

_PROFILE_ROOT = STATE_DIR / "browser_profiles"


def _safe_project_id(project_id: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", (project_id or "default").strip())
    return cleaned[:64] or "default"


def profile_dir(project_id: str) -> Path:
    ensure_state()
    # Prefer registry-backed project browser_profile when the project exists
    try:
        from mainframe.projects.registry import get_project, project_home

        rec = get_project(project_id)
        if rec:
            path = Path(rec["paths"]["browser_profile"])
            path.mkdir(parents=True, exist_ok=True)
            return path
        # Ensure home exists for ad-hoc ids used only as browser profiles
        path = project_home(project_id) / "browser_profile"
        path.mkdir(parents=True, exist_ok=True)
        return path
    except Exception:  # noqa: BLE001
        path = _PROFILE_ROOT / _safe_project_id(project_id)
        path.mkdir(parents=True, exist_ok=True)
        return path


def profile_status(project_id: str) -> dict[str, object]:
    path = profile_dir(project_id)
    return {
        "project_id": project_id,
        "profile_path": str(path),
        "credentials_exported": False,
        "note": "Session cookies/storage stay on disk under profile; tools never return cookie values.",
    }
