import { openDb, newId, sha256Text, DB_PATH, SCHEMA_VERSION, type FreeForgeDb } from "./db.js";
import { DEFAULT_POLICY, assertPolicySafe } from "./policy.js";
import { probeOpenClaw, runLocalCommand, OPENCLAW_PIN, OWNERSHIP } from "./openclaw/index.js";
import { startLoopbackStatusServer } from "./loopback.js";
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { REPO_ROOT } from "./db.js";

function print(data: unknown): void {
  console.log(JSON.stringify(data, null, 2));
}

function unsupported(command: string): never {
  print({
    ok: false,
    unsupported: true,
    command,
    message: `Command '${command}' is unsupported in FreeForge CLI ${OPENCLAW_PIN.packageVersion} adapter bootstrap.`,
  });
  process.exitCode = 2;
  throw new Error("unsupported");
}

async function withDb<T>(fn: (store: FreeForgeDb) => Promise<T> | T): Promise<T> {
  const store = await openDb();
  try {
    const result = await fn(store);
    store.persist();
    return result;
  } finally {
    store.close();
  }
}

export async function cmdDoctor(): Promise<number> {
  assertPolicySafe(DEFAULT_POLICY);
  const probe = await probeOpenClaw();
  const pyDoctor = join(REPO_ROOT, "mainframe");
  let pythonDoctor: unknown = null;
  if (existsSync(pyDoctor)) {
    const r = spawnSync("python", ["-m", "mainframe", "doctor"], {
      cwd: REPO_ROOT,
      encoding: "utf8",
      timeout: 60000,
    });
    if (r.status === 0 && r.stdout.trim()) {
      try {
        pythonDoctor = JSON.parse(r.stdout);
      } catch {
        pythonDoctor = { parse_error: true };
      }
    }
  }
  print({
    suite: "freeforge-cli-doctor",
    policy: DEFAULT_POLICY,
    ownership: OWNERSHIP,
    openclaw: probe,
    sqlite: { path: DB_PATH, schema_version: SCHEMA_VERSION, owner: "freeforge" },
    python_doctor_summary: pythonDoctor
      ? {
          host_kind: (pythonDoctor as { host_context?: { kind?: string } }).host_context?.kind,
          secrets_exposed: (pythonDoctor as { secrets_exposed?: boolean }).secrets_exposed,
          models_downloaded: (pythonDoctor as { models_downloaded?: boolean }).models_downloaded,
        }
      : null,
    paid_credentials_required: false,
    background_model_calls: false,
    automatic_outbound_delivery: false,
    ok: true,
  });
  return 0;
}

export async function cmdRun(argv: string[], title?: string): Promise<number> {
  assertPolicySafe(DEFAULT_POLICY);
  if (!argv.length) {
    print({ ok: false, error: "run requires a command, e.g. freeforge run -- echo hello" });
    return 2;
  }
  return withDb(async (store) => {
    const id = newId("task");
    const now = new Date().toISOString();
    store.db.run(
      `INSERT INTO task_contracts(
        id, created_at, updated_at, title, command_json, status, owner,
        schedule_owner, model_loop_owner, side_effect_owner,
        paid_credentials_used, background_model, outbound_delivery
      ) VALUES (?, ?, ?, ?, ?, ?, 'freeforge', ?, ?, 'freeforge', 0, 0, 0)`,
      [
        id,
        now,
        now,
        title || argv.join(" "),
        JSON.stringify(argv),
        "running",
        OWNERSHIP.schedule,
        OWNERSHIP.model_loop,
      ],
    );
    const stepId = newId("step");
    store.db.run(
      `INSERT INTO workflow_steps(id, task_id, step_index, name, status, detail_json, created_at, updated_at)
       VALUES (?, ?, 0, 'local_command', 'running', ?, ?, ?)`,
      [stepId, id, JSON.stringify({ argv }), now, now],
    );
    store.persist();

    const result = await runLocalCommand(argv);
    const done = new Date().toISOString();
    const status = result.ok ? "succeeded" : "failed";
    store.db.run(`UPDATE task_contracts SET status = ?, updated_at = ? WHERE id = ?`, [
      status,
      done,
      id,
    ]);
    store.db.run(
      `UPDATE workflow_steps SET status = ?, detail_json = ?, updated_at = ? WHERE id = ?`,
      [status, JSON.stringify(result), done, stepId],
    );
    const artId = newId("art");
    store.db.run(
      `INSERT INTO artifacts(id, task_id, kind, path, content_sha256, created_at) VALUES (?, ?, 'stdout', NULL, ?, ?)`,
      [artId, id, sha256Text(result.stdout), done],
    );
    const receiptId = newId("fx");
    store.db.run(
      `INSERT INTO effect_receipts(
        id, task_id, effect_kind, owner, ok, exit_code, stdout_sha256, stderr_sha256, detail_json, created_at
      ) VALUES (?, ?, 'local_command', 'freeforge', ?, ?, ?, ?, ?, ?)`,
      [
        receiptId,
        id,
        result.ok ? 1 : 0,
        result.exitCode,
        sha256Text(result.stdout),
        sha256Text(result.stderr),
        JSON.stringify({
          argv: result.argv,
          via: result.via,
          openclawPrivateDbTouched: false,
          outbound_delivery: false,
          background_model: false,
        }),
        done,
      ],
    );
    store.db.run(
      `INSERT INTO openclaw_touch_log(created_at, interface, note, modified_openclaw_private_db)
       VALUES (?, 'freeforge_local_exec', 'local command via adapter; OpenClaw DB untouched', 0)`,
      [done],
    );
    store.persist();
    print({
      ok: result.ok,
      task_id: id,
      status,
      receipt_id: receiptId,
      exit_code: result.exitCode,
      stdout: result.stdout,
      stderr: result.stderr,
      paid_credentials_used: false,
      openclaw_private_db_modified: false,
    });
    return result.ok ? 0 : 1;
  });
}

export async function cmdStatus(taskId?: string): Promise<number> {
  return withDb(async (store) => {
    if (taskId) {
      const stmt = store.db.prepare(`SELECT * FROM task_contracts WHERE id = ?`);
      stmt.bind([taskId]);
      if (!stmt.step()) {
        stmt.free();
        print({ ok: false, error: "task_not_found", task_id: taskId });
        return 1;
      }
      const task = stmt.getAsObject();
      stmt.free();
      const steps: unknown[] = [];
      const s2 = store.db.prepare(
        `SELECT id, step_index, name, status, updated_at FROM workflow_steps WHERE task_id = ? ORDER BY step_index`,
      );
      s2.bind([taskId]);
      while (s2.step()) steps.push(s2.getAsObject());
      s2.free();
      const receipts: unknown[] = [];
      const s3 = store.db.prepare(
        `SELECT id, effect_kind, owner, ok, exit_code, created_at FROM effect_receipts WHERE task_id = ? ORDER BY created_at`,
      );
      s3.bind([taskId]);
      while (s3.step()) receipts.push(s3.getAsObject());
      s3.free();
      print({ ok: true, task, steps, receipts, recovered_from_sqlite: true });
      return 0;
    }
    const tasks: unknown[] = [];
    const stmt = store.db.prepare(
      `SELECT id, title, status, updated_at, schedule_owner, model_loop_owner, side_effect_owner FROM task_contracts ORDER BY updated_at DESC LIMIT 20`,
    );
    while (stmt.step()) tasks.push(stmt.getAsObject());
    stmt.free();
    print({ ok: true, tasks, db: DB_PATH });
    return 0;
  });
}

export async function cmdResume(taskId: string): Promise<number> {
  return withDb(async (store) => {
    const stmt = store.db.prepare(`SELECT * FROM task_contracts WHERE id = ?`);
    stmt.bind([taskId]);
    if (!stmt.step()) {
      stmt.free();
      print({ ok: false, error: "task_not_found", task_id: taskId });
      return 1;
    }
    const task = stmt.getAsObject() as { status: string; command_json: string; id: string };
    stmt.free();
    if (task.status === "succeeded" || task.status === "failed") {
      print({
        ok: true,
        resumed: false,
        message: "Task already terminal; status recovered from FreeForge SQLite after restart.",
        task_id: task.id,
        status: task.status,
        openclaw_private_db_modified: false,
      });
      return task.status === "succeeded" ? 0 : 1;
    }
    // Incomplete tasks: re-run local command (FreeForge-owned effect).
    const argv = JSON.parse(String(task.command_json)) as string[];
    print({ ok: true, resumed: true, message: "Re-running incomplete task via FreeForge adapter.", task_id: taskId });
    return cmdRun(argv, `resume:${taskId}`);
  });
}

export async function cmdWorkflows(action: string, name?: string): Promise<number> {
  if (action === "list") {
    print({
      ok: true,
      workflows: [
        {
          id: "local_command",
          owner: "freeforge",
          description: "Run a local argv through the OpenClaw adapter local-exec path",
        },
      ],
    });
    return 0;
  }
  if (action === "run" && name === "local_command") {
    print({
      ok: false,
      error: "use `freeforge run -- <cmd>` for local_command workflow",
    });
    return 2;
  }
  unsupported(`workflows ${action}${name ? " " + name : ""}`);
}

export async function cmdEval(): Promise<number> {
  assertPolicySafe(DEFAULT_POLICY);
  // Minimal builtin eval: launch policy + local echo + status recovery semantics.
  const marker = `ff-eval-${Date.now()}`;
  const runCode = await cmdRun(
    process.platform === "win32"
      ? ["cmd", "/c", `echo ${marker}`]
      : ["echo", marker],
    "eval-local-echo",
  );
  if (runCode !== 0) return runCode;
  // Recover last task id from DB
  return withDb(async (store) => {
    const stmt = store.db.prepare(
      `SELECT id, status FROM task_contracts ORDER BY created_at DESC LIMIT 1`,
    );
    stmt.step();
    const row = stmt.getAsObject() as { id: string; status: string };
    stmt.free();
    print({
      suite: "freeforge-cli-eval",
      ok: row.status === "succeeded",
      task_id: row.id,
      status: row.status,
      paid_credentials_required: false,
      openclaw_private_db_modified: false,
    });
    return row.status === "succeeded" ? 0 : 1;
  });
}

export async function cmdServeStatus(port?: number): Promise<number> {
  assertPolicySafe(DEFAULT_POLICY);
  const server = await startLoopbackStatusServer(async () => {
    const store = await openDb();
    try {
      const tasks: unknown[] = [];
      const stmt = store.db.prepare(
        `SELECT id, status, updated_at FROM task_contracts ORDER BY updated_at DESC LIMIT 10`,
      );
      while (stmt.step()) tasks.push(stmt.getAsObject());
      stmt.free();
      return {
        policy: DEFAULT_POLICY,
        ownership: OWNERSHIP,
        tasks,
        bind: DEFAULT_POLICY.bindAddress,
      };
    } finally {
      store.close();
    }
  }, port ?? 18791);
  print({
    ok: true,
    listening: server.url,
    auth: "Bearer <token from .mainframe/freeforge-loopback.auth>",
    note: "Token file created locally; not printed here to avoid secret exposure in logs.",
    automatic_outbound_delivery: false,
  });
  // Keep process alive until SIGINT
  await new Promise<void>((resolve) => {
    process.on("SIGINT", () => {
      void server.close().then(() => resolve());
    });
  });
  return 0;
}

export { unsupported };
