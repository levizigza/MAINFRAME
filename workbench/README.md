# FreeForge Workbench

Branded VS Code-class IDE shell + FreeForge agent (local Ollama). Goal: [docs/IDE_GOAL.md](../docs/IDE_GOAL.md).

## Commands

```powershell
python -m mainframe workbench status
python -m mainframe workbench model-fit
python -m mainframe workbench bootstrap
python -m mainframe workbench accept
python -m mainframe editor agent-accept   # Phase 2 agent UX
```

Clone/build artifacts: `.workbench-build/` (gitignored). Overlay: `overlay/freeforge/` (includes `agentPanel.ts`).
Daily agent UI: `extensions/freeforge-editor` → **FreeForge: Open Agent Panel**.
