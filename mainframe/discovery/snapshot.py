"""Pinned public-apis discovery — local snapshot only; no auto-free; no endpoint spam."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from mainframe.config import ROOT

SNAPSHOT_DIR = ROOT / "docs" / "freeforge" / "public-apis-snapshot"
MANIFEST_PATH = SNAPSHOT_DIR / "MANIFEST.json"
CATALOG_PATH = SNAPSHOT_DIR / "catalog.json"
SHORTLIST_DIR = SNAPSHOT_DIR / "shortlist"
LICENSE_PATH = SNAPSHOT_DIR / "LICENSE"

STATES = ("eligible", "restricted", "unverified", "rejected")

# Evidence older than this relative to "today" is expired when expires_at missing.
DEFAULT_EVIDENCE_MAX_DAYS = 366


def _parse_day(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def load_catalog() -> dict[str, Any]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def load_license_text() -> str:
    if LICENSE_PATH.is_file():
        return LICENSE_PATH.read_text(encoding="utf-8")
    return "MIT — see upstream public-apis LICENSE at pin."


def list_shortlist_ids() -> list[str]:
    if not SHORTLIST_DIR.is_dir():
        return []
    return sorted(p.stem for p in SHORTLIST_DIR.glob("*.json"))


def load_shortlist(shortlist_id: str) -> dict[str, Any]:
    path = SHORTLIST_DIR / f"{shortlist_id}.json"
    if not path.is_file():
        raise FileNotFoundError(shortlist_id)
    return json.loads(path.read_text(encoding="utf-8"))


def search_catalog(
    query: str = "",
    *,
    limit: int = 25,
    include_ads: bool = False,
) -> dict[str, Any]:
    """
    Local discovery over the pinned snapshot.
    Does not call listed API endpoints, execute linked code, or install MCP servers.
    Never marks hits as free automatically.
    """
    manifest = load_manifest()
    catalog = load_catalog()
    q = query.lower().strip()
    hits: list[dict[str, Any]] = []
    skipped_ads = 0
    for entry in catalog.get("entries") or []:
        if entry.get("is_advertisement") or entry.get("is_commercial_listing"):
            skipped_ads += 1
            if not include_ads:
                continue
        blob = " ".join(
            [
                str(entry.get("name") or ""),
                str(entry.get("description") or ""),
                str(entry.get("auth_hint") or ""),
                str(entry.get("category") or ""),
                str(entry.get("link") or ""),
            ]
        ).lower()
        if q and q not in blob:
            continue
        hits.append(
            {
                "name": entry.get("name"),
                "link": entry.get("link"),
                "description": entry.get("description"),
                "auth_hint": entry.get("auth_hint"),
                "category": entry.get("category"),
                "https": entry.get("https"),
                "cors": entry.get("cors"),
                "default_state": entry.get("default_state") or "unverified",
                "free_claimed": False,
                "entitlement_from_catalog": False,
                "is_advertisement": bool(entry.get("is_advertisement")),
                "is_commercial_listing": bool(entry.get("is_commercial_listing")),
            }
        )
        if len(hits) >= limit:
            break

    return {
        "ok": True,
        "local": True,
        "called_listed_endpoints": False,
        "executed_linked_code": False,
        "installed_mcp_servers": False,
        "marked_entries_free_automatically": False,
        "source_pin": manifest["source"]["pin_commit"],
        "source_links": manifest["source"],
        "catalog_license": manifest["catalog_license"],
        "query": query,
        "count": len(hits),
        "hits": hits,
        "ads_skipped": skipped_ads if not include_ads else 0,
        "policy": manifest.get("policy"),
        "note": (
            "Discovery metadata only. Catalog MIT ≠ API terms ≠ returned-data license. "
            "Ads/commercial listings confer no entitlement. Activation requires shortlist evidence."
        ),
    }


def evidence_status(record: dict[str, Any], *, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    last = _parse_day(record.get("last_verification"))
    expires = _parse_day(record.get("evidence_expires_at"))
    pricing = record.get("pricing_evidence") or {}
    missing: list[str] = []
    for key in (
        "official_docs",
        "pricing_evidence",
        "authentication",
        "recurring_quotas",
        "intended_use_restrictions",
        "attribution",
        "retention",
        "availability",
        "licenses",
        "last_verification",
    ):
        if record.get(key) is None:
            missing.append(key)
    if not pricing.get("verified_at") and pricing.get("model") not in {"unknown", "commercial_listing"}:
        missing.append("pricing_evidence.verified_at")

    expired = False
    if expires is not None and expires < today:
        expired = True
    elif last is not None and (today - last).days > DEFAULT_EVIDENCE_MAX_DAYS and expires is None:
        expired = True

    unknown = (
        pricing.get("model") in {None, "unknown"}
        or (record.get("availability") or {}).get("status") in {None, "unknown"}
        or bool(missing)
    )
    return {
        "complete": not missing,
        "missing_fields": missing,
        "expired": expired,
        "unknown": unknown,
        "last_verification": record.get("last_verification"),
        "evidence_expires_at": record.get("evidence_expires_at"),
        "blocks_activation": expired or unknown or bool(missing),
    }


def classify_shortlist(
    record: dict[str, Any],
    *,
    workflow_purpose: str = "general",
    today: date | None = None,
) -> dict[str, Any]:
    """
    Return state in {eligible, restricted, unverified, rejected}.
    Unknown or expired evidence never yields eligible activation.
    """
    ev = evidence_status(record, today=today)
    licenses = record.get("licenses") or {}
    license_layers = {
        "catalog_license": licenses.get("catalog_license"),
        "api_terms": licenses.get("api_terms"),
        "returned_data_license": licenses.get("returned_data_license"),
        "layers_distinguished": True,
    }

    reasons: list[str] = []
    if record.get("is_advertisement") or record.get("is_commercial_listing"):
        return {
            "id": record.get("id"),
            "state": "rejected",
            "reasons": ["advertisement_or_commercial_listing_confers_no_entitlement"],
            "evidence": ev,
            "licenses": license_layers,
            "activation_allowed": False,
        }

    pricing = record.get("pricing_evidence") or {}
    availability = (record.get("availability") or {}).get("status")
    restrictions = list(record.get("intended_use_restrictions") or [])

    if availability == "unavailable":
        reasons.append("service_unavailable")
        return {
            "id": record.get("id"),
            "state": "rejected",
            "reasons": reasons,
            "evidence": ev,
            "licenses": license_layers,
            "activation_allowed": False,
        }

    if pricing.get("trial_only") or pricing.get("model") == "trial_only":
        reasons.append("trial_only")
        return {
            "id": record.get("id"),
            "state": "rejected",
            "reasons": reasons,
            "evidence": ev,
            "licenses": license_layers,
            "activation_allowed": False,
        }

    if pricing.get("paid_upgrade_required") and not pricing.get("recurring_free"):
        reasons.append("paid_upgrade_required")
        return {
            "id": record.get("id"),
            "state": "rejected",
            "reasons": reasons,
            "evidence": ev,
            "licenses": license_layers,
            "activation_allowed": False,
        }

    if ev["expired"] or ev["unknown"] or not ev["complete"]:
        reasons.append("unknown_or_expired_evidence")
        return {
            "id": record.get("id"),
            "state": "unverified",
            "reasons": reasons,
            "evidence": ev,
            "licenses": license_layers,
            "activation_allowed": False,
        }

    if "noncommercial_only" in restrictions:
        if workflow_purpose == "commercial":
            reasons.append("noncommercial_only_rejected_for_commercial_workflow")
            return {
                "id": record.get("id"),
                "state": "rejected",
                "reasons": reasons,
                "evidence": ev,
                "licenses": license_layers,
                "activation_allowed": False,
                "workflow_purpose": workflow_purpose,
            }
        return {
            "id": record.get("id"),
            "state": "restricted",
            "reasons": ["noncommercial_only"],
            "evidence": ev,
            "licenses": license_layers,
            "activation_allowed": workflow_purpose in {"noncommercial", "general", "research"},
            "workflow_purpose": workflow_purpose,
        }

    if restrictions:
        return {
            "id": record.get("id"),
            "state": "restricted",
            "reasons": list(restrictions),
            "evidence": ev,
            "licenses": license_layers,
            "activation_allowed": False,
            "workflow_purpose": workflow_purpose,
        }

    # Eligible only with complete non-expired evidence, recurring free, available
    if (
        pricing.get("recurring_free")
        and pricing.get("model") in {"free_no_key", "free_with_restrictions"}
        and not pricing.get("trial_only")
        and availability == "available"
        and not (record.get("authentication") or {}).get("required")
    ):
        return {
            "id": record.get("id"),
            "state": "eligible",
            "reasons": ["verified_recurring_free_no_key"],
            "evidence": ev,
            "licenses": license_layers,
            "activation_allowed": True,
            "workflow_purpose": workflow_purpose,
        }

    # Auth-required free recurring → restricted until scoped credentials exist
    if pricing.get("recurring_free") and availability == "available":
        return {
            "id": record.get("id"),
            "state": "restricted",
            "reasons": ["auth_or_additional_constraints"],
            "evidence": ev,
            "licenses": license_layers,
            "activation_allowed": False,
            "workflow_purpose": workflow_purpose,
        }

    return {
        "id": record.get("id"),
        "state": "unverified",
        "reasons": ["insufficient_positive_eligibility"],
        "evidence": ev,
        "licenses": license_layers,
        "activation_allowed": False,
    }


def activate_connector(
    shortlist_id: str,
    *,
    workflow_purpose: str = "general",
    today: date | None = None,
) -> dict[str, Any]:
    """
    Attempt activation. Unknown/expired evidence blocks activation.
    Does not execute linked code or call the remote API.
    """
    record = load_shortlist(shortlist_id)
    decision = classify_shortlist(record, workflow_purpose=workflow_purpose, today=today)
    allowed = bool(decision.get("activation_allowed")) and decision.get("state") == "eligible"
    # Restricted noncommercial may activate only for noncommercial purposes
    if decision.get("state") == "restricted" and decision.get("activation_allowed"):
        allowed = True
    if decision.get("evidence", {}).get("blocks_activation") and decision.get("state") != "eligible":
        # eligible path already required complete evidence
        if decision.get("state") in {"unverified", "rejected"}:
            allowed = False
    if decision.get("state") == "unverified":
        allowed = False
    if decision.get("state") == "rejected":
        allowed = False

    return {
        "ok": allowed,
        "activated": allowed,
        "shortlist_id": shortlist_id,
        "state": decision.get("state"),
        "decision": decision,
        "called_endpoint": False,
        "executed_linked_code": False,
        "installed_mcp": False,
        "message": (
            "Activated locally as an eligible connector record (no live call)."
            if allowed
            else f"Activation blocked ({decision.get('state')}: {', '.join(decision.get('reasons') or [])})."
        ),
    }


def snapshot_status() -> dict[str, Any]:
    manifest = load_manifest()
    catalog = load_catalog()
    return {
        "ok": True,
        "snapshot_dir": str(SNAPSHOT_DIR.relative_to(ROOT)).replace("\\", "/"),
        "pin_commit": manifest["source"]["pin_commit"],
        "source_links": manifest["source"],
        "catalog_license": manifest["catalog_license"],
        "license_file_present": LICENSE_PATH.is_file(),
        "entry_count": len(catalog.get("entries") or []),
        "shortlist_ids": list_shortlist_ids(),
        "policy": manifest.get("policy"),
        "readme_present": (SNAPSHOT_DIR / "README.pinned.md").is_file(),
    }
