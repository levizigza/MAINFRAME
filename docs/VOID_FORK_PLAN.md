# FreeForge Workbench fork plan (vscode pin + thin overlay)

**Product track:** FreeForge Workbench is a branded desktop shell downstream of pinned
`microsoft/vscode`, with agent brain in MAINFRAME Python. Void remains an **archived UX
reference** only (`docs/VOID_EVAL.md`) — copy ideas (reviewable apply, DiffZones-style UX),
**not** Void workbench services.

CLI / extension bridge alone is **not** the IDE quality track. Extension path remains useful
as a lightweight host option; the workbench is the branded product.

Layout: [`freeforge-workbench/`](../freeforge-workbench/) — see [`docs/WORKBENCH.md`](WORKBENCH.md).

## Concrete requirements

### 1. Upstream update strategy

- Track microsoft/vscode release tags on a schedule (e.g. monthly). Current pin: `PINS.json`.
- Rebase FreeForge patches as a thin overlay under `src/vs/workbench/contrib/freeforge/`.
- Pin Electron / Node versions to vscode’s published dependency set for that tag.
- Document conflict classes (build tooling, CSP, contribution registration) in PROGRESS.

### 2. Security

- Inherit vscode security advisories; subscribe to GHSA for Electron and vscode.
- No auto-update channel that ships unsigned binaries as a required path.
- Secrets stay in FreeForge `LocalSecretFacility` — never in fork settings JSON exported to chat.
- Renderer CSP: LLM traffic only via Extension Host / main-process bridge to
  `python -m mainframe …` — loopback Ollama only; non-loopback refused by eligibility.

### 3. Build

- Local Windows scripts in `freeforge-workbench/scripts/` (no paid cloud GPU).
- Reproducible builds: lockfiles, pinned toolchains; retain ThirdPartyNotices.
- Electron packaging may be DOCUMENTED_NOT_TESTED on non-Windows CI; Python `workbench accept` still gates overlay + agent bridge.

### 4. Distribution

- Optional install path; CORE CLI must work without the workbench binary.
- License bundle: MIT (vscode + MAINFRAME) + full ThirdPartyNotices.
- Auto-update is opt-in and fee-free; no telemetry SaaS.

### 5. When extension-only is enough

Chat-to-task, selection, reviewable diffs, diagnostics, cancel/resume via
`extensions/freeforge-editor` + `editor` CLI remain supported. Prefer that path for
lightweight hosts; do **not** block Mode A on workbench Electron availability.

## Non-goals

- Vendoring Void `editCodeService` / React workbench internals
- Paid OpenAI/Anthropic/Cursor API as required path
- Claiming Cursor parity without `docs/eval/ide/` measurements
