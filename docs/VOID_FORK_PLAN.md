# FreeForge Workbench — vscode pin + thin overlay

**Product decision (locked):** FreeForge ships a **branded workbench** downstream of pinned `microsoft/vscode`, with a thin overlay at `src/vs/workbench/contrib/freeforge/`. See [`docs/IDE_GOAL.md`](IDE_GOAL.md) and [`workbench/PIN.json`](../workbench/PIN.json).

Void remains **archived UX reference only** — do **not** copy Void workbench services (`editCodeService`, `voidModelService`, React+Tailwind contrib).

The maintained extension ([`extensions/freeforge-editor`](../extensions/freeforge-editor)) remains a bridge into Cursor/VS Code while the workbench build matures. Core CLI never requires the workbench.

## Upstream update strategy

- Track microsoft/vscode **release tags** (pin in `workbench/PIN.json`).
- Thin FreeForge overlay only — never silent multi-month drift of a fat fork.
- Pin Electron / Node to vscode’s published set for that tag.
- Bootstrap: `python -m mainframe workbench bootstrap` (clone → `.workbench-build/vscode`, gitignored).

## Security

- Inherit vscode security advisories.
- No required auto-update / unsigned binary channel for core.
- Secrets stay in FreeForge `LocalSecretFacility`.
- LLM traffic: loopback Ollama/llama.cpp via MAINFRAME eligibility gate — not ad-hoc renderer `fetch` to hosted APIs.

## Build / distribution

- Primary OS: Windows. Hosted CI and code-signing SaaS are **not required**.
- License bundle: MIT (vscode + FreeForge overlay) + full ThirdPartyNotices from upstream.
- App Store / Play uploads remain optional and DOCUMENTED_NOT_TESTED until separately pursued.

## Inference

Mode B only for agent coding: local Ollama / llama.cpp. When unavailable, workbench editing continues; agent UI shows **paused**.
