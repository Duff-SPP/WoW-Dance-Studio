# Shared by setup and the GUI. Local settings are intentionally gitignored.
function Get-StudioDefaults {
    $settings = @{}
    $path = Join-Path $PSScriptRoot 'studio.local.json'
    if (Test-Path -LiteralPath $path) {
        $saved = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
        foreach ($key in @('blender','scene')) {
            if ($saved.$key) { $settings[$key] = [string]$saved.$key }
        }
    }
    if ($env:WDS_BLENDER) { $settings.blender = $env:WDS_BLENDER }
    if (!$settings.blender) { $settings.blender = 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' }
    if (!$settings.scene) { $settings.scene = Join-Path $PSScriptRoot 'Blender\PreparedSource.blend' }
    return $settings
}

function Get-StudioPython {
    param([Parameter(Mandatory=$true)][string]$Blender)
    if (!(Test-Path -LiteralPath $Blender -PathType Leaf)) { throw "Blender executable not found: $Blender" }
    $homeDir = Split-Path -Parent $Blender
    $candidates = @(Get-ChildItem -LiteralPath $homeDir -Directory | Where-Object { $_.Name -match '^\d+\.\d+$' } | ForEach-Object {
        $candidate = Join-Path $_.FullName 'python\bin\python.exe'
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { $candidate }
    })
    if ($candidates.Count -ne 1) { throw "Expected one bundled Python beside $Blender; found $($candidates.Count). Use a complete, separate Blender installation." }
    return $candidates[0]
}
