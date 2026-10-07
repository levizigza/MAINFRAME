# FreeForge Workbench fork plan (vscode pin + thin overlay)

**Product decision (locked):** FreeForge ships a **branded workbench** downstream of pinned `microsoft/vscode`, with a thin overlay under `src/vs/workbench/contrib/freeforge/`. Void is an **archived UX reference only** (`docs/VOID_EVAL.md`) — do **not** vendor Void `editCodeService` / React workbench internals.

CLI + `extensions/freeforge-editor` remain the headless / Extension API twin. The IDE quality track is the desktop workbench.

## Layout

| Path | Role |
|------|------|
| `workbench/PIN.json` | Upstream tag, Void reference commit, inference policy |
| `workbench/overlay/freeforge/` | Thin contrib (chat, AI status, bridge contracts, diff review helpers) |
| `workbench/scripts/bootstrap.ps1` / `bootstrap.sh` | Clone pin + copy overlay |
| `mainframe/workbench/` | Status, model-fit, bootstrap, agent sessions, accept |
| `.workbench-build/` | Local clone/build (gitignored) |

## Upstream update strategy

- Track microsoft/vscode release tags (e.g. monthly deliberate bumps in `PIN.json`).
- Rebase or merge as a **thin overlay** only — never silent multi-month drift of deep workbench forks.
- Pin Electron / Node to vscode’s published dependency set for that tag.
- Document conflict classes (build tooling, CSP) when they appear.

## Security

- Inherit vscode security advisories; subscribe to GHSA for Electron and vscode.
- No auto-update channel that ships unsigned binaries as a required path.
- Secrets stay in FreeForge `LocalSecretFacility` — never in fork settings JSON exported to chat.
- LLM traffic: Extension Host / main-process bridge to `python -m mainframe …` — loopback Ollama only (`eligibility` + `cost_gate`).

## Build

- Primary OS: Windows. Bootstrap scripts prove pin + overlay without hosted CI.
- Full Electron build is a **local opt-in** step (see `workbench/README.md`); MAINFRAME CLI accept does not require it.
- Reproducible: lockfiles inside the vscode pin; FreeForge overlay is MIT.

## Distribution

- Application surface copies pin + overlay pointer under `dist/application/workbench/`.
- License: MIT (vscode) + ThirdPartyNotices retention + FreeForge MIT overlay.
- Code-signing SaaS and App Store upload are **not required** for core usefulness.

## Agent UX (wired to Python)

- Streaming chat panel → `workbench session-start|turn`
- Context chips → `workbench context` / editor selection
- Tool loop → retrieve / propose / verify via MAINFRAME
- Diff review → Accept/Reject via `workbench apply` (never silent overwrite)
- Cancel/resume → async bridge (extension uses `spawn`, not blocking `spawnSync`)

## Inference

- Mode B: `ollama_local` / `llamacpp_local` only; pause when unavailable.
- Mode A: editing + deterministic CLI always work.
- No paid OpenAI/Anthropic/Cursor API path.

## Exit criteria that still matter

If a contributor only needs chat-to-task + reviewable apply inside stock VS Code, the extension path (`editor accept`) is enough. The **branded workbench** is the north-star shell for IDE parity claims — those claims stay **unknown** until measured (`docs/eval/ide/`, codingbench live).
