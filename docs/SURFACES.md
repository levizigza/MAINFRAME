# MAINFRAME product surfaces

Generated: `2026-10-07T02:51:09.669092+00:00`

Two optimized surfaces share the same free-only FreeForge core:

1. **Web** — websites and web applications (browser, connectors, site maintenance, static UI)
2. **Application** — desktop local package + store-market checklist (iOS/Android/desktop markets)

## Web

- Artifact: `/workspace/dist/web`
- Index: `/workspace/dist/web/index.html`
- Build: `python -m mainframe surfaces build-web`
- GitHub Pages: optional (not required)

## Application

- Artifact: `/workspace/dist/application`
- Build: `python -m mainframe surfaces build-app`
- App Store / Play uploads: **not performed**; see checklist for DOCUMENTED_NOT_TESTED items

## Optional GitHub Actions

- Workflow: `.github/workflows/surfaces.yml`
- Runs: https://github.com/levizigza/MAINFRAME/actions
- Optional Pages: https://levizigza.github.io/MAINFRAME/
- Hosted CI is **not** required to use MAINFRAME locally.

## Non-requirements

- Hosted CI, code-signing SaaS, cloud storage, public hosting, paid accounts
