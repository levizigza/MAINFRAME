# Path to Cursor / Claude Code benchmarks — free only

**Goal:** MAINFRAME reports the **same public metrics** those products are scored on, at the **same resolve rate**, using **zero paid APIs**. Cursor’s private CursorBench cannot be cloned. We match the **public** suites and build an equivalent interactive bench from our own sessions.

This is a measurement program, not a claim that today’s build already ties those scores. Until a cell is run here, it stays **unknown**.

## What “the same benchmark” means

| Suite | What it measures | Cursor / Claude public figure (not ours) | MAINFRAME today |
| --- | --- | --- | --- |
| SWE-bench Verified (500) | % of human-filtered GitHub issues resolved by tests in a sandbox | Claude Opus 5: **96%** (Anthropic system card, Jul 2026; Vals.ai independent run **97%**, Sep 2026). DeepSeek-V4-Pro open weights: **80.6%** (DeepSeek, cited Apr 2026). Third-party boards disagree on later open-weight rows (some list ~86–96%). | **unknown** — not wired |
| SWE-bench Multilingual | Same idea, many languages | Composer 2: **73.7** (Cursor technical report, 2026) | **unknown** |
| Terminal-Bench | Agentic terminal tasks | Composer 2: **61.7** (same report) | **unknown** |
| CursorBench | Private tasks from Cursor eng sessions | Composer 2: **61.3**. Not reproducible by outsiders | Proxy only: grow `codingbench` from real FreeForge sessions |
| MAINFRAME `codingbench` | Small held-out fixtures (logic, multifile, decline) | n/a | Accept-gated; **not** SWE-bench |

Scaffold changes the score. Public writeups show the **same model** moving **15+ points** across harnesses. The free win is the harness plus open weights, not a copy of Anthropic’s weights.

## Reverse engineering (public systems only)

No binary dumping, no weight extraction, no paid API keys. Sources: Claude Code docs (agent loop, MCP, permissions), arXiv:2604.14228 (Claude Code design space), Cursor blog (semantic search, indexing), Composer 2 technical report.

### Shared skeleton

Both products are a **while-loop**:

1. Assemble a tight context (system, tools, recent files, task).
2. Model emits tool calls (or a final answer).
3. Run tools. Read-only tools in parallel; writes and shell in order.
4. Append results. Compact when the window fills.
5. Repeat until tests pass, the model stops, or a budget hits.
6. Human can accept/reject diffs (Cursor IDE; Claude Code permissions).

### Claude Code extras we must grow

- Tools: Read, Edit, Write, Glob, Grep, Bash (tests, git). Web only if the route stays free and eligibility-gated.
- Permissions: deny beats allow. Hooks can block a call. Already aligned with MAINFRAME cost gate / capabilities.
- Context compaction so long repairs do not fall off the window.
- **MCP** servers as extra tools, with **tool search** so schemas do not eat the context.
- Skills / hooks as the extension surface.
- Subagents only when a measured bench says they help. Default stays one loop (MAINFRAME already rejects nested supervisors).

### Cursor extras we must grow

- Same small tool set, plus **grep and semantic search together**. Cursor reports semantic search lifting their context bench; they also keep grep. MAINFRAME already learned that unused retrieval (FTS5) should be ablated — semantic search ships only if our bench moves.
- Index = file hashes (Merkle-style incremental sync) + local embeddings. No Cursor cloud index.
- Composer 2’s other moat is **RL inside that harness**. We cannot rent their GPU cluster. We can do the cheap version: every verified repair becomes a training/retrieval example for the next run (self-upgrade), on our traces only.

### What MAINFRAME already has

- Eligibility gate, quota, exact caches, patch apply with review, coding loop lifecycle, editor agent NDJSON, MCP **schema fingerprint + fee re-check** (`mainframe/tools/mcp_bridge.py`).
- Deterministic propose for known fixtures. Mode B model propose **pauses** when Ollama is down.
- Host: ~32 GiB RAM, often ~4 GiB free while the IDE is open. A 27B Q4 (~17 GiB) does not fit until other processes release RAM. A 0.5B–3B model fits sooner and is the first live cell, not the last.

## The free path (ordered)

### 1. Scoreboard before weights

Add a runner that executes **public** tasks with the official resolve rule (fail-to-pass tests). Start with a **bounded subset** (Lite or a pinned 20-instance slice) so a CPU run finishes. Store raw JSON under `docs/eval/`. Columns: suite, instance id, model id, harness git sha, resolved yes/no, tool calls, wall time. **Do not** copy a leaderboard number into our report.

### 2. Harness parity (largest free lever)

Replace the one-shot fixture proposer, for non-fixture repos, with the Claude/Cursor loop:

- `grep` / `glob` / `file_range` (exact-cached reads)
- unique search-replace edit (already in `patch`)
- `pytest` / shell inside the existing exec boundary
- stop when the target tests pass, or when `max_tool_calls` / `max_model_calls` hits
- **best-of-N against the tests**: a smaller model proposes several patches; keep the one that goes green. Electricity is the budget. This is how a local model hunts bugs a single frontier call would also miss without tests.

Wire this through `editor agent-run` so the IDE and the bench share one loop.

### 3. Model ladder on this PC (still free)

1. Install Ollama. Re-run `workbench model-fit` **after** freeing RAM (close browsers). Record available GiB.
2. Pull the **largest catalog model that `verified_fit` accepts**. If none fit, pull the smallest coder model anyway and label the run `unverified_fit` — measure it, do not pretend the doctor approved it.
3. Climb only when a live cell improves holdout resolve rate: 0.5B/1.5B → 3B → 7B → 14B/27B-class **if** RAM and disk allow. Open-weight families with published SWE-bench numbers (Qwen coder lines, DeepSeek V4 Flash-class if the active-parameter count fits) are the candidates. Weights stay local. No hosted “free tier” fallback.

### 4. Retrieval, ablated

- Keep lexical retrieve (already accept-gated).
- Add a local incremental file-hash index (stdlib).
- Optional local embedding model only behind eligibility. If `codingbench` / SWE slice does not move, disable it in code the same way FTS5 was disabled.

### 5. MCP inside the loop

MCP is already a registry concept. Next slice:

- stdio client, local processes only by default
- every server tool passes `evaluate_mcp_tool` (fingerprint, fee, permission)
- paid or remote-billed tools stay **unavailable**, not hidden
- tool search: expose names first, load full schemas on demand
- first servers: git, and a **local** “verified-patch memory” server (below). No required cloud MCP.

### 6. Self-upgrade

Three layers, all local:

1. **Memory.** Every patch that tests verify is stored (exact cache + promote trace). The next similar failure retrieves that edit before calling the model.
2. **Ablation gate.** A change to prompts, tools, or MCP set lands only if the holdout resolve rate does not drop. Joint ablations stay mandatory (single-feature ties can lie).
3. **Weights, optional.** If a small local fine-tune (LoRA on **our** verified traces only) raises the bench, keep it. Never train on scraped Claude/Cursor transcripts. The agent may edit MAINFRAME itself only through the same propose → review → test path.

The upgrade loop is the product: bench → failure cluster → harness or memory change → re-bench → keep or revert.

## Success criteria

| Gate | Pass when |
| --- | --- |
| Protocol | A pinned SWE-bench slice runs offline and writes raw JSON |
| Harness | Same loop used by IDE agent and by the bench |
| Honesty | Report shows model, harness sha, date; competitor cells not copied |
| Climb | Each accepted change raises resolve rate or cuts tool calls at the same rate |
| Parity | Our measured resolve rate on that pinned protocol matches the published figure for the **open-weight** system we chose, then we keep climbing toward the frontier figure with search, memory, and larger fitted weights |
| MCP | A stdio server tool runs inside the loop and a fee-bearing server is refused |
| Self-upgrade | A previously verified repair is reused with zero model calls on a replay |

Physical costs (electricity, disk, RAM) stay the user’s. Software, accounts, and hosted inference stay at zero required fees.

## Explicit non-goals

- Shipping a number we did not measure
- Paid Cursor/Claude APIs as the way to “match the benchmark”
- Vendoring proprietary source or weights
- Nested multi-agent swarms unless an ablation shows a gain
