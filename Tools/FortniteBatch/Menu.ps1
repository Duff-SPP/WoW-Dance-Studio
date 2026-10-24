param([switch]$SmokeTest)
$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$settingsPath = Join-Path $studioRoot 'Output\FortniteBatchMenu\settings.json'
$catalogRoot = Join-Path $studioRoot 'Reports\FortniteBatch\Catalog'
$catalogPath = Join-Path $catalogRoot 'catalog.json'
$downloads = Join-Path $studioRoot 'Output\FortniteBatchDownloads\Assets'
$helper = Join-Path $studioRoot 'Output\FortniteBatchBuild\Batch.dll'
. (Join-Path $studioRoot 'StudioRuntime.ps1')

function Save-MenuSettings {
    param($Value)
    $null = New-Item -ItemType Directory -Path (Split-Path $settingsPath) -Force
    [IO.File]::WriteAllText($settingsPath,($Value | ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
}
function Get-MenuSettings {
    if (!(Test-Path -LiteralPath $settingsPath)) { throw 'Choose 1 to configure and build the helper first.' }
    return Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
}
function Get-HelperFingerprint {
    $files = @(Get-ChildItem -LiteralPath $PSScriptRoot -File -Filter '*.cs')
    $files += Get-Item -LiteralPath (Join-Path $PSScriptRoot 'Build.ps1'),(Join-Path $PSScriptRoot 'build-references.json')
    return (@($files | Sort-Object Name | ForEach-Object { (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }) -join ':')
}
function Invoke-PythonTool {
    param($Settings,[string]$Script,[string[]]$Arguments)
    & $Settings.Python (Join-Path $PSScriptRoot $Script) @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Script failed; inspect the message above. Existing results are preserved." }
}
function Invoke-EmoteHelper {
    param($Settings,[string[]]$Arguments)
    if (!(Test-Path -LiteralPath $helper) -or $Settings.Fingerprint -ne (Get-HelperFingerprint)) {
        throw 'Helper is missing or its source changed. Choose 1 to rebuild it.'
    }
    & $Settings.Dotnet $helper @Arguments
    if ($LASTEXITCODE -ne 0) { throw 'Fortnite helper failed. Inspect its output and the saved report; exports are not automatically imported.' }
}
function Configure-EmoteMenu {
    Write-Host 'Requires Fortnite Porting 4.3.4 configured once in its own application, its matching extracted libraries, a .NET SDK, and a .NET 10 runtime host.'
    $dotnetDefault = (Get-Command dotnet -ErrorAction SilentlyContinue).Source
    $hostPath = (Read-Host "Path to dotnet.exe with .NET 10 installed [Enter: $dotnetDefault]").Trim('"')
    if (!$hostPath) { $hostPath = $dotnetDefault }
    if (!$hostPath -or !(Test-Path -LiteralPath $hostPath -PathType Leaf)) { throw 'dotnet.exe not found.' }
    $runtime = $null
    foreach ($line in @(& $hostPath --list-runtimes)) {
        if ($line -match '^Microsoft\.NETCore\.App (10\.0\.\d+) \[(.+)\]$') { $runtime = Join-Path $Matches[2] $Matches[1] }
    }
    if (!$runtime) { throw 'That dotnet host has no .NET 10.0 runtime. Install .NET 10 or choose its portable host.' }
    $libraries = (Read-Host 'Matching Fortnite Porting library folder (contains FortnitePorting.dll)').Trim('"')
    if (!(Test-Path -LiteralPath (Join-Path $libraries 'FortnitePorting.dll') -PathType Leaf)) { throw 'FortnitePorting.dll not found in that folder.' }
    $pythonDefault = ''
    try { $defaults = Get-StudioDefaults; $pythonDefault = Get-StudioPython $defaults.blender } catch { }
    $python = (Read-Host "Python 3.11+ executable [Enter: $pythonDefault]").Trim('"')
    if (!$python) { $python = $pythonDefault }
    if (!$python -or !(Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Python executable not found.' }
    & $python -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ required"'
    if ($LASTEXITCODE -ne 0) { throw 'Python check failed.' }
    & (Join-Path $PSScriptRoot 'Build.ps1') -RuntimeDirectory $runtime -LibrariesDirectory $libraries
    if ($LASTEXITCODE -ne 0) { throw 'Helper build failed.' }
    & $hostPath $helper --self-test
    if ($LASTEXITCODE -ne 0) { throw 'Helper self-test failed.' }
    $value = [pscustomobject]@{Dotnet=$hostPath;Python=$python;Fingerprint=(Get-HelperFingerprint);LastRun=''}
    Save-MenuSettings $value
    Write-Host 'Configured. Favorites/settings in Fortnite Porting were not changed.'
}
function Get-CurrentRun {
    param($Settings)
    if (!$Settings.LastRun -or !(Test-Path -LiteralPath $Settings.LastRun -PathType Container)) { throw 'Choose 3 to select and audit emotes first.' }
    return $Settings.LastRun
}
function Show-Selection {
    param([string]$Run)
    $selection = Get-Content -LiteralPath (Join-Path $Run 'selection.json') -Raw | ConvertFrom-Json
    Write-Host ('Policy: '+$selection.Policy)
    foreach ($status in @('ready','review','excluded')) {
        $rows = @($selection.Items | Where-Object { $_.Status -eq $status })
        Write-Host ("{0}: {1}" -f $status,$rows.Count)
        foreach ($row in ($rows | Select-Object -First 12)) {
            Write-Host ('  '+$row.Name+' ['+$row.Id+'] '+(@($row.Reasons)+@($row.Review) -join '; '))
        }
    }
    Write-Host ('Complete selection CSV: '+(Join-Path $Run 'selection.csv'))
}
function Select-AndAudit {
    param($Settings)
    if (!(Test-Path -LiteralPath $catalogPath)) { throw 'Choose 2 to scan the available catalog first.' }
    $infoPath = Join-Path $catalogRoot 'catalog-info.json'
    if (!(Test-Path -LiteralPath $infoPath) -or !(Get-Content -LiteralPath $infoPath -Raw | ConvertFrom-Json).Complete) {
        throw 'Catalog scan is incomplete. Choose 2 and let the full scan finish.'
    }
    Write-Host 'Filter: 1 Dance tag, 2 Choose an actual catalog tag, 3 All emote definitions'
    $filter = Read-Host 'Filter [1]'
    $tag = ''
    if (!$filter -or $filter -eq '1') { $tag = 'Cosmetics.UserFacingFlags.Emote.Dance' }
    elseif ($filter -eq '2') {
        $catalog = Get-Content -LiteralPath $catalogPath -Raw | ConvertFrom-Json
        $tags = @($catalog | ForEach-Object { $_.Tags } | Sort-Object -Unique)
        for ($index=0; $index -lt $tags.Count; $index++) { Write-Host ("{0}: {1}" -f ($index+1),$tags[$index]) }
        $number = 0
        if (![int]::TryParse((Read-Host 'Tag number'),[ref]$number) -or $number -lt 1 -or $number -gt $tags.Count) { throw 'Invalid tag number.' }
        $tag = $tags[$number-1]
    } elseif ($filter -ne '3') { throw 'Invalid filter.' }
    $search = Read-Host 'Optional name or ID search [Enter: any]'
    $maximumText = Read-Host 'Maximum candidates [Enter: 25; 0: all matches]'
    $maximum = 25
    if ($maximumText -and (![int]::TryParse($maximumText,[ref]$maximum) -or $maximum -lt 0)) { throw 'Invalid maximum.' }
    $policy = Read-Host 'Policy: 1 Dance/music only [default], 2 Standalone body emotes (music optional)'
    if ($policy -and $policy -notin @('1','2')) { throw 'Invalid policy.' }
    $run = Join-Path $studioRoot ('Reports\FortniteBatch\Runs\'+[DateTime]::UtcNow.ToString('yyyyMMdd_HHmmss')+'_'+[guid]::NewGuid().ToString('N').Substring(0,8))
    $arguments = @('select',$catalogPath,$run,'--limit',$maximum.ToString())
    if ($tag) { $arguments += @('--tag',$tag) }
    if ($search) { $arguments += @('--search',$search) }
    Invoke-PythonTool $Settings 'catalog_tool.py' $arguments
    Write-Host 'Auditing selected animation graphs. Referenced game data may be downloaded into the existing cache.'
    Invoke-EmoteHelper $Settings @($run,'2147483647','--source','catalog','--ids-file',(Join-Path $run 'ids.json'))
    $classify = @($run)
    if ($policy -eq '2') { $classify += '--allow-non-musical' }
    Invoke-PythonTool $Settings 'classify.py' $classify
    $Settings.LastRun = $run
    Save-MenuSettings $Settings
    Show-Selection $run
}

if ($SmokeTest) { Write-Output 'PASS: menu loaded without configuring, initializing a parser, or downloading assets.'; exit 0 }
Push-Location $studioRoot
try {
    while ($true) {
        Write-Host "`nFortnite Emote Downloader - full available catalog (Fortnite Porting 4.3.4)"
        Write-Host '1 Configure paths and build helper'
        Write-Host '2 Scan/refresh full emote catalog and real tags'
        Write-Host '3 Filter, select, and audit emotes'
        Write-Host '4 Review current ready/blocked selection'
        Write-Host '5 Download/export ready selection and verify files'
        Write-Host '6 Import verified downloads into Studio'
        Write-Host '7 Open current report folder'
        Write-Host '0 Exit'
        $choice = Read-Host 'Choose'
        if ($choice -eq '0') { break }
        try {
            if ($choice -eq '1') { Configure-EmoteMenu; continue }
            $settings = Get-MenuSettings
            switch ($choice) {
                '2' {
                    Write-Host 'Reads all available AthenaDanceItemDefinition entries, including hidden definitions. Metadata downloads may take time.'
                    Invoke-EmoteHelper $settings @($catalogRoot,'2147483647','--source','catalog','--catalog-only')
                    Invoke-PythonTool $settings 'catalog_tool.py' @('tags',$catalogPath)
                }
                '3' { Select-AndAudit $settings }
                '4' { Show-Selection (Get-CurrentRun $settings) }
                '5' {
                    $run = Get-CurrentRun $settings
                    Show-Selection $run
                    $selection = Get-Content -LiteralPath (Join-Path $run 'selection.json') -Raw | ConvertFrom-Json
                    $count = @($selection.Items | Where-Object { $_.Status -eq 'ready' }).Count
                    if (!$count) { throw 'No ready emotes. Review held/excluded reasons.' }
                    if ((Read-Host "Download/export $count ready emotes, matching skeletons and available audio? [y/N]") -ne 'y') { continue }
                    Invoke-EmoteHelper $settings @($run,'2147483647','--source','catalog','--export','--destination',$downloads)
                    Invoke-PythonTool $settings 'verify.py' @($run)
                    Write-Host 'Verified. Choose 6 to import into Studio, then Scan Emotes there.'
                }
                '6' {
                    $run = Get-CurrentRun $settings
                    Invoke-PythonTool $settings 'verify.py' @($run)
                    Invoke-PythonTool $settings 'catalog_tool.py' @('import',$run,$downloads)
                }
                '7' { Invoke-Item -LiteralPath (Get-CurrentRun $settings) }
                default { Write-Host 'Choose one of the menu numbers.' }
            }
        } catch { Write-Host ('ERROR: '+$_.Exception.Message) -ForegroundColor Red }
    }
} finally { Pop-Location }
