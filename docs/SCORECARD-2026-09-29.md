# MAINFRAME capability scorecard — 2026-09-29

**Date:** 2026-09-29 (America/Denver context; docs fetched this day)  
**Method:** Official public documentation only for competitor *functional coverage*.  
**Benchmarking policy:** No purchase of Claude, Cursor, or frontier API access for this scorecard. End-to-end competitor task scores = **unmeasured**.  
**Unsupported claims (remain unsupported):** universal superiority; unlimited frontier inference; “schedules / memory / MCP ⇒ advantage” without workload evidence.

**Primary sources (fetched 2026-09-29):**
- Claude Code overview: https://code.claude.com/docs/en/overview
- Claude Code hooks: https://code.claude.com/docs/en/hooks-guide , https://code.claude.com/docs/en/hooks
- Claude Code scheduled tasks / memory: https://code.claude.com/docs/en/scheduled-tasks , https://code.claude.com/docs/en/memory
- Cursor Hooks: https://cursor.com/docs/hooks
- Cursor Automations: https://cursor.com/docs/cloud-agent/automations
- Cursor MCP: https://cursor.com/docs/mcp
- Cursor Cloud Agents: https://cursor.com/docs/cloud-agent

Executable plans: `docs/eval/` · runner: `python -m mainframe scorecard`

---

## 1. Layer separation (do not collapse)

| Layer | What it measures | What it does *not* measure |
|-------|------------------|----------------------------|
| **A. Functional coverage** | Feature exists per public docs / local code | Quality, speed, cost, reliability |
| **B. Model reasoning quality** | Judgment on fixed prompts / repair difficulty | Tooling UX, scheduling, MCP plumbing |
| **C. End-to-end task performance** | Workload outcomes under defined metrics | Feature checklist presence |

Adding schedules, memory, or MCP improves **Layer A** only until Layer C evidence exists.

---

## 2. Layer A — Functional coverage (documentation / code presence)

Legend: `Y` = documented or implemented · `N` = not present · `P` = partial / optional · `U` = unclear from free public docs without account probing

| Capability | Claude Code (docs) | Cursor (docs) | MAINFRAME 0.1.1 |
|------------|--------------------|---------------|-----------------|
| Local agentic coding loop | Y | Y | P (deterministic tasks; optional local AI) |
| Lifecycle hooks / deterministic side effects | Y (shell/HTTP/MCP/prompt/agent hooks) | Y (`hooks.json`, tool/file/session hooks) | N |
| MCP tool connections | Y | Y | N (explicitly out of core; eligibility may add later only if free-only) |
| Project instruction files | Y (`CLAUDE.md` / `AGENTS.md`) | Y (rules / skills) | Y (`.cursor/rules`, docs) |
| Auto / persistent memory | Y (auto memory + CLAUDE.md) | P (rules, memories in product; Automations mention memory tools) | P (`.mainframe/user_notes.md` only) |
| In-session repeat / loop | Y (`/loop`, cron tools) | U | N |
| Scheduled / event automation | Y (Desktop schedules, cloud Routines) | Y (Cloud Automations: schedule, GitHub/GitLab/Slack/webhooks) | N |
| Cloud remote agents | Y (web / routines) | Y (Cloud Agents) | N (by design: local PC) |
| Subagents / parallel agents | Y | Y (Task/subagent hooks) | N |
| CI / PR automation integrations | Y (GH Actions / GitLab cited) | Y (Automations + cloud) | N |
| Offline launch without paid credentials | U (docs: most surfaces need Claude subscription / Console; third-party providers mentioned for some surfaces) | U (product account typical; not measured) | Y (`python -m mainframe status`) |
| Zero required API/subscription fees for core | N (paid subscription required for Desktop; most surfaces need account) | U (not measured; cloud features are commercial product) | Y (stdlib core) |
| Free-only eligibility gate / disabled paid routes | N | N | Y |
| Built-in accept / honest probe (no invented success) | U | U | Y |

**Interpretation:** Claude Code and Cursor lead Layer A on agent automation surface area. That is **not** a Layer C win until workloads are measured.

---

## 3. Layer B — Model reasoning quality

| System | Measurement status | Notes |
|--------|-------------------|-------|
| Claude Code (frontier Claude) | **unmeasured** | Would require eligible access; not purchased for this scorecard |
| Cursor Agent (configurable models) | **unmeasured** | Same |
| MAINFRAME + optional local Ollama | **unmeasured** | Local inference was `paused` on 2026-09-29 (no server on `:11434`) |
| MAINFRAME deterministic path | **N/A** | No model; not a reasoning score |

No Layer B rankings are asserted.

---

## 4. Layer C — End-to-end workloads (targets + baselines)

Shared metric definitions:

| Metric | Definition |
|--------|------------|
| **Correct outcome** | Binary pass on workload acceptance checks (see fixtures) |
| **Completion time** | Wall clock from start command to pass/fail, seconds |
| **Human interventions** | Count of manual edits, approvals, or re-prompts after start |
| **Reliability** | Passes / N identical trials (target N=5 for MAINFRAME deterministic; competitor N unmeasured) |
| **Privacy** | `local_only` if no required cloud account/egress for the run path; else `cloud_involved` |
| **Sustainable throughput** | Successful correct runs per hour on the same machine without paid quota |

### W1 — Repository repair

| Field | Definition |
|-------|------------|
| **Scenario** | Fixture repo with a broken Python module + failing self-check |
| **Correct outcome** | Module imports; `python -m mainframe run workspace-checksum` succeeds; repair report lists changed paths; no credential files created |
| **MAINFRAME target** | Deterministic repair path: correct=true; time ≤ 30s; interventions = 0; reliability ≥ 5/5; privacy=`local_only`; throughput ≥ 60 runs/h |
| **MAINFRAME baseline** | Measured by `python -m mainframe scorecard` (see PROGRESS for observed values) |
| **Claude Code / Cursor** | **unmeasured** (no purchased benchmark run) |

### W2 — Repeated website-maintenance task

| Field | Definition |
|-------|------------|
| **Scenario** | Local static site fixture; repeated maintenance = fix checklist items (broken link marker, stale year meta) idempotently |
| **Correct outcome** | After run, checklist JSON all `ok:true`; second run is no-op (idempotent); site files remain local |
| **MAINFRAME target** | correct=true ×2 consecutive; time ≤ 20s each; interventions=0; reliability ≥ 5/5; privacy=`local_only`; throughput ≥ 90 runs/h |
| **MAINFRAME baseline** | Via scorecard runner |
| **Claude Code / Cursor** | **unmeasured** — note: their schedulers (Routines / Automations) are Layer A features; advantage on *this* workload is **not** assumed |

### W3 — Document-to-report workflow

| Field | Definition |
|-------|------------|
| **Scenario** | Input Markdown → structured report JSON with required keys |
| **Correct outcome** | Report validates against schema (`title`, `source_hash`, `sections[]`, `generated_by`); content sections non-empty |
| **MAINFRAME target** | Deterministic extractor: correct=true; time ≤ 15s; interventions=0; reliability ≥ 5/5; privacy=`local_only`; throughput ≥ 120 runs/h |
| **MAINFRAME baseline** | Via scorecard runner |
| **Claude Code / Cursor** | **unmeasured** |

---

## 5. Proposed MAINFRAME advantages (hypotheses only)

Each requires an executable plan + baseline. None imply universal superiority.

| ID | Proposed advantage | Eval plan | Baseline | Status |
|----|-------------------|-----------|----------|--------|
| **H1** | Core automation launches with zero paid credentials / hosted service | `python -m mainframe status` + accept check `launch_without_credentials_or_hosted`; grep tree for cloud SDK imports | 2026-09-29: accept 10/10; status exit 0 | **supported for core launch** (not for frontier coding quality) |
| **H2** | Deterministic workloads are bit-stable without an LLM | Scorecard runs W1–W3 five times; identical `source_hash` / checksum outputs | Measured in scorecard JSON | **to be filled by runner** |
| **H3** | Privacy: core paths need no cloud egress | Audit: no hosted clients; AI only loopback; scorecard privacy flag `local_only` | Code audit 0.1.1 + scorecard | **supported for deterministic core**; AI path still local-only when used |
| **H4** | Schedules / memory / MCP make MAINFRAME better at W1–W3 | *Do not claim.* If added later, re-run Layer C with/without feature on same fixtures | n/a | **unsupported** (feature ≠ outcome) |
| **H5** | Better model reasoning than Claude/Cursor | Blind Layer B rubric on fixed prompts | n/a | **unmeasured / unsupported** |
| **H6** | Unlimited frontier inference at zero cost | Contradicts free-only contract and physical limits | n/a | **unsupported** |

---

## 6. Evaluation ethics

- Do not invent competitor timings or pass rates.
- Do not use trials, promo credits, or paid APIs “just for the scorecard.”
- When a cell is unknown, write **unmeasured**.
- Re-date the filename (`SCORECARD-YYYY-MM-DD.md`) when sources or results change.
