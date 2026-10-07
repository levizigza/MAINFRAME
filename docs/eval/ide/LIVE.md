# Live IDE / coding quality (Mode B)

Run only after Ollama is installed and a fitted model is pulled (`docs/MODE_B_ONBOARDING.md`).

| Cell | Status | How to fill |
|------|--------|-------------|
| `ai probe` | Fill when available | `python -m mainframe ai probe` |
| `modeleval --live` | **unknown** until run | `python -m mainframe modeleval run --live` |
| `codingbench --live` | **unknown** until run | `python -m mainframe codingbench run --live` |
| Workbench cold start (Windows Electron) | **unknown** until timed locally | Launch from `.workbench-build/vscode` after full build |
| vs Cursor / Claude Code | **unknown** | Optional user-run trial; never invent |

Do not mark these PASS in CI without observed output.
