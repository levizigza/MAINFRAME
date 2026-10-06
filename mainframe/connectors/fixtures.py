"""Offline fixture transport for connector development — no live network."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mainframe.config import ROOT

FIXTURES = ROOT / "docs" / "eval" / "connectors" / "fixtures"


def fixture_path(connector_id: str, name: str) -> Path:
    return FIXTURES / connector_id / f"{name}.json"


def load_fixture(connector_id: str, name: str) -> dict[str, Any]:
    path = fixture_path(connector_id, name)
    return json.loads(path.read_text(encoding="utf-8"))


def list_fixtures(connector_id: str) -> list[str]:
    d = FIXTURES / connector_id
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


class FixtureTransport:
    """Returns canned HTTP-like responses for a connector."""

    def __init__(self, connector_id: str, scenario: str = "ok") -> None:
        self.connector_id = connector_id
        self.scenario = scenario
        self.calls: list[dict[str, Any]] = []

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.calls.append({"method": method, "url": url, "headers": headers or {}, "query": query or {}})
        data = load_fixture(self.connector_id, self.scenario)
        # Allow multi-page fixtures
        pages = data.get("pages")
        if isinstance(pages, list) and pages:
            idx = len([c for c in self.calls if True]) - 1
            # count only this transport's sequential GETs
            page = pages[min(idx, len(pages) - 1)]
            return {
                "ok": True,
                "status": int(page.get("status") or data.get("status") or 200),
                "headers": dict(page.get("headers") or data.get("headers") or {}),
                "body_text": page.get("body_text"),
                "body_json": page.get("body"),
                "url": url,
                "fixture": self.scenario,
                "page_index": idx,
            }
        return {
            "ok": True,
            "status": int(data.get("status") or 200),
            "headers": dict(data.get("headers") or {}),
            "body_text": data.get("body_text"),
            "body_json": data.get("body"),
            "url": url,
            "fixture": self.scenario,
        }
