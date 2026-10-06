"""Write a local scheduled report artifact (deterministic, no model)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_local_report(*, title: str, out_path: Path) -> dict[str, Any]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "title": title,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kind": "scheduled_local_report",
        "model_requests": 0,
        "outbound_delivery": False,
        "generated_by": "mainframe.schedule.report.write_local_report",
    }
    text = json.dumps(payload, indent=2) + "\n"
    out_path.write_text(text, encoding="utf-8")
    return {
        "ok": True,
        "path": str(out_path),
        "bytes": len(text.encode()),
        "title": title,
    }
