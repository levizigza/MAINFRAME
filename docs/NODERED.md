# Node-RED evaluation (optional visual interface)

**Verdict (2026-09-29):** Node-RED is **optional and not required**. For FreeForge edit/invoke, a **simple local loopback form** (`python -m mainframe visual serve`) is sufficient. Do not install Node-RED as a second automation stack.

## Core license (verified)

| Item | Value |
|------|-------|
| Package | `node-red` (npm) |
| License | **Apache-2.0** |
| Copyright | OpenJS Foundation and other contributors |
| Source | https://github.com/node-red/node-red/blob/HEAD/LICENSE |
| Local runtime fee | None (user's Node.js) |
| Hosted service required | No |
| Account for local use | No |

Bundled `@node-red/*` packages (`editor-api`, `nodes`, `runtime`, `util`) are likewise Apache-2.0 on npm for the core line observed.

## Additional nodes

MAINFRAME's bridge **requires zero** palette nodes. Any third-party node must be license- and cost-audited before use (licenses vary; some connectors imply paid SaaS). Paid/cloud palette nodes are out of posture for required paths.

## Ownership rules when Node-RED is present

- **Scheduler owner:** `openclaw_gateway` (FreeForge command policy) — Node-RED must not independently cron/inject-repeat the same FreeForge workflow trigger.
- **Effect ledger:** FreeForge workflow receipts — Node-RED only invokes the bridge.
- **Secrets:** Outside exported flows (`secret_ref:` + `LocalSecretFacility`).

Optional export: `GET /api/export-nodered` produces a manual-only inject (empty `repeat`/`crontab`) that HTTP-POSTs to the FreeForge bridge.

## Remotion

Stop/uninstall the visual server or delete `mainframe/visual` usage. Saved workflows remain under `.mainframe/workflows/`; scheduled execution remains on the existing schedule path.
