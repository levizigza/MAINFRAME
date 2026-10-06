"""Three eligible read-only connectors from documented endpoints (verified 2026-09-29)."""

from __future__ import annotations

from mainframe.connectors.types import (
    AuthSpec,
    ConnectorSpec,
    OperationSpec,
    PaginationSpec,
    RateLimitSpec,
)

# Live doc/endpoint reachability observed 2026-09-29 (not fabricated):
# - https://dog.ceo/dog-api/ + GET /api/breeds/list/all → 200
# - https://open-meteo.com/en/docs + GET api.open-meteo.com/v1/forecast → 200
#   (hosted OpenAPI URL at /openapi → 404; using documented endpoints)
# - https://frankfurter.dev/ + GET api.frankfurter.dev/v1/latest → 200


def dog_ceo_spec() -> ConnectorSpec:
    return ConnectorSpec(
        connector_id="dog_ceo",
        title="Dog CEO — breed list & random image",
        base_url="https://dog.ceo/api/",
        allowed_hosts=["dog.ceo"],
        docs_url="https://dog.ceo/dog-api/",
        openapi_or_docs="https://dog.ceo/dog-api/ (documented endpoints; no published OpenAPI observed)",
        source_kind="documented_endpoints",
        auth=AuthSpec(kind="none"),
        rate_limit=RateLimitSpec(max_requests_per_minute=60),
        shortlist_id="dog_ceo",
        read_only=True,
        default_attribution="Dog CEO API (dog.ceo)",
        operations=[
            OperationSpec(
                op_id="list_breeds",
                capability="read",
                method="GET",
                path="breeds/list/all",
                purpose="List all dog breeds (read-only)",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                output_schema={
                    "type": "object",
                    "required": ["message", "status"],
                    "properties": {
                        "message": {"type": "object"},
                        "status": {"type": "string"},
                    },
                },
                freshness_s=86400,
                attribution="Dog CEO API (dog.ceo)",
            ),
            OperationSpec(
                op_id="random_image",
                capability="read",
                method="GET",
                path="breeds/image/random",
                purpose="Fetch one random dog image URL (read-only)",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                output_schema={
                    "type": "object",
                    "required": ["message", "status"],
                    "properties": {
                        "message": {"type": "string"},
                        "status": {"type": "string"},
                    },
                },
                freshness_s=300,
                attribution="Dog CEO API (dog.ceo)",
            ),
        ],
    )


def open_meteo_spec() -> ConnectorSpec:
    return ConnectorSpec(
        connector_id="open_meteo",
        title="Open-Meteo — current weather forecast",
        base_url="https://api.open-meteo.com/v1/",
        allowed_hosts=["api.open-meteo.com"],
        docs_url="https://open-meteo.com/en/docs",
        openapi_or_docs=(
            "https://open-meteo.com/en/docs (documented endpoints; "
            "https://open-meteo.com/openapi returned 404 at verification)"
        ),
        source_kind="documented_endpoints",
        auth=AuthSpec(kind="none"),
        rate_limit=RateLimitSpec(max_requests_per_minute=30),
        shortlist_id="open_meteo",
        read_only=True,
        default_attribution="Weather data by Open-Meteo.com (CC BY 4.0)",
        operations=[
            OperationSpec(
                op_id="current_weather",
                capability="read",
                method="GET",
                path="forecast",
                purpose="Current temperature for a lat/lon (read-only)",
                input_schema={
                    "type": "object",
                    "required": ["latitude", "longitude"],
                    "additionalProperties": False,
                    "properties": {
                        "latitude": {"type": "number"},
                        "longitude": {"type": "number"},
                    },
                },
                output_schema={
                    "type": "object",
                    "required": ["latitude", "longitude"],
                    "properties": {
                        "latitude": {"type": "number"},
                        "longitude": {"type": "number"},
                        "current": {"type": "object"},
                        "current_units": {"type": "object"},
                    },
                },
                freshness_s=900,
                attribution="Weather data by Open-Meteo.com (CC BY 4.0)",
            ),
        ],
    )


def frankfurter_spec() -> ConnectorSpec:
    return ConnectorSpec(
        connector_id="frankfurter",
        title="Frankfurter — ECB reference FX rates",
        base_url="https://api.frankfurter.dev/v1/",
        allowed_hosts=["api.frankfurter.dev"],
        docs_url="https://frankfurter.dev/",
        openapi_or_docs="https://frankfurter.dev/ (documented REST endpoints)",
        source_kind="documented_endpoints",
        auth=AuthSpec(kind="none"),
        rate_limit=RateLimitSpec(max_requests_per_minute=60),
        shortlist_id="frankfurter",
        read_only=True,
        default_attribution="Rates from Frankfurter (ECB reference rates)",
        operations=[
            OperationSpec(
                op_id="latest_rates",
                capability="read",
                method="GET",
                path="latest",
                purpose="Latest FX rates from a base currency (read-only)",
                input_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "from": {"type": "string"},
                        "to": {"type": "string"},
                    },
                },
                output_schema={
                    "type": "object",
                    "required": ["amount", "base", "date", "rates"],
                    "properties": {
                        "amount": {"type": "number"},
                        "base": {"type": "string"},
                        "date": {"type": "string"},
                        "rates": {"type": "object"},
                    },
                },
                freshness_s=3600,
                attribution="Rates from Frankfurter (ECB reference rates)",
            ),
            OperationSpec(
                op_id="list_currencies",
                capability="read",
                method="GET",
                path="currencies",
                purpose="List supported currency codes (read-only)",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                output_schema={"type": "object", "additionalProperties": {"type": "string"}},
                # currencies map is the whole JSON object
                freshness_s=86400,
                pagination=PaginationSpec(
                    style="page",
                    page_param="page",
                    items_field="items",
                    max_pages=3,
                    default_limit=5,
                ),
                attribution="Rates from Frankfurter (ECB reference rates)",
                # Pagination on currencies is fixture-oriented; live API returns a flat map.
                expose_as_tool=True,
            ),
        ],
    )


def all_connector_specs() -> list[ConnectorSpec]:
    return [dog_ceo_spec(), open_meteo_spec(), frankfurter_spec()]


def get_connector_spec(connector_id: str) -> ConnectorSpec | None:
    for s in all_connector_specs():
        if s.connector_id == connector_id:
            return s
    return None
