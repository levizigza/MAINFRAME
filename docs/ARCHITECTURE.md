# MAINFRAME architecture

## Goals

- Coding + automation on existing Windows hardware
- Zero required fees (software, API, subscription, hosting)
- Deterministic paths usable without any LLM
- Optional free local inference; pause when unavailable

## Layers

1. **CLI** (`mainframe/cli.py`) — entry via `python -m mainframe`
2. **Config / state** (`mainframe/config.py`) — `.mainframe/` local state; cost posture enforced
3. **Workspace inspect** (`mainframe/workspace.py`) — read-only inventory of rules, docs, modules
4. **Automation** (`mainframe/automation`) — named deterministic tasks, run logs under `.mainframe/runs/`
5. **AI gateway** (`mainframe/ai`) — probes `127.0.0.1` Ollama only; never paid APIs

## Cost enforcement

`COST_POSTURE` in config is the source of truth. Loaders force paid/trial/promo/hosted flags to `false`, strip credential keys, and reject non-loopback AI endpoints.

`mainframe/eligibility.py` catalogs eligible vs **disabled** providers. Disabled adapters in `mainframe/ai/rejected.py` hard-refuse with `fallback_used: false`.

See `docs/DEPENDENCIES.md` and `python -m mainframe audit`.

## AI pause contract

- Only `ollama_local` on loopback may run
- `ai probe` → `available` | `paused` | `disabled`
- `ai ask` with no free backend → `paused: true`, prompt preserved, exit 0
- `ai refuse <disabled_id>` proves the route exists and refuses
- Automation never requires AI (`automation.require_ai: false`)
- **No** automatic fallback to paid, trial, promotional, or hosted engines

## Increment workflow

1. Inspect rules + code
2. Preserve user work
3. Ship one runnable increment
4. Run `python -m mainframe accept` (and any extra real checks)
5. Append `docs/PROGRESS.md` with observed results only
