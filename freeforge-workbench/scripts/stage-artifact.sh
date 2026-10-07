#!/usr/bin/env bash
# Stage workbench pin/overlay pointers into dist/application/workbench (no Electron).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$(cd "$ROOT/.." && pwd)/dist/application/workbench"
mkdir -p "$OUT"
cp "$ROOT/PINS.json" "$OUT/PINS.json"
cp "$ROOT/ThirdPartyNotices.txt" "$OUT/ThirdPartyNotices.txt"
cp "$ROOT/README.md" "$OUT/README_WORKBENCH.md"
cat > "$OUT/README.md" <<EOF
# FreeForge Workbench application artifact

Staged from \`freeforge-workbench/\` without a full Electron compile on this host.

- Pin: see PINS.json
- Overlay sources: freeforge-workbench/overlay/
- Windows build: freeforge-workbench/scripts/build-windows.ps1
- Electron cold-start: unknown until measured on Windows

Python twin: \`python -m mainframe workbench status\`
EOF
echo "Staged $OUT"
