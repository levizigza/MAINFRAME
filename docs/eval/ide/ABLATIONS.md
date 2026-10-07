# Workbench / agent ablations

Disable features that do not improve live codingbench rate. Until live Mode B
evals run, keep defaults conservative:

| Lever | Default | Ablate when |
|-------|---------|-------------|
| Model chat reply in agent turn | on when Ollama available | Live rate ≤ deterministic-only |
| Model proposer (`prefer_model`) | on when available | Fixture/deterministic already fixes; or model edits fail validate |
| Inline completion | off until requested + Mode B | Always off if probe paused |
| Nested multi-agent review | off | Already disabled in `review` no-gain routes |
| FTS5 retrieve | measured policy file | Leave off until accept proves gain |

Record measured deltas here after `codingbench --live` — do not invent.
