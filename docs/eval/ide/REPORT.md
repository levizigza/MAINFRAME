# FreeForge Workbench — IDE evidence report

Evidence-gated metrics only. Unmeasured stays **unknown**.

Machine-readable: [`metrics.json`](metrics.json)

| Metric | Status | Notes |
|--------|--------|-------|
| Cold start | **unknown** | Record on Windows after `build-windows.ps1` + first launch |
| Agent task success (live) | **unknown** | Needs fitted Ollama + `codingbench --live` / held-out W1–W3 |
| Agent task success (fixture/mock) | measured in `workbench accept` | Deterministic propose + apply/reject |
| Apply safety | accept/reject path | No silent overwrite; dirty buffers preserved via editor bridge |
| Latency p50 tool/verify | **unknown** | Measure locally under Mode B |
| Offline (AI paused) | supported | Mode A editing + CLI twin |
| vs Cursor | **unknown** | Optional only if you run a paid Cursor trial yourself |

## Target languages (first quality bar)

Python + web (HTML/JS) — matches held-out W1–W3 and existing fixtures.

## Claims policy

Never publish “exceeds Cursor” or “99th percentile” without cells above flipping from unknown → measured with methodology.
