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

Full Electron build of vscode is heavy; bootstrap proves pin + overlay integration. Agent sessions work via CLI twin today:

```powershell
python -m mainframe workbench session-start --workspace . --chat "fix mathutil"
python -m mainframe workbench turn --session <id> --message "repair add" --no-model
python -m mainframe workbench apply --session <id> --accept
```

Overlay modules: chat panel, context chips, tool loop, diff review, bridge (loopback-only Ollama URL).

## License

Upstream vscode: MIT + ThirdPartyNotices. FreeForge overlay: MIT (MAINFRAME). Do not copy Void workbench service internals.
