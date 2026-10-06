# MAINFRAME dependency & migration table

Strict free-only contract. Disabled components are **refused in code** (`mainframe/eligibility.py`, `mainframe/ai/rejected.py`) — not merely omitted from settings. There is **no automatic paid/trial/hosted fallback**.

Generate live JSON: `python -m mainframe audit`

| Component | Status | Purpose | License | Actual cost conditions | Replacement | Affected behavior |
|-----------|--------|---------|---------|------------------------|-------------|-------------------|
| `python_stdlib_cli` | eligible | CLI, config, automation, inspect, accept | MIT + PSF | No fee; installed Python | n/a | Works offline |
| `local_state_files` | eligible | `.mainframe/` config, notes, run logs | User data + MIT | Local disk only | n/a | Replaces cloud DB/storage |
| `ollama_local` | eligible | Optional loopback inference via native `/api/chat` (OpenClaw-aligned; no `/v1`) | Ollama MIT; models vary | No account for local use; explicit pull; `:cloud` refused | n/a | `ai` / `local-model` when model present |
| `llamacpp_local` | eligible | Optional llama.cpp server on loopback | MIT + GGUF licenses vary | Optional; user GGUF; not required | pause | `local-model` when server present |
| `openai_api` | disabled | Hosted chat/completions | Proprietary | Paid / promo tiers | `ollama_local` or pause | Hard refuse; no fallback |
| `anthropic_api` | disabled | Hosted Claude | Proprietary | Paid / trials | pause / local | Hard refuse |
| `azure_openai` | disabled | Azure-hosted OpenAI | Cloud contract | Azure billing | pause / local | Hard refuse |
| `google_gemini_api` | disabled | Hosted Gemini (investigated; unpaid data terms + billing unlock) | Proprietary | Unverifiable recurring free | pause / local | Fixture only; `unverified_live` |
| `aws_bedrock` | disabled | Hosted FMs | AWS | AWS billing | pause / local | Hard refuse |
| `groq_cloud` | disabled | Hosted GroqCloud (investigated; upgrade path + prices) | Proprietary | Unverifiable recurring free | pause / local | Fixture only; `unverified_live` |
| `mistral_api` | disabled | Mistral La Plateforme (investigated; Free→pay-as-you-go) | Proprietary | Unverifiable recurring free | pause / local | Fixture only; `unverified_live` |
| `together_fireworks_replicate` | disabled | Model marketplaces | Proprietary | Paid / trial | pause / local | Hard refuse |
| `hf_inference_api` | disabled | HF hosted inference | Service ToS | Hosted may bill | local weights via Ollama | Remote API disabled |
| `cloud_databases` | disabled | Supabase/Firebase/Atlas/etc. | Vendor SaaS | Hosted; promo tiers | `.mainframe/` files | No cloud DB clients |
| `remote_execution` | disabled | Cloud runners / remote agents | Vendor SaaS | Billed minutes | local `python -m mainframe` | No remote exec hooks |
| `analytics_telemetry` | disabled | Sentry/Segment/PostHog/etc. | Vendor SaaS | Paid after trial | `.mainframe/runs/` | No outbound analytics |
| `hosted_search` | disabled | Algolia/Elastic Cloud/etc. | Vendor SaaS | Paid / trial | local inspect / list-tree | No hosted search |
| `cloud_object_storage` | disabled | S3/GCS/Azure Blob | Cloud vendor | Storage + egress | local filesystem | No cloud storage SDKs |
| `pip_pypi_required_deps` | disabled | Required paid/network packages for core | n/a | Core must launch without them | stdlib only | No install to launch |
| `sqlite_fts5_local` | eligible | Optional local FTS5 lexical index for issue→code retrieval | SQLite/PD | Free local; enabled only if accept measures improvement | exact/identifier/stack lexical ranking | `retrieve`; default off when ablation shows no gain |
| `remote_vector_db` | disabled | Hosted vector / embedding search | Vendor SaaS | Paid / trial common | local retrieve (exact + lexical ± FTS5) | Hard refuse — not wired |
| `paid_embedding_api` | disabled | Cloud embedding endpoints | Vendor API | Billed tokens | local cues / FTS5 | Hard refuse — not wired |
| `stdlib_ast_codeintel` | eligible | Python defs/refs/imports/callers via ast | PSF | Free; always available | n/a | `codeintel` core path |
| `jedi_optional` | eligible | Optional goto/signatures when already installed | MIT | Free local; not required to launch | `stdlib_ast_codeintel` | Used if importable |
| `pyright_optional` | eligible | Optional diagnostics when already on PATH | Pyright license | Free local; not required | AST-only without diags | Used if available |
| `local_quota_ledger` | eligible | Local admit/reserve/reconcile for requests/tokens/context/concurrency | MIT | Local disk only; no account rotation | n/a | `quota` CLI; persists under `.mainframe/quota_ledger.sqlite` |
| `model_eval_routing` | eligible | Holdout eval + capability matrix + measured routing | MIT | Local fixtures; live only if eligible runtime | n/a | `modeleval`; routes invalidate on fingerprint change |
| `adaptive_controller` | eligible | Deterministic / direct / plan-review task control with budgets | MIT | Local; no CoT required | n/a | `controller` CLI |
| `coding_loop` | eligible | Selected-engine lifecycle: contracts→retrieve→patch→verify | MIT | Local; no nested supervisor | n/a | `codingloop` CLI |
| `change_review` | eligible | Deterministic-first gated review; no-gain routes disabled | MIT | Local; model call only when gate justifies | n/a | `review` CLI |
| `exact_reuse_cache` | eligible | Exact caches for scan/retrieve/tools/workflows/model; project-isolated | MIT | Local SQLite under `.mainframe/cache/` | n/a | `cache` CLI |
| `durable_tasks` | eligible | Durable transitions/leases/receipts; FreeForge↔engine status reconcile | MIT | Local SQLite; no WS replay assumption | n/a | `durable` CLI |
| `exec_boundaries` | eligible | Path/process/env/network/resource boundaries; Windows Job Object when verified | MIT | Zero-fee OS Job Object on Windows; policy network deny | n/a | `boundaries` CLI |
| `secret_untrusted_data` | eligible | DPAPI secrets, scoped adapters, redaction, untrusted provenance, SSRF guards | MIT | Local DPAPI/user-scope; no cloud KMS | n/a | `secretdata` CLI |
| `scoped_capabilities` | eligible | Project-scoped grants (read/edit/tests/browse/messages/publish/delete), holds, revoke, emergency stop | MIT | Local SQLite grants/queue; schedules do not expand authority | n/a | `capabilities` CLI |
| `playwright_browser_tools` | eligible | Playwright navigation/locators/DOM/screenshots/downloads/asserts; per-project profiles | MIT | Local Chromium via Playwright; no cloud browser | n/a | `browser` CLI |
| `coding_benchmark_holdout` | eligible | Held-out coding tasks; minimal vs FreeForge harness; raw local JSON | MIT | Fixture agents + optional eligible live (opt-in) | n/a | `codingbench` CLI |
| `versioned_workflows` | eligible | Versioned workflow graph (typed I/O, deps, loops, retries); FreeForge receipts | MIT | Local fixture runner; OpenClaw scheduling/session not duplicated | n/a | `workflow` CLI |
| `workflow_resilience` | eligible | Step checkpoints, retry/reconcile, cancel, concurrency, effect receipts; atomic local writes | MIT | Local SQLite receipts; no paid broker | n/a | `workflow accept-resilience` |
| `workflow_typed_ai` | eligible | Typed AI steps (extract/classify/summarize/propose_code); evidence checks; interactive quota | MIT | Eligibility + local quota ledger; cache exact model responses | n/a | `workflow accept-ai` |
| `openclaw_schedule_integration` | eligible | OpenClaw `--command-argv` payloads; FreeForge cost gate; deterministic fire | MIT | OpenClaw Gateway sole scheduler when present; local dispatcher when deferred | n/a | `schedule` CLI |
| `event_triggers` | eligible | File/repo/local-webhook/bounded-poll triggers; typed events; bound jobs | MIT | Loopback webhook only; no paid tunnel; poll/manual when inbound unavailable | n/a | `triggers` CLI |
| `public_apis_discovery` | eligible | Pinned public-apis snapshot discovery + shortlist evidence/activation states | MIT (catalog) | Local snapshot; no auto-free; ads confer no entitlement | n/a | `discovery` CLI |
| `api_connectors_readonly` | eligible | Read-only connectors from documented endpoints; fixtures; tool exposure | MIT | No key APIs (dog.ceo, Open-Meteo, Frankfurter); fixtures offline | n/a | `connectors` CLI |
| `document_to_report` | eligible | Local ingest→extract→validate→dedupe→CSV/report; optional Tesseract | MIT | Stdlib parsers; Tesseract optional on PATH; no external auto-post | n/a | `docreport` CLI |
| `workflow_promotion` | eligible | Promote accepted traces to deterministic programs; untrusted until tested | MIT | Local only; allowlisted handlers; no training | n/a | `promote` CLI |
| `visual_bridge` | eligible | Optional loopback form to edit/invoke FreeForge; Node-RED optional export | MIT + Apache-2.0 (NR if used) | Form is stdlib; Node-RED not required; no paid nodes | n/a | `visual` CLI |
| `fault_injection_matrix` | eligible | Local fault-injection scenarios + published failure matrix; connector gate | MIT | Deterministic fixtures only; no hosted CI | n/a | `faults` CLI |
| `editor_bridge` | eligible | VS Code extension + shared CLI task state; Void reference only | MIT (ext); Void Apache-2.0 not vendored | No Void workbench copy; completion only if eligible local model | optional Void/vscode fork | `editor` CLI + `extensions/freeforge-editor` |
| `local_dashboard` | eligible | Loopback dashboard: status, history, quota, decisions, artifacts, stop/resume | MIT | Local inbox notify; OpenClaw messaging gated off until verified | n/a | `dashboard` CLI |
| `project_isolation` | eligible | Per-project workspaces, memory, cache, secrets, browser profiles, artifacts, grants | MIT | Explicit project_id binding; local-only pause; export scrub; no secure-erase claim | n/a | `project` CLI |
| `heldout_workload_eval` | eligible | Held-out repair/site/docreport vs minimal+manual; ablations; Wilson CIs | MIT | Local fixtures only; competitors unmeasured without purchase | n/a | `workload-eval` CLI |
| `reproducible_cost_audit` | eligible | Cost audit: surfaces, outbound proofs, hosted-gone sim; boundary disables | MIT | Zero software fees ≠ free electricity/CPU/disk; live non-loopback off without OS net jail | n/a | `cost-audit` CLI |
| `minimal_local_release` | eligible | Pinned release tree, doctor, backup/restore, migrate, upgrade check, removable startup | MIT | Local dist/ only; no hosted CI, signing service, cloud storage, or public hosting required | n/a | `release` CLI |
| `freeforge_recommended_config` | eligible | Evidence-based modes A/B/C, capability matrix, measured demos | MIT | Mode C empty until hosted entitlement verified; Mode B pauses without local model | n/a | `recommend` CLI |
| `dual_product_surfaces` | eligible | Web (sites/webapps) + application (desktop/store checklist) packages | MIT | Optional GH Actions/Pages; store uploads not required; local builds authoritative | n/a | `surfaces` CLI |

## Migration notes

- Prior `mainframe/ai` Ollama probe/generate **retained** as `ollama_adapter.py` behind the eligibility gate; now routes through native `/api/chat` and excludes `:cloud` models.
- Optional `llamacpp_local` adapter retained behind the same eligibility gate (loopback `/health` + `/completion`).
- Automation, workspace inspect, and accept suites were **extended**, not rebuilt.
- Config keys resembling credentials are **stripped on load**; non-loopback AI URLs are **rejected** (rewritten to loopback and recorded under `ollama_base_url_rejected`).
- Hosted Groq/Gemini/Mistral investigated as candidates (see `docs/PROVIDERS.md`); live dispatch remains **disabled** (`unverified_live` fixtures only) until a verified recurring-free entitlement exists.
- Provider API credentials, if ever stored, live only under `.mainframe/credentials/` (broker) — never in `config.json`.
- Selecting a disabled provider via config resets active provider to `ollama_local` and records `provider_refused` — the disabled route remains invocable only as an explicit refuse for audit (`python -m mainframe ai refuse openai_api`).
