# MAINFRAME product surfaces

Generated: `2026-10-06T19:30:49.803628+00:00`

Two optimized surfaces share the same free-only FreeForge core:

1. **Web** — websites and web applications (browser, connectors, site maintenance, static UI)
2. **Application** — desktop local package + store-market checklist (iOS/Android/desktop markets)

## Web

- Artifact: `C:\Users\levyz\OneDrive\Microsoft Copilot Chat Files\Documents\MAINFRAME\dist\web`
- Index: `C:\Users\levyz\OneDrive\Microsoft Copilot Chat Files\Documents\MAINFRAME\dist\web\index.html`
- Build: `python -m mainframe surfaces build-web`
- GitHub Pages: optional (not required)

## Application

- Artifact: `C:\Users\levyz\OneDrive\Microsoft Copilot Chat Files\Documents\MAINFRAME\dist\application`
- Build: `python -m mainframe surfaces build-app`
- App Store / Play uploads: **not performed**; see checklist for DOCUMENTED_NOT_TESTED items

## Optional GitHub Actions

- Workflow: `.github/workflows/surfaces.yml`
- Runs: https://github.com/levizigza/MAINFRAME/actions
- Optional Pages: https://levizigza.github.io/MAINFRAME/
- Hosted CI is **not** required to use MAINFRAME locally.

## Non-requirements

- Hosted CI, code-signing SaaS, cloud storage, public hosting, paid accounts
