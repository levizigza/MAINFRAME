/**
 * FreeForge central capability & cost gate (TypeScript mirror).
 * No runtime switch silently enables spending.
 */

export type CapabilityKind =
  | "inference"
  | "connector"
  | "search"
  | "storage"
  | "remote_execution"
  | "tool"
  | "auxiliary";

export type GateDecision = {
  allowed: boolean;
  capability: CapabilityKind;
  target: string;
  reason: string;
  localZeroFee?: boolean;
  deniedCode?: string;
  spendingSwitchAttempted?: boolean;
};

const SPENDING_SWITCHES = new Set([
  "ENABLE_SPENDING",
  "ALLOW_PAID",
  "FORCE_PAID",
  "MAINFRAME_ALLOW_PAID",
  "FREEFORGE_ALLOW_PAID",
  "ALLOW_BILLING",
  "UNLOCK_PAID_ROUTES",
  "AUTO_UPGRADE",
]);

const PAID_ALIASES = new Set([
  "gpt-4",
  "gpt-4o",
  "gpt-3.5-turbo",
  "claude-3-5-sonnet",
  "claude-3-opus",
  "gemini-pro",
  "o1",
  "o3-mini",
]);

const PAID_HOST_MARKERS = [
  "openai.com",
  "anthropic.com",
  "googleapis.com",
  "amazonaws.com",
  "groq.com",
  "together.xyz",
  "fireworks.ai",
  "replicate.com",
];

const CHARGEABLE_TOOLS = new Set([
  "web_search_paid",
  "browserbase_cloud",
  "remote_sandbox",
  "s3_upload",
]);

const CRED_RE =
  /(api[_-]?key|secret|token|password|authorization|bearer|aws_|azure_|openai|anthropic|private[_-]?key)/i;

export function spendingSwitchAttempted(
  env: Record<string, string | undefined> = process.env as Record<string, string | undefined>,
): boolean {
  for (const k of SPENDING_SWITCHES) {
    if (env[k]) return true;
  }
  return false;
}

export function scrubEnvForChild(
  env: Record<string, string | undefined> = process.env as Record<string, string | undefined>,
): NodeJS.ProcessEnv {
  const out: NodeJS.ProcessEnv = {};
  for (const [k, v] of Object.entries(env)) {
    if (v == null) continue;
    if (SPENDING_SWITCHES.has(k)) continue;
    if (CRED_RE.test(k)) continue;
    out[k] = v;
  }
  return out;
}

export function authorize(input: {
  capability: CapabilityKind;
  target: string;
  local?: boolean;
  endpoint?: string;
  modelAlias?: string;
  tokenPriceUsd?: number;
  nested?: boolean;
}): GateDecision {
  const capability: CapabilityKind = input.nested ? "auxiliary" : input.capability;
  const target = input.target;

  if (spendingSwitchAttempted()) {
    return {
      allowed: false,
      capability,
      target,
      reason: "Spending unlock env var ignored — no silent spend switch.",
      deniedCode: "spending_switch_ignored",
      spendingSwitchAttempted: true,
    };
  }

  if (input.tokenPriceUsd === 0 && !input.local) {
    return {
      allowed: false,
      capability,
      target,
      reason: "Zero token price is not zero-cost for external operations.",
      deniedCode: "zero_token_price_not_zero_cost",
    };
  }

  const alias = (input.modelAlias || target).toLowerCase();
  if ((capability === "inference" || capability === "auxiliary") && PAID_ALIASES.has(alias)) {
    return {
      allowed: false,
      capability,
      target,
      reason: `Paid model alias '${alias}' blocked before dispatch.`,
      deniedCode: "paid_model_alias",
    };
  }

  if (input.endpoint) {
    try {
      const host = new URL(input.endpoint).hostname.toLowerCase();
      if (PAID_HOST_MARKERS.some((m) => host === m || host.endsWith("." + m))) {
        return {
          allowed: false,
          capability,
          target,
          reason: `Paid/cloud endpoint blocked: ${input.endpoint}`,
          deniedCode: "paid_endpoint",
        };
      }
    } catch {
      /* ignore parse */
    }
  }

  if (CHARGEABLE_TOOLS.has(target)) {
    return {
      allowed: false,
      capability,
      target,
      reason: `Chargeable tool '${target}' blocked before dispatch.`,
      deniedCode: "chargeable_tool",
    };
  }

  if (input.local) {
    if (
      target === "local_command" ||
      target === "ollama_local" ||
      target.startsWith("local.")
    ) {
      return {
        allowed: true,
        capability,
        target,
        reason: "Local zero-fee operation.",
        localZeroFee: true,
      };
    }
    return {
      allowed: false,
      capability,
      target,
      reason: `Unknown local target '${target}'.`,
      deniedCode: "unknown_local_target",
    };
  }

  return {
    allowed: false,
    capability,
    target,
    reason: "External operation denied — no verified free entitlement in FreeForge CLI gate.",
    deniedCode: "entitlement_missing",
  };
}

export function gateSelfTest(): {
  ok: boolean;
  passed: number;
  failed: number;
  cases: { id: string; ok: boolean }[];
} {
  const cases: { id: string; ok: boolean }[] = [];
  const expect = (id: string, d: GateDecision, allowed: boolean, code?: string) => {
    cases.push({
      id,
      ok: d.allowed === allowed && (code ? d.deniedCode === code : true),
    });
  };
  expect(
    "fake_paid_endpoint",
    authorize({
      capability: "inference",
      target: "openai_api",
      endpoint: "https://api.openai.com/v1",
    }),
    false,
    "paid_endpoint",
  );
  expect(
    "chargeable_tool",
    authorize({ capability: "tool", target: "web_search_paid" }),
    false,
    "chargeable_tool",
  );
  expect(
    "paid_alias",
    authorize({ capability: "inference", target: "x", modelAlias: "gpt-4o" }),
    false,
    "paid_model_alias",
  );
  expect(
    "local_ok",
    authorize({ capability: "tool", target: "local_command", local: true }),
    true,
  );
  const prev = process.env.ENABLE_SPENDING;
  process.env.ENABLE_SPENDING = "1";
  expect(
    "no_silent_spend",
    authorize({ capability: "tool", target: "local_command", local: true }),
    false,
    "spending_switch_ignored",
  );
  if (prev === undefined) delete process.env.ENABLE_SPENDING;
  else process.env.ENABLE_SPENDING = prev;

  const scrubbed = scrubEnvForChild({ PATH: "x", OPENAI_API_KEY: "sk", FOO: "1" });
  cases.push({
    id: "scrub_creds",
    ok: !("OPENAI_API_KEY" in scrubbed) && scrubbed.FOO === "1",
  });

  const passed = cases.filter((c) => c.ok).length;
  return { ok: passed === cases.length, passed, failed: cases.length - passed, cases };
}
