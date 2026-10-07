# Clone pinned microsoft/vscode into .workbench-build/vscode (not committed).
param(
  [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)

$ErrorActionPreference = "Stop"
$pinPath = Join-Path $RepoRoot "workbench\PIN.json"
$pin = Get-Content $pinPath -Raw | ConvertFrom-Json
$tag = $pin.upstream.tag
$cloneDir = Join-Path $RepoRoot $pin.build.clone_dir

Write-Host "FreeForge workbench bootstrap"
Write-Host "  pin tag: $tag"
Write-Host "  clone:   $cloneDir"

New-Item -ItemType Directory -Force -Path (Split-Path $cloneDir) | Out-Null

if (-not (Test-Path (Join-Path $cloneDir ".git"))) {
  git clone --depth 1 --branch $tag $pin.upstream.repo $cloneDir
} else {
  Push-Location $cloneDir
  git fetch --depth 1 origin tag $tag
  git checkout $tag
  Pop-Location
}

$overlaySrc = Join-Path $RepoRoot "workbench\overlay\freeforge"
$overlayDest = Join-Path $cloneDir "src\vs\workbench\contrib\freeforge"
New-Item -ItemType Directory -Force -Path $overlayDest | Out-Null
Copy-Item -Path (Join-Path $overlaySrc "*") -Destination $overlayDest -Recurse -Force

Write-Host "Overlay applied to $overlayDest"
Write-Host "Next: follow vscode build docs inside clone (yarn/npm). Hosted CI not required."
Write-Host '{"ok":true,"tag":"' + $tag + '","clone":"' + ($cloneDir -replace '\\','/') + '"}'
