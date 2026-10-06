# Recommended FreeForge configuration

Generated: `2026-10-06T19:30:21.316770+00:00`
Recommended mode: **`deterministic_offline`**

## Objective

Optimize **correct completed work per available resource** (CPU, RAM, disk, time, verified free quota) — not agent count, model size, or a cosmetic frontier label.

Unlimited frontier performance is **not claimed**.

## Three modes

### `deterministic_offline` — Deterministic offline automation

- Inference: `none`
- Behavior: Workflows, connectors (fixtures), docreport, coding harness patches, schedule fire, dashboard, project isolation — all run without models.
- When inference unavailable: N/A — this mode never calls inference. AI steps are not scheduled.

### `deterministic_plus_optional_cpu_ai` — Core + optional CPU AI (loopback) — available_now=`False`

- Inference: `ollama_local | llamacpp_local`
- Behavior: Same deterministic core. Typed AI steps / coding completion only when an eligible loopback model answers; quota ledger admits requests.
- When inference unavailable: AI-dependent steps pause (checkpoint). Deterministic predecessors/siblings continue. No automatic paid or hosted fallback. Progress preserved.

### `deterministic_plus_eligible_free_hosted_ai` — Core + currently eligible free hosted AI — available_now=`False`

- Inference: `eligible_free_hosted_only`
- Behavior: Same deterministic core. Hosted inference activates only after verification in eligibility.py — marketing free tiers are not entitlements.
- When inference unavailable: Today: always unavailable (zero verified hosted entitlements). Behavior: refuse hosted routes; pause AI steps; continue deterministic work; no trial/promo/billing activation; no silent switch to paid endpoints.

**Rationale:** Optimize correct completed work per available resource. On this host local Ollama is paused/unreachable, so Mode A is recommended. Mode C has no currently eligible free hosted providers.

## Capability matrix (concise)

| Capability | Status | Note |
|------------|--------|------|
| `deterministic_automation` | `measured` | Held-out W1–W3 + workflow fixtures; model_calls=0 |
| `optional_cpu_ai` | `unknown` | Ollama paused/unreachable — live local model quality unmeasured on this host. |
| `eligible_free_hosted_ai` | `unavailable` | No verified recurring-free hosted entitlement (see docs/PROVIDERS.md). |
| `competitor_claude_code_cursor_e2e` | `unknown` | Unmeasured — no purchased access. |
| `frontier_unlimited_performance` | `unknown` | not claimed |

## Measured workloads (held-out)

| Workload | FreeForge | Minimal | Manual | Outperforms minimal? |
|----------|-----------|---------|--------|----------------------|
| repository_repair | 1.0 (n=5, small_sample) | 0.0 | 1.0 | True |
| website_maintenance | 1.0 (n=5, small_sample) | 0.0 | 1.0 | True |
| document_reporting | 1.0 (n=5, small_sample) | 0.0 | 1.0 | True |

## Sustainable quotas

- Wall-clock theoretical volumes from sub-second deterministic runs are NOT interactive capacity. Prefer quota + human review limits.
- Default AI bucket (when Mode B used): `{'requests': 60, 'tokens': 100000, 'context': 32000, 'concurrency': 4, 'source': 'quota ledger default bucket'}`
- Interactive daily capacity: **unknown** (not wall-clock theoretical volume)

## Hardware observations (this host)

- CPU: `Intel64 Family 6 Model 154 Stepping 3, GenuineIntel` (20 logical)
- RAM available GiB: `None` / total `None`
- Optional CPU inference budget GiB: `None`
- Free disk GiB: `None`
- AI probe: `paused`

## Where this build outperforms measured baselines

- FreeForge correct rate >> minimal free agent on held-out repair / site / docreport (n=5)
- FreeForge matches manual correctness with less active human time on those workloads
- Retrieval improves site + docreport; review improves docreport (ablations)

## Where it does not / unmeasured

- Does not exceed manual correctness rate on those workloads (tied at 1.0)
- Competitor Claude Code / Cursor E2E: unknown
- Live local/hosted model coding quality on this host: unknown (AI paused)
- Unlimited frontier performance: not claimed

## Unresolved weaknesses

- **per_feature_vs_joint_ablation** (medium): None
- **small_n_heldout** (medium): None
- **no_local_model_on_host** (high_for_ai_tasks): None
- **no_eligible_hosted_free** (high_for_hosted_ai): None
- **no_os_network_isolation** (medium): None
- **competitor_e2e_unmeasured** (unknown): None
- **schtasks_elevation** (low): None
- **theoretical_daily_volume** (high_misread_risk): None

## Prioritized next improvements

1. **fit_and_measure_local_cpu_model** — Install a RAM-fitting local model; run modeleval live holdout; update Mode B cells from unknown → measured
2. **expand_heldout_n** — Increase held-out n beyond 5 before tightening CI-based claims
3. **verify_or_keep_refusing_hosted** — Only enable Mode C after recurring-free entitlement evidence; otherwise keep refuse
4. **operational_quota_calibration** — Replace theoretical wall-clock volume with measured sustainable interactive quotas
5. **optional_os_network_isolation** — If live connectors needed, verify OS network isolation before re-enabling non-loopback

## Acceptance demos (this run)

- Coding (W1 repair): `PASS` — None
- Coding (cb_hold_logic): `PASS`
- Reusable automation (input_to_report): `PASS` — None

## Strict contract reminder

No required paid account, trial, promo credit, or hosted component for Mode A. Mode B pauses without local model. Mode C has zero currently eligible hosted providers.
