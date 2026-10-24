$script:m2Dialog=$null; $script:m2Plan=$null; $script:m2Revision=0
$prepareM2Command={
    param($command)
    $script:m2ExtraArgs=@()
    if ($command -eq 'm2-scan') { $script:m2Plan=$null; $script:m2ValidateButton.Enabled=$false; $script:m2ExportButton.Enabled=$false }
    elseif ($command -eq 'm2-preview') {
        if (!$script:m2Scan -or $script:m2Scan.target -ne $script:selectedTarget) { throw 'Selected model changed; scan the model again.' }
        $ids=@($script:m2Dances.CheckedItems | ForEach-Object id)
        if (!$ids.Count) { throw 'Select approved dances with committed DBC IDs first.' }
        $script:m2PreviewRevision=$script:m2Revision
        $folder=Join-Path $studioRoot 'Output\M2\requests'; [IO.Directory]::CreateDirectory($folder) | Out-Null
        $path=Join-Path $folder ([guid]::NewGuid().ToString()+'.json')
        [IO.File]::WriteAllText($path,(@{target=$script:selectedTarget;emotes=$ids}|ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))
        $script:m2ExtraArgs=@('--m2-request',$path)
    }
    else {
        if (!$script:m2Plan) { throw 'Preview and validate a model export first.' }
        $script:m2ExtraArgs=@('--m2-plan',$script:m2Plan)
    }
    return $true
}
$refreshM2={
    param($command,$exitCode)
    if (!$script:m2Dialog -or $script:m2Dialog.IsDisposed) { return }
    if ($exitCode -ne 0) { $script:m2Details.Text='Operation blocked or failed; inspect the main log. No original model or existing package was overwritten.'; return }
    $folder=Join-Path $studioRoot 'Output\M2'
    if ($command -eq 'm2-scan') {
        $script:m2Scan=Get-Content (Join-Path $folder 'scan.json') -Raw | ConvertFrom-Json
        $script:m2Dances.Items.Clear()
        foreach ($dance in $script:m2Scan.dances) {
            $dance | Add-Member NoteProperty label ($dance.name+' | ID '+$dance.animation_id+' | '+$dance.reason)
            $null=$script:m2Dances.Items.Add($dance)
        }
        $script:m2Details.Text=$script:m2Scan | ConvertTo-Json -Depth 10
    } else {
        $file=switch ($command) { 'm2-preview' {'preview_result.json'} 'm2-validate' {'validation.json'} 'm2-export' {'export_result.json'} }
        $data=Get-Content (Join-Path $folder $file) -Raw | ConvertFrom-Json
        if ($command -eq 'm2-preview') {
            if ($script:m2PreviewRevision -ne $script:m2Revision) { $script:m2Details.Text='Selection changed; preview again.'; return }
            $script:m2Plan=$data.plan_path; $script:m2ValidateButton.Enabled=$true; $script:m2ExportButton.Enabled=$false
        }
        if ($command -eq 'm2-validate') { $script:m2ExportButton.Enabled=$data.valid -eq $true }
        if ($command -eq 'm2-export') { $script:m2Plan=$null; $script:m2ValidateButton.Enabled=$false; $script:m2ExportButton.Enabled=$false }
        $script:m2Details.Text=$data | ConvertTo-Json -Depth 12
    }
}
$m2Button=New-Object Windows.Forms.Button; $m2Button.Text='M2 / ANIM'; $m2Button.SetBounds(895,45,95,32)
$m2Button.Add_Click({ & $guardUi 'M2 Export Manager' {
    if ($script:m2Dialog -and !$script:m2Dialog.IsDisposed) { $script:m2Dialog.Activate(); return }
    $script:m2Dialog=New-Object Windows.Forms.Form; $script:m2Dialog.Text='Append-only M2 / ANIM Export Manager'
    $script:m2Dialog.Size=New-Object Drawing.Size(1050,720); $script:m2Dialog.StartPosition='CenterParent'
    $scan=New-Object Windows.Forms.Button; $scan.Text='Scan Selected Model'; $scan.Tag='m2-scan'; $scan.SetBounds(12,12,230,32)
    $scan.Add_Click({ & $guardUi 'M2 eligibility scan' { & $runCommand } })
    $all=New-Object Windows.Forms.Button; $all.Text='Select Eligible Dances'; $all.SetBounds(252,12,230,32)
    $all.Add_Click({ for ($i=0;$i -lt $script:m2Dances.Items.Count;$i++) { if ($script:m2Dances.Items[$i].eligible) { $script:m2Dances.SetItemChecked($i,$true) } } })
    $open=New-Object Windows.Forms.Button; $open.Text='Open M2 Output'; $open.SetBounds(762,12,250,32)
    $open.Add_Click({ & $guardUi 'M2 output folder' { $folder=Join-Path $studioRoot 'Output\M2'; [IO.Directory]::CreateDirectory($folder) | Out-Null; Start-Process explorer.exe -ArgumentList ('"'+$folder+'"') } })
    $script:m2Dances=New-Object Windows.Forms.CheckedListBox; $script:m2Dances.DisplayMember='label'; $script:m2Dances.CheckOnClick=$true; $script:m2Dances.SetBounds(12,58,1000,170)
    $script:m2Dances.Add_ItemCheck({ param($sender,$eventArgs)
        if (!$script:m2Dances.Items[$eventArgs.Index].eligible) { $eventArgs.NewValue=[Windows.Forms.CheckState]::Unchecked }
        $script:m2Revision++; $script:m2Plan=$null; $script:m2ValidateButton.Enabled=$false; $script:m2ExportButton.Enabled=$false
    })
    $script:m2Details=New-Object Windows.Forms.TextBox; $script:m2Details.Multiline=$true; $script:m2Details.ReadOnly=$true; $script:m2Details.ScrollBars='Both'; $script:m2Details.WordWrap=$false; $script:m2Details.SetBounds(12,240,1000,320)
    $position=12
    foreach ($pair in @(@('Preview Package','m2-preview'),@('Validate Export','m2-validate'),@('Export Model + ANIMs','m2-export'))) {
        $button=New-Object Windows.Forms.Button; $button.Text=$pair[0]; $button.Tag=$pair[1]; $button.SetBounds($position,575,310,36)
        $button.Add_Click({ & $guardUi 'M2 operation' { & $runCommand } }); $script:m2Dialog.Controls.Add($button); $position+=340
        if ($pair[1] -eq 'm2-validate') { $script:m2ValidateButton=$button; $button.Enabled=$false }
        if ($pair[1] -eq 'm2-export') { $script:m2ExportButton=$button; $button.Enabled=$false }
    }
    $note=New-Object Windows.Forms.Label; $note.Text='Each package contains the original model plus checked dances; use Select Eligible Dances for a full library package. Committed DBC IDs are required. Missing original ANIM references are retained. Packaging, slash aliases, props and music triggers are not generated.'; $note.SetBounds(12,625,1000,45)
    $script:m2Dialog.Controls.AddRange(@($scan,$all,$open,$script:m2Dances,$script:m2Details,$note)); $script:m2Dialog.Show($form)
} })
$form.Controls.Add($m2Button)
