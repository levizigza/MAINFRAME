# FreeForge Workbench

**FreeForge Workbench** = a VS Code-class desktop shell + FreeForge local agent.

MAINFRAME CLI alone is **not** an IDE. The workbench is the product track for editor UX
(chat, reviewable apply, context). The CLI remains the headless twin for automation and CI.

## Locked product choices

| Decision | Choice |
|----------|--------|
| Shell | Branded workbench downstream of pinned `microsoft/vscode` (Void = UX reference only) |
| Inference | Mode B: optional loopback Ollama / llama.cpp on this PC |
| Cost | Zero paid software/API/hosting; electricity/CPU/RAM/disk are physical costs |
| When AI unavailable | Chat pauses; editing, terminal, SCM, and deterministic CLI still work |

## What this is not

- Not a claim that FreeForge exceeds Cursor or sits at a “99th percentile” without measurements
- Not a Void fork (Void is archived; ideas only — see `docs/VOID_EVAL.md`)
- Not dependent on paid OpenAI/Anthropic/Cursor APIs
- Not blocked when local models are missing (Mode A always usable)

## Layout

```
freeforge-workbench/     vscode pin + FreeForge overlay + build scripts
mainframe/workbench/     Python: fitness, agent bridge, onboarding, accept
docs/eval/ide/           Evidence-gated IDE metrics (unknown until measured)
```

## Commands

```powershell
python -m mainframe workbench status
python -m mainframe workbench fitness
python -m mainframe workbench onboarding
python -m mainframe workbench agent-turn --task <id> --message "..."
python -m mainframe workbench accept
```

Workbench Electron build (Windows primary): see `freeforge-workbench/README.md`.

## Mode B first steps (user-initiated)

1. Install [Ollama](https://ollama.com) locally (free software; not required for Mode A).
2. Run `python -m mainframe doctor` and `python -m mainframe workbench fitness`.
3. Pull **only** a model listed under `eligible_to_consider` (doctor never auto-downloads).
4. Re-run `python -m mainframe ai probe` until status is `available`.
5. Then run live `modeleval` / `codingbench --live` — cells stay **unknown** until that succeeds.

## Honesty

Competitor Cursor/Claude E2E quality remains **unknown** unless you measure it yourself.
Live local coding quality remains **unknown** until an eligible model is installed and evals run.
