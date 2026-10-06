# Doctor (Windows target)

```powershell
python -m mainframe doctor
```

Measures **this process's host view**: RAM, CPU, free disk, runtimes (Python/Node/Git/rg), shell behavior, browsers/Playwright. Detects container/remote-dev contexts and **will not** treat those measurements as the user's physical PC.

Also emits:

- Resource limits for indexing, browser workers, tests, optional CPU inference
- Model **fit estimates** (weights + KV estimate + overhead) verified against **measured** RAM/budget — throughput stays `unmeasured`; **no downloads**
- Startup / sleep / offline limitations for background jobs
- `docker_desktop.required_for_core: false`

Doctor never exposes secrets, enables startup tasks, or claims unmeasured performance.
