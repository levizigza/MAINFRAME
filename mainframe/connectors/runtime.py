"""Execute connector operations — fixtures or live; read/write separation."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from mainframe.connectors.catalog import all_connector_specs, get_connector_spec
from mainframe.connectors.errors import (
    MALFORMED_RESPONSE,
    PARTIAL_PAGINATION,
    QUOTA_EXHAUSTED,
    SCHEMA_DRIFT,
    WRITE_ON_READ_CONNECTOR,
    structured_error,
)
from mainframe.connectors.fixtures import FixtureTransport
from mainframe.connectors.http_client import LiveTransport
from mainframe.connectors.pagination import extract_items, next_page_args, pagination_complete
from mainframe.connectors.provenance import build_provenance
from mainframe.connectors.schema_check import validate_output
from mainframe.connectors.security import (
    build_url,
    refuse_credentials_to_foreign_url,
    refuse_model_chosen_url,
)
from mainframe.connectors.types import ConnectorSpec, OperationSpec
from mainframe.workflows.typesafe import validate_value_against_schema

# Exact in-process cache for stable read GETs (keyed by connector/op/query).
_RESPONSE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _cache_key(connector_id: str, op_id: str, query: dict[str, Any]) -> str:
    return f"{connector_id}:{op_id}:{json.dumps(query, sort_keys=True, default=str)}"


def _cache_get(key: str) -> dict[str, Any] | None:
    import time

    row = _RESPONSE_CACHE.get(key)
    if not row:
        return None
    expires, payload = row
    if time.time() > expires:
        _RESPONSE_CACHE.pop(key, None)
        return None
    out = dict(payload)
    out["cache_hit"] = True
    out["request_avoided"] = True
    return out


def _cache_put(key: str, payload: dict[str, Any], freshness_s: int) -> None:
    import time

    _RESPONSE_CACHE[key] = (time.time() + max(1, freshness_s), dict(payload))


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def call_operation(
    connector_id: str,
    op_id: str,
    args: dict[str, Any] | None = None,
    *,
    mode: str = "fixture",
    fixture_scenario: str = "ok",
    transport: Any = None,
) -> dict[str, Any]:
    """
    mode: fixture | live
    Never sends credentials to model-chosen URLs; hosts must match allowlist.
    """
    args = dict(args or {})
    spec = get_connector_spec(connector_id)
    if spec is None:
        return structured_error("unknown_connector", f"Unknown connector: {connector_id}")

    refused = refuse_model_chosen_url(args)
    if refused:
        return structured_error(
            refused["error"],
            refused["message"],
            detail={"key": refused.get("key")},
        )

    op = spec.operation(op_id)
    if op is None:
        return structured_error("unknown_operation", f"Unknown operation: {op_id}")

    if spec.read_only and op.capability != "read":
        return structured_error(
            WRITE_ON_READ_CONNECTOR,
            "Write operations are not exposed on this read-only connector.",
        )

    ok_in, in_reason = validate_value_against_schema(args, op.input_schema)
    if not ok_in:
        return structured_error("invalid_input", f"input_schema:{in_reason}")

    path_keys = [p.strip("{}") for p in op.path.split("/") if p.startswith("{")]
    path_params = {k: args[k] for k in path_keys if k in args}
    query = {k: v for k, v in args.items() if k not in path_params}

    if connector_id == "open_meteo" and op_id == "current_weather":
        query = {
            "latitude": args["latitude"],
            "longitude": args["longitude"],
            "current": "temperature_2m",
        }

    url = build_url(spec.base_url, op.path, path_params)
    has_creds = spec.auth.kind != "none"
    cred_refuse = refuse_credentials_to_foreign_url(
        target_url=url, allowed_hosts=spec.allowed_hosts, has_credentials=has_creds
    )
    if cred_refuse:
        return structured_error(cred_refuse["error"], cred_refuse["message"], detail=cred_refuse)

    cache_key = _cache_key(connector_id, op_id, query)
    if mode == "live" and op.cacheable and op.method == "GET":
        hit = _cache_get(cache_key)
        if hit is not None:
            return hit

    if transport is None:
        if mode == "live":
            transport = LiveTransport(
                allowed_hosts=spec.allowed_hosts, rate_limit=spec.rate_limit
            )
            from mainframe.costaudit.boundary import allow_non_loopback_live

            boundary = allow_non_loopback_live(purpose=f"connector:{connector_id}:{op_id}")
            if not boundary.get("allowed"):
                return structured_error(
                    "live_disabled_without_os_network_isolation",
                    (
                        "Live non-loopback connector calls are disabled because OS network "
                        "isolation is not available. Application policy cannot constrain "
                        "arbitrary processes with network access. Use mode=fixture."
                    ),
                    detail=boundary,
                )
        else:
            transport = FixtureTransport(connector_id, scenario=fixture_scenario)

    if spec.auth.kind == "api_key_header" and spec.auth.header_name:
        return structured_error("auth_not_configured", "No credential resolved for connector")

    pages_out: list[Any] = []
    bodies: list[dict[str, Any]] = []
    page_index = 0
    q = dict(query)
    partial = False
    last_raw: dict[str, Any] = {}
    flat_live_map: dict[str, Any] | None = None

    while True:
        raw = transport.request(method=op.method, url=url, headers={}, query=q)
        last_raw = raw
        status = int(raw.get("status") or 0)

        if status == 429 or raw.get("error") in {"rate_limited", "quota_exhausted"}:
            return structured_error(
                QUOTA_EXHAUSTED,
                "Quota or rate limit exhausted",
                retryable=True,
                http_status=status or 429,
                detail={"headers": raw.get("headers"), "retry_after_s": raw.get("retry_after_s")},
            )

        if not raw.get("ok") and raw.get("error"):
            return structured_error(
                str(raw.get("error")),
                str(raw.get("message") or raw.get("error")),
                retryable=bool(raw.get("retryable")),
                http_status=status or None,
                detail=raw,
            )

        if status >= 400:
            return structured_error(
                "http_error",
                f"HTTP {status}",
                retryable=status in {408, 429, 500, 502, 503, 504},
                http_status=status,
                detail={"body_text": (raw.get("body_text") or "")[:500]},
            )

        body = raw.get("body_json")
        if body is None:
            text = raw.get("body_text") or ""
            if not text:
                return structured_error(
                    MALFORMED_RESPONSE, "Empty or non-JSON response", http_status=status
                )
            try:
                body = json.loads(text)
            except json.JSONDecodeError:
                return structured_error(
                    MALFORMED_RESPONSE,
                    "Response is not valid JSON",
                    http_status=status,
                    detail={"body_preview": text[:200]},
                )

        if not isinstance(body, dict):
            return structured_error(
                MALFORMED_RESPONSE,
                "JSON root must be an object for this operation",
                detail={"type": type(body).__name__},
            )

        if op.pagination.style == "none":
            check = validate_output(body, op.output_schema)
            if not check.get("ok"):
                return structured_error(
                    SCHEMA_DRIFT,
                    f"Schema drift: {check.get('reason')}",
                    detail=check,
                    http_status=status,
                )

        bodies.append(body)

        if op.pagination.style == "none":
            break

        # Live Frankfurter /currencies returns a flat code→name map (no pages).
        if op_id == "list_currencies" and not extract_items(body, op.pagination):
            if body and all(isinstance(v, str) for v in body.values()):
                flat_live_map = body
                break

        items = extract_items(body, op.pagination)
        pages_out.extend(items)
        if body.get("_partial") or raw.get("fixture") == "partial_pagination":
            partial = True
        if pagination_complete(body, op.pagination, page_index + 1):
            break
        nxt = next_page_args(
            op.pagination, page_index=page_index + 1, prior_body=body, query=q
        )
        if nxt is None:
            break
        q = nxt
        page_index += 1
        if page_index >= op.pagination.max_pages:
            partial = True
            break

    if partial and op.pagination.style != "none" and flat_live_map is None:
        prov = _provenance(spec, op, mode, last_raw.get("url"))
        return {
            "ok": False,
            "error": {
                "code": PARTIAL_PAGINATION,
                "message": "Pagination incomplete or truncated before max_pages",
                "retryable": True,
                "detail": {"pages_fetched": page_index + 1, "items": len(pages_out)},
            },
            "data": {"items": pages_out, "pages": bodies},
            "provenance": prov,
            "connector_id": connector_id,
            "op_id": op_id,
            "capability": op.capability,
        }

    if flat_live_map is not None:
        data: Any = flat_live_map
    elif op.pagination.style != "none":
        data = {"items": pages_out, "page_count": len(bodies)}
    else:
        data = bodies[0] if bodies else {}

    prov = _provenance(spec, op, mode, last_raw.get("url"))
    result = {
        "ok": True,
        "connector_id": connector_id,
        "op_id": op_id,
        "capability": op.capability,
        "data": data,
        "provenance": prov,
        "mode": mode,
        "fixture_scenario": fixture_scenario if mode == "fixture" else None,
        "cache_hit": False,
        "request_avoided": False,
    }
    if mode == "live" and op.cacheable and op.method == "GET":
        _cache_put(cache_key, result, op.freshness_s)
    return result


def _provenance(
    spec: ConnectorSpec, op: OperationSpec, mode: str, request_url: str | None
) -> dict[str, Any]:
    prov = build_provenance(
        source=spec.docs_url,
        docs_url=spec.docs_url,
        attribution=op.attribution or spec.default_attribution,
        freshness_s=op.freshness_s,
        retrieved_via=mode,
        request_url=request_url,
    )
    retrieved = _utc()
    prov["fresh_until_hint"] = (retrieved + timedelta(seconds=op.freshness_s)).isoformat()
    return prov


def list_connectors() -> list[dict[str, Any]]:
    return [s.to_dict() for s in all_connector_specs()]
