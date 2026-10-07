# Local Windows build — no paid cloud GPU / signing SaaS required for core usefulness.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Src = Join-Path $Root ".cache" "vscode-src"
$Out = Join-Path (Split-Path $Root) "dist" "application" "workbench"

if (-not (Test-Path $Src)) {
    throw "Missing vscode source. Run fetch-vscode.ps1 then apply-overlay.ps1"
}

New-Item -ItemType Directory -Path $Out -Force | Out-Null
Push-Location $Src
try {
    Write-Host "npm ci (may take a long time)…"
    npm ci
    Write-Host "Building…"
    npm run compile
    # gulp vscode-win32-x64 is the usual packaging target when gulp is available
    if (Get-Command gulp -ErrorAction SilentlyContinue) {
        npx gulp vscode-win32-x64
    } else {
        Write-Host "gulp not on PATH — compile-only artifact; package with upstream gulp when ready."
    }
} finally {
    Pop-Location
}

@"
# FreeForge Workbench build artifact

Generated: $(Get-Date -Format o)
Host: Windows local build script
Upstream pin: see freeforge-workbench/PINS.json

About dialog must show FreeForge Workbench.
AI status: paused when Ollama unavailable.

Cold start timing: record manually in docs/eval/ide/metrics.json after first launch.
"@ | Set-Content (Join-Path $Out "BUILD_README.md") -Encoding UTF8

Copy-Item (Join-Path $Root "PINS.json") (Join-Path $Out "PINS.json") -Force
Copy-Item (Join-Path $Root "ThirdPartyNotices.txt") (Join-Path $Out "ThirdPartyNotices.txt") -Force
Write-Host "Staged notices + pins under $Out"
