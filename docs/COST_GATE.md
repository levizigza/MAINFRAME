# Cost & capability gate — enforcement boundary

Central module: `mainframe/cost_gate.py` (Python) and `freeforge-cli/src/costGate.ts` (TypeScript mirror).

## Boundary

**Before dispatch** of any of the following, callers must obtain an allow decision from `authorize()` / `authorize({...})`:

| Capability | Examples |
|------------|----------|
| inference | Completions, chat, embeddings |
| connector | Third-party SaaS connectors |
| search | Hosted search APIs |
| storage | Cloud object/DB storage |
| remote_execution | Cloud runners / remote sandboxes |
| tool | Named tools (including newly chargeable tools) |
| auxiliary | Retries, summaries, nested/helper model calls |

Fail-closed: unknown targets and unknown pricing are denied.

## Local zero-fee (eligible without entitlement file)

- Loopback inference (e.g. Ollama on `127.0.0.1`)
- Local filesystem / FreeForge SQLite
- Local command execution via FreeForge adapter
- Deterministic MAINFRAME automation

No external account is assumed for these paths.

## External operations

Require a **current verified free entitlement** in `.mainframe/entitlements.json` with:

- `pricing_known: true`
- `billing_dependency: false` and `paid_subscription_dependency: false`
- `trial: false`, `promotional: false`
- `allows_paid_overage: false`, `allows_automatic_upgrade: false`
- `zero_token_price_only: false` (a $0 token price alone is **not** zero-cost)
- `expires_at` in the future

Default file ships with **zero** entitlements — all external routes denied.

## Hard denials (before dispatch)

- Fake/real paid endpoint hosts (OpenAI, Anthropic, cloud AI, etc.)
- Paid / frontier **model aliases** (`gpt-4o`, `claude-3-5-sonnet`, …)
- Newly chargeable tool ids (`web_search_paid`, `s3_upload`, …)
- Expired or invalid entitlement evidence
- Unknown pricing, trials, promotional access, paid overages, automatic upgrades

## No silent spending switch

Environment variables such as `ENABLE_SPENDING`, `ALLOW_PAID`, `FORCE_PAID`, `AUTO_UPGRADE` are **detected and ignored**. Their presence causes **deny**, not unlock. There is no config flag that flips the core into a spending mode.

## Credentials & child processes

`scrub_env_for_child` / `scrubEnvForChild` strip credential-shaped env keys and spending switches before spawning untrusted children (FreeForge local command adapter).

## External account assumptions

- MAINFRAME/FreeForge core **does not** create or bill cloud accounts.
- Any future external free entitlement must be human-verified and recorded explicitly; marketing “free tier” copy is insufficient.
- OpenClaw Gateway, when used, remains subject to the same gate for model/tool dispatch FreeForge initiates; OpenClaw’s private DB is never used as a spend bypass.

## Commands

```powershell
python -m mainframe gate
python -m mainframe accept
```
