param(
    [Parameter(Mandatory=$true)][string]$RuntimeDirectory,
    [Parameter(Mandatory=$true)][string]$LibrariesDirectory,
    [string]$Compiler
)
$ErrorActionPreference = 'Stop'
$runtime = (Resolve-Path -LiteralPath $RuntimeDirectory).Path
$libraries = (Resolve-Path -LiteralPath $LibrariesDirectory).Path
$runtimeVersion = Split-Path $runtime -Leaf
if ($runtimeVersion -notmatch '^10\.0\.\d+$') { throw 'Use the .NET 10 shared/Microsoft.NETCore.App/10.0.x runtime directory.' }
if (!$Compiler) {
    $sdks = @(& dotnet --list-sdks)
    if ($LASTEXITCODE -ne 0 -or !$sdks.Count) { throw 'Install a .NET SDK with the Roslyn C# compiler.' }
    if ($sdks[-1] -notmatch '^(\S+)\s+\[(.+)\]$') { throw 'Cannot resolve the installed .NET SDK.' }
    $Compiler = Join-Path (Join-Path $Matches[2] $Matches[1]) 'Roslyn\bincore\csc.dll'
}
if (!(Test-Path -LiteralPath $Compiler -PathType Leaf)) { throw "C# compiler not found: $Compiler" }
$studioRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$output = Join-Path $studioRoot 'Output\FortniteBatchBuild'
$null = New-Item -ItemType Directory -Path $output -Force
$references = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'build-references.json') -Raw | ConvertFrom-Json
$arguments = @('/nostdlib+','/nullable:enable','/target:exe',('/out:"'+(Join-Path $output 'Batch.dll')+'"'))
foreach ($group in @(@($references.runtime,$runtime),@($references.libraries,$libraries))) {
    foreach ($name in $group[0]) {
        if ([IO.Path]::GetFileName($name) -ne $name) { throw 'Invalid reference filename.' }
        $path = Join-Path $group[1] $name
        if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required reference missing: $path" }
        $arguments += '/reference:"'+$path+'"'
    }
}
foreach ($source in (Get-ChildItem -LiteralPath $PSScriptRoot -File -Filter '*.cs' | Sort-Object Name)) {
    $arguments += '"'+$source.FullName+'"'
}
$response = Join-Path $output 'compile.rsp'
[IO.File]::WriteAllLines($response,$arguments,[Text.UTF8Encoding]::new($false))
& dotnet $Compiler /noconfig ('@'+$response)
if ($LASTEXITCODE -ne 0) { throw 'Batch helper compilation failed.' }
# Keep external application libraries beside the helper, as in the recorded build.
foreach ($file in (Get-ChildItem -LiteralPath $libraries -File -Filter '*.dll')) {
    if ($file.Name -ne 'Batch.dll') { Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $output $file.Name) }
}
$config = @{runtimeOptions=@{tfm='net10.0';framework=@{name='Microsoft.NETCore.App';version=$runtimeVersion}}} | ConvertTo-Json -Depth 5
[IO.File]::WriteAllText((Join-Path $output 'Batch.runtimeconfig.json'),$config,[Text.UTF8Encoding]::new($false))
Write-Host "Built $output\Batch.dll. Run with the matching .NET 10 host. No parser or asset download was started."
