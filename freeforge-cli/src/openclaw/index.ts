/** Pin router — isolate version-specific OpenClaw integration. */
export { probeOpenClawV2026_9_6 as probeOpenClaw, runLocalCommand } from "./v2026_9_6/adapter.js";
export type { AdapterProbe, LocalCommandResult } from "./v2026_9_6/adapter.js";
export {
  DOCUMENTED_PLUGIN_HOOKS,
  OPENCLAW_PIN,
  OWNERSHIP,
  SUPPORTED_INTERFACES,
} from "./v2026_9_6/schema.js";
