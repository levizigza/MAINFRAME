# MAINFRAME

Open-source **coding and automation** that runs on your existing Windows PC with **zero required** software, API, subscription, or hosting fees.

Existing hardware, electricity, and internet are physical prerequisites — not things this software makes free. No GPU purchase. No paid accounts, trials, or paid fallbacks.

## Requirements

- Python 3.11+ already on the machine (stdlib only for core)
- Optional: local [Ollama](https://ollama.com) for free on-device inference — **not required**

## Quick start

```powershell
cd MAINFRAME
python -m mainframe status
python -m mainframe inspect
python -m mainframe tasks
python -m mainframe run echo --param message=hello
python -m mainframe ai probe
python -m mainframe audit
python -m mainframe scorecard
python -m mainframe freeforge spike
python -m mainframe doctor
python -m mainframe gate
python -m mainframe demo
python -m mainframe accept
python -m mainframe release accept
python -m mainframe recommend accept
python -m mainframe surfaces accept
cd freeforge-cli; npm install; npm run accept
```

TypeScript FreeForge CLI (OpenClaw adapter): see [`freeforge-cli/README.md`](freeforge-cli/README.md).

Minimal local release package (pins, SETUP, uninstall): `python -m mainframe release run` → `dist/release/` + [`docs/RELEASE.md`](docs/RELEASE.md).

**Product surfaces:** web (sites/webapps) vs application (desktop + store markets) — `python -m mainframe surfaces accept` → [`docs/SURFACES.md`](docs/SURFACES.md). Optional GitHub Actions: https://github.com/levizigza/MAINFRAME/actions (not required locally).

No `pip install` is required for core commands.

## Principles

| Rule | Behavior |
|------|----------|
| Deterministic first | Automation works with AI offline |
| Free-only AI | Loopback Ollama only; pauses if unavailable; disabled routes hard-refuse |
| Preserve work | `.mainframe/user_notes.md` and user files are kept |
| Honest checks | Never invents successful tests or live account results |
| Progress log | Every increment recorded in `docs/PROGRESS.md` |
| Dependency audit | `python -m mainframe audit` + `docs/DEPENDENCIES.md` |

## Layout

```
.cursor/rules/     Persistent agent rules (always apply)
mainframe/         Stdlib Python package (CLI + automation + optional AI)
docs/              Architecture and progress log
.mainframe/        Local state (created on first run; user notes preserved)
```

## License

MIT — see [LICENSE](LICENSE).
