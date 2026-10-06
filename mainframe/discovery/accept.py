"""Acceptance: local public-apis snapshot discovery + shortlist activation gates."""

from __future__ import annotations

from datetime import date
from typing import Any

from mainframe.discovery.snapshot import (
    activate_connector,
    classify_shortlist,
    load_manifest,
    load_shortlist,
    search_catalog,
    snapshot_status,
)


def run_discovery_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    status = snapshot_status()
    manifest = load_manifest()
    checks.append(
        {
            "id": "pinned_snapshot_preserves_license_and_source_links",
            "ok": (
                status.get("ok") is True
                and status.get("license_file_present") is True
                and status.get("readme_present") is True
                and (status.get("entry_count") or 0) > 100
                and manifest["catalog_license"]["spdx"] == "MIT"
                and "pin_commit" in (manifest.get("source") or {})
                and "git_url" in (manifest.get("source") or {})
                and manifest["policy"]["mark_every_entry_free_automatically"] is False
                and manifest["policy"]["execute_linked_code"] is False
                and manifest["policy"]["install_listed_mcp_servers"] is False
                and manifest["policy"]["discovery_calls_listed_endpoints"] is False
            ),
            "detail": {
                "pin": status.get("pin_commit"),
                "entries": status.get("entry_count"),
                "source_links": status.get("source_links"),
                "policy": status.get("policy"),
            },
        }
    )

    local = search_catalog("dog", limit=10)
    checks.append(
        {
            "id": "discovery_works_locally_without_calling_endpoints",
            "ok": (
                local.get("ok") is True
                and local.get("local") is True
                and local.get("called_listed_endpoints") is False
                and local.get("executed_linked_code") is False
                and local.get("installed_mcp_servers") is False
                and local.get("marked_entries_free_automatically") is False
                and (local.get("count") or 0) >= 1
                and all(h.get("free_claimed") is False for h in local.get("hits") or [])
                and all(h.get("entitlement_from_catalog") is False for h in local.get("hits") or [])
            ),
            "detail": {
                "count": local.get("count"),
                "sample": (local.get("hits") or [])[:2],
                "ads_skipped": local.get("ads_skipped"),
            },
        }
    )

    # Genuinely eligible connector
    dog = activate_connector("dog_ceo", workflow_purpose="general")
    dog_cls = classify_shortlist(load_shortlist("dog_ceo"))
    checks.append(
        {
            "id": "genuinely_eligible_connector",
            "ok": (
                dog_cls.get("state") == "eligible"
                and dog.get("activated") is True
                and dog.get("called_endpoint") is False
                and (dog_cls.get("licenses") or {}).get("layers_distinguished") is True
            ),
            "detail": {"classify": dog_cls, "activate": dog},
        }
    )

    # Noncommercial-only rejected for commercial workflow
    nc_com = activate_connector("open_library_covers_nc", workflow_purpose="commercial")
    nc_cls = classify_shortlist(
        load_shortlist("open_library_covers_nc"), workflow_purpose="commercial"
    )
    nc_ok = classify_shortlist(
        load_shortlist("open_library_covers_nc"), workflow_purpose="noncommercial"
    )
    checks.append(
        {
            "id": "noncommercial_rejected_for_commercial_workflow",
            "ok": (
                nc_cls.get("state") == "rejected"
                and "noncommercial_only_rejected_for_commercial_workflow" in (nc_cls.get("reasons") or [])
                and nc_com.get("activated") is False
                and nc_ok.get("state") == "restricted"
            ),
            "detail": {"commercial": nc_cls, "noncommercial": nc_ok, "activate": nc_com},
        }
    )

    # Trial-only rejection
    trial = activate_connector("weather_saas_trial", workflow_purpose="general")
    trial_cls = classify_shortlist(load_shortlist("weather_saas_trial"))
    checks.append(
        {
            "id": "trial_only_rejection",
            "ok": (
                trial_cls.get("state") == "rejected"
                and "trial_only" in (trial_cls.get("reasons") or [])
                and trial.get("activated") is False
            ),
            "detail": {"classify": trial_cls, "activate": trial},
        }
    )

    # Unavailable service
    dead = activate_connector("discontinued_geo_demo", workflow_purpose="general")
    dead_cls = classify_shortlist(load_shortlist("discontinued_geo_demo"), today=date(2026, 9, 29))
    checks.append(
        {
            "id": "unavailable_service",
            "ok": (
                dead_cls.get("state") == "rejected"
                and "service_unavailable" in (dead_cls.get("reasons") or [])
                and dead.get("activated") is False
            ),
            "detail": {"classify": dead_cls, "activate": dead},
        }
    )

    # Unknown/expired evidence blocks activation
    expired_ev = dead_cls.get("evidence") or {}
    checks.append(
        {
            "id": "unknown_or_expired_evidence_blocks_activation",
            "ok": (
                expired_ev.get("expired") is True
                and expired_ev.get("blocks_activation") is True
                and dead.get("activated") is False
            ),
            "detail": expired_ev,
        }
    )

    # Ads confer no entitlement
    ad = classify_shortlist(load_shortlist("apilayer_marketplace_ad"))
    ad_act = activate_connector("apilayer_marketplace_ad")
    checks.append(
        {
            "id": "ads_commercial_listings_no_entitlement",
            "ok": (
                ad.get("state") == "rejected"
                and "advertisement_or_commercial_listing_confers_no_entitlement" in (ad.get("reasons") or [])
                and ad_act.get("activated") is False
            ),
            "detail": {"classify": ad, "activate": ad_act},
        }
    )

    # License layers distinguished on shortlist
    dog_rec = load_shortlist("dog_ceo")
    lic = dog_rec.get("licenses") or {}
    checks.append(
        {
            "id": "catalog_api_and_data_licenses_distinguished",
            "ok": (
                "catalog_license" in lic
                and "api_terms" in lic
                and "returned_data_license" in lic
                and lic["catalog_license"].get("spdx") == "MIT"
                and bool(lic["returned_data_license"].get("note"))
            ),
            "detail": lic,
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {"ok": failed == 0, "passed": passed, "failed": failed, "checks": checks}
