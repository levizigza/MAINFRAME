import { createHash, randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import initSqlJs, { type Database, type SqlJsStatic } from "sql.js";
import { DEFAULT_POLICY } from "./policy.js";

const PKG_ROOT = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const REPO_ROOT = join(PKG_ROOT, "..");
export const STATE_DIR = join(REPO_ROOT, ".mainframe");
export const DB_PATH = join(STATE_DIR, "freeforge-cli.sqlite");
export const AUTH_PATH = join(STATE_DIR, "freeforge-loopback.auth");

const SCHEMA_VERSION = 1;

let SQL: SqlJsStatic | null = null;

async function getSql(): Promise<SqlJsStatic> {
  if (!SQL) {
    const dist = join(PKG_ROOT, "node_modules", "sql.js", "dist");
    SQL = await initSqlJs({
      locateFile: (file: string) => join(dist, file),
    });
  }
  return SQL;
}

function ensureDirs(): void {
  mkdirSync(STATE_DIR, { recursive: true });
}

export function loadOrCreateLoopbackToken(): string {
  ensureDirs();
  if (existsSync(AUTH_PATH)) {
    return readFileSync(AUTH_PATH, "utf8").trim();
  }
  const token = randomBytes(24).toString("hex");
  writeFileSync(AUTH_PATH, token + "\n", { encoding: "utf8", mode: 0o600 });
  return token;
}

export type FreeForgeDb = {
  db: Database;
  persist: () => void;
  close: () => void;
};

export async function openDb(): Promise<FreeForgeDb> {
  ensureDirs();
  const sql = await getSql();
  const db = existsSync(DB_PATH)
    ? new sql.Database(readFileSync(DB_PATH))
    : new sql.Database();
  migrate(db);
  const persist = () => {
    const data = db.export();
    writeFileSync(DB_PATH, Buffer.from(data));
  };
  persist();
  return {
    db,
    persist,
    close: () => {
      persist();
      db.close();
    },
  };
}

function migrate(db: Database): void {
  db.run(`
    CREATE TABLE IF NOT EXISTS schema_migrations (
      version INTEGER PRIMARY KEY,
      applied_at TEXT NOT NULL
    );
  `);
  const ver = currentVersion(db);
  if (ver < 1) {
    db.exec(`
      CREATE TABLE IF NOT EXISTS task_contracts (
        id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        title TEXT NOT NULL,
        command_json TEXT NOT NULL,
        status TEXT NOT NULL,
        owner TEXT NOT NULL CHECK(owner = 'freeforge'),
        schedule_owner TEXT NOT NULL,
        model_loop_owner TEXT NOT NULL,
        side_effect_owner TEXT NOT NULL,
        paid_credentials_used INTEGER NOT NULL DEFAULT 0,
        background_model INTEGER NOT NULL DEFAULT 0,
        outbound_delivery INTEGER NOT NULL DEFAULT 0
      );

      CREATE TABLE IF NOT EXISTS workflow_steps (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        step_index INTEGER NOT NULL,
        name TEXT NOT NULL,
        status TEXT NOT NULL,
        detail_json TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(task_id) REFERENCES task_contracts(id)
      );

      CREATE TABLE IF NOT EXISTS artifacts (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        path TEXT,
        content_sha256 TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(task_id) REFERENCES task_contracts(id)
      );

      CREATE TABLE IF NOT EXISTS effect_receipts (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        effect_kind TEXT NOT NULL,
        owner TEXT NOT NULL,
        ok INTEGER NOT NULL,
        exit_code INTEGER,
        stdout_sha256 TEXT,
        stderr_sha256 TEXT,
        detail_json TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(task_id) REFERENCES task_contracts(id)
      );

      CREATE TABLE IF NOT EXISTS openclaw_touch_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        interface TEXT NOT NULL,
        note TEXT NOT NULL,
        modified_openclaw_private_db INTEGER NOT NULL DEFAULT 0
      );
    `);
    db.run("INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)", [
      SCHEMA_VERSION,
      new Date().toISOString(),
    ]);
  }
}

function currentVersion(db: Database): number {
  try {
    const stmt = db.prepare("SELECT COALESCE(MAX(version), 0) AS v FROM schema_migrations");
    stmt.step();
    const row = stmt.getAsObject() as { v: number };
    stmt.free();
    return Number(row.v) || 0;
  } catch {
    return 0;
  }
}

export function sha256Text(text: string): string {
  return createHash("sha256").update(text, "utf8").digest("hex");
}

export function newId(prefix: string): string {
  return `${prefix}_${randomBytes(8).toString("hex")}`;
}

export function ownershipDefaults() {
  return {
    schedule_owner: "openclaw_gateway",
    model_loop_owner: "openclaw_embedded_when_enabled",
    side_effect_owner: "freeforge",
    policy: DEFAULT_POLICY,
  };
}

export function expandHome(p: string): string {
  if (p.startsWith("~/")) return join(homedir(), p.slice(2));
  return p;
}

export function assertNeverWritesOpenClawDb(pathAttempt?: string): void {
  const privateDb = expandHome(DEFAULT_POLICY.openclawPrivateDbPath);
  if (pathAttempt && dirname(pathAttempt) && pathAttempt.replace(/\\/g, "/").includes("/.openclaw/")) {
    throw new Error(
      `Refusing to open OpenClaw private state for write: ${pathAttempt}. Use supported CLI/WS interfaces only.`,
    );
  }
  // Soft check — we never pass this path to sql.js for write.
  void privateDb;
}

export { SCHEMA_VERSION, REPO_ROOT, PKG_ROOT };
