param([string]$Blender, [string]$Scene, [string]$SourceSkeleton, [switch]$CheckImporters)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'StudioRuntime.ps1')
$settings = Get-StudioDefaults
if ($Blender) { $settings.blender = [IO.Path]::GetFullPath($Blender) }
if ($Scene) {
    $settings.scene = [IO.Path]::GetFullPath($Scene)
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
$prepareArgs = @((Join-Path $PSScriptRoot 'studio.py'),'prepare-source','--blender',$settings.blender,'--scene',$settings.scene,'--emotes',(Join-Path $PSScriptRoot 'Input\Fortnite'),'--if-available')
if ($SourceSkeleton) { $prepareArgs += '--source-skeleton'; $prepareArgs += [IO.Path]::GetFullPath($SourceSkeleton) }
& $python @prepareArgs
if ($LASTEXITCODE -ne 0) { throw 'Source preparation failed. See the reported log or select a source skeleton explicitly.' }
$json = $settings | ConvertTo-Json
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'studio.local.json'),$json,[Text.UTF8Encoding]::new($false))
Write-Host 'Setup complete. Launch Studio. Register Folder prepares the source scene automatically if your exports arrive later.'
