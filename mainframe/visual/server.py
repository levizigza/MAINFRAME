"""Loopback-only HTTP form for FreeForge visual edit/invoke — stdlib, removable."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from mainframe.visual.bridge import (
    bridge_status,
    create_simple_reporting_workflow,
    describe_workflow,
    invoke_workflow,
    refuse_nodered_independent_trigger,
    schedule_via_freeforge_only,
)
from mainframe.visual.nodered_flow import export_nodered_flow
from mainframe.visual.store import list_workflows, load_saved, save_workflow

FORM_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>FreeForge visual bridge</title>
  <style>
    :root { --bg:#1a1f1c; --fg:#e8eee9; --accent:#3d7a5f; --muted:#8a9a90; --card:#242b27; }
    body { font-family: "Segoe UI", "IBM Plex Sans", sans-serif; background:radial-gradient(1200px 600px at 10% -10%,#2a4035,var(--bg)); color:var(--fg); margin:0; padding:2rem; }
    h1 { font-weight:600; letter-spacing:.02em; }
    .sub { color:var(--muted); max-width:40rem; }
    main { max-width:52rem; margin:0 auto; }
    label { display:block; margin:.75rem 0 .25rem; color:var(--muted); font-size:.9rem; }
    input, textarea, select, button { font:inherit; }
    input, textarea, select { width:100%; box-sizing:border-box; background:var(--card); color:var(--fg); border:1px solid #3a4540; padding:.55rem .7rem; }
    button { background:var(--accent); color:#fff; border:0; padding:.65rem 1.1rem; cursor:pointer; margin-top:1rem; }
    button.secondary { background:#3a4540; }
    pre { background:var(--card); padding:1rem; overflow:auto; border:1px solid #3a4540; font-size:.85rem; }
    .row { display:flex; gap:.75rem; flex-wrap:wrap; }
    .warn { color:#d4a017; }
  </style>
</head>
<body>
<main>
  <h1>FreeForge</h1>
  <p class="sub">Simple local form — edits/invokes FreeForge workflows. Not a second automation stack.
  Scheduler owner remains OpenClaw/FreeForge. Secrets stay outside flows.</p>
  <p class="warn" id="statusLine">Loading…</p>
  <label>Workflow id</label>
  <input id="wid" value="visual_reporting" />
  <label>Title</label>
  <input id="title" value="Visual bridge report" />
  <div class="row">
    <button type="button" id="btnCreate">Create &amp; save</button>
    <button type="button" class="secondary" id="btnDescribe">Show schemas / permissions / blocked AI</button>
    <button type="button" id="btnRun">Execute</button>
  </div>
  <label>Result</label>
  <pre id="out">{}</pre>
</main>
<script>
async function j(url, opts){
  const r = await fetch(url, opts);
  return r.json();
}
async function refreshStatus(){
  const s = await j('/api/status');
  document.getElementById('statusLine').textContent =
    'scheduler=' + s.scheduler_owner + ' · visual=' + s.visual_kind +
    ' · nodered=' + (s.nodered && s.nodered.verdict) + ' · removable=' + s.removable;
}
document.getElementById('btnCreate').onclick = async () => {
  const body = {workflow_id: wid.value, title: title.value};
  out.textContent = JSON.stringify(await j('/api/create', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)}), null, 2);
};
document.getElementById('btnDescribe').onclick = async () => {
  out.textContent = JSON.stringify(await j('/api/describe?id=' + encodeURIComponent(wid.value)), null, 2);
};
document.getElementById('btnRun').onclick = async () => {
  const body = {workflow_id: wid.value, title: title.value};
  out.textContent = JSON.stringify(await j('/api/run', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)}), null, 2);
};
refreshStatus();
</script>
</body>
</html>
"""


class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "FreeForgeVisualBridge/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        return  # quiet accept runs

    def _json(self, code: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, indent=2, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            raw = FORM_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if parsed.path == "/api/status":
            self._json(200, bridge_status())
            return
        if parsed.path == "/api/list":
            self._json(200, {"ok": True, "workflows": list_workflows(self.server.workflows_root)})  # type: ignore[attr-defined]
            return
        if parsed.path == "/api/describe":
            qs = parse_qs(parsed.query)
            wid = (qs.get("id") or [""])[0]
            loaded = load_saved(wid, self.server.workflows_root)  # type: ignore[attr-defined]
            if not loaded.get("ok"):
                self._json(404, loaded)
                return
            self._json(200, {"ok": True, **describe_workflow(loaded["workflow"])})
            return
        if parsed.path == "/api/export-nodered":
            qs = parse_qs(parsed.query)
            wid = (qs.get("id") or ["visual_reporting"])[0]
            loaded = load_saved(wid, self.server.workflows_root)  # type: ignore[attr-defined]
            wf = loaded.get("workflow") if loaded.get("ok") else None
            self._json(
                200,
                export_nodered_flow(
                    bridge_base_url=f"http://127.0.0.1:{self.server.server_port}",
                    workflow_id=wid,
                    workflow=wf,
                ),
            )
            return
        self._json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        body = self._read_json()
        root = self.server.workflows_root  # type: ignore[attr-defined]
        if parsed.path == "/api/create":
            wid = str(body.get("workflow_id") or "visual_reporting")
            title = str(body.get("title") or "Visual bridge report")
            wf = create_simple_reporting_workflow(workflow_id=wid, title=title)
            # Refuse if client tried to embed secrets
            if body.get("password") or body.get("api_key"):
                self._json(400, {"ok": False, "error": "secrets_not_allowed_in_flow"})
                return
            saved = save_workflow(wf, root)
            self._json(200, {"ok": saved.get("ok"), "saved": saved, "describe": describe_workflow(wf)})
            return
        if parsed.path == "/api/run":
            wid = str(body.get("workflow_id") or "")
            loaded = load_saved(wid, root)
            if not loaded.get("ok"):
                # allow inline create+run
                wf = create_simple_reporting_workflow(
                    workflow_id=wid or "visual_reporting",
                    title=str(body.get("title") or "Visual bridge report"),
                )
                save_workflow(wf, root)
            else:
                wf = loaded["workflow"]
            work = Path(self.server.work_root) / wid  # type: ignore[attr-defined]
            work.mkdir(parents=True, exist_ok=True)
            out = invoke_workflow(
                wf,
                work_dir=work,
                inputs={"title": body.get("title")} if body.get("title") else {},
                records=body.get("records"),
            )
            self._json(200, out)
            return
        if parsed.path == "/api/schedule":
            self._json(200, schedule_via_freeforge_only(body))
            return
        if parsed.path == "/api/refuse-dual-trigger":
            self._json(200, refuse_nodered_independent_trigger(body))
            return
        self._json(404, {"ok": False, "error": "not_found"})


class VisualBridgeServer(ThreadingHTTPServer):
    def __init__(
        self,
        host: str,
        port: int,
        *,
        workflows_root: Path,
        work_root: Path,
    ) -> None:
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("loopback_only")
        super().__init__((host, port), BridgeHandler)
        self.workflows_root = workflows_root
        self.work_root = work_root


def start_bridge(
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    workflows_root: Path,
    work_root: Path,
) -> tuple[VisualBridgeServer, threading.Thread]:
    server = VisualBridgeServer(host, port, workflows_root=workflows_root, work_root=work_root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread
