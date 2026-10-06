# Evaluation fixtures & plans

Dated scorecard: [`../SCORECARD-2026-09-29.md`](../SCORECARD-2026-09-29.md)

```powershell
python -m mainframe scorecard
python -m mainframe scorecard --trials 5
python -m mainframe workload-eval run --trials 5
python -m mainframe workload-eval accept
```

| Workload | Fixture | Runner |
|----------|---------|--------|
| W1 repo repair | `fixtures/w1_repo_repair/` | `mainframe.scorecard._w1_once` |
| W2 site maint | `fixtures/w2_site_maint/` | `mainframe.scorecard._w2_once` |
| W3 doc→report | `fixtures/w3_doc_report/` | `mainframe.scorecard._w3_once` |

Held-out comparison (FreeForge vs minimal vs manual + ablations): `workloads/holdout/` → `workloads/HELDOUT_EVAL.md`.

Competitor Claude Code / Cursor E2E results are always emitted as `unmeasured` unless a free policy-compliant measurement is recorded later.
