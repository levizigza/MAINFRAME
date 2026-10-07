# FreeForge Workbench

Branded VS Code-class desktop shell + FreeForge local agent (Mode B optional Ollama).

**Product truth:** CLI alone is not the IDE. This directory is the workbench track.

## Pins

See [`PINS.json`](PINS.json) — upstream `microsoft/vscode` tag, Electron/Node pins.

Void is **UX reference only** — do not copy Void workbench services.

## Layout

```
PINS.json                 upstream pin
ThirdPartyNotices.txt     license retention
overlay/                  thin FreeForge contrib (copied onto vscode tree)
scripts/                  Windows fetch + build helpers
media/                    product icons / branding stubs
```

## Build (Windows primary)

Requires: Git, Node matching `PINS.json`, Python for MAINFRAME CLI twin.

```powershell
cd freeforge-workbench
.\scripts\fetch-vscode.ps1
.\scripts\apply-overlay.ps1
.\scripts\build-windows.ps1
```

Artifacts land under `../dist/application/workbench/` when build succeeds.

On non-Windows CI hosts, Electron packaging is **documented_not_tested** — Python bridge
accept (`python -m mainframe workbench accept`) still validates overlay presence + agent UX.

## AI status

Workbench UI must show **AI paused** when `python -m mainframe ai probe` is not `available`.
Deterministic editing, terminal, and SCM (stock vscode) remain usable.

Settings: Ollama base URL loopback-only (`http://127.0.0.1:11434`) — enforced by MAINFRAME eligibility.

## Onboarding

```powershell
python -m mainframe workbench onboarding
python -m mainframe workbench fitness
```

## Honesty

Do not claim Cursor parity or “99th percentile” without published local measurements in `docs/eval/ide/`.
