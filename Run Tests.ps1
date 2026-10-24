$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'StudioRuntime.ps1')
$settings = Get-StudioDefaults
$python = Get-StudioPython $settings.blender
Push-Location $PSScriptRoot
try {
    foreach ($folder in @('Reports','Output','Output/FortniteImports')) { $null = New-Item -ItemType Directory -Path $folder -Force }
    & $python -m unittest discover -s . -p 'test_*.py'
    if ($LASTEXITCODE -ne 0) { throw 'Regression tests failed.' }
    & $python Tools/check_release.py
    if ($LASTEXITCODE -ne 0) { throw 'Public-source audit failed.' }
} finally { Pop-Location }
