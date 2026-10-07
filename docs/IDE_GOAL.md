# MAINFRAME / FreeForge IDE — final goal

**Final goal:** FreeForge Workbench is a professional AI IDE that **matches or exceeds** Cursor and Claude Code on measured coding tasks — with **zero required paid APIs, accounts, or hosted compute**.

## The dilemma

| Constraint | Implication |
|------------|-------------|
| No paid frontier APIs | Cannot buy Cursor/Claude model quality |
| No hosted compute bill | Inference on the user's PC (Ollama / llama.cpp) |
| Physical costs remain | Electricity, CPU/RAM, disk, model downloads are user-borne |
| Honesty | Never invent Cursor-beating scores; publish measurements or mark **unknown** |

**Winning strategy under constraints:**

1. **Shell parity** — Branded VS Code-class workbench (explorer, editor, terminal, SCM).
2. **System superiority** — Deterministic-first retrieve → patch → verify → review; tight context; reviewable apply.
3. **Local model fitness** — Fit weights to measured RAM; prefer models that win *our* codingbench.
4. **Offline core** — Editing, tests, and deterministic automation never require AI.
5. **Evidence iteration** — Expand held-out tasks; ablate no-gain features; claim parity only when measured.

## Product shape (locked)

- **Shell:** Branded FreeForge workbench from pinned `microsoft/vscode` (Void = UX reference only).
- **Inference:** Mode B — loopback Ollama / llama.cpp; pause when unavailable.
- **Brain:** MAINFRAME Python (`editor`, `codingloop`, `retrieve`, `patching`, `verify`, `review`, `quota`).

## Goal status

| Milestone | Status |
|-----------|--------|
| CLI automation + free-only gates | Measured |
| Thin editor bridge | Partial (not IDE) |
| Branded workbench bootstrap | In progress (`workbench/`) |
| Mode B on this host | Blocked until Ollama installed + fitted pull |
| Live codingbench vs Cursor/Claude | **unknown** |
| Match/exceed on measured suites | **not yet achieved** — north star |

See `docs/MODE_B_ONBOARDING.md` and `python -m mainframe workbench accept`.
