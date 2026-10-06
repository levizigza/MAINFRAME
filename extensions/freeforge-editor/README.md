# FreeForge Editor Extension

Maintained **VS Code / Cursor extension** using the public Extension API.

- Does **not** copy Void `editCodeService` / `voidModelService` or other workbench internals.
- Shares task state with `python -m mainframe editor …` under `.mainframe/editor_tasks/`.
- Preserves unsaved buffers via `freeforge.syncDirtyBuffers` / on-save hooks.
- See `docs/VOID_EVAL.md` for licensing and Void evaluation at pin `b3166e7…`.

## Install (dev)

Open this folder as an extension development host, or copy into `.vscode/extensions`.

Requires MAINFRAME on `PYTHONPATH` / runnable as `python -m mainframe`.
