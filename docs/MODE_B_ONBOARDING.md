# Mode B — local CPU AI onboarding (Windows)

FreeForge coding quality needs a **fitted local model**. No MAINFRAME account. No paid API.

```powershell
# 1) Install Ollama from https://ollama.com — ensure on PATH
ollama --version

# 2) Fit recommendation (no download)
python -m mainframe doctor
python -m mainframe workbench model-fit

# 3) Explicit pull (follow doctor / model-fit output), e.g.:
# ollama pull qwen2.5-coder:3b

# 4) Verify
python -m mainframe ai probe
python -m mainframe local-model status

# 5) Live quality when probe is available
python -m mainframe modeleval run --live
python -m mainframe codingbench run --live
```

When AI is unavailable: editing and deterministic CLI continue; agent chat shows **paused** — no paid fallback.

Physical costs (electricity, CPU, disk for weights) remain yours.
