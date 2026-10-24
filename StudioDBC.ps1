# Existing asynchronous runner and guard are shared with the main Windows Forms GUI.
$script:dbcDialog = $null
$script:dbcPlan = $null
$script:dbcExtraArgs = @()
$script:dbcUiRevision = 0
$prepareDBCCommand = {
    param($command)
    $script:dbcExtraArgs = @()
    if ($command -eq 'dbc-scan') {
        $script:dbcPlan=$null; $script:dbcExportButton.Enabled=$false; $script:dbcValidateButton.Enabled=$false; $script:dbcPreviewButton.Enabled=$false
    }
    if ($command -eq 'dbc-preview') {
        $script:dbcPreviewRevision=$script:dbcUiRevision
        $selected = @($script:dbcDances.CheckedItems | ForEach-Object { $_.id })
        if (!$selected.Count -and !$script:dbcScan.custom_ids.PSObject.Properties.Count) {
            $script:dbcDetails.Text = 'Select approved converted dances. A zero-change copy is available through the CLI.'; return $false
        }
        $template = if ($script:dbcSounds.SelectedItem) { $script:dbcSounds.SelectedItem.id } else { $null }
        $request = @{ emotes=$selected; include_sound=$script:dbcIncludeSound.Checked; include_client_audio=$script:dbcIncludeSound.Checked; full_soundtrack=$true; include_text=$script:dbcIncludeText.Checked; sound_template=$template }
        if ($script:dbcTextSound.Checked) {
            if (!$script:dbcRaces.SelectedItem -or $script:dbcSex.SelectedIndex -lt 0) { throw 'Select an explicit race and sex for text sound records.' }
            $request.text_sound_target = @{race_id=$script:dbcRaces.SelectedItem.race_id; sex_id=$script:dbcSex.SelectedIndex}
        }
        $requestFolder = Join-Path $studioRoot 'Output\DBC\requests'
        [IO.Directory]::CreateDirectory($requestFolder) | Out-Null
        $requestPath = Join-Path $requestFolder ([guid]::NewGuid().ToString()+'.json')
        [IO.File]::WriteAllText($requestPath,($request | ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
        $script:dbcExtraArgs = @('--dbc-request',$requestPath)
    }
    elseif ($command -in @('dbc-validate','dbc-export')) {
        if (!$script:dbcPlan) { $script:dbcDetails.Text='Preview New Records first.'; return $false }
        $script:dbcExtraArgs = @('--dbc-plan',$script:dbcPlan)
    }
    elseif ($command -eq 'dbc-ids') {
        $table = if ($script:dbcFiles.SelectedItems.Count) { [IO.Path]::GetFileNameWithoutExtension($script:dbcFiles.SelectedItems[0].Text) } else { 'AnimationData' }
        $script:dbcExtraArgs = @('--dbc-table',$table)
        if ($script:dbcFindID.Text) {
            $number = 0
            if (![int]::TryParse($script:dbcFindID.Text,[ref]$number) -or $number -lt 0) { throw 'Enter a nonnegative record ID.' }
            $script:dbcExtraArgs += @('--dbc-id',$number.ToString())
        }
    }
    return $true
}
$refreshDBC = {
    param($command,$exitCode)
    if (!$script:dbcDialog -or $script:dbcDialog.IsDisposed) { return }
    if ($exitCode -ne 0) { $script:dbcDetails.Text='Operation failed. Inspect the main window log; existing DBC exports are preserved.'; return }
    $root = Join-Path $studioRoot 'Output\DBC'
    if ($command -eq 'dbc-scan') {
        $script:dbcScan=Get-Content (Join-Path $root 'scan.json') -Raw | ConvertFrom-Json
        $script:dbcFiles.Items.Clear(); $script:dbcDances.Items.Clear(); $script:dbcSounds.Items.Clear(); $script:dbcRaces.Items.Clear()
        foreach ($row in $script:dbcScan.files) {
            $status = if ($row.valid -eq $true) { 'Valid' } elseif ($row.status) { $row.status } else { 'Invalid: '+$row.error }
            $item = New-Object Windows.Forms.ListViewItem($row.file)
            foreach ($value in @($status,$row.format,$row.records,$row.fields,$row.record_size,$row.highest_id,($row.duplicate_ids -join ','),$row.sha256)) { $null=$item.SubItems.Add([string]$value) }
            $null=$script:dbcFiles.Items.Add($item)
        }
        foreach ($dance in $script:dbcScan.library) {
            $dance | Add-Member NoteProperty label ($dance.name+$(if ($dance.eligible) {' [approved]'} else {' [blocked - review required]'}))
            $null=$script:dbcDances.Items.Add($dance)
        }
        foreach ($template in $script:dbcScan.sound_templates) {
            $template | Add-Member NoteProperty label ("$($template.id): $($template.name) | type $($template.sound_type), flags $($template.flags)")
            $null=$script:dbcSounds.Items.Add($template)
        }
        $recommended = $script:dbcSounds.Items | Where-Object native_cycle_compatible | Select-Object -First 1
        if ($recommended) { $script:dbcSounds.SelectedItem=$recommended }
        $script:dbcIncludeSound.Checked = $includeAudio.Checked -and @($script:dbcScan.library | Where-Object has_audio).Count -gt 0
        foreach ($race in $script:dbcScan.text_sound_targets) {
            $race | Add-Member NoteProperty label ("$($race.race_id): $($race.name)")
            $null=$script:dbcRaces.Items.Add($race)
        }
        $script:dbcDetails.Text="Original reference diagnostics: $($script:dbcScan.original_reference_diagnostics.Count). Existing issues are preserved; new links must validate.`r`nDanceMoves is read-only / experimental.`r`nSelect a dance to inspect export eligibility. Select a table and Show IDs to inspect original/custom records."
        $script:dbcPreviewButton.Enabled = !@($script:dbcScan.files | Where-Object { $_.valid -eq $false }).Count
    }
    else {
        $file = switch ($command) { 'dbc-preview' {'preview_result.json'} 'dbc-validate' {'validation.json'} 'dbc-export' {'export_result.json'} 'dbc-ids' {'ids.json'} }
        $data = Get-Content (Join-Path $root $file) -Raw | ConvertFrom-Json
        if ($command -eq 'dbc-preview') {
            if ($script:dbcPreviewRevision -ne $script:dbcUiRevision) { $script:dbcDetails.Text='Options changed during preview. Preview New Records again.'; return }
            $script:dbcPlan=$data.plan_path; $script:dbcValidateButton.Enabled=$true; $script:dbcExportButton.Enabled=$false
        }
        if ($command -eq 'dbc-validate') { $script:dbcExportButton.Enabled=$data.valid -eq $true }
        if ($command -eq 'dbc-export') { $script:dbcPlan=$null; $script:dbcExportButton.Enabled=$false; $script:dbcValidateButton.Enabled=$false }
        $script:dbcDetails.Text=$data | ConvertTo-Json -Depth 30
    }
}
$dbcButton=New-Object Windows.Forms.Button
$dbcButton.Text='DBC Manager'; $dbcButton.SetBounds(895,10,95,32)
$dbcButton.Add_Click({ & $guardUi 'DBC Manager' {
    if ($script:dbcDialog -and !$script:dbcDialog.IsDisposed) { $script:dbcDialog.Activate(); return }
    $script:dbcDialog=New-Object Windows.Forms.Form
    $script:dbcDialog.Text='DBC Manager - append-only 3.3.5a exports'
    $script:dbcDialog.Size=New-Object Drawing.Size(1120,770)
    $script:dbcDialog.StartPosition='CenterParent'
    $scan=New-Object Windows.Forms.Button
    $scan.Text='Scan DBCs / View Status'; $scan.Tag='dbc-scan'; $scan.SetBounds(12,10,200,30); $scan.Add_Click({ & $guardUi 'DBC scan' { & $runCommand } })
    $ids=New-Object Windows.Forms.Button
    $ids.Text='Show Existing / Custom IDs'; $ids.Tag='dbc-ids'; $ids.SetBounds(222,10,210,30); $ids.Add_Click({ & $guardUi 'DBC ID lookup' { & $runCommand } })
    $script:dbcFindID=New-Object Windows.Forms.TextBox; $script:dbcFindID.SetBounds(440,12,100,26)
    $open=New-Object Windows.Forms.Button; $open.Text='Open Output Folder'; $open.SetBounds(850,10,230,30)
    $open.Add_Click({ & $guardUi 'DBC output folder' {
        $folder=Join-Path $studioRoot 'Output\DBC'; [IO.Directory]::CreateDirectory($folder) | Out-Null; Start-Process explorer.exe -ArgumentList ('"'+$folder+'"')
    } })
    $script:dbcFiles=New-Object Windows.Forms.ListView
    $script:dbcFiles.SetBounds(12,50,1070,170); $script:dbcFiles.View='Details'; $script:dbcFiles.FullRowSelect=$true
    foreach ($column in @('File','Status','Format','Rows','Fields','Size','Highest ID','Conflicts','SHA256')) { $null=$script:dbcFiles.Columns.Add($column, $(if ($column -eq 'File') {190} elseif ($column -eq 'SHA256') {300} else {90})) }
    $script:dbcDances=New-Object Windows.Forms.CheckedListBox
    $script:dbcDances.DisplayMember='label'; $script:dbcDances.SetBounds(12,235,300,240); $script:dbcDances.CheckOnClick=$true
    $script:dbcDances.Add_ItemCheck({ param($sender,$eventArgs)
        if (!$script:dbcDances.Items[$eventArgs.Index].eligible) { $eventArgs.NewValue=[Windows.Forms.CheckState]::Unchecked }
        $script:dbcUiRevision++
        $script:dbcPlan=$null; $script:dbcExportButton.Enabled=$false; $script:dbcValidateButton.Enabled=$false
    })
    $script:dbcDances.Add_SelectedIndexChanged({
        if ($script:dbcDances.SelectedItem) { $script:dbcDetails.Text=$script:dbcDances.SelectedItem | ConvertTo-Json -Depth 12 }
    })
    $script:dbcDetails=New-Object Windows.Forms.TextBox
    $script:dbcDetails.Multiline=$true; $script:dbcDetails.ReadOnly=$true; $script:dbcDetails.ScrollBars='Both'; $script:dbcDetails.WordWrap=$false
    $script:dbcDetails.SetBounds(325,235,755,240)
    $script:dbcIncludeSound=New-Object Windows.Forms.CheckBox; $script:dbcIncludeSound.Text='Include Client Soundtrack'; $script:dbcIncludeSound.SetBounds(12,485,290,25)
    $script:dbcSounds=New-Object Windows.Forms.ComboBox; $script:dbcSounds.DisplayMember='label'; $script:dbcSounds.DropDownStyle='DropDownList'; $script:dbcSounds.SetBounds(325,485,755,26)
    $script:dbcIncludeText=New-Object Windows.Forms.CheckBox; $script:dbcIncludeText.Text='Include Text Emote Records'; $script:dbcIncludeText.SetBounds(12,520,290,25); $script:dbcIncludeText.Checked=$true
    $script:dbcTextSound=New-Object Windows.Forms.CheckBox; $script:dbcTextSound.Text='Explicit text sound race / sex'; $script:dbcTextSound.SetBounds(12,555,290,25)
    $script:dbcRaces=New-Object Windows.Forms.ComboBox; $script:dbcRaces.DisplayMember='label'; $script:dbcRaces.DropDownStyle='DropDownList'; $script:dbcRaces.SetBounds(325,555,460,26)
    $script:dbcSex=New-Object Windows.Forms.ComboBox; $script:dbcSex.DropDownStyle='DropDownList'; $script:dbcSex.SetBounds(800,555,280,26)
    $null=$script:dbcSex.Items.Add('Male (0)'); $null=$script:dbcSex.Items.Add('Female (1)')
    $position=12
    foreach ($pair in @(@('Preview New Records','dbc-preview'),@('Validate Export','dbc-validate'),@('Export Updated DBCs','dbc-export'))) {
        $button=New-Object Windows.Forms.Button; $button.Text=$pair[0]; $button.Tag=$pair[1]; $button.SetBounds($position,600,245,35)
        $button.Add_Click({ & $guardUi 'DBC operation' { & $runCommand } }); $script:dbcDialog.Controls.Add($button); $position+=260
        $button.Enabled=$false
        switch ($pair[1]) { 'dbc-preview' {$script:dbcPreviewButton=$button} 'dbc-validate' {$script:dbcValidateButton=$button} 'dbc-export' {$script:dbcExportButton=$button} }
    }
    $note=New-Object Windows.Forms.Label
    $note.Text='Include Client Soundtrack creates SoundEntries for native M2 playback. Re-export M2/ANIM, then Build Pack to include the audio. Intro/loop repeats with the animation cycle; a sound already playing may finish when you stop dancing.'
    $note.SetBounds(12,650,1070,50)
    $script:dbcDialog.Controls.AddRange(@($scan,$ids,$script:dbcFindID,$open,$script:dbcFiles,$script:dbcDances,$script:dbcDetails,
        $script:dbcIncludeSound,$script:dbcSounds,$script:dbcIncludeText,$script:dbcTextSound,$script:dbcRaces,$script:dbcSex,$note))
    $invalidate={ $script:dbcUiRevision++; $script:dbcPlan=$null; $script:dbcValidateButton.Enabled=$false; $script:dbcExportButton.Enabled=$false }
    foreach ($box in @($script:dbcIncludeSound,$script:dbcIncludeText,$script:dbcTextSound)) { $box.Add_CheckedChanged($invalidate) }
    foreach ($combo in @($script:dbcSounds,$script:dbcRaces,$script:dbcSex)) { $combo.Add_SelectedIndexChanged($invalidate) }
    $script:dbcDialog.Show($form)
} })
$form.Controls.Add($dbcButton)
