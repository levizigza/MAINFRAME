# FreeForge TypeScript CLI

Minimal CLI + OpenClaw adapter bootstrap (pinned OpenClaw **v2026.9.6**).

```powershell
cd freeforge-cli
npm install
npm run ff -- doctor
npm run ff -- run -- cmd /c echo hello
npm run ff -- status
npm run accept
```

## Commands

| Command | Purpose |
|---------|---------|
| `doctor` | Policy, SQLite, OpenClaw supported-interface probe |
| `run -- <cmd>` | Local command via adapter; FreeForge receipts |
| `workflows` | List/run named workflows |
| `status [taskId]` | Recover task state from FreeForge SQLite |
| `resume <taskId>` | Resume/recover after process restart |
| `eval` | Built-in eval |
| `serve-status` | Loopback HTTP + bearer auth |

Unimplemented commands print `{ "unsupported": true }` and exit 2.

## Ownership

- Schedule / local effects / FreeForge SQLite: **FreeForge**
- Model loop: **OpenClaw embedded** (when enabled; disabled background calls by policy)
- OpenClaw private DB: **never modified**

## Policy defaults

No paid credentials, no background model calls, no paid defaults, no automatic outbound delivery. Listeners bind `127.0.0.1` with a local bearer token (`.mainframe/freeforge-loopback.auth`).
