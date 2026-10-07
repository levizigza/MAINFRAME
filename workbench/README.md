# FreeForge Workbench (branded VS Code-class IDE)

Pinned upstream: see [PIN.json](PIN.json). Overlay sources: [overlay/freeforge](overlay/freeforge).

## Goal

Ship a professional AI IDE shell + FreeForge agent that can **match or exceed** Cursor/Claude Code on measured tasks using **free local inference only**. See [docs/IDE_GOAL.md](../docs/IDE_GOAL.md).

## Layout

```
workbench/
  PIN.json                 Upstream vscode pin + policy
  overlay/freeforge/       Thin contrib copied into vscode tree
  scripts/                 Clone / apply-overlay / build (Windows)
  README.md                This file
```

Clone/build artifacts live in `.workbench-build/` (gitignored) — not committed.

## Quick commands

```powershell
python -m mainframe workbench status
python -m mainframe workbench model-fit
python -m mainframe workbench bootstrap   # clone pin + apply overlay (needs git + network once)
python -m mainframe workbench accept
```

Full Electron build of vscode is heavy; bootstrap proves pin + overlay integration. Daily coding still uses MAINFRAME CLI until Phase 2 agent UI lands in the workbench.

## License

Upstream vscode: MIT + ThirdPartyNotices. FreeForge overlay: MIT (MAINFRAME). Do not copy Void workbench service internals.
