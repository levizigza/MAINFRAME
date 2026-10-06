import { spawn, spawnSync } from "node:child_process";
import { createConnection } from "node:net";
import { authorize, scrubEnvForChild } from "../../costGate.js";
import {
  DOCUMENTED_PLUGIN_HOOKS,
  DEFAULT_GATEWAY,
  OPENCLAW_PIN,
  OWNERSHIP,
  SUPPORTED_INTERFACES,
} from "./schema.js";

export type AdapterProbe = {
  pin: typeof OPENCLAW_PIN;
  supportedInterfaces: typeof SUPPORTED_INTERFACES;
  documentedPluginHooks: typeof DOCUMENTED_PLUGIN_HOOKS;
  ownership: typeof OWNERSHIP;
  cliPresent: boolean;
  cliVersion: string | null;
  gatewayLoopbackReachable: boolean;
  gatewayUrl: string;
  privateDbModified: false;
  schemasInspected: Record<string, unknown>;
};

function whichSync(cmd: string): string | null {
  const probe = spawnSync(process.platform === "win32" ? "where" : "which", [cmd], {
    encoding: "utf8",
  });
  if (probe.status !== 0) return null;
  const line = (probe.stdout || "").split(/\r?\n/).map((s) => s.trim()).find(Boolean);
  return line || null;
}

function probeTcp(host: string, port: number, timeoutMs = 400): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = createConnection({ host, port });
    const done = (ok: boolean) => {
      socket.removeAllListeners();
      socket.destroy();
      resolve(ok);
    };
    socket.setTimeout(timeoutMs);
    socket.once("connect", () => done(true));
    socket.once("timeout", () => done(false));
    socket.once("error", () => done(false));
  });
}

/**
 * Inspect installed OpenClaw surfaces via supported CLI only.
 * Never opens ~/.openclaw SQLite.
 */
export async function probeOpenClawV2026_9_6(): Promise<AdapterProbe> {
  const cliPath = whichSync("openclaw");
  let cliVersion: string | null = null;
  const schemasInspected: Record<string, unknown> = {
    note: "Cold inspect only when CLI present; runtime inspect requires Gateway.",
    documentedHooks: DOCUMENTED_PLUGIN_HOOKS,
  };

  if (cliPath) {
    const ver = spawnSync(cliPath, ["--version"], { encoding: "utf8" });
    cliVersion = (ver.stdout || ver.stderr || "").trim().split(/\r?\n/)[0] || null;
    // Best-effort schema-ish inspect; tolerate missing subcommands.
    const inspect = spawnSync(cliPath, ["plugins", "list", "--json"], {
      encoding: "utf8",
      timeout: 8000,
    });
    if (inspect.status === 0 && inspect.stdout.trim()) {
      try {
        schemasInspected.pluginsList = JSON.parse(inspect.stdout);
      } catch {
        schemasInspected.pluginsListRaw = inspect.stdout.slice(0, 2000);
      }
    } else {
      schemasInspected.pluginsList = {
        unsupported_or_unavailable: true,
        stderr: (inspect.stderr || "").slice(0, 400),
      };
    }
  }

  const reachable = await probeTcp("127.0.0.1", DEFAULT_GATEWAY.port);

  return {
    pin: OPENCLAW_PIN,
    supportedInterfaces: SUPPORTED_INTERFACES,
    documentedPluginHooks: DOCUMENTED_PLUGIN_HOOKS,
    ownership: OWNERSHIP,
    cliPresent: Boolean(cliPath),
    cliVersion,
    gatewayLoopbackReachable: reachable,
    gatewayUrl: DEFAULT_GATEWAY.url,
    privateDbModified: false,
    schemasInspected,
  };
}

export type LocalCommandResult = {
  ok: boolean;
  exitCode: number | null;
  stdout: string;
  stderr: string;
  argv: string[];
  owner: "freeforge";
  via: "freeforge_openclaw_adapter_local_exec";
  openclawPrivateDbTouched: false;
};

/**
 * Execute a local command under FreeForge ownership.
 * This is the adapter's local side-effect path — not an OpenClaw model loop
 * and not channel delivery.
 */
export function runLocalCommand(argv: string[], cwd?: string): Promise<LocalCommandResult> {
  return new Promise((resolve) => {
    if (!argv.length) {
      resolve({
        ok: false,
        exitCode: 2,
        stdout: "",
        stderr: "empty argv",
        argv,
        owner: "freeforge",
        via: "freeforge_openclaw_adapter_local_exec",
        openclawPrivateDbTouched: false,
      });
      return;
    }
    // Cost gate: local command only; credentials scrubbed from child env.
    const gate = authorize({
      capability: "tool",
      target: "local_command",
      local: true,
    });
    if (!gate.allowed) {
      resolve({
        ok: false,
        exitCode: 2,
        stdout: "",
        stderr: gate.reason,
        argv,
        owner: "freeforge",
        via: "freeforge_openclaw_adapter_local_exec",
        openclawPrivateDbTouched: false,
      });
      return;
    }
    const child = spawn(argv[0], argv.slice(1), {
      cwd,
      shell: false,
      windowsHide: true,
      env: scrubEnvForChild(process.env as Record<string, string | undefined>),
    });
    let stdout = "";
    let stderr = "";
    child.stdout?.on("data", (b) => {
      stdout += b.toString("utf8");
    });
    child.stderr?.on("data", (b) => {
      stderr += b.toString("utf8");
    });
    child.on("error", (err) => {
      resolve({
        ok: false,
        exitCode: null,
        stdout,
        stderr: String(err),
        argv,
        owner: "freeforge",
        via: "freeforge_openclaw_adapter_local_exec",
        openclawPrivateDbTouched: false,
      });
    });
    child.on("close", (code) => {
      resolve({
        ok: code === 0,
        exitCode: code,
        stdout,
        stderr,
        argv,
        owner: "freeforge",
        via: "freeforge_openclaw_adapter_local_exec",
        openclawPrivateDbTouched: false,
      });
    });
  });
}
