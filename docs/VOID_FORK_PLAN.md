# Optional Void / VS Code full-fork plan

This plan is **optional**. FreeForge’s default editor path is a maintained extension + shared CLI task state (`docs/VOID_EVAL.md`).

A full fork of Void (or vscode) is only justified when Extension API limits block required UX. If pursued, treat it as a separate product track.

## Concrete requirements before forking

### 1. Upstream update strategy

- Track microsoft/vscode release tags on a schedule (e.g. monthly).
- Rebase or merge Void-derived patches as a thin overlay under `src/vs/workbench/contrib/freeforge/` — never silent multi-month drift.
- Pin Electron / Node versions to vscode’s published dependency set for that tag.
- Document every conflict class (build tooling, CSP, React mount) and an owner.

### 2. Security

- Inherit vscode security advisories; subscribe to GHSA for Electron and vscode.
- No auto-update channel that ships unsigned binaries.
- Secrets stay in FreeForge `LocalSecretFacility` — never in fork settings JSON exported to chat.
- Renderer CSP: LLM traffic only via main-process IPC (Void pattern) or Extension Host — not ad-hoc `fetch` from untrusted webviews without review.

### 3. Build

- Use a public build pipeline (Void’s void-builder is a reference, not a dependency).
- Reproducible builds: lockfiles, pinned toolchains, SBOM.
- CI must build Windows (primary MAINFRAME target) without paid cloud GPU / hosted secrets.

### 4. Distribution

- Optional install path only; CORE CLI must work without the fork.
- License bundle: Apache-2.0 (Void-derived overlay) + MIT (vscode) + full ThirdPartyNotices.
- Auto-update is opt-in and fee-free; no telemetry SaaS.

### 5. Exit criteria to *not* fork

If chat-to-task, selection context, reviewable diffs, diagnostics, cancel/resume, and shared patch apply work via the Extension API + CLI (acceptance in `editor accept`), **do not fork**.
