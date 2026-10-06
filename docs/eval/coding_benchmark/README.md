# Held-out coding benchmark

Reproducible tasks with **ground truth outside agent workspaces** (`keys/expectations.json`).

## Splits

- **tune** — may be used for harness development (not holdout claims)
- **holdout** — disjoint IDs; used for reported benchmark outcomes

## Run

```bash
python -m mainframe codingbench run
python -m mainframe codingbench run --split holdout
python -m mainframe codingbench accept
```

Raw JSON is written to `.mainframe/runs/codingbench-*.json`.

## Measurement kinds

| Kind | Meaning |
|------|---------|
| `mock_integration` | Fixture agents — validates harness + verifier only |
| `live_model_quality` | Opt-in (`--live`); unmeasured when no eligible runtime |

Mock integration results must **not** be treated as frontier model quality.
