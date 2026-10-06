# Failure matrix — fault injection (local deterministic)

Integration fixtures only. Live service observations are separate and must not be fabricated.

- Passed: **11** / Failed: **0**
- Hosting: `local_deterministic_no_hosted_ci`
- Allow more connectors: **True**

| Scenario | Class | Expected recovery | Actual recovery | Pass |
|----------|-------|-------------------|-----------------|------|
| `duplicate_events` | integration_fixture | `one_run_duplicate_suppressed` | `one_run_duplicate_suppressed` | PASS |
| `clock_changes` | integration_fixture | `record_anomaly_defer_catchup_to_scheduler_owner` | `record_anomaly_defer_catchup_to_scheduler_owner` | PASS |
| `interrupted_files` | integration_fixture | `discard_tmp_atomic_complete_no_corruption` | `discard_tmp_atomic_complete_no_corruption` | PASS |
| `process_crashes` | integration_fixture | `resume_suppress_duplicate_write_effect` | `resume_suppress_duplicate_write_effect` | PASS |
| `service_timeouts` | integration_fixture | `no_blind_retry_reconcile_or_unknown` | `no_blind_retry_reconcile_or_unknown` | PASS |
| `malformed_model_output` | integration_fixture | `reject_unsupported_no_side_effect` | `reject_unsupported_no_side_effect` | PASS |
| `expired_credentials` | integration_fixture | `refuse_use_require_refresh_or_pause` | `refuse_use_require_refresh_or_pause` | PASS |
| `exhausted_free_quotas` | integration_fixture | `pause_no_paid_fallback` | `pause_no_paid_fallback` | PASS |
| `lost_acknowledgement_external_write` | integration_fixture | `outcome_unknown_visible_no_blind_retry` | `outcome_unknown_visible_no_blind_retry` | PASS |
| `cancellation_completed_effects_recorded` | integration_fixture | `cancel_blocks_new_effects_completed_remain` | `cancel_blocks_new_effects_completed_remain` | PASS |
| `unauthorized_actions_and_paid_fallback` | integration_fixture | `deny_no_paid_fallback` | `deny_no_paid_fallback` | PASS |

## Connector gate

Fix data loss, duplicate effects, unauthorized actions, and paid fallback paths before adding more connectors.

```json
{
  "data_loss": true,
  "duplicate_effects": true,
  "unauthorized_actions": true,
  "paid_fallback": true,
  "allow_more_connectors": true
}
```
