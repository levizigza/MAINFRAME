/**
 * FreeForge editor bridge — VS Code Extension API only.
 * Does not import or vendor Void workbench services.
 * Shares task state with: python -m mainframe editor …
 */
const vscode = require("vscode");
const { spawnSync } = require("child_process");
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

function runEditorCli(args) {
  const root = mfRoot();
  const r = spawnSync(pythonBin(), ["-m", "mainframe", "editor", ...args], {
    cwd: root,
    encoding: "utf-8",
    env: process.env,
  });
  if (r.error) {
    return { ok: false, error: String(r.error) };
  }
  try {
    return JSON.parse(r.stdout || "{}");
  } catch (e) {
    return { ok: false, error: "invalid_json", stderr: r.stderr, stdout: r.stdout };
  }
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
    const out = runEditorCli(["buffer", "--task", taskId, "--json", payload]);
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
      const out = runEditorCli(["chat", "--text", chat, "--workspace", mfRoot()]);
      if (!out.ok) {
        vscode.window.showErrorMessage(`FreeForge: ${out.error || JSON.stringify(out)}`);
        return;
      }
      await setActiveTaskId(context, out.task.task_id);
      vscode.window.showInformationMessage(`FreeForge task ${out.task.task_id} (shared with CLI)`);
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
      const out = runEditorCli(["select", "--task", taskId, "--json", payload]);
      if (!out.ok) {
        vscode.window.showErrorMessage(`FreeForge: ${out.error}`);
        return;
      }
      vscode.window.showInformationMessage("FreeForge: selection attached to shared task");
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("freeforge.syncDirtyBuffers", () => syncDirtyBuffers(context))
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("freeforge.cancelTask", async () => {
      const taskId = activeTaskId(context);
      if (!taskId) return;
      const out = runEditorCli(["cancel", "--task", taskId]);
      vscode.window.showInformationMessage(
        out.ok ? "FreeForge: task cancelled (completed effects kept)" : `Cancel failed: ${out.error}`
      );
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("freeforge.resumeTask", async () => {
      const taskId = activeTaskId(context);
      if (!taskId) return;
      const out = runEditorCli(["resume", "--task", taskId]);
      vscode.window.showInformationMessage(out.ok ? "FreeForge: resumed" : `Resume: ${out.error}`);
    })
  );

  // Preserve dirty buffers into shared state before apply-related commands
  context.subscriptions.push(
    vscode.workspace.onWillSaveTextDocument(async (e) => {
      // Still sync into task so CLI sees latest even after save
      const taskId = activeTaskId(context);
      if (!taskId || e.document.uri.scheme !== "file") return;
      const rel = vscode.workspace.asRelativePath(e.document.uri);
      runEditorCli([
        "buffer",
        "--task",
        taskId,
        "--json",
        JSON.stringify({ path: rel, text: e.document.getText(), dirty: false, version: e.document.version }),
      ]);
    })
  );
}

function deactivate() {}

module.exports = { activate, deactivate };
