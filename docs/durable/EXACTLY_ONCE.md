# Exactly-once execution — what MAINFRAME does and does not guarantee

MAINFRAME durable tasks aim for **at-least-once with reconciliation**, not magical exactly-once across every destination.

## Guarantees we aim for

- Durable transitions among: `planned`, `started`, `succeeded`, `failed`, `cancelled`, `outcome_unknown`.
- Operation IDs, checkpoints, leases, and effect receipts persisted locally (SQLite).
- After restart or connection gaps, FreeForge records are reconciled with the **selected engine** (`openclaw_embedded_agent_runtime`) through **supported status APIs**.
- A timeout after an external mutation triggers **status reconciliation**, not an automatic duplicate mutation.
- Where the destination supports idempotency keys (`local_effect_sink`, selected engine), keys are attached and duplicate applies are suppressed when the sink still has the prior receipt.

## Exactly-once cannot be guaranteed when

1. The destination does **not** support idempotency keys (`generic_http_no_key`).
2. A crash occurs after an external mutation is applied but **before** a durable receipt is written **and** the destination has no queryable status API.
3. Lease fencing is bypassed (two workers force-hold the same operation).
4. Recovery incorrectly assumes a **WebSocket** event stream will replay missed events — MAINFRAME explicitly does **not** assume that.

## Prefer

1. Idempotency keys when supported.
2. Poll status APIs after gaps / timeouts.
3. Treat `outcome_unknown` as “reconcile first,” never “mutate again blindly.”
