# MAINFRAME / FreeForge IDE — final goal

**Final goal:** FreeForge Workbench is a professional AI IDE that **matches or exceeds** Cursor and Claude Code on measured coding tasks — **with zero required paid APIs, accounts, or hosted compute**.

This is not a slogan. It is an engineering dilemma under hard constraints. The solution is not “run a bigger paid model.” It is a **system** that makes free local intelligence finish correct work as often (or more often) than frontier-hosted agents, while remaining usable when AI is offline.

## The dilemma (stated clearly)

| Constraint | Implication |
|------------|-------------|
| No paid frontier APIs | Cannot buy Cursor/Claude model quality |
| No hosted compute bill | Inference runs on the user’s PC (Ollama / llama.cpp) |
| Physical costs remain | Electricity, CPU/RAM, disk, model downloads are user-borne — not “software fees” |
| Honesty | Never invent Cursor-beating scores; publish measurements or mark **unknown** |

**Winning strategy under constraints:**

1. **Shell parity** — Ship a branded VS Code-class workbench (explorer, editor, terminal, SCM, search). Users should not feel “downgraded” from Cursor’s chrome.
2. **System superiority** — Deterministic-first retrieve → patch → verify → review loops; tight context; reviewable apply; quota discipline. Waste fewer tokens than cloud agents.
3. **Local model fitness** — Fit weights to measured RAM; prefer models that win *our* codingbench, not marketing parameter counts.
4. **Offline core** — Editing, tests, and deterministic automation never require AI.
5. **Evidence iteration** — Expand held-out tasks; ablate features that don’t raise success rate; only then claim parity on those tasks.

Cursor/Claude Code remain **unknown** competitors until a side-by-side is run. The goal is to make that comparison *winnable* on free local stack — then publish it.

## Product shape (locked)

- **Shell:** Branded FreeForge workbench forked from pinned `microsoft/vscode` (Void = UX reference only; do not vendor Void internals).
- **Inference:** Mode B — loopback Ollama / llama.cpp; pause when unavailable.
- **Brain:** MAINFRAME Python agent (`editor`, `codingloop`, `retrieve`, `patching`, `verify`, `review`, `quota`, `eligibility`).

## Status of the goal

| Milestone | Status |
|-----------|--------|
| CLI automation + free-only gates | Measured (existing accepts) |
| Thin editor bridge | Partial (not IDE) |
| Branded workbench bootstrap | In progress (`workbench/`) |
| Mode B local model on this host | Blocked until Ollama installed + fitted pull |
| Live codingbench vs Cursor/Claude | **unknown** |
| Goal: match/exceed on measured suites | **not yet achieved** — active north star |

## How to read progress

- `python -m mainframe workbench status|accept`
- `python -m mainframe doctor` — model fit recommendations
- `python -m mainframe recommend accept` — mode recommendation
- `docs/eval/ide/` — IDE-specific evidence (grows with increments)

When live model quality is measured and meets or beats a published Cursor/Claude baseline on the same held-out suite, update this document with dates and numbers. Until then: **unknown**, not claimed.
