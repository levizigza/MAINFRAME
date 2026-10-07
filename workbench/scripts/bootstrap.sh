#!/usr/bin/env bash
# Clone pinned microsoft/vscode and apply FreeForge overlay (local; hosted CI not required).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PIN="$ROOT/workbench/PIN.json"
TAG="$(python3 -c "import json; print(json.load(open('$PIN'))['upstream']['tag'])")"
REPO="$(python3 -c "import json; print(json.load(open('$PIN'))['upstream']['repo'])")"
CLONE_REL="$(python3 -c "import json; print(json.load(open('$PIN'))['build']['clone_dir'])")"
CLONE="$ROOT/$CLONE_REL"

echo "FreeForge workbench bootstrap"
echo "  pin tag: $TAG"
echo "  clone:   $CLONE"

mkdir -p "$(dirname "$CLONE")"
if [[ ! -d "$CLONE/.git" ]]; then
  git clone --depth 1 --branch "$TAG" "$REPO" "$CLONE"
else
  git -C "$CLONE" fetch --depth 1 origin "tag" "$TAG" || true
  git -C "$CLONE" checkout "$TAG" || true
fi

DEST="$CLONE/src/vs/workbench/contrib/freeforge"
mkdir -p "$DEST"
cp -a "$ROOT/workbench/overlay/freeforge/." "$DEST/"
echo "Overlay applied to $DEST"
echo "{\"ok\":true,\"tag\":\"$TAG\",\"clone\":\"$CLONE\"}"
