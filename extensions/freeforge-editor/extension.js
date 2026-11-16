/**
 * FreeForge editor bridge — VS Code Extension API only.
 * Phase 2: async CLI, agent webview (NDJSON stream), apply/reject.
 * Shares task state with: python -m mainframe editor …
 */
const vscode = require("vscode");
const { spawn } = require("child_process");
const path = require("path");

function mfRoot() {
  const cfg = vscode.workspace.getConfiguration("freeforge");
  const override = cfg.get("workspaceRoot");
  if (override) return override;
  const folders = vscode.workspace.workspaceFolders;
  return folders && folders[0] ? folders[0].uri.fsPath : process.cwd();
}

function pythonBin() {
  return vscode.workspace.getConfiguration("freeforge").get("python") || "python";
}

/**
 * Async CLI — replace blocking spawnSync so Cancel can race.
 * @returns {Promise<{ok:boolean, [k:string]:any, _stderr?:string, _code?:number}>}
 */
function runEditorCliAsync(args, { onStdoutLine, signal } = {}) {
  return new Promise((resolve) => {
    const root = mfRoot();
    const child = spawn(pythonBin(), ["-m", "mainframe", "editor", ...args], {
      cwd: root,
      env: process.env,
    });
    let stdout = "";
    let stderr = "";
    let killed = false;
    if (signal) {
      const onAbort = () => {
        killed = true;
        try {
          child.kill();
        } catch (_) {
          /* ignore */
        }
      };
      if (signal.aborted) onAbort();
      else signal.addEventListener("abort", onAbort, { once: true });
    }
    child.stdout.on("data", (buf) => {
      const chunk = buf.toString("utf8");
      stdout += chunk;
      if (onStdoutLine) {
        const parts = chunk.split(/\r?\n/);
        for (const line of parts) {
          if (line.trim()) onStdoutLine(line);
        }
      }
    });
    child.stderr.on("data", (buf) => {
      stderr += buf.toString("utf8");
    });
    child.on("error", (err) => {
      resolve({ ok: false, error: String(err), _stderr: stderr });
    });
    child.on("close", (code) => {
      if (killed) {
        resolve({ ok: false, cancelled: true, error: "cancelled", _stderr: stderr, _code: code });
        return;
      }
      if (onStdoutLine) {
        resolve({ ok: code === 0, _code: code, _stderr: stderr, streamed: true });
        return;
      }
      try {
        const parsed = JSON.parse(stdout || "{}");
        resolve({ ...parsed, _code: code, _stderr: stderr });
      } catch (e) {
        resolve({
          ok: false,
          error: "invalid_json",
          stdout,
          stderr,
          _code: code,
        });
      }
    });
  });
}

function activeTaskId(context) {
  return context.workspaceState.get("freeforge.taskId");
}

function setActiveTaskId(context, id) {
  return context.workspaceState.update("freeforge.taskId", id);
}

async function syncDirtyBuffers(context) {
  const taskId = activeTaskId(context);
  if (!taskId) {
    vscode.window.showWarningMessage("FreeForge: no active task");
    return;
  }
  for (const doc of vscode.workspace.textDocuments) {
    if (doc.isUntitled || doc.uri.scheme !== "file") continue;
    if (!doc.isDirty) continue;
    const rel = vscode.workspace.asRelativePath(doc.uri);
    const payload = JSON.stringify({
      path: rel,
      text: doc.getText(),
      dirty: true,
      version: doc.version,
    });
    const out = await runEditorCliAsync(["buffer", "--task", taskId, "--json", payload]);
    if (!out.ok) {
      vscode.window.showErrorMessage(`FreeForge buffer sync failed: ${out.error || "unknown"}`);
      return;
    }
  }
  vscode.window.showInformationMessage("FreeForge: unsaved buffers preserved in shared task state");
}

function agentWebviewHtml() {
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
  :root { --bg:#1e1e1e; --fg:#d4d4d4; --muted:#858585; --accent:#3d7eff; --chip:#2a2a2a; --ok:#4ec9b0; --warn:#ce9178; }
  body { margin:0; font:13px/1.45 Consolas, "Cascadia Mono", monospace; background:var(--bg); color:var(--fg); }
  header { padding:10px 12px; border-bottom:1px solid #333; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
  #ai { font-size:11px; color:var(--muted); }
  #ai.available { color:var(--ok); }
  #ai.paused, #ai.disabled { color:var(--warn); }
  #chips { display:flex; flex-wrap:wrap; gap:6px; padding:8px 12px; border-bottom:1px solid #333; min-height:28px; }
  .chip { background:var(--chip); border:1px solid #444; padding:2px 8px; font-size:11px; }
  #log { padding:12px; height:calc(100vh - 140px); overflow:auto; white-space:pre-wrap; }
  .delta { color:var(--fg); }
  .tool { color:var(--muted); }
  .prop { color:var(--accent); }
  footer { position:fixed; bottom:0; left:0; right:0; padding:8px 12px; background:#252526; border-top:1px solid #333; display:flex; gap:8px; }
  input { flex:1; background:#1e1e1e; color:var(--fg); border:1px solid #555; padding:6px 8px; }
  button { background:var(--accent); color:#fff; border:0; padding:6px 12px; cursor:pointer; }
  button.secondary { background:#3c3c3c; }
</style>
</head>
<body>
<header>
  <strong>FreeForge Agent</strong>
  <span id="ai">ai: …</span>
  <span id="task" style="color:var(--muted);font-size:11px"></span>
</header>
<div id="chips"></div>
<div id="log"></div>
<footer>
  <input id="msg" placeholder="Ask FreeForge (local / deterministic)…" />
  <button id="send">Send</button>
  <button id="apply" class="secondary">Apply</button>
  <button id="reject" class="secondary">Reject</button>
  <button id="cancel" class="secondary">Cancel</button>
</footer>
<script>
const vscode = acquireVsCodeApi();
const log = document.getElementById('log');
const chipsEl = document.getElementById('chips');
const aiEl = document.getElementById('ai');
const taskEl = document.getElementById('task');
function append(cls, text) {
  const d = document.createElement('div');
  d.className = cls;
  d.textContent = text;
  log.appendChild(d);
  log.scrollTop = log.scrollHeight;
}
window.addEventListener('message', (e) => {
  const m = e.data || {};
  if (m.type === 'reset') { log.textContent = ''; chipsEl.textContent = ''; }
  if (m.type === 'task') { taskEl.textContent = m.taskId || ''; }
  if (m.type === 'event') {
    const ev = m.event || {};
    if (ev.type === 'ai_status') {
      aiEl.textContent = 'ai: ' + (ev.state || '?') + (ev.detail ? ' — ' + ev.detail : '');
      aiEl.className = ev.state || '';
    } else if (ev.type === 'context_chips') {
      chipsEl.innerHTML = '';
      (ev.chips || []).forEach(c => {
        const s = document.createElement('span');
        s.className = 'chip';
        s.textContent = (c.kind || '') + (c.path ? ': ' + c.path : '') + (c.message ? ' ' + c.message : '');
        chipsEl.appendChild(s);
      });
    } else if (ev.type === 'message_delta') {
      append('delta', ev.delta || '');
    } else if (ev.type === 'tool_call') {
      append('tool', '→ ' + ev.tool + ' ' + JSON.stringify(ev.arguments || {}));
    } else if (ev.type === 'tool_result') {
      append('tool', '← ' + ev.tool + ' ok=' + !!(ev.result && ev.result.ok));
    } else if (ev.type === 'proposal') {
      append('prop', 'PROPOSAL op=' + (ev.operation_id || '') + ' edits=' + ((ev.edits||[]).length));
      (ev.reviewable_diffs || []).forEach(d => append('prop', typeof d === 'string' ? d : JSON.stringify(d)));
    } else if (ev.type === 'done') {
      append('tool', 'done awaiting_apply=' + !!ev.awaiting_apply);
    } else if (ev.type === 'error' || ev.type === 'cancelled') {
      append('tool', JSON.stringify(ev));
    }
  }
  if (m.type === 'info') append('tool', m.text || '');
});
document.getElementById('send').onclick = () => {
  const v = document.getElementById('msg').value;
  vscode.postMessage({ type: 'send', message: v });
};
document.getElementById('apply').onclick = () => vscode.postMessage({ type: 'apply' });
document.getElementById('reject').onclick = () => vscode.postMessage({ type: 'reject' });
document.getElementById('cancel').onclick = () => vscode.postMessage({ type: 'cancel' });
</script>
</body>
</html>`;
}

/** @param {vscode.ExtensionContext} context */
function activate(context) {
  let agentAbort = null;
  let panel = null;

  const openAgent = async () => {
    if (!panel) {
      panel = vscode.window.createWebviewPanel(
        "freeforgeAgent",
        "FreeForge Agent",
        vscode.ViewColumn.Beside,
        { enableScripts: true, retainContextWhenHidden: true }
      );
      panel.webview.html = agentWebviewHtml();
      panel.onDidDispose(() => {
        panel = null;
        if (agentAbort) agentAbort.abort();
      });
      panel.webview.onDidReceiveMessage(async (msg) => {
        const taskId = activeTaskId(context);
        if (msg.type === "send") {
          await runAgentTurn(context, panel, msg.message || "");
        } else if (msg.type === "apply") {
          if (!taskId) return;
          const out = await runEditorCliAsync(["apply", "--task", taskId]);
          panel.webview.postMessage({
            type: "info",
            text: out.ok ? "Applied." : "Apply failed: " + (out.error || JSON.stringify(out)),
          });
        } else if (msg.type === "reject") {
          if (!taskId) return;
          const out = await runEditorCliAsync(["reject", "--task", taskId]);
          panel.webview.postMessage({
            type: "info",
            text: out.ok ? "Rejected." : "Reject failed: " + (out.error || ""),
          });
        } else if (msg.type === "cancel") {
          if (agentAbort) agentAbort.abort();
          if (taskId) await runEditorCliAsync(["cancel", "--task", taskId]);
          panel.webview.postMessage({ type: "info", text: "Cancelled." });
        }
      });
    }
    panel.reveal();
    const tid = activeTaskId(context);
    panel.webview.postMessage({ type: "task", taskId: tid || "(none — send creates task)" });
  };

  async function runAgentTurn(context, panel, message) {
    panel.webview.postMessage({ type: "reset" });
    let taskId = activeTaskId(context);
    if (!taskId) {
      const created = await runEditorCliAsync([
        "chat",
        "--text",
        message || "agent",
        "--workspace",
        mfRoot(),
        "--source",
        "agent",
      ]);
      if (!created.ok || !created.task) {
        panel.webview.postMessage({
          type: "info",
          text: "Failed to create task: " + (created.error || JSON.stringify(created)),
        });
        return;
      }
      taskId = created.task.task_id;
      await setActiveTaskId(context, taskId);
      panel.webview.postMessage({ type: "task", taskId });
    }
    // Context chips: selection, active file, host diagnostics
    const editor = vscode.window.activeTextEditor;
    if (editor && editor.document.uri.scheme === "file") {
      const rel = vscode.workspace.asRelativePath(editor.document.uri);
      await runEditorCliAsync(["active", "--task", taskId, "--path", rel]);
      if (!editor.selection.isEmpty) {
        await runEditorCliAsync([
          "select",
          "--task",
          taskId,
          "--json",
          JSON.stringify({
            path: rel,
            text: editor.document.getText(editor.selection),
            start_line: editor.selection.start.line + 1,
            end_line: editor.selection.end.line + 1,
          }),
        ]);
      }
    }
    try {
      const all = vscode.languages.getDiagnostics();
      const diags = [];
      for (const [uri, list] of all) {
        if (uri.scheme !== "file") continue;
        const rel = vscode.workspace.asRelativePath(uri);
        for (const d of list.slice(0, 5)) {
          diags.push({
            path: rel,
            severity: String(d.severity),
            message: d.message,
          });
          if (diags.length >= 12) break;
        }
        if (diags.length >= 12) break;
      }
      if (diags.length) {
        const tmp = require("os").tmpdir();
        const fs = require("fs");
        const diagPath = require("path").join(tmp, `freeforge-diag-${taskId}.json`);
        fs.writeFileSync(diagPath, JSON.stringify(diags), "utf8");
        await runEditorCliAsync(["diagnostics", "--task", taskId, "--file", diagPath]);
      }
    } catch (_) {
      /* diagnostics optional */
    }
    if (agentAbort) agentAbort.abort();
    agentAbort = new AbortController();
    const args = ["agent-run", "--task", taskId];
    if (message) {
      args.push("--message", message);
    }
    let lineBuf = "";
    await runEditorCliAsync(args, {
      signal: agentAbort.signal,
      onStdoutLine: (line) => {
        lineBuf += line;
        // spawn may split mid-line; try parse each complete attempt
        try {
          const ev = JSON.parse(line);
          panel.webview.postMessage({ type: "event", event: ev });
        } catch (_) {
          /* partial */
        }
      },
    });
  }

  context.subscriptions.push(
    vscode.commands.registerCommand("freeforge.openAgent", openAgent),
    vscode.commands.registerCommand("freeforge.chatToTask", async () => {
      const chat = await vscode.window.showInputBox({ prompt: "Chat → FreeForge task" });
      if (!chat) return;
      const out = await runEditorCliAsync(["chat", "--text", chat, "--workspace", mfRoot()]);
      if (!out.ok) {
        vscode.window.showErrorMessage(`FreeForge: ${out.error || JSON.stringify(out)}`);
        return;
      }
      await setActiveTaskId(context, out.task.task_id);
      vscode.window.showInformationMessage(`FreeForge task ${out.task.task_id} (shared with CLI)`);
    }),
    vscode.commands.registerCommand("freeforge.attachSelection", async () => {
      const taskId = activeTaskId(context);
      if (!taskId) {
        vscode.window.showWarningMessage("FreeForge: create a task first");
        return;
      }
      const editor = vscode.window.activeTextEditor;
      if (!editor || editor.selection.isEmpty) {
        vscode.window.showWarningMessage("FreeForge: select code first");
        return;
      }
      const doc = editor.document;
      const text = doc.getText(editor.selection);
      const rel = vscode.workspace.asRelativePath(doc.uri);
      const payload = JSON.stringify({
        path: rel,
        text,
        start_line: editor.selection.start.line + 1,
        end_line: editor.selection.end.line + 1,
      });
      const out = await runEditorCliAsync(["select", "--task", taskId, "--json", payload]);
      if (!out.ok) {
        vscode.window.showErrorMessage(`FreeForge: ${out.error}`);
        return;
      }
      vscode.window.showInformationMessage("FreeForge: selection attached to shared task");
    }),
    vscode.commands.registerCommand("freeforge.syncDirtyBuffers", () => syncDirtyBuffers(context)),
    vscode.commands.registerCommand("freeforge.applyProposal", async () => {
      const taskId = activeTaskId(context);
      if (!taskId) return;
      const out = await runEditorCliAsync(["apply", "--task", taskId]);
      vscode.window.showInformationMessage(
        out.ok ? "FreeForge: proposal applied" : `Apply failed: ${out.error || "unknown"}`
      );
    }),
    vscode.commands.registerCommand("freeforge.rejectProposal", async () => {
      const taskId = activeTaskId(context);
      if (!taskId) return;
      const out = await runEditorCliAsync(["reject", "--task", taskId]);
      vscode.window.showInformationMessage(
        out.ok ? "FreeForge: proposal rejected" : `Reject failed: ${out.error || "unknown"}`
      );
    }),
    vscode.commands.registerCommand("freeforge.cancelTask", async () => {
      if (agentAbort) agentAbort.abort();
      const taskId = activeTaskId(context);
      if (!taskId) return;
      const out = await runEditorCliAsync(["cancel", "--task", taskId]);
      vscode.window.showInformationMessage(
        out.ok ? "FreeForge: task cancelled (completed effects kept)" : `Cancel failed: ${out.error}`
      );
    }),
    vscode.commands.registerCommand("freeforge.resumeTask", async () => {
      const taskId = activeTaskId(context);
      if (!taskId) return;
      const out = await runEditorCliAsync(["resume", "--task", taskId]);
      vscode.window.showInformationMessage(out.ok ? "FreeForge: resumed" : `Resume: ${out.error}`);
    }),
    vscode.workspace.onWillSaveTextDocument(async (e) => {
      const taskId = activeTaskId(context);
      if (!taskId || e.document.uri.scheme !== "file") return;
      const rel = vscode.workspace.asRelativePath(e.document.uri);
      runEditorCliAsync([
        "buffer",
        "--task",
        taskId,
        "--json",
        JSON.stringify({
          path: rel,
          text: e.document.getText(),
          dirty: false,
          version: e.document.version,
        }),
      ]);
    })
  );
}

function deactivate() {}

module.exports = { activate, deactivate };
