# Local offline demonstrations

Labeled **non-AI deterministic automation** (not model reasoning):

1. **Repository inspect + test** — `docs/demo/fixtures/repo_inspect/`
2. **Records → validated report** — `docs/demo/fixtures/records_report/`
3. **Browser interaction on local HTML** — `docs/demo/fixtures/browser_local/`

Plus **mock-inference issue→patch** using the shared tool broker (`read_file` / `apply_patch` / `run_tests`). Model output is scripted; filesystem edits and test results are real.

```powershell
python -m mainframe demo
```

Runs with external network disabled (loopback only). Includes failure, cancellation, and honest AI-pause paths.
