"""Loopback HTML dashboard — reuses FreeForge stores; evidence over decoration."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from mainframe.dashboard.aggregate import build_dashboard, task_detail
from mainframe.dashboard.controls import resume_task, stop_task
from mainframe.dashboard.notify import notify_policy, refuse_openclaw_outbound, send_local_notification

DASH_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>FreeForge dashboard</title>
  <style>
    :root {
      --bg:#121816; --fg:#e6eee8; --muted:#8a9a90; --card:#1c2420;
      --ok:#3d7a5f; --block:#a65d3a; --run:#4a6fa5; --unk:#9a7b2f; --prop:#6b5b8a;
    }
    body { font-family:"Segoe UI","IBM Plex Sans",sans-serif; margin:0; padding:1.5rem;
      background:radial-gradient(900px 500px at 0% 0%,#1e3228,var(--bg)); color:var(--fg); }
    h1 { font-weight:600; margin:0 0 .25rem; letter-spacing:.02em; }
    .sub { color:var(--muted); max-width:44rem; margin-bottom:1.25rem; }
    main { max-width:64rem; margin:0 auto; }
    .grid { display:grid; grid-template-columns:1fr 1fr; gap:1rem; }
    @media (max-width:800px){ .grid { grid-template-columns:1fr; } }
    section { background:var(--card); border:1px solid #2e3a34; padding:1rem; }
    section h2 { font-size:1rem; margin:0 0 .75rem; color:var(--muted); font-weight:600; }
    .task { border-top:1px solid #2e3a34; padding:.75rem 0; }
    .task:first-of-type { border-top:0; }
    .badge { display:inline-block; font-size:.75rem; padding:.15rem .45rem; border:1px solid currentColor; }
    .s-verified { color:var(--ok); } .s-blocked { color:var(--block); }
    .s-running { color:var(--run); } .s-outcome_unknown { color:var(--unk); }
    .s-proposed { color:var(--prop); } .s-cancelled { color:var(--muted); }
    pre, .mono { font-family:Consolas,"IBM Plex Mono",monospace; font-size:.8rem; white-space:pre-wrap; }
    button { font:inherit; background:var(--ok); color:#fff; border:0; padding:.4rem .8rem; cursor:pointer; margin-right:.4rem; margin-top:.4rem; }
    button.secondary { background:#3a4540; }
    button.danger { background:var(--block); }
    .meta { color:var(--muted); font-size:.85rem; }
    #detail { margin-top:1rem; }
    .warn { color:var(--unk); }
  </style>
</head>
<body>
<main>
  <h1>FreeForge</h1>
  <p class="sub">Local dashboard — task status, workflow history, quota, pending decisions,
  artifacts, stop/resume. Actual checks and evidence only. Auth and project boundaries intact.
  Notifications default to local inbox; OpenClaw messaging stays off until verified.</p>
  <p class="warn" id="policy"></p>
  <div class="grid">
    <section>
      <h2>Quota availability</h2>
      <pre id="quota">{}</pre>
    </section>
    <section>
      <h2>Notifications</h2>
      <pre id="notify">{}</pre>
    </section>
  </div>
  <section style="margin-top:1rem">
    <h2>Pending decisions</h2>
    <pre id="decisions">[]</pre>
  </section>
  <section style="margin-top:1rem">
    <h2>Tasks</h2>
    <div id="tasks"></div>
  </section>
  <section style="margin-top:1rem" id="detailBox" hidden>
    <h2>Recovery (no logs required)</h2>
    <div id="detail"></div>
  </section>
</main>
<script>
const stateClass = s => 'badge s-' + (s||'running');
async function j(url, opts){
  const r = await fetch(url, opts);
  return r.json();
}
function esc(s){ const d=document.createElement('div'); d.textContent=s==null?'':String(s); return d.innerHTML; }
async function load(){
  const d = await j('/api/dashboard');
  document.getElementById('policy').textContent =
    'project=' + d.project_id + ' · auth_boundaries=' + d.auth_boundaries_intact +
    ' · decorative_agent_activity=' + d.decorative_agent_activity +
    ' · openclaw_messaging=' + (d.notifications && d.notifications.openclaw_messaging_enabled);
  document.getElementById('quota').textContent = JSON.stringify(d.quota, null, 2);
  document.getElementById('notify').textContent = JSON.stringify(d.notifications, null, 2);
  document.getElementById('decisions').textContent = JSON.stringify(
    (d.pending_decisions||[]).map(t => t.pending_decisions), null, 2);
  const root = document.getElementById('tasks');
  root.innerHTML = '';
  (d.tasks||[]).forEach(t => {
    const el = document.createElement('div');
    el.className = 'task';
    const checks = (t.checks||[]).map(c =>
      (c.ok?'✓':'✗') + ' ' + (c.step_id||'') + (c.error?(' — '+c.error):'')
    ).join('\\n') || '(no checks yet)';
    const arts = (t.artifacts||[]).join(', ') || '—';
    el.innerHTML =
      '<div><span class="'+stateClass(t.state)+'">'+esc(t.state)+'</span> '+
      '<strong>'+esc(t.label)+'</strong> <span class="meta">'+esc(t.kind)+' · '+esc(t.id)+'</span></div>'+
      '<div class="meta">'+esc((t.recovery&&t.recovery.headline)||'')+'</div>'+
      '<pre class="mono">'+esc(checks)+'</pre>'+
      '<div class="meta">artifacts: '+esc(arts)+'</div>'+
      '<button data-id="'+esc(t.id)+'" data-act="detail">Open recovery</button>'+
      (t.controls&&t.controls.stop?'<button class="danger" data-id="'+esc(t.id)+'" data-kind="'+esc(t.kind)+'" data-act="stop">Stop</button>':'')+
      (t.controls&&t.controls.resume?'<button class="secondary" data-id="'+esc(t.id)+'" data-kind="'+esc(t.kind)+'" data-act="resume">Resume</button>':'');
    root.appendChild(el);
  });
  root.querySelectorAll('button').forEach(b => b.onclick = onCtl);
}
async function onCtl(ev){
  const btn = ev.currentTarget;
  const id = btn.dataset.id;
  const act = btn.dataset.act;
  const kind = btn.dataset.kind;
  if(act==='detail'){
    const det = await j('/api/task?id='+encodeURIComponent(id));
    document.getElementById('detailBox').hidden = false;
    document.getElementById('detail').innerHTML =
      '<pre>'+esc(JSON.stringify(det, null, 2))+'</pre>';
    return;
  }
  const body = {task_id:id, kind:kind};
  const out = await j('/api/'+act, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  document.getElementById('detailBox').hidden = false;
  document.getElementById('detail').innerHTML = '<pre>'+esc(JSON.stringify(out, null, 2))+'</pre>';
  await load();
}
load();
setInterval(load, 8000);
</script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "FreeForgeDashboard/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        return

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
            raw = DASH_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if parsed.path == "/api/dashboard":
            project = (parse_qs(parsed.query).get("project") or ["default"])[0]
            self._json(200, build_dashboard(project_id=project))
            return
        if parsed.path == "/api/task":
            qs = parse_qs(parsed.query)
            tid = (qs.get("id") or [""])[0]
            self._json(200, task_detail(tid))
            return
        if parsed.path == "/api/notify-policy":
            self._json(200, notify_policy())
            return
        self._json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        body = self._read_json()
        if parsed.path == "/api/stop":
            self._json(200, stop_task(str(body.get("task_id") or ""), kind=body.get("kind")))
            return
        if parsed.path == "/api/resume":
            self._json(200, resume_task(str(body.get("task_id") or ""), kind=body.get("kind")))
            return
        if parsed.path == "/api/notify-local":
            self._json(
                200,
                send_local_notification(
                    title=str(body.get("title") or "dashboard"),
                    body=str(body.get("body") or ""),
                    task_id=body.get("task_id"),
                ),
            )
            return
        if parsed.path == "/api/notify-openclaw":
            # Always refuse until fee/connector/recipient/disclosure verified
            self._json(200, refuse_openclaw_outbound(destination=body.get("destination")))
            return
        self._json(404, {"ok": False, "error": "not_found"})


class DashboardServer(ThreadingHTTPServer):
    allow_reuse_address = True


def start_dashboard(*, host: str = "127.0.0.1", port: int = 8788) -> dict[str, Any]:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        return {"ok": False, "error": "loopback_only", "host": host}
    httpd = DashboardServer((host, port), DashboardHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return {
        "ok": True,
        "url": f"http://{host}:{httpd.server_address[1]}/",
        "host": host,
        "port": httpd.server_address[1],
        "server": httpd,
        "thread": thread,
        "auth_boundaries_intact": True,
        "notifications": notify_policy(),
    }
