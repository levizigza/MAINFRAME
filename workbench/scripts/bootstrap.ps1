# Clone pinned microsoft/vscode and apply FreeForge overlay (.workbench-build/, not committed).
param(
  [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)
$ErrorActionPreference = "Stop"
$pin = Get-Content (Join-Path $RepoRoot "workbench\PIN.json") -Raw | ConvertFrom-Json
$tag = $pin.upstream.tag
$cloneDir = Join-Path $RepoRoot $pin.build.clone_dir
Write-Host "pin=$tag clone=$cloneDir"
New-Item -ItemType Directory -Force -Path (Split-Path $cloneDir) | Out-Null
if (-not (Test-Path (Join-Path $cloneDir ".git"))) {
  git clone --depth 1 --branch $tag $pin.upstream.repo $cloneDir
} else {
  Push-Location $cloneDir
  git fetch --depth 1 origin "refs/tags/$tag`:refs/tags/$tag"
  git checkout $tag
  Pop-Location
}
$dest = Join-Path $cloneDir "src\vs\workbench\contrib\freeforge"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Copy-Item -Path (Join-Path $RepoRoot "workbench\overlay\freeforge\*") -Destination $dest -Recurse -Force
Write-Host "overlay_applied=$dest"
Write-Host "ok=true"
