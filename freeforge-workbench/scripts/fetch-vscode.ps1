# Fetch pinned microsoft/vscode tag (Windows). No paid cloud GPU.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Pins = Get-Content (Join-Path $Root "PINS.json") -Raw | ConvertFrom-Json
$Tag = $Pins.tag
$Dest = Join-Path $Root ".cache" "vscode-src"

Write-Host "FreeForge Workbench: fetching microsoft/vscode@$Tag"
if (-not (Test-Path $Dest)) {
    New-Item -ItemType Directory -Path (Split-Path $Dest) -Force | Out-Null
    git clone --depth 1 --branch $Tag https://github.com/microsoft/vscode.git $Dest
} else {
    Write-Host "Already present: $Dest"
}

# Retain upstream ThirdPartyNotices
$UpstreamNotice = Join-Path $Dest "ThirdPartyNotices.txt"
if (Test-Path $UpstreamNotice) {
    Copy-Item $UpstreamNotice (Join-Path $Root "ThirdPartyNotices.vscode.txt") -Force
}

Write-Host "Verify Electron/Node in upstream package.json against PINS.json"
Get-Content (Join-Path $Dest "package.json") | Select-String -Pattern '"electron"|"node"' | Select-Object -First 20
