# Held-out workload evaluation

Generated: `2026-10-06T18:53:34.909795+00:00`

Workloads: repository repair, website maintenance, document reporting.
Inputs: `docs/eval/workloads/holdout/` (held out from scorecard W1–W3 and demo fixtures).
Competitors (Claude Code / Cursor E2E): **unmeasured** — no purchased access.

Sample size is small; Wilson 95% intervals are reported and flagged `small_sample`.

## Comparison (correct completion rate)

| Workload | FreeForge | Minimal agent | Manual process |
|----------|-----------|---------------|----------------|
| repository_repair | 1.0 (n=5, 0.5655–1.0) | 0.0 (n=5, 0.0–0.4345) | 1.0 (n=5, 0.5655–1.0) |
| website_maintenance | 1.0 (n=5, 0.5655–1.0) | 0.0 (n=5, 0.0–0.4345) | 1.0 (n=5, 0.5655–1.0) |
| document_reporting | 1.0 (n=5, 0.5655–1.0) | 0.0 (n=5, 0.0–0.4345) | 1.0 (n=5, 0.5655–1.0) |

## Metrics (FreeForge full)

### repository_repair

- Correct rate: `{'n': 5, 'successes': 5, 'rate': 1.0, 'ci95_low': 0.5655, 'ci95_high': 1.0, 'small_sample': True, 'note': 'Small-n Wilson interval; not a substitute for a large held-out study.'}`
- Mean elapsed s: `0.0082`
- Mean active human s: `0.0`
- Retries total: `1`
- Model calls total: `0`
- Failure recoveries: `1`
- Setup s sum: `0.0334` (separate)
- Maintenance s sum: `0.0` (separate)
- Sustainable daily volume est: `3529411.76` (wall_clock_8h_theoretical)

### website_maintenance

- Correct rate: `{'n': 5, 'successes': 5, 'rate': 1.0, 'ci95_low': 0.5655, 'ci95_high': 1.0, 'small_sample': True, 'note': 'Small-n Wilson interval; not a substitute for a large held-out study.'}`
- Mean elapsed s: `0.0058`
- Mean active human s: `0.0`
- Retries total: `0`
- Model calls total: `0`
- Failure recoveries: `0`
- Setup s sum: `0.0197` (separate)
- Maintenance s sum: `0.0` (separate)
- Sustainable daily volume est: `4965517.24` (wall_clock_8h_theoretical)

### document_reporting

- Correct rate: `{'n': 5, 'successes': 5, 'rate': 1.0, 'ci95_low': 0.5655, 'ci95_high': 1.0, 'small_sample': True, 'note': 'Small-n Wilson interval; not a substitute for a large held-out study.'}`
- Mean elapsed s: `0.0059`
- Mean active human s: `0.0`
- Retries total: `0`
- Model calls total: `0`
- Failure recoveries: `0`
- Setup s sum: `0.0178` (separate)
- Maintenance s sum: `0.0` (separate)
- Sustainable daily volume est: `4848484.85` (wall_clock_8h_theoretical)

## Ablations (FreeForge)

### repository_repair

| Condition | Rate |
|-----------|------|
| full | 1.0 (n=5) |
| no_retrieval | 1.0 (n=5) |
| no_workflow_reuse | 1.0 (n=5) |
| no_review | 1.0 (n=5) |
| no_caching | 1.0 (n=5) |

### website_maintenance

| Condition | Rate |
|-----------|------|
| full | 1.0 (n=5) |
| no_retrieval | 0.0 (n=5) |
| no_workflow_reuse | 1.0 (n=5) |
| no_review | 1.0 (n=5) |
| no_caching | 1.0 (n=5) |

### document_reporting

| Condition | Rate |
|-----------|------|
| full | 1.0 (n=5) |
| no_retrieval | 0.0 (n=5) |
| no_workflow_reuse | 1.0 (n=5) |
| no_review | 0.0 (n=5) |
| no_caching | 1.0 (n=5) |

## Disable policy (features that do not help)

```json
{
  "repository_repair": {
    "retrieval": {
      "disabled": true,
      "reason": "ablation_rate_ge_full",
      "full_rate": 1.0,
      "ablation_rate": 1.0
    },
    "workflow_reuse": {
      "disabled": true,
      "reason": "ablation_rate_ge_full",
      "full_rate": 1.0,
      "ablation_rate": 1.0
    },
    "review": {
      "disabled": true,
      "reason": "ablation_rate_ge_full",
      "full_rate": 1.0,
      "ablation_rate": 1.0
    },
    "caching": {
      "disabled": true,
      "reason": "ablation_rate_ge_full",
      "full_rate": 1.0,
      "ablation_rate": 1.0
    }
  },
  "website_maintenance": {
    "retrieval": {
      "disabled": false,
      "reason": "ablation_worsened_outcomes",
      "full_rate": 1.0,
      "ablation_rate": 0.0,
      "contribution": 1.0
    },
    "workflow_reuse": {
      "disabled": true,
      "reason": "ablation_rate_ge_full",
      "full_rate": 1.0,
      "ablation_rate": 1.0
    },
    "review": {
      "disabled": true,
      "reason": "ablation_rate_ge_full",
      "full_rate": 1.0,
      "ablation_rate": 1.0
    },
    "caching": {
      "disabled": true,
      "reason": "ablation_rate_ge_full",
      "full_rate": 1.0,
      "ablation_rate": 1.0
    }
  },
  "document_reporting": {
    "retrieval": {
      "disabled": false,
      "reason": "ablation_worsened_outcomes",
      "full_rate": 1.0,
      "ablation_rate": 0.0,
      "contribution": 1.0
    },
    "workflow_reuse": {
      "disabled": true,
      "reason": "ablation_rate_ge_full",
      "full_rate": 1.0,
      "ablation_rate": 1.0
    },
    "review": {
      "disabled": false,
      "reason": "ablation_worsened_outcomes",
      "full_rate": 1.0,
      "ablation_rate": 0.0,
      "contribution": 1.0
    },
    "caching": {
      "disabled": true,
      "reason": "ablation_rate_ge_full",
      "full_rate": 1.0,
      "ablation_rate": 1.0
    }
  }
}
```

## Claims (evidence-gated)

- **SUPPORTED** `repository_repair`: freeforge_correct_rate_exceeds_minimal_free_agent
- **SUPPORTED** `repository_repair`: freeforge_matches_manual_correctness_with_less_active_human_time
- **SUPPORTED** `repository_repair`: disable_retrieval_for_this_workload
- **SUPPORTED** `repository_repair`: disable_workflow_reuse_for_this_workload
- **SUPPORTED** `repository_repair`: disable_review_for_this_workload
- **SUPPORTED** `repository_repair`: disable_caching_for_this_workload
- **SUPPORTED** `website_maintenance`: freeforge_correct_rate_exceeds_minimal_free_agent
- **SUPPORTED** `website_maintenance`: freeforge_matches_manual_correctness_with_less_active_human_time
- **SUPPORTED** `website_maintenance`: retrieval_improves_correct_rate
- **SUPPORTED** `website_maintenance`: disable_workflow_reuse_for_this_workload
- **SUPPORTED** `website_maintenance`: disable_review_for_this_workload
- **SUPPORTED** `website_maintenance`: disable_caching_for_this_workload
- **SUPPORTED** `document_reporting`: freeforge_correct_rate_exceeds_minimal_free_agent
- **SUPPORTED** `document_reporting`: freeforge_matches_manual_correctness_with_less_active_human_time
- **SUPPORTED** `document_reporting`: retrieval_improves_correct_rate
- **SUPPORTED** `document_reporting`: disable_workflow_reuse_for_this_workload
- **SUPPORTED** `document_reporting`: review_improves_correct_rate
- **SUPPORTED** `document_reporting`: disable_caching_for_this_workload
- **UNSUPPORTED/UNMEASURED** `*`: competitor_claude_code_cursor_e2e
- **SUPPORTED** `document_reporting`: simplified_freeforge_preferred_or_tied

