# Mode B — local CPU AI onboarding (Windows)

FreeForge Workbench coding quality depends on a **fitted local model**. No MAINFRAME account. No paid API.

## Prerequisites (this host pattern)

- Windows PC with enough free RAM (doctor reports `optional_cpu_inference.ram_budget_gib`)
- User installs [Ollama](https://ollama.com) themselves (free software)
- MAINFRAME never auto-downloads large weights without an explicit user command

## Steps

```powershell
# 1) Install Ollama from https://ollama.com (user action) and ensure it is on PATH
ollama --version

# 2) Fit recommendation from measurements (no download)
python -m mainframe doctor
python -m mainframe workbench model-fit

# 3) Explicit pull of a recommended small/mid model (example — follow doctor output)
# ollama pull qwen2.5-coder:3b
# or: ollama pull llama3.2:3b

# 4) Verify loopback inference
python -m mainframe ai probe
python -m mainframe local-model status

# 5) Live quality (only when probe is available)
python -m mainframe modeleval run --live
python -m mainframe codingbench run --live
```

## When AI is unavailable

- Workbench editing, terminal, SCM, and deterministic CLI continue.
- Agent chat shows **paused** — no paid fallback, no trial upsell.

## Physical costs (not software fees)

Electricity, CPU time, disk for weights, and RAM pressure remain yours. That is required for free local intelligence.
