/** FreeForge policy defaults — fail closed until explicitly configured. */
export type FreeForgePolicy = {
  requirePaidCredentials: false;
  backgroundModelCalls: false;
  paidDefaults: false;
  automaticOutboundDelivery: false;
  bindAddress: "127.0.0.1";
  /** Gateway WS default from OpenClaw docs (loopback). */
  openclawGatewayUrl: string;
  openclawPrivateDbPath: string;
  freeforgeOwnsSchedule: true;
  freeforgeOwnsModelLoop: false;
  openclawOwnsModelLoop: true;
  freeforgeOwnsLocalEffects: true;
};

export const DEFAULT_POLICY: FreeForgePolicy = {
  requirePaidCredentials: false,
  backgroundModelCalls: false,
  paidDefaults: false,
  automaticOutboundDelivery: false,
  bindAddress: "127.0.0.1",
  openclawGatewayUrl: "ws://127.0.0.1:18789",
  // Documented OpenClaw state location — never opened for write by FreeForge.
  openclawPrivateDbPath: "~/.openclaw/state/openclaw.sqlite",
  freeforgeOwnsSchedule: true,
  freeforgeOwnsModelLoop: false,
  openclawOwnsModelLoop: true,
  freeforgeOwnsLocalEffects: true,
};

export function assertPolicySafe(policy: FreeForgePolicy): void {
  if (policy.requirePaidCredentials) {
    throw new Error("Policy violation: paid credentials must remain disabled.");
  }
  if (policy.backgroundModelCalls) {
    throw new Error("Policy violation: background model calls disabled until configured.");
  }
  if (policy.paidDefaults) {
    throw new Error("Policy violation: paid defaults disabled.");
  }
  if (policy.automaticOutboundDelivery) {
    throw new Error("Policy violation: automatic outbound delivery disabled until configured.");
  }
  if (policy.bindAddress !== "127.0.0.1" && policy.bindAddress !== "localhost") {
    throw new Error("Policy violation: listeners must bind loopback only.");
  }
}
