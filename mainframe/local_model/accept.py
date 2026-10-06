"""Acceptance for optional local-model adapter."""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from mainframe.local_model.bench import run_benchmarks
from mainframe.local_model.cloud_guard import assert_local_only, is_cloud_model_name
from mainframe.local_model.download import download_plan
from mainframe.local_model.ollama_native import NATIVE_CHAT, chat, list_local_models, show_model
from mainframe.local_model.protocol import verify_protocol
from mainframe.local_model.select import select_candidate
from mainframe.local_model.status import local_model_status
from mainframe.automation import run_task


class _MockOllama(BaseHTTPRequestHandler):
    """Minimal native Ollama surface for offline accept (no real weights)."""

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        return

    def _json(self, code: int, obj: dict[str, Any]) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/tags"):
            self._json(
                200,
                {
                    "models": [
                        {"name": "tinyllama:1.1b"},
                        {"name": "evil:cloud"},  # must be filtered
                    ]
                },
            )
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001
            payload = {}
        if self.path.startswith("/api/show"):
            self._json(
                200,
                {
                    "license": "Apache License Version 2.0 (fixture)",
                    "template": "{{ .System }}{{ .Prompt }}",
                    "modelfile": 'TEMPLATE """{{ .Prompt }}"""',
                    "details": {"family": "tinyllama"},
                    "capabilities": [],
                },
            )
            return
        if self.path.startswith("/api/chat"):
            model = str(payload.get("model") or "")
            if model.endswith(":cloud"):
                self._json(403, {"error": "cloud disabled"})
                return
            tools = payload.get("tools")
            if tools:
                self._json(
                    200,
                    {
                        "model": model,
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "lookup_symbol",
                                        "arguments": {"name": "total"},
                                    }
                                }
                            ],
                        },
                        "done": True,
                    },
                )
                return
            # Extraction / coding shallow responses
            user = ""
            for m in payload.get("messages") or []:
                if m.get("role") == "user":
                    user = str(m.get("content") or "")
            if "Extract JSON" in user:
                content = '{"name":"MAINFRAME","version":"0.1.18"}'
            elif "add(a, b)" in user:
                content = "def add(a, b):\n    return a + b\n"
            else:
                content = "ok"
            self._json(
                200,
                {
                    "model": model,
                    "message": {"role": "assistant", "content": content},
                    "done": True,
                    "eval_count": 8,
                },
            )
            return
        if self.path.startswith("/v1/"):
            # Prove we can detect misuse; handler exists only to fail tests if used.
            self._json(501, {"error": "openai compat not used by MAINFRAME adapter"})
            return
        self._json(404, {"error": "not found"})


def _start_mock() -> tuple[HTTPServer, str, threading.Thread]:
    # Bind ephemeral loopback port
    httpd = HTTPServer(("127.0.0.1", 0), _MockOllama)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, f"http://127.0.0.1:{port}", thread


def _network_guard_blocks_non_loopback() -> bool:
    """True if connecting to a public IP fails quickly (simulates disabled network)."""
    try:
        # 1.1.1.1:443 — should fail when network is disabled; when network is up,
        # we still treat loopback-only chat as the offline-capable path.
        sock = socket.create_connection(("1.1.1.1", 443), timeout=0.3)
        sock.close()
        return False  # network reachable — still OK; we verify loopback path separately
    except OSError:
        return True


def run_local_model_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    # --- Cloud model rejection ---
    cloud_name = assert_local_only("http://127.0.0.1:11434", "kimi-k2.5:cloud")
    cloud_host = assert_local_only("https://ollama.com", "gemma4")
    checks.append(
        {
            "id": "reject_cloud_model_and_host",
            "ok": (
                cloud_name.get("ok") is False
                and cloud_host.get("ok") is False
                and is_cloud_model_name("foo:cloud")
            ),
            "detail": {"model": cloud_name, "host": cloud_host},
        }
    )

    # --- Native route constant (OpenClaw) ---
    checks.append(
        {
            "id": "native_chat_route_not_v1",
            "ok": NATIVE_CHAT == "/api/chat" and "/v1" not in NATIVE_CHAT,
            "detail": {"chat_route": NATIVE_CHAT},
        }
    )

    # --- Doctor selection + explicit download (no auto) ---
    sel = select_candidate()
    plan = download_plan()
    checks.append(
        {
            "id": "doctor_select_and_explicit_download",
            "ok": (
                sel.get("ok") is True
                and sel.get("auto_download") is False
                and sel.get("coding_quality_assumed") is False
                and plan.get("auto_download") is False
                and plan.get("executed") is False
                and plan.get("confirm_required") is True
            ),
            "detail": {
                "selection_reason": sel.get("selection_reason"),
                "selected": (sel.get("selected") or {}).get("id"),
                "download_message": plan.get("message"),
            },
        }
    )

    # --- Visible unavailable OR mock offline success ---
    live = local_model_status()
    checks.append(
        {
            "id": "status_visible_when_unavailable_or_available",
            "ok": (
                live.get("visible") is True
                and live.get("no_local_model_supported") is True
                and live.get("frontier_parity_claimed") is False
                and live.get("feature_status") in {"available", "unavailable", "disabled_in_config"}
            ),
            "detail": {
                "feature_status": live.get("feature_status"),
                "message": live.get("message"),
            },
        }
    )

    # --- No-local-model mode: deterministic task still works ---
    echo = run_task("echo", {"message": "no-local-model"})
    checks.append(
        {
            "id": "no_local_model_mode_supported",
            "ok": echo.ok and echo.output.get("message") == "no-local-model",
            "detail": echo.output if echo.ok else echo.error,
        }
    )

    # --- Offline mock: network-independent loopback native chat + benches ---
    httpd, base, _thread = _start_mock()
    try:
        tags = list_local_models(base, timeout_s=2.0)
        shown = show_model(base, "tinyllama:1.1b", timeout_s=2.0)
        chat_out = chat(
            base,
            "tinyllama:1.1b",
            [{"role": "user", "content": "Extract JSON with keys name and version from: Package MAINFRAME version 0.1.18."}],
            timeout_s=5.0,
        )
        refused_cloud = chat(base, "evil:cloud", [{"role": "user", "content": "hi"}], timeout_s=5.0)
        # Bench against mock
        bench = run_benchmarks(base_url=base, model="tinyllama:1.1b", timeout_s=5.0)
        net_disabled = _network_guard_blocks_non_loopback()

        checks.append(
            {
                "id": "offline_loopback_native_chat",
                "ok": (
                    tags.get("available") is True
                    and "evil:cloud" in (tags.get("cloud_models_excluded") or [])
                    and "tinyllama:1.1b" in (tags.get("models") or [])
                    and shown.get("chat_template", {}).get("present") is True
                    and shown.get("license", {}).get("reported") is True
                    and chat_out.get("ok") is True
                    and chat_out.get("route") == "/api/chat"
                    and chat_out.get("openai_compat_used") is False
                    and refused_cloud.get("ok") is False
                ),
                "detail": {
                    "tags_models": tags.get("models"),
                    "excluded": tags.get("cloud_models_excluded"),
                    "license_reported": shown.get("license", {}).get("reported"),
                    "chat_ok": chat_out.get("ok"),
                    "cloud_refused": refused_cloud.get("refused") or not refused_cloud.get("ok"),
                    "public_network_disabled_observed": net_disabled,
                    "note": (
                        "Loopback mock proves protocol without weights. "
                        "If public network is up, feature still does not require it."
                    ),
                },
            }
        )

        task_names = {t["task"]: t for t in bench.get("tasks") or []}
        checks.append(
            {
                "id": "bench_extraction_tools_coding_measured",
                "ok": (
                    bench.get("feature_status") == "available"
                    and bench.get("frontier_parity_claimed") is False
                    and bench.get("coding_quality_claimed") is False
                    and task_names.get("extraction", {}).get("score", {}).get("task_ok") is True
                    and task_names.get("tool_use", {}).get("score", {}).get("tool_calls_seen") is True
                    and task_names.get("coding", {}).get("score", {}).get("task_ok") is True
                    and all("latency_ms" in t for t in bench.get("tasks") or [])
                ),
                "detail": {
                    "tasks": [
                        {
                            "task": t["task"],
                            "latency_ms": t.get("latency_ms"),
                            "task_ok": (t.get("score") or {}).get("task_ok"),
                        }
                        for t in bench.get("tasks") or []
                    ],
                    "measured_limits": bench.get("measured_limits"),
                    "disclaimer": bench.get("disclaimer"),
                },
            }
        )
    finally:
        httpd.shutdown()
        httpd.server_close()

    # --- Live protocol report (honest unavailable OK); short timeout ---
    proto = verify_protocol(also_probe_llamacpp=False)
    checks.append(
        {
            "id": "protocol_verify_honest",
            "ok": (
                proto.get("frontier_parity_claimed") is False
                and proto.get("feature_status") in {"available", "unavailable", "available_llamacpp"}
                and (proto.get("protocol") or {}).get("openai_compat_used", True) is False
            ),
            "detail": {
                "feature_status": proto.get("feature_status"),
                "reason": proto.get("reason"),
            },
        }
    )

    # Combined acceptance clause: model works offline (mock) OR live unavailable visible
    clause = (
        any(c["id"] == "offline_loopback_native_chat" and c["ok"] for c in checks)
        and any(c["id"] == "status_visible_when_unavailable_or_available" and c["ok"] for c in checks)
    )
    checks.append(
        {
            "id": "accept_clause_offline_or_unavailable",
            "ok": clause and any(c["id"] == "no_local_model_mode_supported" and c["ok"] for c in checks),
            "detail": "Eligible mock works on loopback with cloud rejected; live may be unavailable.",
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "checks": checks,
        "live_status": live.get("feature_status"),
        "frontier_parity_claimed": False,
    }
