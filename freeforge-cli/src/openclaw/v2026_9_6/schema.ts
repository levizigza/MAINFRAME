/**
 * OpenClaw v2026.9.6 — documented surfaces FreeForge may use.
 * Isolated so newer pins can add sibling folders without mixing APIs.
 *
 * Sources (2026-09-29):
 * - https://docs.openclaw.ai/gateway/config-gateway (bind loopback, auth token)
 * - https://docs.openclaw.ai/gateway/protocol/auth
 * - https://docs.openclaw.ai/plugins (plugins inspect --runtime --json)
 * - https://docs.openclaw.ai/plugins/agent-tools (definePluginEntry, registerTool, hooks)
 * - https://docs.openclaw.ai/concepts/agent (embedded agent; private SQLite ownership)
 */

export const OPENCLAW_PIN = {
  ref: "v2026.9.6",
  commit: "eb377ac59e6c9fd6c7705028034812becf00271b",
  packageVersion: "2026.9.6",
} as const;

/** Supported read/control interfaces — never private DB mutation. */
export const SUPPORTED_INTERFACES = [
  "openclaw_cli_plugins_inspect",
  "openclaw_cli_status_if_present",
  "gateway_ws_loopback_with_token",
  "gateway_hooks_http_bearer", // documented hooks.token; FreeForge does not enable delivery
] as const;

export type SupportedInterface = (typeof SUPPORTED_INTERFACES)[number];

/** Documented plugin hook / registration names we care about (inspect-oriented). */
export const DOCUMENTED_PLUGIN_HOOKS = [
  "api.registerTool",
  "api.registerHttpRoute",
  "definePluginEntry",
  "defineChannelPluginEntry",
  "plugins.inspect --runtime",
  "hooks.enabled + hooks.token (header auth only)",
] as const;

export const DEFAULT_GATEWAY = {
  bind: "loopback" as const,
  port: 18789,
  url: "ws://127.0.0.1:18789",
  authMode: "token" as const,
};

/** Ownership matrix for this pin — one owner per concern. */
export const OWNERSHIP = {
  schedule: "openclaw_gateway", // sole scheduler; FreeForge builds payloads + cost-gates commands
  model_loop: "openclaw_embedded_agent_runtime", // selected earlier; not nested
  side_effects_local_command: "freeforge",
  command_policy: "freeforge", // permissions/cost on command itself — not tools.exec approvals
  channel_delivery: "openclaw_when_configured", // kept disabled by FreeForge policy (--no-deliver default)
  openclaw_private_sqlite: "openclaw_only",
} as const;
