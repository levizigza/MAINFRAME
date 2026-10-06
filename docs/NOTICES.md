# Third-party notices — FreeForge / MAINFRAME integration

This file records upstream projects FreeForge references or pins. It does not
claim those projects are vendored into this tree unless a path is listed.

## openclaw/openclaw

- Pin: v2026.9.6 / commit `eb377ac59e6c9fd6c7705028034812becf00271b`
- License: MIT (Copyright (c) 2026 OpenClaw Foundation) — see upstream `LICENSE`
- Upstream also ships `THIRD_PARTY_NOTICES.md`; retain that file if OpenClaw
  source is copied into this repository.
- Docs consulted: https://docs.openclaw.ai/

## voideditor/void

- Pin: commit `b3166e7ef2aefbdfeb139445fdf248a561b85d4d` (repository archived)
- License: Apache License 2.0 — upstream `LICENSE.txt`
  (appendix notice: Copyright 2025 Glass Devtools, Inc.)
- Status: deprecated; reference source only — not a FreeForge runtime dependency.
- Inherited VS Code tree: microsoft/vscode is MIT-licensed with extensive third-party
  notices; a full fork must retain those notices. FreeForge does **not** vendor
  Void workbench services; see `docs/VOID_EVAL.md` and `docs/VOID_FORK_PLAN.md`.
- Evaluation date: 2026-10-06 (guide + LICENSE + README at pin).

## public-apis/public-apis

- Pin: commit `8939d468fa4580039c4e22cc4998eb3fef8130d1`
- License: MIT (Copyright (c) 2022 public-apis) — retained at
  `docs/freeforge/public-apis-snapshot/LICENSE`
- Local snapshot: `docs/freeforge/public-apis-snapshot/` (README.pinned.md + catalog.json)
- Source links recorded in `MANIFEST.json`
- Used for discovery catalog metadata only; individual APIs have their own API terms
  and returned-data licenses (distinct from the catalog MIT license)
- Advertisements / commercial listings in the upstream README confer **no** entitlement
- FreeForge does **not** execute linked code, install listed MCP servers, or mark
  every catalog entry free automatically

## Playwright

- Browser automation library used by FreeForge probes when installed locally.
- License: Apache-2.0 (Microsoft Playwright) — follow package license when
  depending on it; FreeForge core CLI still runs if Playwright is absent
  (probe pauses).

## SQLite

- FreeForge-owned records use Python's stdlib `sqlite3` (PSF) against a local
  file under `.mainframe/`. Not the same database as OpenClaw's Gateway SQLite.
