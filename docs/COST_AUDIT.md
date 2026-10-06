# MAINFRAME reproducible cost audit

Generated: `2026-10-06T18:57:14.576309+00:00`

## Separation: zero fees vs physical resources

- **Zero fees (software contract):** no required paid account, trial, promotional credit, or hosted SaaS for core.
- **Physical resources (not fees):** electricity, local CPU/GPU, disk, RAM, and optional bandwidth for user-chosen downloads remain user-borne.

## Acceptance checklist

- `PASS` **no_required_paid_account**
- `PASS` **no_trial_or_promo_required**
- `PASS` **no_required_hosted_component**
- `PASS` **zero_fees_separated_from_physical_resources**
- `PASS` **outbound_controls_proven**
- `PASS` **paths_outside_enforceable_boundary_handled**
- `PASS` **deterministic_usable_when_hosted_gone**
- `PASS` **ai_pauses_without_local_model**
- `PASS` **no_automatic_paid_fallback**

## Network boundary honesty

- OS network isolation: `False`
- Application policy alone constrains arbitrary processes: `False`
- Note: Application-level policy cannot constrain arbitrary processes that already have network access. Non-loopback live outbound is disabled unless OS network isolation is verified on this host.

## Hosted-gone / became-paid simulation

- Hosted providers refused: `True`
- AI probe: `paused`
- Deterministic echo usable: `True`
- No automatic paid fallback: `True`

## Outbound control proofs

- `PASS` `inference:openai_api`
- `PASS` `inference:anthropic_api`
- `PASS` `inference:groq_cloud`
- `PASS` `openclaw_messaging`
- `PASS` `openclaw_command_payload`
- `PASS` `non_loopback_live`
- `PASS` `loopback_inference`
- `PASS` `notification_defaults`

## Surfaces

- `PASS` **installation** — hidden_paid=`False`
- `PASS` **inference** — hidden_paid=`False`
- `PASS` **search** — hidden_paid=`False`
- `PASS` **storage** — hidden_paid=`False`
- `PASS` **runtime** — hidden_paid=`False`
- `PASS` **browser_use** — hidden_paid=`False`
- `PASS` **ci** — hidden_paid=`False`
- `PASS` **notifications** — hidden_paid=`False`
- `PASS` **plugins** — hidden_paid=`False`
- `PASS` **backups** — hidden_paid=`False`
- `PASS` **distribution** — hidden_paid=`False`

