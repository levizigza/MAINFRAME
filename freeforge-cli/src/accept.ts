/**
 * Acceptance: launch without paid credentials, run local command via adapter,
 * recover status after restart; unsupported commands report unsupported.
 */
import { spawnSync } from "node:child_process";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { gateSelfTest } from "./costGate.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const tsxCli = join(root, "node_modules", "tsx", "dist", "cli.mjs");
const cli = join(root, "src", "cli.ts");

function run(args: string[]): { status: number | null; stdout: string; stderr: string } {
  const r = spawnSync(process.execPath, [tsxCli, cli, ...args], {
    cwd: root,
    encoding: "utf8",
    env: { ...process.env, FREEFORGE_ACCEPT: "1" },
  });
  return { status: r.status, stdout: r.stdout || "", stderr: r.stderr || "" };
}

function parseJson(text: string): unknown {
  const start = text.indexOf("{");
  if (start < 0) throw new Error("no json: " + text.slice(0, 200));
  return JSON.parse(text.slice(start));
}

const checks: { id: string; ok: boolean; detail: unknown }[] = [];

// 0) cost gate
{
  const g = gateSelfTest();
  checks.push({ id: "cost_gate_self_test", ok: g.ok, detail: g });
}

// 1) doctor launches without paid credentials
{
  const r = run(["doctor"]);
  const j = parseJson(r.stdout) as {
    paid_credentials_required?: boolean;
    ok?: boolean;
    openclaw?: { privateDbModified?: boolean };
  };
  checks.push({
    id: "launch_without_paid_credentials",
    ok: r.status === 0 && j.paid_credentials_required === false && j.ok === true,
    detail: {
      status: r.status,
      paid_credentials_required: j.paid_credentials_required,
      privateDbModified: j.openclaw?.privateDbModified,
    },
  });
}

// 2) local command through adapter
let taskId = "";
{
  const marker = `accept-${Date.now()}`;
  const r =
    process.platform === "win32"
      ? run(["run", "--", "cmd", "/c", `echo ${marker}`])
      : run(["run", "--", "echo", marker]);
  const j = parseJson(r.stdout) as {
    ok?: boolean;
    task_id?: string;
    openclaw_private_db_modified?: boolean;
    paid_credentials_used?: boolean;
    stdout?: string;
  };
  taskId = j.task_id || "";
  checks.push({
    id: "local_command_via_adapter",
    ok:
      r.status === 0 &&
      j.ok === true &&
      Boolean(taskId) &&
      j.openclaw_private_db_modified === false &&
      j.paid_credentials_used === false &&
      String(j.stdout || "").includes(marker),
    detail: j,
  });
}

// 3) recover status after "restart" (new process)
{
  const r = run(["status", taskId]);
  const j = parseJson(r.stdout) as {
    ok?: boolean;
    recovered_from_sqlite?: boolean;
    task?: { status?: string; id?: string };
  };
  checks.push({
    id: "status_after_restart",
    ok:
      r.status === 0 &&
      j.ok === true &&
      j.recovered_from_sqlite === true &&
      j.task?.id === taskId &&
      j.task?.status === "succeeded",
    detail: j,
  });
}

// 4) resume recovers terminal task
{
  const r = run(["resume", taskId]);
  const j = parseJson(r.stdout) as { ok?: boolean; status?: string; openclaw_private_db_modified?: boolean };
  checks.push({
    id: "resume_after_restart",
    ok: r.status === 0 && j.ok === true && j.status === "succeeded" && j.openclaw_private_db_modified === false,
    detail: j,
  });
}

// 5) unsupported command
{
  const r = run(["teleport-to-moon"]);
  const j = parseJson(r.stdout) as { unsupported?: boolean; command?: string };
  checks.push({
    id: "unimplemented_reports_unsupported",
    ok: r.status === 2 && j.unsupported === true,
    detail: { status: r.status, body: j, stderr: r.stderr.slice(0, 200) },
  });
}

const failed = checks.filter((c) => !c.ok).length;
const payload = {
  suite: "freeforge-cli-accept",
  passed: checks.length - failed,
  failed,
  ok: failed === 0,
  checks,
};
console.log(JSON.stringify(payload, null, 2));
process.exit(failed === 0 ? 0 : 1);
