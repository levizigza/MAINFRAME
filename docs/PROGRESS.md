# MAINFRAME progress log

Honest results only. Never invent successful tests or live account checks.

---

## 2026-09-29 — Increment 0.1.0: zero-cost local core

### Intent

Bootstrap MAINFRAME as an open-source coding/automation system with zero required fees; persist always-apply agent rules; ship a runnable stdlib CLI with deterministic automation and optional free AI that pauses when unavailable.

### Inspected

- Workspace was empty (no prior code, no git repo).
- Created `.cursor/rules/mainframe-core.mdc` (`alwaysApply: true`).

### Preserved

- No prior user work present.
- `.mainframe/user_notes.md` created as a preserved notes file for future increments.

### Implemented

- Stdlib package `mainframe/` with CLI: `status`, `inspect`, `tasks`, `run`, `ai probe|ask`, `accept`
- Deterministic tasks: `echo`, `list-tree`, `workspace-checksum`, `write-run-report`
- Free-only AI gateway (local Ollama probe); pause + preserve prompt when unavailable
- Docs: `README.md`, `docs/ARCHITECTURE.md`, MIT `LICENSE`
- Fixed recursion bug in `ensure_state` ↔ `save_config` discovered during first accept run

### Acceptance (observed)

Commands run from repo root with `python -m mainframe ...`:

| Check | Result | Notes |
|-------|--------|-------|
| `status` | PASS exit 0 | Cost posture all free/required=false |
| `inspect` | PASS exit 0 | Found `mainframe-core.mdc` + package modules |
| `run echo --param message=hello` | PASS exit 0 | `{"message":"hello"}` |
| `ai probe` | PASS exit 0 | **status=`paused`** — no listener at `127.0.0.1:11434` (timed out). Not claimed available. |
| `ai ask "ping"` | PASS exit 0 | `paused: true`, prompt preserved, no paid fallback |
| `accept` | PASS exit 0 | **6/6 checks passed**, `ok: true` |

Checksum from accept suite: `sha256=2b4e5deec4b87659e853ba38c5a308e910cfc076367c13a9d72feacee599d9ea` (11 files at time of check; before this PROGRESS entry).

### Blockers

- Free local inference unavailable on this machine right now (Ollama not responding). Deterministic automation remains usable; AI steps correctly paused.

### Next increments (suggested)

- Coding helpers that stay deterministic (diff/summarize files without LLM)
- Optional Ollama wiring only when user installs it locally (still free)
- Git init / publish when user asks

---

## 2026-09-29 — Increment 0.1.1: strict free-only audit & eligibility gate

### Intent

Audit the project against the strict free-only contract; publish a dependency/migration table; disable nonqualifying routes in code (not merely hide settings); retain the working Ollama adapter behind a gate; keep automation/inspect/accept.

### Inspected

- Full tree: stdlib CLI + local Ollama probe only; no pip deps; no cloud SDKs found in code.
- Gap: `ollama_base_url` could point off-loopback (hosted/remote loophole); no explicit disabled-provider catalog; cost posture lacked hosted/analytics/search/storage flags.

### Preserved

- `.mainframe/user_notes.md`, run logs, prior automation tasks, workspace inspect, accept suite (extended).
- Ollama probe/generate logic retained as `mainframe/ai/ollama_adapter.py`.

### Implemented

- `mainframe/eligibility.py` — eligible vs disabled catalog + loopback gate (fail closed)
- `mainframe/ai/rejected.py` — disabled routes hard-refuse (`fallback_used: false`)
- Config load strips credentials, forces free-only flags, rejects non-loopback URLs / non-eligible providers
- CLI: `audit`, `ai refuse <id>`; accept checks expanded to 10
- Docs: `docs/DEPENDENCIES.md`; rules/architecture/README updated

### Removed / disabled (not hidden)

- All listed hosted LLM, cloud DB, remote exec, analytics, hosted search, cloud storage routes — **never present as callable success paths**; now explicitly refuse.
- Automatic paid/trial/hosted fallbacks: **none** (policy + accept check).

### Acceptance (observed)

| Check | Result | Notes |
|-------|--------|-------|
| `status` | PASS exit 0 | `credentials_required: false`, version 0.1.1 |
| `audit` | PASS exit 0 | Dependency table emitted |
| `ai refuse openai_api` | PASS exit 0 | `refused: true`, `fallback_used: false` |
| `ai ask "offline check"` | PASS exit 0 | `paused: true` (Ollama timed out); no fallback |
| `accept` | PASS exit 0 | **10/10** checks; `ok: true` |

### Capability report

| Class | Items |
|-------|--------|
| **Works offline** | `status`, `inspect`, `tasks`, `run` (deterministic), `audit`, `ai refuse`, accept non-AI checks, local `.mainframe/` state |
| **Requires eligible free inference** | `ai ask` with loopback Ollama **and** an installed model — **unverified on this machine** (probe status=`paused`, timeout to `:11434`) |
| **Removed / never shipping as routes** | OpenAI/Anthropic/Azure/Gemini/Bedrock/Groq/Together/Fireworks/Replicate/HF Inference API; cloud DBs; remote execution; analytics; hosted search; cloud object storage; required PyPI deps for core |
| **Unverified** | Actual Ollama completion success (no local server responding during this run) |

### Blockers

- Same as 0.1.0: free local inference not running here. Deterministic paths OK.

---

## 2026-09-29 — Increment 0.1.2: dated capability scorecard + eval baselines

### Intent

Build a dated scorecard from official Claude Code and Cursor docs; define measurable targets for three workloads; separate coverage / reasoning / E2E; mark unmeasured competitor cells; ship executable eval plans without purchasing access.

### Inspected

- Claude Code docs: overview, hooks, scheduled tasks, memory, MCP (code.claude.com)
- Cursor docs: hooks, automations, MCP, cloud agents (cursor.com/docs)
- Existing MAINFRAME automation/eligibility preserved

### Preserved

- Free-only gate, automation tasks, accept suite (extended), user notes

### Implemented

- `docs/SCORECARD-2026-09-29.md`
- Fixtures + runner: `docs/eval/`, `mainframe/scorecard.py`, CLI `scorecard`
- Canvas: capability scorecard (open beside chat)
- Accept checks 11–12 for scorecard doc + baseline run

### Acceptance (observed)

| Check | Result | Notes |
|-------|--------|-------|
| `scorecard --trials 5` | PASS exit 0 | W1/W2/W3 all meet targets; competitors **unmeasured** |
| W1 mean time | 0.0072s | reliability 5/5; bit-stable; interventions 0; privacy local_only |
| W2 mean time | 0.0037s | idempotent; reliability 5/5 |
| W3 mean time | 0.0012s | schema-valid; reliability 5/5 |
| `accept` | PASS exit 0 | includes dated scorecard + workload baseline checks |
| Layer B reasoning | unmeasured | no purchased model access |
| H4/H5/H6 | unsupported / unmeasured | as required |

Report: `.mainframe/runs/scorecard-20260929T165640Z.json`

### Claims discipline

- **Supported:** H1 core zero-credential launch; H2 deterministic bit-stability on these fixtures; H3 local-only privacy for deterministic paths
- **Unsupported:** universal superiority; unlimited frontier inference; schedules/memory/MCP as automatic advantages

---

## 2026-09-29 — Increment 0.1.3: FreeForge thin integration + coding-engine spike

### Intent

Inspect pinned OpenClaw / Void / public-apis; design FreeForge as thin integration; select one coding engine after spike without nesting loops; document extension points, ownership, licenses, notices, risks; reuse MAINFRAME capabilities; Playwright for browsers; SQLite for FreeForge records.

### Inspected (observed)

| Repo | Pin | License | Notes |
|------|-----|---------|-------|
| openclaw/openclaw | **v2026.9.6** / `eb377ac59e6c9fd6c7705028034812becf00271b` | MIT (+ THIRD_PARTY_NOTICES.md) | Gateway + automations + embedded agent; ACP OpenCode is separate harness |
| voideditor/void | `b3166e7ef2aefbdfeb139445fdf248a561b85d4d` | Apache-2.0 | **Archived / deprecated** — reference only |
| public-apis/public-apis | `8939d468fa4580039c4e22cc4998eb3fef8130d1` | MIT | Discovery catalog |

Local bins: `openclaw` absent, `opencode` absent, Playwright **available** (Chromium about:blank OK).

### Coding engine decision

- **Selected:** `openclaw_embedded_agent_runtime`
- **Rejected:** `opencode_acp_worker` (default path)
- **Nested loops:** refused
- Runtime status: `deferred_openclaw_not_installed` until Gateway CLI exists

### Implemented

- `docs/FREEFORGE.md`, `docs/NOTICES.md`, `docs/freeforge/PINS.json`
- `mainframe/freeforge.py` + CLI `freeforge status|spike|discover`
- FreeForge SQLite `.mainframe/freeforge.sqlite` (separate from OpenClaw)

### Acceptance (observed)

| Check | Result |
|-------|--------|
| `freeforge spike` | PASS exit 0 |
| `freeforge discover --query weather` | PASS; 5 hits at pinned README; no auto paid enable |
| `accept` | PASS (includes `freeforge_pins_and_engine`) |
| Playwright probe | **available** |
| OpenClaw coding runtime | **deferred** (CLI not installed) — not invented as live |

### Preserved / reused

Eligibility gate, automation, scorecard W1–W3, accept/audit — not rebuilt.

---

## 2026-09-29 — Increment 0.1.4: Windows doctor

### Intent

Implement `doctor` for the user's Windows PC: measure RAM/CPU/disk/runtimes/Git/rg/shell/browsers; set resource limits; estimate model fit then verify against measurements; report startup/sleep/offline limits; no Docker Desktop requirement; no secrets/downloads/startup mutations/unmeasured perf claims.

### Implemented

- `mainframe/doctor.py`, CLI `python -m mainframe doctor`, `docs/DOCTOR.md`
- Host-context detection: container/codespace markers revoke `trust_hardware_as_user_pc`; `CURSOR_AGENT` alone does not (agent on user PC)
- Limits for indexing / browser workers / tests / optional CPU inference
- Model catalog fit = weights + KV estimate + overhead; recommend only if measured available + budget clear; `tokens_per_sec: unmeasured`

### Acceptance (observed)

| Check | Result |
|-------|--------|
| `doctor` | PASS exit 0 — `native_windows`, trust=true |
| RAM | total **31.69 GiB**, available ~12 GiB (Win32_OperatingSystem) |
| CPU | i7-12700H, 14 cores / 20 logical |
| Disk | ~108 GiB free on workspace volume |
| Tools | Python 3.12.4, Node v22.12.0, Git 2.47.1, rg present; Docker absent (not required) |
| Playwright | available |
| Flags | secrets_exposed/models_downloaded/startup_tasks_enabled/performance_benchmarks_claimed all **false** |
| `accept` | PASS **14/14** including `doctor_windows_env` |

Background: startup tasks not enabled; sleep suspends local Gateway jobs; offline deterministic paths OK.

---

## 2026-09-29 — Increment 0.1.5: FreeForge TypeScript CLI + OpenClaw adapter

### Intent

Bootstrap minimal TS CLI with doctor/run/workflows/status/resume/eval; versioned SQLite; OpenClaw adapter isolated for pin v2026.9.6; loopback+auth; no paid defaults / background models / outbound delivery; never modify OpenClaw private DB.

### Implemented

- `freeforge-cli/` — Node ≥22.12, pinned `commander@12.1.0`, `sql.js@1.12.0`, `typescript@5.7.2`, `tsx@4.19.2`
- Version-specific code: `src/openclaw/v2026_9_6/`
- Tables: `task_contracts`, `workflow_steps`, `artifacts`, `effect_receipts` (+ migrations)
- Loopback status server with bearer token file (not printed in logs)

### Acceptance (observed)

`npm run accept` in `freeforge-cli` → **5/5 PASS**:

| Check | Result |
|-------|--------|
| Launch without paid credentials | PASS |
| Local command via adapter | PASS (`task_8e2a0e3a4b1857ce`) |
| Status after restart | PASS (`recovered_from_sqlite`) |
| Resume after restart | PASS |
| Unsupported command | PASS exit 2 + `unsupported: true` |

OpenClaw private DB modified: **false** on all paths.

---

## 2026-09-29 — Increment 0.1.6: central capability & cost gate

### Intent

Central gate for inference/connectors/search/storage/remote execution/tools/auxiliary; local zero-fee eligible; external needs verified free entitlement; deny trials/promos/unknown pricing/overages/aliases/fake paid endpoints; no silent spend switch; scrub credentials from child env.

### Implemented

- `mainframe/cost_gate.py` + CLI `python -m mainframe gate`
- Wired into AI dispatch (`run_ai_step`) and FreeForge TS adapter (`costGate.ts` + scrubbed child env)
- Docs: `docs/COST_GATE.md`; entitlements file `.mainframe/entitlements.json` (empty by default)

### Acceptance (observed)

| Suite | Result |
|-------|--------|
| `python -m mainframe gate` | **10/10** — paid endpoint, chargeable tool, expired evidence, model alias, $0 token price, nested alias, spend switch ignored, cred scrub |
| `python -m mainframe accept` | **15/15** including `cost_gate_blocks_before_dispatch` |
| `freeforge-cli npm run accept` | **6/6** including `cost_gate_self_test` |

No runtime switch enables spending (`ENABLE_SPENDING` → deny).

---

## 2026-09-29 — Increment 0.1.7: offline demos + mock issue→patch

### Intent

Three labeled non-AI deterministic demos (repo inspect/test, records→report, local browser); mock-inference repair via shared broker with real FS/tests; offline network; failure/cancel/AI-pause paths.

### Acceptance (observed)

`python -m mainframe demo` → **8/8**:

| Check | Result |
|-------|--------|
| Deterministic repo inspect+test | PASS (`non_ai_deterministic`) |
| Deterministic records→report | PASS |
| Deterministic local browser click | PASS (`Clicked offline`) |
| Mock repair failing→passing | PASS (`False → True`) |
| Failure path (bad patch) | PASS |
| Cancellation path | PASS (no file written) |
| AI pause without model | PASS (`paused_no_model`, prompt preserved) |
| External network disabled | PASS |

`accept` includes `offline_demos_and_mock_repair` — **16/16** PASS.

---

## 2026-09-29 — Increment 0.1.8: repository inventory (Git/rg/FS)

### Intent

Deterministic repository inventory: packages, languages, source roots, entry points, tests, generated files, dependencies, build config. Store content hashes + provenance (not full-repo prompt dumps). Respect ignore/privacy; handle untracked, monorepos, Windows path casing, symlinks, change-during-scan. Incremental updates; bounded overview + file-range tools. No embedding service or model request.

### Implemented

- `mainframe/inventory/` — `ignore`, `store` (SQLite), `detect`, `scan`, `tools`, `accept`
- CLI: `python -m mainframe inventory scan|overview|file-range|accept`
- Fixture: `docs/inventory/fixtures/sample_repo` + `expected_inventory.json`

### Acceptance (observed)

`python -m mainframe inventory accept` → **28/28**:

| Check | Result |
|-------|--------|
| Fixture vs expected (packages/roots/entries/tests/deps/build) | PASS |
| Privacy exclusions (`.env`, `secrets.json`; file-range denied) | PASS |
| Ignored paths absent (`build/`, `noise.bin`) | PASS |
| Bounded overview + file-range (max 80 lines) | PASS |
| One-file edit work | PASS (`hashed=1`, `reused=12`) |
| No embedding / model request | PASS |
| Windows path casefold | PASS |

`python -m mainframe accept` includes `repository_inventory` — **17/17** PASS.

---

## 2026-09-29 — Increment 0.1.9: local issue→code retrieval

### Intent

Retrieve code for issues via exact identifiers, filenames, stack traces, error messages, imports, and lexical ranking. Optional SQLite FTS5 only when measured helpful. Explainable signals, deduped ranges with surrounding context, goal preserved beside search terms, follow-up searches, explicit `no_relevant_evidence`. No remote vector DB or paid embeddings.

### Implemented

- `mainframe/retrieval/` — parse, rank, index (FTS5), retrieve, accept
- CLI: `python -m mainframe retrieve search|accept`
- Fixtures: misleading names, bug outside stack, exact id, follow-up, no-evidence
- Eligibility: `remote_vector_db` / `paid_embedding_api` disabled; local FTS5 eligible

### Acceptance (observed)

`python -m mainframe retrieve accept` → **8/8**:

| Metric | Result |
|--------|--------|
| Mean relevant-file recall | **1.0** |
| Mean context chars | **673** |
| Misleading names (`auth_bug.py` not first; `payments/processor.py` hit) | PASS |
| Bug outside stack (`lib/calc.py` via import+error; not inventing handler-only) | PASS |
| `no_relevant_evidence` for unrelated K8s issue | PASS |
| FTS5 ablation | Same recall/context → **FTS5 disabled** (no measured improvement) |
| Misses manufactured | None (`misses: []` when recall 1.0) |
| Remote vector / paid embedding | **false** |

`accept` check `issue_to_code_retrieval` — full suite **18/18** PASS.

---

## 2026-09-29 — Increment 0.1.10: local codeintel (AST + optional Jedi/Pyright)

### Intent

Integrate maintained language tools/parsers for definitions, references, diagnostics, signatures, imports, and symbol lookup (Python first). Resolve dependency APIs against installed versions. Label `language_server_fact` vs `parser_approximate` vs `installed_api_fact`; never emit model hypotheses. Lexical/AST fallback with limitation when Jedi/Pyright missing. Attach path/range/content version. Narrow tools for callers/signature/reject-call. No model service.

### Implemented

- `mainframe/codeintel/` — provenance, versions, python_ast, python_jedi, python_pyright, deps, tools, accept
- CLI: `python -m mainframe codeintel status|lookup|callers|signature|definition|imports|diagnostics|deps|reject-call|accept`
- Fixture: `docs/codeintel/fixtures/dup_callers` (duplicate `process`, vendor_dep)

### Acceptance (observed)

`python -m mainframe codeintel accept` → **12/12**:

| Check | Result |
|-------|--------|
| Duplicate `process` in `alpha.util` / `beta.util` disambiguated | PASS |
| Callers: `alpha_process` → alpha only; bare `process` → beta only | PASS |
| Reject `vendor_dep.missing_api` / `json.loads_everything_secretly` | PASS |
| Accept `vendor_dep.real_api` / `json.loads` | PASS |
| Content versions (sha256) on ranges | PASS |
| Evidence kinds include `parser_approximate`; no `model_hypothesis` | PASS |
| `model_service_used` | **false** |

Adapters observed on this machine: stdlib_ast=true, jedi=true, pyright=true (optional; not required).

`accept` check `codeintel_symbols_callers_deps` — full suite **19/19** PASS.

---

## 2026-09-29 — Increment 0.1.11: dependency/test map + verify plan

### Intent

Lightweight map from imports, package boundaries, build files, and observed test runs. Select affected modules and verification commands. Represent uncertainty (dynamic imports, reflection, generated code, external services); incomplete maps widen the plan. Cache by file/config hashes. No separate graph service.

### Implemented

- `mainframe/depmap/` — build, uncertainty, cache (SQLite), plan, accept
- CLI: `python -m mainframe depmap build|plan|accept`
- Fixture: `docs/depmap/fixtures/cross_pkg`

### Acceptance (observed)

`python -m mainframe depmap accept` → **6/6**:

| Check | Result |
|-------|--------|
| Cross-package `pkg_core/widget.py` → `tests/test_pkg_app.py` + direct compile | PASS |
| Dynamic `import_module(name)` remains `unresolved` | PASS |
| Incomplete map widens to `pytest -q` | PASS |
| Cache hit by config/content hashes | PASS |
| Graph service / model | **false** |

`accept` check `dependency_test_map` — full suite **20/20** PASS.

---

## 2026-09-29 — Increment 0.1.12: task contracts

### Intent

Contracts with desired behavior, scope, constraints, invariants, acceptance checks, permitted side effects, unresolved questions. Kinds: explanation, repair, feature, refactor, UI, automation. Deterministic classification; model polish only on an already-needed turn. Ask only when missing info changes correctness/authorization; else assume and continue. Known workflows use I/O schemas + executable assertions; NL intent retained.

### Implemented

- `mainframe/contracts/` — types, classify, ask, workflows, schema, assertions, build, accept
- CLI: `python -m mainframe contract build|start|accept`

### Acceptance (observed)

`python -m mainframe contract accept` → **7/7**:

| Check | Result |
|-------|--------|
| Refactor contract + preserve interface (ok vs signature break) | PASS |
| Ambiguous "make it better" → exactly one focused question | PASS |
| Routine `workspace checksum` starts without clarification | PASS |
| No separate model label call | PASS |
| NL intent retained | PASS |

`accept` check `task_contracts` — full suite **21/21** PASS.

---

## 2026-09-29 — Increment 0.1.13: progressive context assembly

### Intent

Assemble progressive context (task contract, repo overview, symbols, exact ranges, diagnostics). Reserve budget for output, reasoning, tool-protocol. Rank by relevance/novelty; preserve signatures, invariants, source pointers; never silently drop critical evidence — request focused additional reads instead. Prefer installed types; cache attributed excerpts; fetched text untrusted. Report estimated and actual tokens when inference available.

### Implemented

- `mainframe/context/` — budget, tokens, rank, gather, docs_cache, assemble, accept
- CLI: `python -m mainframe context assemble|accept`
- Fixture: `docs/context/fixtures/constrained_fix`

### Acceptance (observed)

`python -m mainframe context accept` → **8/8**:

| Check | Result |
|-------|--------|
| Retains compute_total signature + AssertionError + buggy.py + contract | PASS |
| Omits irrelevant_*.py | PASS |
| Omits repeated TRACE spam | PASS |
| `silently_dropped_critical=false` | PASS |
| Estimated tokens reported; actual honest when inference paused | PASS |
| Installed types trusted; fetched marked untrusted | PASS |
| Budget reserves output/reasoning/tools | PASS |

`accept` check `progressive_context` — full suite **22/22** PASS.

---

## 2026-09-29 — Increment 0.1.14: local project memory

### Intent

Local memory for confirmed build commands, module responsibilities, accepted solutions, and failure patterns — with source refs, content hashes, dates, scope, verification status. Separate user instructions / observations / hypotheses / external text / generated summaries. Summaries never override the user. Revalidate when support files change. Project-isolated retrieve. No secrets or full conversations by default. No hosted storage or model training.

### Implemented

- `mainframe/memory/` — trust, filter, store, accept
- CLI: `python -m mainframe memory remember|retrieve|revalidate|reject|accept`
- Store: `.mainframe/memory/project_memory.sqlite`

### Acceptance (observed)

`python -m mainframe memory accept` → **10/10**:

| Check | Result |
|-------|--------|
| Reuse verified `pytest` command on second task | PASS |
| Invalidate after `pyproject.toml` change | PASS |
| Projects isolated | PASS |
| Rejected patch not trusted | PASS |
| Injected repo instruction ≠ user authority | PASS |
| Generated summary no authority | PASS |
| Secrets / full conversations refused | PASS |
| No hosted storage / training | PASS |

`accept` check `project_memory` — full suite **23/23** PASS.

---

## 2026-09-29 — Increment 0.1.15: typed tool registry

### Intent

Typed registry for search, file ranges, symbols, diagnostics, patching, tests, diffs — each with purpose, validated args, permission, timeout, structured result. Preserve call IDs; reject incomplete streaming args; specific errors; one bounded correction. Optional MCP via same registry with schema fingerprints and fee/permission re-eval. Task-relevant exposure only.

### Implemented

- `mainframe/tools/` — types, validate, audit, impl, registry, mcp_bridge, invoke, accept
- CLI: `python -m mainframe tools list|invoke|accept`

### Acceptance (observed)

`python -m mainframe tools accept` → **12/12**:

| Check | Result |
|-------|--------|
| Unknown tool / invented params / malformed JSON / incomplete stream | no side effects |
| Duplicate call_id | no side effects |
| Valid `file_range` + `patch` | intended impl + audit |
| Stale hash patch refused | PASS |
| One bounded str→int correction | PASS |
| Task filter hides `patch` from explanation | PASS |
| MCP fingerprint change + paid endpoint unavailable | PASS |

`accept` check `typed_tool_registry` — full suite **24/24** PASS.

---

## 2026-09-29 — Increment 0.1.16: precise patch application

### Intent

Hash-bound, scoped, preconditioned patches with reviewable diffs; validate batches before write; journal recovery without claiming FS multi-file atomicity. Preserve CRLF/encoding/mode; reject ambiguous and stale patches; detect post-inspection edits; selective rollback of agent-owned edits only — never reset the whole tree.

### Implemented

- `mainframe/patching/` — io_preserve, snapshot, validate, journal, apply, accept
- CLI: `python -m mainframe patch snapshot|apply|rollback|accept`

### Acceptance (observed)

`python -m mainframe patch accept` → **7/7**:

| Check | Result |
|-------|--------|
| Duplicate blocks → ambiguous reject | PASS |
| Unicode + UTF-8 BOM + CRLF preserved | PASS |
| Concurrent user edit → stale reject | PASS |
| Interrupted multi-file write + journal recover | PASS |
| Unrelated user changes kept | PASS |
| Selective rollback; no full tree reset; `filesystem_atomicity_claimed=false` | PASS |

`accept` check `precise_patching` — full suite **25/25** PASS.

---

## 2026-09-29 — Increment 0.1.17: verify / repair evaluation

### Intent

Reproduce failures before repair where practical; run targeted tests, type checks, risk-based regression. Distinguish product defects from missing deps / unavailable services / flaky / environment failures. Bind results to exact code+environment. Derive edge cases from the task contract. Keep evaluator-owned checks outside the editable workspace. Detect weakened assertions/deleted tests unless traced to the user spec. Invalidate verification when relevant code changes.

### Implemented

- `mainframe/verify/` — taxonomy, binding, integrity, edge_cases, runner, pipeline, accept
- CLI: `python -m mainframe verify reproduce|run|accept`

### Acceptance (observed)

`python -m mainframe verify accept` → **7/7**:

| Check | Result |
|-------|--------|
| Preexisting failure identified before repair | PASS |
| Example-only patch fails contract edge cases | PASS |
| Evaluator tests outside editable workspace | PASS |
| Weakened asserts blocked without spec; allowed with spec | PASS |
| Good fix passes; binding invalidated after code change | PASS |

## 2026-09-29 — Increment 0.1.18: optional local-model adapter

### Intent

Optional local-model adapter via OpenClaw-documented Ollama native `/api/chat` (not `/v1`) or llama.cpp on loopback. Verify protocol, chat template, tools, license. Local-only config — refuse `:cloud` / `ollama.com`. Doctor RAM fit selects a small candidate; downloads explicit. Bench extraction/tool-use/coding with latency + client RSS. CPU fit ≠ coding quality. No-local-model mode fully supported; no frontier parity claims.

### Implemented

- `mainframe/local_model/` — catalog, cloud_guard, ollama_native, llamacpp, protocol, select, download, bench, status, accept
- CLI: `python -m mainframe local-model status|select|protocol|download-plan|pull|bench|accept`
- `ollama_adapter` now uses native `/api/chat` and excludes cloud models
- Eligibility: `llamacpp_local` added; `docs/DEPENDENCIES.md` updated

### Acceptance (observed)

`python -m mainframe local-model accept` → **9/9**:

| Check | Result |
|-------|--------|
| Reject `:cloud` model + `ollama.com` host | PASS |
| Native chat route `/api/chat` (not `/v1`) | PASS |
| Doctor select + explicit download (no auto) | PASS |
| Live status visible when unavailable | PASS (`unavailable`) |
| No-local-model deterministic mode | PASS |
| Offline loopback mock: template/license/chat; cloud filtered | PASS |
| Bench extraction/tool-use/coding with latency (mock) | PASS |
| Protocol verify honest (no frontier claim) | PASS |
| Accept clause offline-or-unavailable | PASS |

Live Ollama/llama.cpp: **unavailable** on this machine (probe timeout). Feature visibly unavailable; deterministic paths OK. No frontier parity claimed.

`python -m mainframe accept` → **27/27** (includes `local_model_adapter`).

## 2026-09-29 — Increment 0.1.19: hosted provider adapters (investigated)

### Intent

Adapters only for verified recurring free API access. Investigate Groq, Gemini, Mistral as candidates (not preapproved). Check eligibility, intended use, data handling, model IDs, quotas, billing. Disable unverifiable. Preserve native roles, tools, streaming, cancellation, usage. Credentials in broker; no paid fallback. Exhaustion pauses without billing.

### Investigation (observed)

| Candidate | Verdict |
|-----------|---------|
| Groq | **disabled** — upgrade path + published prices; recurring free unverifiable |
| Gemini | **disabled** — unpaid data terms + billing unlocks Paid Tier |
| Mistral | **disabled** — Free mode → pay-as-you-go / tier upgrades |

### Implemented

- `mainframe/providers/` — investigation, broker, exhaust, groq/gemini/mistral adapters, dispatch, accept
- Native translators (Gemini `contents`/`model` roles ≠ OpenAI)
- CLI: `providers investigate|list|fixture|live|accept`
- `docs/PROVIDERS.md`; eligibility + DEPENDENCIES updated; `.mainframe/credentials/` gitignored

### Acceptance (observed)

`python -m mainframe providers accept` → **9/9** (fixtures; live labeled `unverified_live`; exhaustion pauses with `billing_activated=false`).

`python -m mainframe accept` → **28/28** (includes `hosted_provider_adapters`). No live hosted calls claimed.

## 2026-09-29 — Increment 0.1.20: quota-aware admission control

### Intent

Admit on requests/tokens/context/concurrency/reset windows. Reserve estimated usage before dispatch; reconcile actual (tool/reasoning overhead). Handle 429/Retry-After/timeouts/cancel/unknown conservatively. Persist reservations across restart. Interactive ahead of background without starvation. No identity rotation to evade limits; more providers ≠ unlimited.

### Implemented

- `mainframe/quota/` — ledger (SQLite), admit, retry, schedule, identity, accept
- CLI: `python -m mainframe quota status|admit|reconcile|release|accept`
- Denials include reason + `retry_after_s` or explicit `reset_unknown`

### Acceptance (observed)

`python -m mainframe quota accept` → **11/11** (simultaneous no overspend; 429 cooldown; cancel release; persist; priority; no rotation).

`python -m mainframe accept` → **29/29** (includes `quota_admission`).

## 2026-09-29 — Increment 0.1.21: model eval set + measured routing

### Intent

Small eval set for code repair, tool selection, structured extraction, planning, optional vision. Hold out from tuning. Measure correctness, latency, invalid tools, retries, quota. Eligible/available models only; record version/provider/context/date. Local measurements ≠ published claims. Capability matrix; best measured model per class within budget; interpretable reversible routes. Model fingerprint change invalidates stale rankings.

### Implemented

- `docs/eval/model_tasks/catalog.json` — tune/holdout tasks
- `mainframe/modeleval/` — catalog, metrics, runners, matrix, routing, accept
- CLI: `python -m mainframe modeleval models|run|route|accept`

### Acceptance (observed)

`python -m mainframe modeleval accept` → **9/9** (holdout disjoint; measured routing beats marketing-size label; unknowns stay unknown; FP invalidates).

`python -m mainframe accept` → **30/30** (includes `model_eval_routing`).

## 2026-09-29 — Increment 0.1.22: adaptive task controller

### Intent

Adaptive controller: deterministic tools for known ops, direct model for bounded tasks, plan/review for ambiguous or high-impact work. Escalate on observable evidence (failed verification, unresolved deps, conflicts, repeated invalid actions) — not confidence alone. Explicit turn/token/tool/time budgets. Concise journal (hypotheses/decisions/evidence); no CoT required. Stop on accept or unavailable info/capacity; no-progress yields a useful checkpoint.

### Implemented

- `mainframe/controller/` — classify, escalate, loop, types, accept
- CLI: `python -m mainframe controller run|accept`

### Acceptance (observed)

`python -m mainframe controller accept` → **9/9**.

`python -m mainframe accept` → **31/31** (includes `adaptive_controller`).

## 2026-09-29 — Increment 0.1.23: coding loop lifecycle

### Intent

Connect contracts, retrieval, tools, patches, and verification into one coding loop: reproduce → investigate → propose → apply → check → report. Reuse the selected engine lifecycle (`openclaw_embedded_agent_runtime`) — not a nested independent supervisor. On failure attach diagnostics and update the hypothesis. Detect repeated patches, oscillation, and irrelevant file churn. Checkpoint before risky apply; preserve user-protected paths. Report actual diffs/checks; never describe a proposal as implemented/verified.

### Implemented

- `mainframe/codingloop/` — lifecycle, churn, loop, accept
- Fixtures: `docs/codingloop/fixtures/{multi_repair,impossible}/`
- CLI: `python -m mainframe codingloop run|accept`

### Acceptance (observed)

`python -m mainframe codingloop accept` → **5/5** (multi-file e2e, impossible stop, resume, interrupt-before-apply honesty, engine binding).

`python -m mainframe accept` → **32/32** (includes `coding_loop`).

## 2026-09-29 — Increment 0.1.24: gated change review

### Intent

Review changes only when measured benefit justifies another model call. Always run deterministic checks first. Give the reviewer the task contract, diff, relevant context, and results; ask for specific counterexamples and unsupported assumptions. Keep review separate from patch generation; acknowledge shared blind spots when the same model/lineage authors both. For unresolved high-value failures, allow one bounded alternative in an isolated worktree. Rank by evaluator-owned acceptance checks and human requirements — not majority vote. Do not spawn a swarm for every task. Disable routes whose extra quota use produced no measurable improvement.

### Implemented

- `mainframe/review/` — routes, gate, deterministic, packet, reviewer, rank, alternative, pipeline, accept
- Fixture: `docs/review/fixtures/seeded_defect/`
- Disabled in code: `always_model_review`, `swarm_review`, `majority_vote_rank`
- CLI: `python -m mainframe review run|accept`

### Acceptance (observed)

`python -m mainframe review accept` → **9/9** (seeded defect + reproducible evidence; no-gain routes disabled; ranking ≠ majority; bounded alt worktree).

`python -m mainframe accept` → **33/33** (includes `change_review`).

## 2026-09-29 — Increment 0.1.25: exact-reuse caches

### Intent

Caches for repository scans, retrieval results, tool outputs, accepted workflow artifacts, and model responses where exact reuse is valid. Keys include content, environment, model, configuration, and permission versions. Exact caching is separate from approximate similarity. Never reuse stale authorization, external mutation, or time-sensitive answers as current. Redact secrets; isolate projects. Provider prompt caching only where officially supported; record observed benefits — do not assume it removes every quota charge. Prefer avoiding an unnecessary request entirely.

### Implemented

- `mainframe/cache/` — keys, redact, policy, store, invalidate, prompt_cache, runtime, facades, accept
- Fixture: `docs/cache/fixtures/readonly_task/`
- CLI: `python -m mainframe cache scan|retrieve|model|accept`

### Acceptance (observed)

`python -m mainframe cache accept` → **13/13** (repeated read-only less work + identical results; source/permission/freshness invalidate; auth refused; projects isolated).

`python -m mainframe accept` → **34/34** (includes `exact_reuse_cache`).

## 2026-09-29 — Increment 0.1.26: durable tasks

### Intent

Durable task transitions, checkpoints, operation IDs, leases, and effect receipts. Separate planned / started / succeeded / failed / cancelled / outcome-unknown. Reconcile FreeForge records with the selected engine through supported status APIs after restart or connection gaps — do not assume WebSocket replays missed events. Timeout after an external mutation triggers status reconciliation, not an automatic duplicate mutation. Use idempotency keys where supported; document where exactly-once cannot be guaranteed.

### Implemented

- `mainframe/durable/` — states, store, idempotency, engine_status, reconcile, runner, accept
- `docs/durable/EXACTLY_ONCE.md`
- CLI: `python -m mainframe durable plan|recover|accept`

### Acceptance (observed)

`python -m mainframe durable accept` → **9/9** (crash before dispatch / during execution / after effect before ack; recover without losing work or falsely denying side effects; timeout→reconcile not duplicate).

`python -m mainframe accept` → **35/35** (includes `durable_tasks`).

## 2026-09-29 — Increment 0.1.27: executable-tool boundaries

### Intent

Define executable-tool boundaries for filesystem paths, process spawning, environment variables, network access, CPU, memory, and elapsed time. Treat repository scripts, dependencies, and downloaded plugins as executable code. Use a zero-fee OS isolation mechanism (Windows Job Object) when available and verify enforcement on this host. A working directory, Git worktree, argument validator, or prompt is not a security sandbox. If reliable isolation is unavailable, restrict to trusted local workloads and disable unattended untrusted execution. Keep model credentials outside worker environments.

### Implemented

- `mainframe/boundaries/` — policy, paths, env, network, job_object, isolation, process, report, accept
- CLI: `python -m mainframe boundaries report|accept`

### Acceptance (observed)

`python -m mainframe boundaries accept` → **9/9** (path traversal + symlink escape denied; unauthorized network policy-denied; runaway timed out under Job Object; credentials scrubbed; Job Object verified on this Windows host).

Enforced: filesystem paths, env scrub, network policy, process spawn gates, elapsed time, CPU/memory via Job Object (verified).

Assumptions: OS network isolation and OS filesystem jail are **not** provided by Job Object alone.

`python -m mainframe accept` → **36/36** (includes `exec_boundaries`).

## 2026-09-29 — Increment 0.1.28: secrets + untrusted data

### Intent

Store credentials through an appropriate local secret facility (Windows DPAPI when available) and redact logs, traces, prompts, screenshots, and exports. Give each adapter only its required credential scope. Treat repository text, web pages, API responses, MCP descriptions, and imported workflows as untrusted data — their instructions cannot authorize new tools, destinations, purchases, or disclosure. Preserve provenance through retrieval and summaries. Validate URLs, redirects, payload sizes, and content types; protect against SSRF and unexpected local-network access in generic HTTP tools. Never auto-install code suggested by a retrieved page.

### Implemented

- `mainframe/secretdata/` — facility, scope, redact, untrusted, gate, http_guard, install_guard, accept
- Provider broker stores via DPAPI facility when available
- CLI: `python -m mainframe secretdata status|redact|accept`

### Acceptance (observed)

`python -m mainframe secretdata accept` → **7/7** (scoped DPAPI secrets; adapter scope; redaction surfaces; seeded injection cannot obtain secrets/change policy/trigger unauthorized actions; quoted install instructions remain data; SSRF/local/metadata/file blocked).

`python -m mainframe accept` → **37/37** (includes `secret_untrusted_data`).

## 2026-09-29 — Increment 0.1.29: scoped capabilities

### Intent

Bind grants to projects, destinations, allowed operations, and expiration for reading, editing, running tests, browsing, sending messages, publishing, and deletion. Carry forward existing user authorization so reversible in-scope local work does not re-prompt. Hold external or irreversible actions with a concrete preview. Expose revocation and emergency stop (cancels queued work). Connector/workflow edits must not silently expand authority; schedules alone grant no new permissions.

### Implemented

- `mainframe/capabilities/` — types, store, authorize, preview, runner, revoke, schedule_policy, connector, accept
- CLI: `python -m mainframe capabilities accept`

### Acceptance (observed)

`python -m mainframe capabilities accept` → **10/10** (scoped grants; carry-forward; local edit without re-prompt; authorized recurring report twice without prompts; new recipient and destructive deletion held with concrete preview; specific deny decision; schedule does not grant permissions; connector change does not silently expand; revoke + emergency stop blocks further auth).

`python -m mainframe accept` → **38/38** (includes `scoped_capabilities`).

## 2026-09-29 — Increment 0.1.30: Playwright browser tools + site maintenance demo

### Intent

Add Playwright tools for navigation, semantic locators, form filling, DOM inspection, screenshots, downloads, and assertions — preferring direct Playwright APIs and observable waits. DOM evidence first; visual interpretation only through eligible routes. Separate browser profiles per project; protect session credentials. Local website-maintenance demo detects a broken page, patches HTML via coding tools, verifies behavior/layout, holds unapproved external submissions, and preserves auth challenges for the user.

### Implemented

- `mainframe/browser/` — profiles, session, locators, waits, tools, auth, visual gate, submit guard, demo, accept
- Tool registry: `browser_navigate`, `browser_fill`, `browser_click`, `browser_dom`, `browser_screenshot`, `browser_download`, `browser_assert`, `browser_wait`
- Fixtures: `docs/demo/fixtures/site_maintenance/`
- CLI: `python -m mainframe browser status|demo|accept`

### Acceptance (observed)

`python -m mainframe browser accept` → **8/8** (tools registered; per-project profiles; external submit held; DOM-before-visual; modest layout v2 via `get_by_role`; maintenance demo missing control → patch → healthy; auth challenge paused; session tool smoke).

`python -m mainframe accept` → **39/39** (includes `playwright_browser_tools`).

## 2026-09-29 — Increment 0.1.31: held-out coding benchmark

### Intent

Reproducible held-out coding benchmark (logic, multi-file, dependency trap, UI, decline/clarify). Expected outcomes live outside agent workspaces. Compare **minimal** vs **FreeForge** harness with fixed budgets; record success, regressions, human interventions, latency, and model calls. Report all attempts/timeouts/unavailable providers; separate mock integration from live model quality.

### Implemented

- `docs/eval/coding_benchmark/` — catalog, fixtures, keys
- `mainframe/codingbench/` — workspace, verify, agents, harness, run, report, accept
- CLI: `python -m mainframe codingbench run|accept`

### Acceptance (observed)

`python -m mainframe codingbench accept` → **9/9** (holdout disjoint; keys outside workspace; mock vs live separated; fixture-strong holdout green; fixture-weak surfaces failures; raw JSON published; largest failure category prioritized; FreeForge vs minimal comparison; metrics recorded).

`python -m mainframe accept` → **40/40** (includes `coding_benchmark_holdout`).

## 2026-09-29 — Increment 0.1.32: versioned workflows

### Intent

Versioned workflow format with typed inputs/outputs, dependencies, conditions, bounded loops, retries, timeouts, permissions, and artifact references. Distinguish deterministic, AI, and human steps. Validate the graph before execution (invalid refs, unbounded cycles, incompatible schemas, unavailable capabilities, undeclared effects). Dry-run plan + local fixture runner. FreeForge owns workflow semantics and receipts; OpenClaw keeps scheduling/session management.

### Implemented

- `mainframe/workflows/` — schema, validate, plan, runner, handlers, receipts, load, accept
- Fixtures: `docs/eval/workflows/fixtures/input_to_report`, `input_to_report_with_ai`
- CLI: `python -m mainframe workflow validate|plan|run|accept`

### Acceptance (observed)

`python -m mainframe workflow accept` → **10/10** (versioned format; reject invalid refs/cycles/undeclared effects/unavailable AI; dry-run plan; offline input→report; AI step blocks with prior `report.json` unchanged; bounded loops; FreeForge ownership note).

`python -m mainframe accept` → **41/41** (includes `versioned_workflows`).

## 2026-09-29 — Increment 0.1.33: OpenClaw automation payloads ↔ FreeForge schedule

### Intent

Integrate OpenClaw's documented automation command payloads with the FreeForge workflow entry. Prefer exact `--command-argv` arrays over shell `--command` (especially on Windows). Verify installed CLI/schema when present. Keep **one scheduler owner** (`openclaw_gateway`). Deterministic jobs execute without an agent turn. Apply FreeForge permissions/cost policy to the command itself — not model-tool approvals. Handle timezone, DST, overlaps, missed runs, restart, and laptop sleep; document that the computer must be running.

### Implemented

- `mainframe/schedule/` — openclaw_payload, cli_probe, policy, timing, store, dispatcher, entry, report, instrument, accept
- FreeForge CLI ownership: `schedule: openclaw_gateway`
- CLI: `python -m mainframe schedule probe|add-report|fire|accept` and `automation-report`

### Acceptance (observed)

`python -m mainframe schedule accept` → **11/11** (argv preferred over shell; CLI probe deferred when absent; sole OpenClaw scheduler owner; schedule local report with `--command-argv` + `--no-deliver`; restart reloads job; fire writes receipt with `model_requests=0` and no outbound; receipt survives restart; sleep/missed + computer-must-run; TZ duration parse; overlap skip; not governed by model-tool approvals).

`python -m mainframe accept` → **42/42** (includes `openclaw_schedule_integration`).

## 2026-09-29 — Increment 0.1.34: event triggers (file/repo/webhook/poll)

### Intent

Add file-change, repository-change, local webhook, and bounded polling triggers through the chosen scheduler's supported interfaces. Normalize events (source, timestamp, dedupe key, permission scope). Debounce file storms, avoid self-retrigger, handle partial writes. Authenticate webhooks with signatures; reject replay/oversized payloads. No paid public tunnel; loopback is not claimed as public. When inbound internet is unavailable: eligible polling or manual trigger with explicit tradeoff. Events cannot select arbitrary commands — only pre-bound jobs.

### Implemented

- `mainframe/triggers/` — events, store, bindings, file_watch, repo_watch, webhook, poll, router, accept
- CLI: `python -m mainframe triggers accept`

### Acceptance (observed)

`python -m mainframe triggers accept` → **11/11** (fixed job binding; duplicate→one run; unrelated/self→none; partial held; auth cannot select command; webhook signature/replay/size; webhook fires bound job only; poll/manual tradeoff; typed event fields).

`python -m mainframe accept` → **43/43** (includes `event_triggers`).

## 2026-09-29 — Increment 0.1.35: workflow resilience (checkpoints / retries / effects)

### Intent

Step-level checkpoints, retry policies, cancellation, concurrency limits, and effect receipts in the workflow runner. Retry transient reads safely; reconcile uncertain writes before retry. Pass stable operation IDs through connectors. Separate execution success from delivery success. Compensation only when an operation has a real inverse (local draft delete ≠ message retract). Transactional local state and atomic file replacement; diagnostics without secrets.

### Acceptance criterion

Interrupt a multi-step workflow after an output is created; resume without duplicating it; retain a failed delivery for review; correctly report an external action whose final outcome is unknown.

### Implemented

- `mainframe/workflows/` — `atomic`, `effects`, `retry_policy`, `redact_diag`; expanded `receipts` (checkpoints, effect_index, cancel, concurrency); `handlers` (atomic write, deliver fail/unknown, delete_local_draft); `runner` (resume, interrupt, cancel, concurrency, op IDs, skip succeeded steps); `resilience_accept`
- Fixture: `docs/eval/workflows/fixtures/interrupt_resume_delivery`
- CLI: `python -m mainframe workflow accept-resilience`

### Acceptance (observed)

`python -m mainframe workflow accept-resilience` → **9/9** (interrupt after output; resume without duplicate; failed delivery retained with execution≠delivery; outcome_unknown; compensation inverse rules; stable op IDs; cancel; concurrency limit; redacted diagnostics).

`python -m mainframe workflow accept` → **10/10** (prior offline input→report still green).

`python -m mainframe accept` → **44/44** (includes `workflow_resilience`).

## 2026-09-29 — Increment 0.1.36: typed AI workflow steps

### Intent

Typed AI workflow steps for extraction, classification, summarization, and proposing code. Route through the same eligibility gate and interactive quota ledger as coding. Parsers/validated rules for known formats. Model output requires schema validation plus task-specific evidence checks (valid JSON ≠ factual correctness). Explicit uncertain results allowed. Cache stable inputs when reuse is valid. If inference is unavailable: checkpoint the AI step and continue only independent work. Deterministic fallback must not silently change promised meaning.

### Acceptance criterion

A mixed workflow finishes its non-AI steps offline, resumes the semantic step later, and rejects a plausible but unsupported extracted value.

### Implemented

- `mainframe/workflows/` — `parsers`, `evidence`, `ai_runtime`, `ai_accept`; handlers for extract/classify/summarize/propose_code; runner checkpoint + independent-work continue
- Fixture: `docs/eval/workflows/fixtures/mixed_ai_extract`
- CLI: `python -m mainframe workflow accept-ai`

### Acceptance (observed)

`python -m mainframe workflow accept-ai` → **9/9** (offline non-AI complete + AI checkpointed; resume extract; reject unsupported `9.9.9`; valid JSON ≠ factual; uncertain allowed; known-format parser; silent fallback refused; cache hit; interactive quota).

`python -m mainframe workflow accept` → **10/10** (prior offline still green).

`python -m mainframe accept` → **45/45** (includes `workflow_typed_ai_steps`).

## 2026-09-29 — Increment 0.1.37: public-apis pinned discovery + shortlist gates

### Intent

Import a pinned snapshot of public-apis/public-apis as discovery metadata, preserving license and source links. Do not execute linked code, install listed MCP servers, or mark every entry free automatically. For shortlisted services, record official docs, pricing evidence, auth, recurring quotas, intended-use restrictions, attribution, retention, availability, and last verification. Distinguish catalog license, API terms, and returned-data license. States: eligible / restricted / unverified / rejected. Unknown or expired evidence blocks activation. Ads and commercial listings confer no entitlement.

### Acceptance criterion

Demonstrate a genuinely eligible connector, a noncommercial-only service rejected for a commercial workflow, a trial-only rejection, and an unavailable service. Discovery must work locally without calling every listed endpoint.

### Implemented

- Snapshot: `docs/freeforge/public-apis-snapshot/` (LICENSE, README.pinned.md, MANIFEST.json, catalog.json, shortlist/*)
- `mainframe/discovery/` — local search, shortlist classify/activate, accept
- `freeforge discover` uses local snapshot (no network README fetch required)
- CLI: `python -m mainframe discovery status|search|shortlist|activate|accept`

### Acceptance (observed)

`python -m mainframe discovery accept` → **9/9** (license/source preserved; local discovery; eligible dog_ceo; NC rejected for commercial; trial rejected; unavailable; expired evidence blocks; ads no entitlement; license layers distinguished).

`python -m mainframe accept` → **46/46** (includes `public_apis_discovery`).

## 2026-09-29 — Increment 0.1.38: verified read-only API connectors

### Intent

Build connectors from verified official OpenAPI specs or documented endpoints. Typed inputs/outputs, auth handling, pagination, bounded retries, rate-limit behavior, caching hooks, structured errors. Expose only necessary read operations through the tool registry. Validate hostnames/redirects; never send credentials to model-chosen URLs. Start with three eligible read-only APIs + local fixtures. Do not fabricate live checks.

### OpenAPI gap (honest)

No published OpenAPI document was retrieved for the three chosen APIs at verification (`https://open-meteo.com/openapi` → 404). Connectors are built from **official documented endpoints** instead (`source_kind=documented_endpoints`).

### Implemented (3 connectors)

| Connector | Docs | Live probe 2026-09-29 |
|-----------|------|------------------------|
| `dog_ceo` | https://dog.ceo/dog-api/ | GET `/api/breeds/list/all` → 200 |
| `open_meteo` | https://open-meteo.com/en/docs | GET `/v1/forecast?...` → 200 |
| `frankfurter` | https://frankfurter.dev/ | GET `/v1/latest` → 200 |

- `mainframe/connectors/` — types, security, http_client, pagination, fixtures, runtime, registry_bridge, accept
- Fixtures: schema drift, quota exhaustion, partial pagination, malformed response
- Tool registry: `conn_*` read-only tools only
- CLI: `python -m mainframe connectors list|call|accept`

### Acceptance (observed)

`python -m mainframe connectors accept` → **10/10** (3 read-only connectors; fixtures: schema drift, quota exhaustion, partial pagination, malformed JSON; model-chosen URL refused; tool registry read-only; live provenance on dog_ceo + open_meteo + frankfurter with source/retrieval_time/attribution/freshness; OpenAPI gap documented).

`python -m mainframe accept` → **47/47** (includes `api_connectors_readonly`).

## 2026-09-29 — Increment 0.1.39: local document → report

### Intent

Ingest supported files; extract text/structured fields with local parsers and optional Tesseract OCR before AI; validate; deduplicate; emit CSV + readable report. Preserve page/row provenance; represent missing/ambiguous explicitly; handle decimals, dates, units, encodings, spreadsheet formula injection. Never auto-post financial/PII externally. Optional eligible semantic step queues uncertain fields for review.

### Implemented

- `mainframe/docreport/` — ingest, ocr, values, extract, validate, dedupe, emit, pipeline, accept
- Fixtures: `docs/eval/docreport/fixtures/{clean,scanned,malformed,duplicate}`
- Scanned path: Tesseract when on PATH; otherwise honest `ocr_unavailable` + fixture sidecar `.ocr.txt`
- CLI: `python -m mainframe docreport run|accept`

### Acceptance (observed)

`python -m mainframe docreport accept` → **7/7**

| Check | Result |
|-------|--------|
| clean CSV field accuracy 1.0, 0 unresolved | PASS |
| scanned OCR/sidecar extract | PASS (Tesseract absent; sidecar used) |
| malformed unresolved + formula neutralization + review queue | PASS (6 unresolved instances) |
| duplicate dedupe 4→3 kept | PASS |
| decimal / ambiguous date / latin-1 / formula helpers | PASS |
| accuracy reported; not wholesale “all correct” | PASS |
| CSV provenance columns | PASS |

`python -m mainframe accept` → **48/48** (includes `document_to_report`).

## 2026-09-29 — Increment 0.1.40: workflow promotion from accepted traces

### Intent

Promote an accepted task trace into a small deterministic program: extract stable steps/parameters, remove unnecessary model decisions, keep genuine semantic AI/human steps explicit. Treat generated programs as untrusted until reviewed and tested on varied inputs and failure cases. Record supported conditions, permissions, source trace, version, and rollback path. One success ≠ generality. Reuse of tested behavior — not training or free new reasoning.

### Implemented

- `mainframe/promote/` — types, trace, extract, generate, contract, runner, trust, accept
- Reporting demo: strip title-choice + summarize AI (2 model calls avoided)
- Website demo: strip diagnose AI; keep external-submit as explicit human step
- Generated `.py` is for review only; runner uses allowlisted handlers (no blind exec)
- CLI: `python -m mainframe promote from-reporting|run|accept`

### Acceptance (observed)

`python -m mainframe promote accept` → **9/9**

| Check | Result |
|-------|--------|
| Untrusted until reviewed; 2 model calls avoided | PASS |
| Unnecessary AI removed (load→transform→write) | PASS |
| Conditions / permissions / source / version recorded | PASS |
| ≥3 varied valid + OOC failure cases | PASS |
| Rerun 3 new inputs with 0 model calls | PASS |
| Out-of-contract rejected; no artifact written | PASS |
| Version bump + rollback path | PASS |
| No generality claim from example | PASS |
| Website: human kept, AI dropped, varied+OOC | PASS |

`python -m mainframe accept` → **49/49** (includes `workflow_promotion`).

## 2026-09-29 — Increment 0.1.41: optional visual bridge (Node-RED evaluated)

### Intent

Evaluate local Node-RED as an optional visual interface: verify core license and additional-node costs; keep removable. Build a narrow bridge that edits/invokes FreeForge workflows; reuse scheduler + effect ledger; forbid Node-RED and OpenClaw independently running the same trigger; secrets outside exported flows. Prefer a simple local form over a second automation stack.

### Evaluation (observed)

| Item | Result |
|------|--------|
| Node-RED core license | Apache-2.0 (upstream LICENSE + npm) |
| Local runtime fee / hosted required | none / no |
| Additional nodes required | **none** (form bridge) |
| Verdict | optional_not_required — simple local form sufficient |

### Implemented

- `mainframe/visual/` — eval_nodered, store, secrets_policy, bridge, server, nodered_flow, accept
- Loopback HTML form: create/save/describe/run FreeForge workflows
- Dual-trigger refuse; optional Node-RED export without repeat/cron
- Docs: `docs/NODERED.md`
- CLI: `python -m mainframe visual status|eval-nodered|serve|accept`

### Acceptance (observed)

`python -m mainframe visual accept` → **9/9** (license/costs; simple form; create+schemas/permissions/blocked AI; execute; ≡ CLI sha256; dual-trigger refuse; export scrubbed; secrets outside flows; remove visual → workflows+schedule remain).

`python -m mainframe accept` → **50/50** (includes `visual_bridge`).

## 2026-10-06 — Increment 0.1.42: fault-injection failure matrix

### Intent

Targeted fault injection for duplicate events, clock changes, interrupted files, process crashes, service timeouts, malformed model output, expired credentials, and exhausted free quotas. Cover external write with lost acknowledgement (reconcile / visible unknown — no blind retry). Cancellation must block new effects while keeping completed effects recorded. Local deterministic only; fixtures ≠ live. Publish expected vs actual recovery matrix. Gate more connectors on critical categories.

### Implemented

- `mainframe/faults/` — clock, files, credentials, scenarios, matrix, accept
- Published: `docs/eval/faults/FAILURE_MATRIX.md` + `.json`
- CLI: `python -m mainframe faults matrix|accept`

### Acceptance (observed)

`python -m mainframe faults accept` → **14/14**

Published matrix: **11/11** scenarios PASS; `allow_more_connectors=true` (data_loss, duplicate_effects, unauthorized_actions, paid_fallback all clear).

| Scenario | Expected = actual |
|----------|-------------------|
| duplicate_events | one_run_duplicate_suppressed |
| clock_changes | record_anomaly_defer_catchup… |
| interrupted_files | discard_tmp_atomic_complete… |
| process_crashes | resume_suppress_duplicate_write… |
| service_timeouts | no_blind_retry_reconcile_or_unknown |
| malformed_model_output | reject_unsupported_no_side_effect |
| expired_credentials | refuse_use_require_refresh_or_pause |
| exhausted_free_quotas | pause_no_paid_fallback |
| lost_acknowledgement_external_write | outcome_unknown_visible_no_blind_retry |
| cancellation_completed_effects_recorded | cancel_blocks_new_effects_completed_remain |
| unauthorized_actions_and_paid_fallback | deny_no_paid_fallback |

## 2026-10-06 — Increment 0.1.43: Void eval + maintained editor bridge

### Intent

Inspect Void at pin `b3166e7…` (codebase guide + editor services). Evaluate diff apply, model sync, context, completion UX. Check Apache-2.0, inherited VS Code licensing, third-party notices before any copy. Prefer maintained extension APIs; Void workbench is not drop-in. Full fork optional with concrete plan. Implement chat→task, selection context, reviewable diffs, diagnostics, cancel/resume; budgeted completion only if eligible model.

### Evaluation

- Void: Apache-2.0 (Glass Devtools appendix); archived/deprecated — reference only
- Inherited vscode: MIT + ThirdPartyNotices required if forking
- **No Void workbench code copied**
- Docs: `docs/VOID_EVAL.md`, `docs/VOID_FORK_PLAN.md`; `docs/NOTICES.md` updated

### Implemented

- `mainframe/editor/` — shared task store, buffers, bridge, completion gate, accept
- `extensions/freeforge-editor/` — VS Code Extension API (chat/select/buffer/cancel/resume)
- CLI: `python -m mainframe editor …`

### Acceptance (observed)

`python -m mainframe editor accept` → **9/9** (Void eval no-copy; one shared task state; selection; unsaved buffers preserved; diagnostics; reviewable diffs; same patch apply deduped; cancel blocks new effects; completion gated off without eligible model).

## 2026-10-06 — Increment 0.1.44: local dashboard + gated notifications

### Intent

Local dashboard (stdlib loopback HTML) aggregating existing FreeForge views: task status, workflow history, quota availability, pending decisions, artifacts, stop/resume. States: proposed / running / verified / blocked / outcome_unknown (+ cancelled). Show actual checks and evidence — not decorative agent activity. Auth and project boundaries intact. Local notifications by default; OpenClaw messaging channels only after fee/connector/recipient/disclosure verification. Inherited automatic outbound delivery disabled. Acceptance: recover a blocked task without reading logs; notification failure must not rerun completed work or send to an unintended destination.

### Inspected

- Reused: `workflows.receipts`, `editor.tasks`, `capabilities.queue`, `durable.tasks`, `quota.ledger`
- Visual bridge pattern for loopback HTTP; schedule payloads already `--no-deliver`

### Preserved

- Existing stores and OpenClaw scheduler ownership; no second automation stack

### Implemented

- `mainframe/dashboard/` — states, notify, aggregate, controls, server, accept
- CLI: `python -m mainframe dashboard show|task|stop|resume|serve|accept`
- DEPENDENCIES: `local_dashboard` eligible row

### Acceptance (observed)

`python -m mainframe dashboard accept` → **10/10**

| Check | Result |
|-------|--------|
| states_distinguished | PASS — proposed/running/verified/blocked/outcome_unknown/cancelled |
| blocked_recoverable_without_logs | PASS — headline + steps + failed check evidence (`path_outside_workspace`) |
| stop_resume_controls | PASS — cancel blocks resume; non-cancelled resume OK; work_rerun=false |
| auth_project_boundaries | PASS — project_id + workspace boundary |
| evidence_not_decorative | PASS — reused views; decorative_agent_activity=false |
| local_notify_openclaw_gated | PASS — local_inbox default; OpenClaw refused; auto outbound off |
| notify_failure_no_rerun_no_mistarget | PASS — work_rerun=false; unintended_destination=false |
| outcome_unknown_no_blind_retry | PASS — primary_action=reconcile |
| loopback_dashboard_serve | PASS — `http://127.0.0.1:<ephemeral>/` |
| quota_history_artifacts_surface | PASS — quota + history + pending_decisions keys |

### Blockers

- None for this increment. OpenClaw messaging remains disabled pending fee/connector/recipient/disclosure verification.

## 2026-10-06 — Increment 0.1.45: project isolation + egress + export

### Intent

Project-specific workspaces, memories, caches, secrets, browser profiles, artifacts, and permission grants. Bind every tool and workflow run to an explicit project identity. Define which data may leave the device and which eligible providers may receive it; free hosted inference is not automatically suitable for confidential material. Support local-only projects that pause without an approved local model. Retention controls; export/delete with preview of affected records; no false secure-erasure claims. Acceptance: cross-project retrieval, reused browser sessions, malicious path references, and stale permission tokens cannot expose another project's data; exports contain no credentials.

### Inspected

- Existing partial isolation: cache `project_id(root)`, memory `project_key`, browser `profile_dir`, capability grants by `project_id`
- Path boundary helper `boundaries.paths.resolve_under_root`

### Preserved

- Prior stores remain; new registry lives under `.mainframe/projects/`

### Implemented

- `mainframe/projects/` — registry, egress, bind, isolation, tokens, retention, export_delete, secrets, cache_ns, accept
- Tool `invoke` / workflow `run_workflow`: optional `project_id` + `require_project`
- Browser `get_page_for_project` refuses cross-project session reuse
- CLI: `python -m mainframe project create|list|show|egress|retention|preview|export|delete|accept`
- DEPENDENCIES: `project_isolation`

### Acceptance (observed)

`python -m mainframe project accept` → **12/12**

| Check | Result |
|-------|--------|
| create_project_workspaces | PASS |
| bind_tool_and_workflow | PASS — missing project_id refused |
| cross_project_retrieval_blocked | PASS — memory not leaked |
| cache_cross_project_blocked | PASS |
| reused_browser_session_blocked | PASS |
| malicious_path_references_blocked | PASS |
| stale_permission_tokens_blocked | PASS — foreign + expired refuse |
| egress_and_local_only_pause | PASS — secrets never leave; hosted not auto; local-only pauses |
| export_contains_no_credentials | PASS — scrubbed; secrets omitted |
| retention_and_delete_preview_honest | PASS — `secure_erasure_guaranteed=false` |
| permission_grants_project_bound | PASS |
| delete_marks_gone_without_secure_claim | PASS |

### Blockers

- None. Hosted free inference remains unsuitable for confidential/local-only without explicit policy (still never auto).

## 2026-10-06 — Increment 0.1.46: held-out workload evaluation + ablations

### Intent

Evaluate repository repair, website maintenance, and document reporting on **held-out** inputs. Compare FreeForge vs minimal free agent vs scripted prior manual process. Competitors unmeasured (no purchase). Report correct completion rate (Wilson 95% CI), elapsed time, active human time, retries, model calls, failure recovery, sustainable daily volume; setup/maintenance separate. Ablate retrieval, workflow reuse, review, caching; disable features that do not improve outcomes. Only workload-specific evidence-supported superiority claims.

### Implemented

- Holdout fixtures: `docs/eval/workloads/holdout/{w1,w2,w3}_*/`
- `mainframe/workload_eval/` — runners, stats, ablations, disable policy, suite, accept
- Reports: `docs/eval/workloads/HELDOUT_EVAL.md` + `.json` + `feature_disable_policy.json`
- CLI: `python -m mainframe workload-eval run|accept`

### Acceptance (observed)

`python -m mainframe workload-eval accept --trials 3` → **9/9**

`python -m mainframe workload-eval run --trials 5` → published report (small_sample acknowledged).

| Workload | FreeForge | Minimal | Manual |
|----------|-----------|---------|--------|
| repository_repair | 1.0 (n=5, CI 0.57–1.0) | 0.0 | 1.0 |
| website_maintenance | 1.0 | 0.0 | 1.0 |
| document_reporting | 1.0 | 0.0 | 1.0 |

Ablation contributions retained: **website retrieval**, **docreport retrieval + review**. Disabled when ablation ≥ full: caching / unused workflow_reuse / unused review on repair & site (see policy JSON).

Competitors: Claude Code / Cursor E2E **unmeasured**.

### Blockers

- Small-n only (n=5); not a large held-out study.
- Wall-clock daily volume for sub-second deterministic runs is theoretical — not interactive capacity.

## 2026-10-06 — Increment 0.1.47: reproducible cost audit

### Intent

Audit installation, runtime, inference, search, models, plugins, browser, storage, notifications, backups, CI, and distribution for hidden paid dependencies. Check licenses, entitlements, inherited defaults, automatic fallbacks. Trace outbound paths (OpenClaw, coding engine, plugins, workers) and prove controls. Application policy alone cannot constrain arbitrary networked processes — disable non-loopback live paths without OS network isolation. Simulate hosted providers gone/paid: deterministic workflows remain; AI pauses without approved local model. Separate zero software fees from physical resource consumption.

### Implemented

- `mainframe/costaudit/` — surfaces, scan, outbound proofs, boundary gate, hosted-gone simulation, suite, accept
- Live connectors refuse when `os_network_isolation` is false (`live_disabled_without_os_network_isolation`); fixtures remain
- Reports: `docs/COST_AUDIT.md` + `.json`
- CLI: `python -m mainframe cost-audit run|accept`

### Acceptance (observed)

`python -m mainframe cost-audit accept` → **7/7**

| Check | Result |
|-------|--------|
| reports_published | PASS |
| acceptance_all_pass | PASS — no paid account/trial/hosted required |
| zero_fees_vs_physical_separated | PASS |
| outbound_proofs_pass | PASS |
| hosted_gone_deterministic_ok | PASS — echo works; AI pauses; no paid fallback |
| live_outside_boundary_disabled | PASS — live dog.ceo refused; fixture OK |
| no_required_paid_account_trial_hosted | PASS |

### Blockers

- This host reports `os_network_isolation=false` (Job Object process limits ≠ network jail). Live non-loopback remains disabled by design.

## 2026-10-06 — Increment 0.1.48: minimal local release package

### Intent

Package a minimal release with pinned dependencies, licenses, source links, local setup, and clean uninstall. Verify actual Windows target (no obsolete installer commands). Include doctor, optional eligible credential posture, offline fixtures, backups, DB migration recovery, upgrade check. Startup scheduling explicit and removable. Builds/checks local only — hosted CI, code-signing, cloud storage, public hosting must not become requirements. Label DOCUMENTED_NOT_TESTED steps accurately.

### Implemented

- `mainframe/release/` — pins, target measure, package tree, backup/restore, migrate workflow+DB, upgrade check, credentials status, startup (local job + optional schtasks), smoke, uninstall, suite, accept
- Package: `dist/release/mainframe-0.1.48/` with `SETUP.md`, `UNINSTALL.md`, `PINNED_DEPENDENCIES.json`, `LICENSE`, notices, fixtures
- CLI: `python -m mainframe release run|accept|package|smoke|backup|restore|migrate-*|upgrade-check|credentials-status|startup-*|uninstall*`
- Reports: `docs/RELEASE.md` + `.json`; DEPENDENCIES row `minimal_local_release`

### Acceptance (observed)

`python -m mainframe release accept` → **8/8**

| Check | Result |
|-------|--------|
| reports_published | PASS |
| clean_install_smoke | PASS — status/echo/fixture from packaged tree; no pip |
| backup_restore | PASS |
| migrate_workflow_and_db | PASS — 0.9→1.0 workflow; additive SQLite cancel_requested |
| upgrade_check_and_pins | PASS |
| startup_explicit_removable | PASS — local FreeForge job; schtasks Access denied labeled |
| no_hosted_requirements | PASS |
| package_tree_local | PASS |

### Target measured

- `Windows-11-10.0.26200-SP0`; registry ProductName `Windows 10 Home` / 25H2 / build 26200
- Python 3.12.4 (miniconda); Node v22.12.0; Git present
- Refused as required: choco/winget Python, pip requirements, docker compose

### DOCUMENTED_NOT_TESTED

- OpenClaw Gateway; Docker; elevated schtasks ONLOGON create/fire; winget/choco; code-signing; cloud/public upload

### Blockers

- Non-elevated `schtasks /Create /SC ONLOGON` returns Access denied — local removable schedule is the enforced path on this host.

## 2026-10-06 — Increment 0.1.49: recommended FreeForge configuration

### Intent

Use accumulated evidence for a recommended FreeForge configuration optimizing correct completed work per available resource (not agent count, model size, or frontier label). Three modes: deterministic offline; + optional CPU AI; + currently eligible free hosted AI. Describe unavailable-route behavior. Publish capability matrix, measured workloads, quotas, hardware, weaknesses, next improvements. Unmeasured stays unknown. Demo one coding task + one reusable automation under strict contract. State where build outperforms measured baselines and where it does not. Never promise unlimited frontier performance.

### Implemented

- `mainframe/recommend/` — modes, evidence loader, matrix, demos, suite, accept
- Reports: `docs/FREEFORGE_RECOMMENDED.md` + `.json`
- CLI: `python -m mainframe recommend run|accept`
- DEPENDENCIES: `freeforge_recommended_config`

### Acceptance (observed)

`python -m mainframe recommend accept` → **7/7**

| Check | Result |
|-------|--------|
| reports_published | PASS |
| three_modes_and_recommended | PASS — recommended=`deterministic_offline` |
| mode_c_no_false_hosted_eligibility | PASS — zero eligible hosted |
| verified_coding_task | PASS — held-out W1 repair (retrieval on; no model) |
| reusable_automation | PASS — `input_to_report` workflow |
| baselines_stated_honestly | PASS |
| no_unlimited_frontier_promise | PASS |

### Key evidence used

- Held-out W1–W3: FreeForge ≫ minimal; ties manual correctness; less human time
- Doctor: i7-12700H, ~31 GiB RAM, AI probe paused
- PROVIDERS/cost audit: no verified free hosted entitlement
- Quota default bucket: 60 req / 100k tokens / concurrency 4 (reset_unknown)

### Blockers / unknowns

- Mode B/C unavailable on this host (Ollama paused; hosted empty)
- Competitor E2E unmeasured; interactive daily capacity unknown
- Joint all-disabled feature flags ≠ safe recommendation (compensating features)

## 2026-10-06 — Increment 0.1.50: web + application surfaces + optional Actions

### Intent

Publish dual product surfaces: **web** optimized for websites/webapps; **application** for desktop + iOS/Android/store markets (checklist, no forced uploads). Optional GitHub Actions/Pages for visibility; local builds remain authoritative. Commit and push to github.com/levizigza/MAINFRAME.

### Implemented

- `mainframe/surfaces/` — catalog, web static build, application desktop package + store checklist, suite, accept
- `.github/workflows/surfaces.yml` — Windows local checks + optional Pages deploy (`continue-on-error`)
- Docs: `docs/SURFACES.md` + `.json`
- CLI: `python -m mainframe surfaces run|accept|catalog|build-web|build-app`

### Acceptance (observed)

`python -m mainframe surfaces accept` → **7/7**

### Links

- Actions: https://github.com/levizigza/MAINFRAME/actions
- Optional Pages: https://levizigza.github.io/MAINFRAME/

### Blockers

- App Store / Play / Microsoft Store uploads: DOCUMENTED_NOT_TESTED (accounts outside free contract)
- Pages deploy succeeds only after GitHub Pages is enabled for the repo

## 2026-10-06 — Increment 0.1.51: CI harden recommend + surfaces workflow

### Intent

Fix GitHub Actions failure on `recommend accept` (run 37517450106). Harden Windows/CI: ASCII JSON print, CI-lite doctor (skip CIM/Playwright), bash steps, assert report JSON files.

### Acceptance

Local: `CI=true python -m mainframe recommend accept` and `surfaces accept` exit 0. Push triggers Actions re-run.

## 2026-10-07 — Increment 0.1.52: FreeForge Workbench + Mode B fitness

### Intent

Ship FreeForge Branded Workbench track: product truth (CLI ≠ IDE), Mode B fitness via doctor, vscode pin + thin FreeForge overlay, agent UX bridge (chips/stream/apply/reject/cancel), deterministic-first propose with optional model gate, onboarding + `docs/eval/ide/` evidence gates. No Cursor-parity claims.

### Inspected

- Plan: FreeForge Workbench IDE (shell B / inference Mode B).
- Existing: `codingloop.propose_fixes` fixture-only; `editor` bridge; `extensions/freeforge-editor`; Void archived reference; Ollama paused on this host.

### Preserved

- No user notes overwritten. Void not vendored. Extension bridge retained.

### Implemented

- Docs: `docs/WORKBENCH.md`, `docs/VOID_FORK_PLAN.md` (workbench product track), `docs/eval/ide/{REPORT,metrics,ABLATIONS}.md`
- Python: `mainframe/workbench/` (fitness, status, onboarding, agent, accept)
- `mainframe/codingloop/propose.py` — deterministic-first + cached retrieve + optional model under eligibility/quota
- CLI: `python -m mainframe workbench status|fitness|onboarding|agent-turn|apply|reject|chips|cancel|resume|accept`
- `freeforge-workbench/` — PINS.json (vscode 1.140.0), ThirdPartyNotices, overlay contrib (chat + AI status), Windows build scripts
- Application surface stages `dist/application/workbench/`
- Rules/DEPENDENCIES/README updated; version `0.1.52`

### Acceptance (observed)

| Check | Result | Notes |
|-------|--------|-------|
| `workbench status` | PASS | AI **paused**; claims exceeds_cursor=unknown |
| `workbench fitness` | PASS | Mode B; auto_download=false; Ollama unreachable |
| `workbench accept` | PASS **14/14** | Overlay pin, agent chips/stream, apply/reject, artifact |
| `codingloop accept` | PASS 5/5 | After local `pytest` install (was missing on host) |
| `editor accept` | PASS | Regression |
| `ai probe` | paused | Live modeleval/codingbench **not** run — quality stays unknown |
| Windows Electron build | DOCUMENTED_NOT_TESTED | Linux cloud host; scripts present for Windows |

### Blockers

- Fitted Ollama model not installed → live coding quality **unknown**
- Full vscode Electron compile not executed on this host
- vs Cursor **unknown** (no paid trial measurement)

### Honesty

Never invent Cursor parity or live model scores. Fill `docs/eval/ide/metrics.json` only after measured runs.
