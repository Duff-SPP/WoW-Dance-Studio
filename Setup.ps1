param([string]$Blender, [string]$Scene, [switch]$CheckImporters)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'StudioRuntime.ps1')
$settings = Get-StudioDefaults
if ($Blender) { $settings.blender = [IO.Path]::GetFullPath($Blender) }
if ($Scene) {
    if (!(Test-Path -LiteralPath $Scene -PathType Leaf)) { throw "Prepared source scene not found: $Scene" }
    $settings.scene = (Resolve-Path -LiteralPath $Scene).Path
}
$python = Get-StudioPython $settings.blender
foreach ($folder in @('Input\WoW','Input\Fortnite','Input\DBC','Blender','Profiles\Clients','Output','Reports')) {
    $null = New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot $folder) -Force
}
$activeProfile = Join-Path $PSScriptRoot 'Profiles\Clients\active.json'
if (!(Test-Path -LiteralPath $activeProfile)) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Profiles\Clients\conservative.example.json') -Destination $activeProfile
}
& $python (Join-Path $PSScriptRoot 'check_setup.py')
if ($LASTEXITCODE -ne 0) { throw 'Python setup check failed.' }
if ($CheckImporters) {
    & $settings.blender --background --python-exit-code 1 --python (Join-Path $PSScriptRoot 'check_setup.py')
    if ($LASTEXITCODE -ne 0) { throw 'Blender importer check failed. Install/enable the required add-ons and save Blender preferences.' }
}
$json = $settings | ConvertTo-Json
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'studio.local.json'),$json,[Text.UTF8Encoding]::new($false))
Write-Host 'Setup complete. Read docs/SETUP.md to prepare your own source scene, then launch Studio.'
