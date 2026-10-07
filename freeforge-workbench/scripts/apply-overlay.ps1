# Copy FreeForge overlay into vscode tree + product branding patch.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Src = Join-Path $Root ".cache" "vscode-src"
if (-not (Test-Path $Src)) {
    throw "Missing vscode source. Run fetch-vscode.ps1 first."
}

$Overlay = Join-Path $Root "overlay" "src" "vs" "workbench" "contrib" "freeforge"
$Target = Join-Path $Src "src" "vs" "workbench" "contrib" "freeforge"
New-Item -ItemType Directory -Path (Split-Path $Target) -Force | Out-Null
if (Test-Path $Target) { Remove-Item -Recurse -Force $Target }
Copy-Item -Recurse $Overlay $Target

$Patch = Get-Content (Join-Path $Root "overlay" "product.json.patch.json") -Raw | ConvertFrom-Json
$ProductPath = Join-Path $Src "product.json"
$Product = Get-Content $ProductPath -Raw | ConvertFrom-Json
$Product.nameShort = $Patch.nameShort
$Product.nameLong = $Patch.nameLong
$Product.applicationName = $Patch.applicationName
$Product.dataFolderName = $Patch.dataFolderName
$Product.urlProtocol = $Patch.urlProtocol
$Product | ConvertTo-Json -Depth 40 | Set-Content $ProductPath -Encoding UTF8

Write-Host "Overlay applied to $Target"
Write-Host "product.json branded as FreeForge Workbench"
