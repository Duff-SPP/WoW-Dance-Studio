$script:packDialog=$null
$preparePackCommand={
    param($command)
    $script:packExtraArgs=@()
    if ($command -eq 'pack-build') {
        $paths=@($script:packList.CheckedItems | ForEach-Object path)
        if (!$paths.Count) { throw 'Select at least one model package first.' }
        $folder=Join-Path $studioRoot 'Output\Packs\requests'; [IO.Directory]::CreateDirectory($folder) | Out-Null
        $path=Join-Path $folder ([guid]::NewGuid().ToString()+'.json')
        [IO.File]::WriteAllText($path,(@{packages=$paths;addon_audio=$script:packAddonAudio.Checked}|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
        $script:packExtraArgs=@('--pack-request',$path)
    }
}
$refreshPack={
    param($command,$exitCode)
    if (!$script:packDialog -or $script:packDialog.IsDisposed) { return }
    if ($exitCode -ne 0) { $script:packDetails.Text='Pack was not built. See the main log for the blocking reason.'; return }
    $folder=Join-Path $studioRoot 'Output\Packs'
    if ($command -eq 'pack-scan') {
        $data=Get-Content (Join-Path $folder 'scan.json') -Raw | ConvertFrom-Json
        $script:packList.Items.Clear()
        foreach ($row in $data.packages) { $null=$script:packList.Items.Add($row) }
        $script:packDetails.Text='Select one export per model. All selected exports must share the same DBC snapshot. TEST FIXTURE exports are for testing and do not represent production approval.'
    } else {
        $data=Get-Content (Join-Path $folder 'build_result.json') -Raw | ConvertFrom-Json
        $script:lastPackOutput=$data.output
        $script:packDetails.Text="Pack built: $($data.output)`r`nModels: $($data.models)`r`nMissing original ANIM references: $($data.missing_original_anim_count) (existing client archives must supply these).`r`nIncludes Client, Server, manifest.json and INSTALL.txt. Nothing has been installed. In-game playback remains unverified."
    }
}
$packButton=New-Object Windows.Forms.Button; $packButton.Text='Build Pack'; $packButton.SetBounds(895,80,95,32)
$packButton.Add_Click({ & $guardUi 'Build Pack' {
    if ($script:packDialog -and !$script:packDialog.IsDisposed) { $script:packDialog.Activate(); return }
    $script:packDialog=New-Object Windows.Forms.Form; $script:packDialog.Text='Build Client + Server Pack'; $script:packDialog.Size=New-Object Drawing.Size(1000,650); $script:packDialog.StartPosition='CenterParent'
    $note=New-Object Windows.Forms.Label; $note.Text='Build Pack includes changed M2, new ANIMs and DBCs. Matching original ANIM/SKIN files stay in your existing client patches.'; $note.SetBounds(12,12,950,30)
    $script:packList=New-Object Windows.Forms.CheckedListBox; $script:packList.DisplayMember='label'; $script:packList.CheckOnClick=$true; $script:packList.HorizontalScrollbar=$true; $script:packList.SetBounds(12,50,950,285)
    $script:packAddonAudio=New-Object Windows.Forms.CheckBox; $script:packAddonAudio.Text='Addon-managed music (stops on movement); collection addon is included in every pack'; $script:packAddonAudio.SetBounds(12,338,950,24); $script:packAddonAudio.Checked=$true
    $script:packDialog.Controls.Add($script:packAddonAudio)
    $script:packList.Add_SelectedIndexChanged({ if ($script:packList.SelectedItem) { $script:packDetails.Text=$script:packList.SelectedItem.label } })
    $script:packList.Add_ItemCheck({ param($sender,$eventArgs)
        if (!$script:packList.Items[$eventArgs.Index].eligible) { $eventArgs.NewValue=[Windows.Forms.CheckState]::Unchecked }
    })
    $script:packDetails=New-Object Windows.Forms.TextBox; $script:packDetails.Multiline=$true; $script:packDetails.ReadOnly=$true; $script:packDetails.ScrollBars='Both'; $script:packDetails.SetBounds(12,410,950,185)
    $scan=New-Object Windows.Forms.Button; $scan.Text='Scan Exports'; $scan.Tag='pack-scan'; $scan.SetBounds(12,365,280,34); $scan.Add_Click({ & $guardUi 'Scan pack exports' { & $runCommand } })
    $build=New-Object Windows.Forms.Button; $build.Text='Build Pack'; $build.Tag='pack-build'; $build.SetBounds(312,365,280,34); $build.Add_Click({ & $guardUi 'Assemble pack' { & $runCommand } })
    $open=New-Object Windows.Forms.Button; $open.Text='Open Pack Folder'; $open.SetBounds(612,365,350,34)
    $open.Add_Click({ & $guardUi 'Open pack folder' {
        $folder=Join-Path $studioRoot 'Output\Packs'; if ($script:lastPackOutput) { $folder=$script:lastPackOutput }
        [IO.Directory]::CreateDirectory($folder) | Out-Null; Start-Process explorer.exe -ArgumentList ('"'+$folder+'"')
    } })
    $script:packDialog.Controls.AddRange(@($note,$script:packList,$scan,$build,$open,$script:packDetails)); $script:packDialog.Show($form)
    $scan.PerformClick()
} })
$form.Controls.Add($packButton)
