# IDE feature ablations

Disable UI/agent features that do not improve live codingbench rate.

| Lever | Default | Ablate when |
|-------|---------|-------------|
| Context chips | on | No measured gain vs selection-only |
| Model propose (after deterministic miss) | on when Mode B available | Live rate ≤ deterministic-only |
| Inline completion | Mode B + budget only | Increases latency without task wins |
| Nested multi-agent | off | Already disabled in `review` |

Record measured live rates in `REPORT.json` / codingbench — do not claim wins without numbers.
