"""FreeForge thin integration — pins, spike, SQLite, discovery, Playwright probe."""

from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from mainframe.config import ROOT, ensure_state
from mainframe.eligibility import decide_provider

PINS_PATH = ROOT / "docs" / "freeforge" / "PINS.json"
DB_PATH = ROOT / ".mainframe" / "freeforge.sqlite"
SELECTED_ENGINE = "openclaw_embedded_agent_runtime"
REJECTED_ENGINE = "opencode_acp_worker"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_pins() -> dict[str, Any]:
    with PINS_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def connect_db() -> sqlite3.Connection:
    ensure_state()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS spike_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            selected_engine TEXT NOT NULL,
            rejected_engine TEXT NOT NULL,
            openclaw_present INTEGER NOT NULL,
            opencode_present INTEGER NOT NULL,
            playwright_present INTEGER NOT NULL,
            nested_loops_allowed INTEGER NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS discovery_hits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            query TEXT NOT NULL,
            api_name TEXT NOT NULL,
            description TEXT,
            auth_hint TEXT,
            source_pin TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def probe_bins() -> dict[str, Any]:
    return {
        "openclaw": shutil.which("openclaw"),
        "opencode": shutil.which("opencode"),
        "playwright": shutil.which("playwright"),
    }


def probe_playwright() -> dict[str, Any]:
    """FreeForge-owned browser probe. Pauses if Playwright/runtime missing."""
    if not shutil.which("playwright") and not _can_import_playwright():
        return {
            "status": "paused",
            "detail": "Playwright not importable/on PATH; browser checks paused.",
            "ownership": "freeforge",
        }
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "paused",
            "detail": f"Playwright import failed ({type(exc).__name__}: {exc}).",
            "ownership": "freeforge",
        }
    # Local about:blank — no hosted browser service.
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("about:blank")
            title = page.title()
            browser.close()
        return {
            "status": "available",
            "detail": f"Chromium launched; about:blank title={title!r}",
            "ownership": "freeforge",
            "engine": "playwright",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "paused",
            "detail": (
                f"Playwright present but browser launch failed "
                f"({type(exc).__name__}: {exc}). No cloud browser fallback."
            ),
            "ownership": "freeforge",
        }


def _can_import_playwright() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


@dataclass
class SpikeResult:
    selected_engine: str
    rejected_engine: str
    nested_loops_allowed: bool
    openclaw_present: bool
    opencode_present: bool
    playwright_probe: dict[str, Any]
    runtime_status: str
    rationale: list[str]
    pins: dict[str, Any]
    extension_points_doc: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_spike() -> SpikeResult:
    """Integration spike: pick one coding engine; refuse nesting."""
    pins = load_pins()
    bins = probe_bins()
    oc = bins["openclaw"] is not None
    op = bins["opencode"] is not None
    rationale = [
        "OpenClaw docs: embedded agent runtime is one integrated loop.",
        "OpenClaw docs: ACP OpenCode is an external harness process with separate auth/tools.",
        "FreeForge refuses nesting embedded coding + OpenCode ACP on the same job.",
        "OpenCode provider plugin is not treated as the coding worker.",
    ]
    selected = SELECTED_ENGINE
    rejected = REJECTED_ENGINE
    if oc and op:
        rationale.append(
            "Both CLIs present: still select OpenClaw embedded; OpenCode remains non-default."
        )
    elif oc:
        rationale.append("openclaw CLI present; embedded path is the selected engine when Gateway runs.")
    else:
        rationale.append(
            "openclaw CLI absent — architectural selection recorded; coding runtime deferred."
        )
    if not op:
        rationale.append("opencode CLI absent — ACP worker path unverified on this host.")

    runtime_status = "ready_if_gateway_configured" if oc else "deferred_openclaw_not_installed"
    playwright_probe = probe_playwright()

    result = SpikeResult(
        selected_engine=selected,
        rejected_engine=rejected,
        nested_loops_allowed=False,
        openclaw_present=oc,
        opencode_present=op,
        playwright_probe=playwright_probe,
        runtime_status=runtime_status,
        rationale=rationale,
        pins=pins,
        extension_points_doc="docs/FREEFORGE.md",
    )
    with connect_db() as conn:
        conn.execute(
            """
            INSERT INTO spike_runs (
                created_at, selected_engine, rejected_engine,
                openclaw_present, opencode_present, playwright_present,
                nested_loops_allowed, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _utc(),
                selected,
                rejected,
                int(oc),
                int(op),
                int(playwright_probe.get("status") == "available"),
                0,
                json.dumps(result.to_dict()),
            ),
        )
        conn.commit()
    return result


def freeforge_status() -> dict[str, Any]:
    pins = load_pins()
    bins = probe_bins()
    with connect_db() as conn:
        row = conn.execute(
            "SELECT created_at, selected_engine, payload_json FROM spike_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    last = None
    if row:
        last = {
            "created_at": row["created_at"],
            "selected_engine": row["selected_engine"],
            "payload": json.loads(row["payload_json"]),
        }
    return {
        "name": "FreeForge",
        "role": "cost_policy_repo_tools_verified_workflows",
        "selected_coding_engine": SELECTED_ENGINE,
        "rejected_coding_engine": REJECTED_ENGINE,
        "nested_loops_allowed": False,
        "bins": bins,
        "sqlite": str(DB_PATH.relative_to(ROOT)).replace("\\", "/"),
        "pins_path": str(PINS_PATH.relative_to(ROOT)).replace("\\", "/"),
        "last_spike": last,
        "openclaw_pin": pins["components"]["openclaw/openclaw"],
        "void_policy": "reference_only_archived",
        "eligibility_sample": decide_provider("openai_api").to_dict(),
    }


def discover_apis(query: str, limit: int = 15) -> dict[str, Any]:
    """
    Discovery against the pinned local public-apis snapshot.
    Does not call listed API endpoints. Prefer local snapshot (offline).
    Network fetch of upstream README is no longer required for discovery.
    """
    from mainframe.discovery.snapshot import search_catalog

    pins = load_pins()
    sha = pins["components"]["public-apis/public-apis"]["pin_commit"]
    local = search_catalog(query, limit=limit)
    if not local.get("ok"):
        return {
            "ok": False,
            "paused": True,
            "detail": "Local public-apis snapshot unavailable.",
            "source_pin": sha,
        }

    # Persist hits for FreeForge SQLite audit (still local-only)
    with connect_db() as conn:
        for h in local.get("hits") or []:
            conn.execute(
                """
                INSERT INTO discovery_hits (created_at, query, api_name, description, auth_hint, source_pin)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    _utc(),
                    query,
                    h.get("name"),
                    h.get("description"),
                    h.get("auth_hint"),
                    sha,
                ),
            )
        conn.commit()

    return {
        **local,
        "source_pin": sha,
        "paid_routes_auto_enabled": False,
        "backend": "local_pinned_snapshot",
    }
