# MAINFRAME minimal release

Release: `0.1.48`
Generated: `2026-10-06T19:03:53.753145+00:00`

## Zero fees vs physical resources

- **Zero fees:** no required paid account, trial, promo credit, hosted CI, code-signing service, cloud storage, or public hosting.
- **Physical:** electricity, CPU/GPU, disk, RAM, optional download bandwidth.

## Target platform (measured on this host)

- platform: `Windows-11-10.0.26200-SP0`
- ProductName: `Windows 10 Home` / DisplayVersion `25H2` / build `26200`
- Python: `3.12.4`

## Acceptance evidence

- Clean-install smoke: `PASS` (3/3)
- Backup then restore: `PASS`
- Migrate saved workflow + DB recovery: `PASS`
- Upgrade compatibility: `PASS`
- Startup register/remove: `PASS`
- Doctor included: `PASS`

## Documented but not tested on this host

- **DOCUMENTED_NOT_TESTED:** OpenClaw Gateway install/start (openclaw binary absent on packaging host)
- **DOCUMENTED_NOT_TESTED:** Docker Desktop install (not present; not required)
- **DOCUMENTED_NOT_TESTED:** Actual Windows logon Task Scheduler create (Access denied without elevation on this host; local FreeForge startup job register/remove verified instead)
- **DOCUMENTED_NOT_TESTED:** Actual Windows logon fire of MAINFRAME-LocalStatus task
- **DOCUMENTED_NOT_TESTED:** winget/choco Python installers (Python already present — commands refused)
- **DOCUMENTED_NOT_TESTED:** Code-signing a release binary (no signing service; source tree distribution only)
- **DOCUMENTED_NOT_TESTED:** Uploading package to cloud object storage or public hosting

## Artifacts

- Package tree: `C:\Users\levyz\OneDrive\Microsoft Copilot Chat Files\Documents\MAINFRAME\dist\release\mainframe-0.1.48`
- Pins: `PINNED_DEPENDENCIES.json` inside the package
- Setup: `SETUP.md` / Uninstall: `UNINSTALL.md`
- Report JSON: `docs/RELEASE.json`

## Local checks only

Hosted CI was not used. Code-signing services were not used. Cloud storage was not used. Public hosting was not used.
