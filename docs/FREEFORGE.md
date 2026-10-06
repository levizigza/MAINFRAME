# FreeForge — thin integration design (2026-09-29)

FreeForge sits **beside** MAINFRAME: cost policy, repository tools, and verified workflows. It does **not** replace OpenClaw's Gateway or invent a second agent loop.

## Roles

| Piece | Owns | Does not own |
|-------|------|----------------|
| **OpenClaw** (pinned) | Local Gateway, automations/cron scheduling, channel delivery, **selected** embedded agent coding runtime | FreeForge cost policy DB; MAINFRAME scorecard fixtures |
| **FreeForge** | Cost/eligibility policy (reuses MAINFRAME gate), repo tools, verified workflow runners, Playwright browser checks, **its own** SQLite | Gateway process; competing coding loop |
| **public-apis** (pinned) | Discovery catalog of public HTTP APIs | Runtime calls; paid APILayer upsell |
| **Void** (pinned, archived) | Optional **reference** for editor UX/source ideas | Foundation dependency; CI submodule auto-bumps; live product track |

## Pinned revisions (observed 2026-09-29)

Machine-readable: [`PINS.json`](PINS.json)

| Repo | Pin | License (observed) |
|------|-----|--------------------|
| [openclaw/openclaw](https://github.com/openclaw/openclaw) | tag **v2026.9.6** → commit `eb377ac59e6c9fd6c7705028034812becf00271b` (npm version `2026.9.6`) | **MIT** (`LICENSE`); GitHub API `NOASSERTION`; redistribute with `THIRD_PARTY_NOTICES.md` |
| [voideditor/void](https://github.com/voideditor/void) | commit `b3166e7ef2aefbdfeb139445fdf248a561b85d4d` (**archived**) | **Apache-2.0** (`LICENSE.txt`) |
| [public-apis/public-apis](https://github.com/public-apis/public-apis) | commit `8939d468fa4580039c4e22cc4998eb3fef8130d1` | **MIT** |

Upstream `main` HEAD for OpenClaw at audit time was newer (`e89ae26…`); FreeForge pins the **release tag**, not floating main.

## Extension points (actual, from OpenClaw docs — not invented)

Sources: https://docs.openclaw.ai/concepts/agent · https://docs.openclaw.ai/automation · https://docs.openclaw.ai/tools/acp-agents/quickstart · https://docs.openclaw.ai/plugins/reference/opencode

1. **Gateway process** — control plane for sessions, tools, events, channels; automations run **inside the Gateway**, not inside the model.
2. **Automations / cron** — `openclaw automations` (alias `openclaw cron`); schedules persist in OpenClaw shared SQLite; Gateway must be running.
3. **Embedded agent runtime** — single built-in agent loop, tool wiring, prompt assembly; workspace bootstrap files (`AGENTS.md`, etc.); session DB under `~/.openclaw/agents/<id>/…`.
4. **Skills dirs** — workspace / `.agents/skills` / `~/.openclaw/skills` / bundled / `skills.load.extraDirs`.
5. **Hooks** — internal lifecycle hooks + plugin tool hooks (separate from HTTP webhook triggers).
6. **ACP harness path** (`@openclaw/acpx`) — **external** coding harness process; OpenClaw owns routing/task state/delivery; harness owns auth, model catalog, native tools. Targets include `opencode`, `claude`, `codex`, `cursor`, …
7. **OpenCode plugin** (`@openclaw/opencode-provider`) — model **provider** + session catalog / Continue-via-ACP — **not** the same as “FreeForge coding engine.”

FreeForge hooks in by: (a) verified workflow CLIs FreeForge owns, (b) optional skill wrappers that **call** those CLIs, (c) cost policy checks **before** any paid/hosted route, (d) recording results in FreeForge SQLite. It does **not** patch OpenClaw internals in v0.

## Coding-engine spike (select one — no nested loops)

### Candidates

| Path | What runs the coding loop | Prerequisites (docs / local) |
|------|---------------------------|------------------------------|
| **A. OpenClaw embedded agent** | OpenClaw-owned embedded runtime | OpenClaw Gateway + configured model (local eligible preferred) |
| **B. OpenCode ACP worker** | External OpenCode harness via `sessions_spawn({ runtime: "acp", agentId: "opencode" })` | `@openclaw/acpx` enabled + OpenCode CLI + **harness provider auth** |

### Local spike result (2026-09-29, this machine)

| Probe | Result |
|-------|--------|
| `openclaw` on PATH | **absent** |
| `opencode` on PATH | **absent** |
| `playwright` on PATH | **present** |

### Decision

**Selected coding engine: OpenClaw embedded agent runtime** (`openclaw_embedded_agent_runtime`).

**Not selected: OpenCode ACP worker** for FreeForge-default coding jobs.

Reasons (evidence-based, not invented compatibility):

1. Docs define ACP as a **separate** harness process with its own auth/tools — using OpenCode ACP **and** OpenClaw embedded coding on the same FreeForge job would nest competing loops; FreeForge refuses that pattern.
2. OpenCode provider plugin ≠ coding worker; conflating them would invent compatibility.
3. Neither CLI is installed yet — selection is architectural. Runtime remains **deferred** until OpenClaw is installed; FreeForge deterministic workflows (MAINFRAME scorecard/automation) stay usable without it.
4. OpenCode worker typically needs harness provider auth; FreeForge/MAINFRAME free-only gate still applies — paid OpenCode providers stay disabled.

If a future job **explicitly** requests OpenCode-only coding: Gateway may schedule an ACP spawn **without** also running an embedded coding turn for that job. That is opt-in, not the default engine.

## Execution ownership

| Concern | Owner |
|---------|--------|
| Schedule fire time / cron persistence | **OpenClaw Gateway** (sole scheduler owner) |
| Channel delivery | OpenClaw |
| Coding agent loop (default) | OpenClaw embedded runtime |
| Cost eligibility / refuse paid routes | FreeForge (= MAINFRAME `eligibility`) |
| Automation **command** cost/permission policy | FreeForge (not `tools.exec` model-tool approvals) |
| OpenClaw-compatible `--command-argv` payloads + local deterministic fire when Gateway deferred | FreeForge (`mainframe.schedule`) |
| Repo inspect / checksum / verified workflows | FreeForge / MAINFRAME automation |
| Browser automation for maintenance checks | FreeForge + **Playwright** |
| FreeForge run history, discovery cache, spike records | FreeForge **SQLite** (`.mainframe/freeforge.sqlite`) |
| OpenClaw sessions / automation history | OpenClaw SQLite (do not merge DBs) |
| Editor product line | **None** — Void is reference-only |

## Reuse before new infrastructure

Already in MAINFRAME — FreeForge reuses, does not rebuild:

- `mainframe.eligibility` — free-only gate
- `mainframe.automation` — deterministic tasks
- `mainframe.scorecard` — W1–W3 verified workflows
- `mainframe.ai` — optional loopback Ollama only
- `python -m mainframe accept|audit|scorecard`

New surface is intentionally thin: pins, spike recorder, SQLite, Playwright probe, public-apis discovery helper.

## Playwright

Used for FreeForge browser verification (e.g. W2-style checks against a local or allowed URL). Not a second agent. If Playwright browsers are missing, probe reports pause — no paid cloud browser service.

## public-apis discovery

- Pin commit above; **local snapshot** under `docs/freeforge/public-apis-snapshot/`
  (LICENSE + README.pinned.md + catalog.json + shortlist evidence).
- Discovery searches the local catalog — it does **not** call every listed endpoint,
  execute linked code, or install MCP servers.
- Catalog MIT license ≠ API terms ≠ returned-data license (recorded separately on shortlists).
- Default catalog state is `unverified`. Never mark every entry free automatically.
- Shortlist evidence records docs, pricing, auth, quotas, intended-use, attribution,
  retention, availability, and last verification. States: `eligible` | `restricted` |
  `unverified` | `rejected`. Unknown or expired evidence blocks activation.
- Advertisements and commercial listings (e.g. APILayer README marketing) confer **no** entitlement.
- CLI: `python -m mainframe discovery status|search|shortlist|activate|accept`
  (and `freeforge discover` for the same local search).

## Void maintenance risks

- Repo **archived**; README: deprecated, not accepting contributions.
- VS Code fork — large surface, private upstream build complexity; **do not** auto-maintain as FreeForge foundation.
- Allowed use: read pinned tree / copy isolated ideas with Apache-2.0 notice retention.
- Prefer linking [`void-forks`](https://github.com/voideditor/void-forks) only as human research, not as a FreeForge dependency.

## Other maintenance risks

| Risk | Mitigation |
|------|------------|
| OpenClaw moves fast (`main` ahead of release) | Pin release tag; bump deliberately |
| OpenClaw MIT + third-party notices | Keep notices file when vendoring |
| ACP / OpenCode auth drift | Keep OpenCode **not selected**; document opt-in only |
| public-apis churn + commercial README noise | Pin commit; eligibility filter |
| Nesting agent loops | Hard rule in FreeForge spike/status |
| Merging OpenClaw + FreeForge SQLite | Forbidden |

## TypeScript CLI (bootstrap)

See [`freeforge-cli/README.md`](../freeforge-cli/README.md). Commands: `doctor`, `run`, `workflows`, `status`, `resume`, `eval`, `serve-status`. OpenClaw integration for pin **v2026.9.6** is isolated under `freeforge-cli/src/openclaw/v2026_9_6/`. FreeForge SQLite is `.mainframe/freeforge-cli.sqlite` — never OpenClaw's private DB.

## Commands

```powershell
python -m mainframe freeforge status
python -m mainframe freeforge spike
python -m mainframe freeforge discover --query auth
python -m mainframe discovery search --query dog
python -m mainframe discovery accept
```
