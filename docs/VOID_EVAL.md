# Void evaluation (pin `b3166e7ef2aefbdfeb139445fdf248a561b85d4d`)

Sources inspected 2026-10-06 (and originally pinned 2026-09-29):

- https://raw.githubusercontent.com/voideditor/void/b3166e7ef2aefbdfeb139445fdf248a561b85d4d/VOID_CODEBASE_GUIDE.md
- https://raw.githubusercontent.com/voideditor/void/b3166e7ef2aefbdfeb139445fdf248a561b85d4d/LICENSE.txt
- https://raw.githubusercontent.com/voideditor/void/b3166e7ef2aefbdfeb139445fdf248a561b85d4d/README.md

## Status

Void is **deprecated / archived** and no longer accepting contributions. Useful as **reference** for editor UX ideas — not as a drop-in FreeForge runtime or automatically maintainable foundation.

## Licensing (before any copy)

| Layer | Observed | Implication |
|-------|----------|-------------|
| Void `LICENSE.txt` | **Apache-2.0** (appendix: Copyright 2025 Glass Devtools, Inc.) | Copying Void-authored files requires Apache-2.0 notice retention |
| Inherited VS Code tree | Microsoft vscode is typically **MIT** plus extensive third-party notices | A fork must retain VS Code MIT + ThirdPartyNotices; not “Apache only” |
| Third-party | Upstream ships many bundled deps (Electron, Monaco, etc.) | Must audit NOTICE / ThirdPartyNotices before redistribution |

**MAINFRAME decision:** Do **not** copy Void workbench services (`editCodeService`, `voidModelService`, React+Tailwind workbench UI). Prefer a **maintained VS Code / Cursor extension** using the public Extension API. Ideas (diff zones, model sync, apply UX) inform design only.

## Service evaluation (reuse posture)

| Concern | Void approach (guide) | FreeForge reuse |
|---------|----------------------|-----------------|
| Diff application | `editCodeService`: DiffZones, Fast Apply (search/replace blocks), Slow Apply (whole file), streaming red/green | Reuse **concept**; implement via MAINFRAME `patching.apply_batch` + reviewable unified diffs — not Void internals |
| Text-model sync | `voidModelService`: write to `ITextModel` by URI; sync OS ↔ buffers | Extension API: `TextDocument` / `WorkspaceEdit`; preserve dirty buffers in shared task state before disk write |
| Context selection | Chat sidebar + Cmd+K smaller DiffZone; feature/model selection in settings | Extension: selection → shared task `context.selection`; CLI reads same task JSON |
| Completion UX | FeatureName Autocomplete / FIM via custom LLM pipeline | **Budgeted completion only** when an eligible local model is present; otherwise disable |

**Void internal workbench services are not drop-in extension modules** — they depend on `registerSingleton`, Electron main/browser IPC, and a forked build pipeline.

## Preferred path

1. **Maintained editor extension** (`extensions/freeforge-editor`) using supported VS Code APIs.
2. **Shared task state** under `.mainframe/editor_tasks/` consumed by extension and `python -m mainframe editor …`.
3. **Optional full Void/VS Code fork** — see `docs/VOID_FORK_PLAN.md`; not required for core FreeForge.

## What was not copied

No files from `src/vs/workbench/contrib/void/` are vendored into MAINFRAME.
