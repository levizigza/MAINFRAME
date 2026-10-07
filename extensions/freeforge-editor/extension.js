/**
 * FreeForge editor bridge — VS Code Extension API only.
 * Does not import or vendor Void workbench services.
 * Shares task state with: python -m mainframe editor …
 * Async child_process.spawn + cancellation (non-blocking propose/apply paths).
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
 * Async CLI invoke with optional cancellation.
 * @param {string[]} args
 * @param {{ token?: vscode.CancellationToken }} [opts]
 * @returns {Promise<object>}
 */
function runEditorCliAsync(args, opts = {}) {
  const root = mfRoot();
  return new Promise((resolve) => {
    const child = spawn(pythonBin(), ["-m", "mainframe", "editor", ...args], {
      cwd: root,
      env: process.env,
    });
    let stdout = "";
    let stderr = "";
    let cancelled = false;
    const onCancel = () => {
      cancelled = true;
      try {
        child.kill();
      } catch (_) {
        /* ignore */
      }
    };
    if (opts.token) {
      if (opts.token.isCancellationRequested) {
        onCancel();
      } else {
        opts.token.onCancellationRequested(onCancel);
      }
    }
    child.stdout.on("data", (d) => {
      stdout += d.toString();
    });
    child.stderr.on("data", (d) => {
      stderr += d.toString();
    });
    child.on("error", (err) => {
      resolve({ ok: false, error: String(err), cancelled });
    });
    child.on("close", () => {
      if (cancelled) {
        resolve({ ok: false, cancelled: true, error: "cancelled" });
        return;
      }
      try {
        resolve(JSON.parse(stdout || "{}"));
      } catch (e) {
        resolve({ ok: false, error: "invalid_json", stderr, stdout });
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

async function syncDirtyBuffers(context, token) {
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
    const out = await runEditorCliAsync(["buffer", "--task", taskId, "--json", payload], {
      token,
    });
    if (!out.ok) {
      vscode.window.showErrorMessage(`FreeForge buffer sync failed: ${out.error || "unknown"}`);
      return;
    }
  }
  vscode.window.showInformationMessage("FreeForge: unsaved buffers preserved in shared task state");
}

/**
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand("freeforge.chatToTask", async () => {
      const chat = await vscode.window.showInputBox({ prompt: "Chat → FreeForge task" });
      if (!chat) return;
      await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: "FreeForge: creating task",
          cancellable: true,
        },
        async (_progress, token) => {
          const out = await runEditorCliAsync(
            ["chat", "--text", chat, "--workspace", mfRoot()],
            { token }
          );
          if (out.cancelled) {
            vscode.window.showWarningMessage("FreeForge: cancelled");
            return;
          }
          if (!out.ok) {
            vscode.window.showErrorMessage(`FreeForge: ${out.error || JSON.stringify(out)}`);
            return;
          }
          await setActiveTaskId(context, out.task.task_id);
          vscode.window.showInformationMessage(
            `FreeForge task ${out.task.task_id} (shared with CLI)`
          );
        }
      );
    })
  );

  context.subscriptions.push(
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
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("freeforge.syncDirtyBuffers", () =>
      vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: "FreeForge: syncing buffers",
          cancellable: true,
        },
        (_p, token) => syncDirtyBuffers(context, token)
      )
    )
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("freeforge.proposeApply", async () => {
      const taskId = activeTaskId(context);
      if (!taskId) {
        vscode.window.showWarningMessage("FreeForge: create a task first");
        return;
      }
      const editsPath = await vscode.window.showInputBox({
        prompt: "Path to edits JSON (list of {path,old,new})",
      });
      if (!editsPath) return;
      await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: "FreeForge: propose + apply",
          cancellable: true,
        },
        async (_progress, token) => {
          const prop = await runEditorCliAsync(
            ["propose", "--task", taskId, "--edits", editsPath],
            { token }
          );
          if (prop.cancelled) {
            vscode.window.showWarningMessage("FreeForge: propose cancelled");
            return;
          }
          if (!prop.ok) {
            vscode.window.showErrorMessage(`Propose failed: ${prop.error || JSON.stringify(prop)}`);
            return;
          }
          const choice = await vscode.window.showQuickPick(["Accept", "Reject"], {
            placeHolder: "Reviewable patch — never silent overwrite",
          });
          if (choice !== "Accept") {
            vscode.window.showInformationMessage("FreeForge: proposal rejected (disk unchanged)");
            return;
          }
          const applied = await runEditorCliAsync(["apply", "--task", taskId], { token });
          if (applied.cancelled) {
            vscode.window.showWarningMessage("FreeForge: apply cancelled");
            return;
          }
          vscode.window.showInformationMessage(
            applied.ok ? "FreeForge: patch applied" : `Apply failed: ${applied.error}`
          );
        }
      );
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("freeforge.cancelTask", async () => {
      const taskId = activeTaskId(context);
      if (!taskId) return;
      const out = await runEditorCliAsync(["cancel", "--task", taskId]);
      vscode.window.showInformationMessage(
        out.ok ? "FreeForge: task cancelled (completed effects kept)" : `Cancel failed: ${out.error}`
      );
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("freeforge.resumeTask", async () => {
      const taskId = activeTaskId(context);
      if (!taskId) return;
      const out = await runEditorCliAsync(["resume", "--task", taskId]);
      vscode.window.showInformationMessage(out.ok ? "FreeForge: resumed" : `Resume: ${out.error}`);
    })
  );

  context.subscriptions.push(
    vscode.workspace.onWillSaveTextDocument(async (e) => {
      const taskId = activeTaskId(context);
      if (!taskId || e.document.uri.scheme !== "file") return;
      const rel = vscode.workspace.asRelativePath(e.document.uri);
      // Fire-and-forget async so save is not blocked
      void runEditorCliAsync([
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

module.exports = { activate, deactivate, runEditorCliAsync };
