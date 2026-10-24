# Dot sourced by StudioGUI.ps1. Reuses its asynchronous CLI runner and timer.
$script:selectedTarget = 'human2_male'
$script:modelRecords = @{}
$script:profileDialog = $null
$script:pendingOverrides = $null
$resolveModelProfile = {
    param($model)
    $candidates = @()
    $approvedPath = $null
    if ($model.approved_profiles) {
        $approved = $model.approved_profiles.PSObject.Properties[$model.source.signature]
        if ($approved) { $approvedPath = $approved.Value; $candidates += $approvedPath }
    }
    if ($model.profile) { $candidates += $model.profile }
    foreach ($path in $candidates) {
        if ([string]::IsNullOrWhiteSpace($path)) { continue }
        if (!(Test-Path -LiteralPath $path -PathType Leaf)) { continue }
        try { $candidate = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json } catch { continue }
        $batchAuthorized = $candidate.status -eq 'Batch Export Authorized' -and $candidate.approval.kind -eq 'user_requested_batch_export'
        if ($path -eq $approvedPath -and (($candidate.status -ne 'Approved' -and !$batchAuthorized) -or !$candidate.validation.passed)) { continue }
        if ($candidate.model_id -eq $model.id -and $candidate.model_identity -eq $model.identity -and
            $candidate.target_signature -eq $model.signature -and $candidate.source_signature -eq $model.source.signature) { return $path }
    }
    return ''
}
$getProfileRequirement = {
    if ([string]::IsNullOrWhiteSpace($fields.profile.Text)) { return 'Matching profile required' }
    if (!(Test-Path -LiteralPath $fields.profile.Text -PathType Leaf)) { return 'Matching profile required' }
    try { $selectedProfile = Get-Content -LiteralPath $fields.profile.Text -Raw | ConvertFrom-Json } catch { return 'Invalid bone profile' }
    if (!$selectedProfile.generator) { return '' }
    $registeredModel = $script:modelRecords[$targetModel.Text]
    if ($registeredModel -and ($selectedProfile.model_id -ne $registeredModel.id -or
        $selectedProfile.model_identity -ne $registeredModel.identity -or
        $selectedProfile.target_signature -ne $registeredModel.signature -or
        $selectedProfile.source_signature -ne $registeredModel.source.signature)) { return 'Matching profile required' }
    if ($selectedProfile.status -eq 'Validated Technically') { return 'Profile approval required' }
    $batchAuthorized = $selectedProfile.status -eq 'Batch Export Authorized' -and $selectedProfile.approval.kind -eq 'user_requested_batch_export'
    if (($selectedProfile.status -ne 'Approved' -and !$batchAuthorized) -or !$selectedProfile.validation.passed) { return 'Profile validation required' }
    return ''
}
$profileHint = New-Object Windows.Forms.LinkLabel
$profileHint.SetBounds(170,170,710,22)
$profileHint.Add_LinkClicked({ $modelsButton.PerformClick() })
$form.Controls.Add($profileHint)
$refreshProfileHint = {
    $requirement = & $getProfileRequirement
    $profileHint.Text = if ($requirement) { $requirement+' - open Models to review / approve the bone profile' } else { 'Matching bone profile selected - ready for conversion' }
    $profileHint.LinkColor = if ($requirement) { [Drawing.Color]::DarkOrange } else { [Drawing.Color]::DarkGreen }
}
$refreshProfileGrid = {
    if (!$script:profileDialog -or $script:profileDialog.IsDisposed) { return }
    $script:mappingGrid.Rows.Clear()
    if ([string]::IsNullOrWhiteSpace($fields.profile.Text)) { return }
    if (!(Test-Path -LiteralPath $fields.profile.Text)) { return }
    $profileData = Get-Content -LiteralPath $fields.profile.Text -Raw | ConvertFrom-Json
    $registered = $script:modelRecords[$targetModel.Text]
    $displayProfileStatus = $profileData.status
    if ($profileData.generator -and $registered -and ($profileData.model_identity -ne $registered.identity -or $profileData.target_signature -ne $registered.signature)) { $displayProfileStatus = 'Outdated' }
    $script:profileStatus.Text = "Status: $displayProfileStatus | Source: $($profileData.source) | Target: $($profileData.target) | Revision: $($profileData.revision)`r`n$($profileData.validation.errors -join '; ')"
    foreach ($entry in $profileData.mapping.PSObject.Properties) {
        $evidence = $profileData.evidence | Where-Object source -eq $entry.Name | Select-Object -First 1
        $null = $script:mappingGrid.Rows.Add($entry.Name,$entry.Value,$evidence.confidence,($evidence.evidence -join '; '),(($evidence.alternatives | ForEach-Object target) -join ', '))
    }
    foreach ($evidence in $profileData.evidence) {
        if ($evidence.source -and !$profileData.mapping.PSObject.Properties[$evidence.source]) {
            $null = $script:mappingGrid.Rows.Add($evidence.source,'',$evidence.confidence,($evidence.evidence -join '; '),(($evidence.alternatives | ForEach-Object target) -join ', '))
        }
    }
    $script:profilePaths.Items.Clear()
    $folder = Join-Path $studioRoot ('Profiles\'+$script:selectedTarget)
    if (Test-Path -LiteralPath $folder) {
        foreach ($file in Get-ChildItem -LiteralPath $folder -Filter '*.json' | Sort-Object LastWriteTime -Descending) { $null = $script:profilePaths.Items.Add($file.FullName) }
    }
    $script:profilePaths.Text = $fields.profile.Text
}
$refreshModels = {
    param([switch]$UseLatest)
    $registry = Join-Path $studioRoot 'Output\Models\models.json'
    if (!(Test-Path -LiteralPath $registry)) { return }
    $registryInfo = Get-Item -LiteralPath $registry
    $registryStamp = "$($registryInfo.Length):$($registryInfo.LastWriteTimeUtc.Ticks):$($registryInfo.CreationTimeUtc.Ticks)"
    if (!$script:modelRegistryState -or $script:modelRegistryStamp -ne $registryStamp) {
        $script:modelRegistryState = Get-Content -LiteralPath $registry -Raw | ConvertFrom-Json
        $script:modelRegistryStamp = $registryStamp
    }
    $state = $script:modelRegistryState
    foreach ($model in $state.models) {
        $label = if ($model.id -eq 'human2_male') { 'Human2 Male' } elseif ($model.display_name) { $model.display_name } else { $model.id }
        $script:modelRecords[$label] = $model
        if (!$targetModel.Items.Contains($label)) { $null = $targetModel.Items.Add($label) }
        if ($UseLatest -and $model.id -eq $script:selectedTarget -and $model.profile -and $script:lastExitCode -eq 0) {
            $fields.profile.Text = $model.profile
        }
    }
    & $refreshProfileGrid
    & $refreshProfileHint
}
$targetModel.Add_SelectedIndexChanged({
    & $guardUi 'target model selection' {
    $selectedModel = $script:modelRecords[$targetModel.Text]
    if ($selectedModel) {
        $script:selectedTarget = $selectedModel.id
        $fields.scene.Text = $selectedModel.scene
        $fields.profile.Text = & $resolveModelProfile $selectedModel
    }
    else { $script:selectedTarget = 'human2_male' }
    & $refreshProfileGrid
    & $refreshCatalog
    }
})
$modelsButton = New-Object Windows.Forms.Button
$modelsButton.Text = 'Models'; $modelsButton.SetBounds(900,195,85,32)
$modelsButton.Add_Click({
    & $guardUi 'open Models' {
    if ($script:profileDialog -and !$script:profileDialog.IsDisposed) { $script:profileDialog.Activate(); return }
    $script:profileDialog = New-Object Windows.Forms.Form
    $script:profileDialog.Text = 'Model and Bone Profile Manager'
    $script:profileDialog.Size = New-Object Drawing.Size(1000,650)
    $script:profileDialog.StartPosition = 'CenterParent'
    $help = New-Object Windows.Forms.Label
    $help.Text = 'Select target in the main window. Register imports M2 folders. Edit Target cells, then Save Corrections; Validate before manual Approve. Visual review is separate.'
    $help.SetBounds(12,10,960,38)
    $script:profileStatus = New-Object Windows.Forms.Label
    $script:profileStatus.SetBounds(12,50,960,50)
    $script:profilePaths = New-Object Windows.Forms.ComboBox
    $script:profilePaths.SetBounds(12,105,960,25); $script:profilePaths.DropDownStyle = 'DropDownList'
    $script:profilePaths.Add_SelectionChangeCommitted({ & $guardUi 'profile revision selection' { $fields.profile.Text=$script:profilePaths.Text; & $refreshProfileGrid } })
    $script:mappingGrid = New-Object Windows.Forms.DataGridView
    $script:mappingGrid.SetBounds(12,140,960,350)
    $script:mappingGrid.AllowUserToAddRows=$false; $script:mappingGrid.AllowUserToDeleteRows=$false
    foreach ($column in @('Source','Target','Evidence category','Evidence','Alternatives')) {
        $index=$script:mappingGrid.Columns.Add($column,$column)
        $script:mappingGrid.Columns[$index].ReadOnly=($column -ne 'Target')
        $script:mappingGrid.Columns[$index].Width=if ($column -eq 'Evidence') { 330 } else { 145 }
    }
    $position=12
    foreach ($pair in @(@('Register Folder','model-register'),@('Generate','profile-generate'),@('Validate','profile-validate'),@('Approve','profile-approve'))) {
        $button=New-Object Windows.Forms.Button
        $button.Text=$pair[0]; $button.Tag=$pair[1]; $button.SetBounds($position,505,140,32)
        if ($pair[1] -eq 'model-register') {
            $button.Add_Click({
                & $guardUi 'register model folder' {
                $dialog=New-Object Windows.Forms.FolderBrowserDialog
                $dialog.SelectedPath=$fields.wow.Text
                if ($dialog.ShowDialog() -eq 'OK') { $fields.wow.Text=$dialog.SelectedPath; & $runCommand }
                $dialog.Dispose()
                }
            })
        } else {
            $button.Add_Click({
                & $guardUi 'model/profile operation' {
                # Finish an active cell edit before starting asynchronous work.
                if (!$script:mappingGrid.EndEdit()) { throw 'Finish or cancel the current mapping edit before continuing.' }
                if ($this.Tag -eq 'profile-approve') {
                    $result=[Windows.Forms.MessageBox]::Show('Confirm you visually reviewed this character and these mappings. This records manual profile approval; animations still need separate review.','Approve profile','OKCancel')
                    if ($result -ne 'OK') { return }
                }
                & $runCommand
                }
            })
        }
        $script:profileDialog.Controls.Add($button); $position+=150
    }
    $save=New-Object Windows.Forms.Button
    $save.Text='Save Corrections'; $save.Tag='profile-generate'; $save.SetBounds(612,505,150,32)
    $save.Add_Click({
        & $guardUi 'save bone corrections' {
        $script:mappingGrid.EndEdit()
        $corrections=@{}
        $original=Get-Content -LiteralPath $fields.profile.Text -Raw | ConvertFrom-Json
        foreach ($row in $script:mappingGrid.Rows) {
            $sourceBone=[string]$row.Cells[0].Value; $targetBone=[string]$row.Cells[1].Value
            if ($targetBone -and $original.mapping.$sourceBone -ne $targetBone) { $corrections[$sourceBone]=$targetBone }
            elseif (!$targetBone -and $original.manual_corrections.PSObject.Properties[$sourceBone]) { $corrections[$sourceBone]=$null }
        }
        $script:pendingOverrides=Join-Path $studioRoot ('Output\Models\overrides_'+[guid]::NewGuid().ToString()+'.json')
        [IO.File]::WriteAllText($script:pendingOverrides,($corrections|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
        & $runCommand
        }
    })
    $visual=New-Object Windows.Forms.Button
    $visual.Text='Open Target Scene'; $visual.SetBounds(772,505,190,32)
    $visual.Add_Click({ Start-Process -FilePath $fields.blender.Text -ArgumentList ('"'+$fields.scene.Text+'"') })
    $script:profileDialog.Controls.AddRange(@($help,$script:profileStatus,$script:profilePaths,$script:mappingGrid,$save,$visual))
    & $refreshProfileGrid
    $script:profileDialog.Show($form)
    }
})
$form.Controls.Add($modelsButton)
& $refreshModels
$fields.profile.Add_TextChanged({ & $guardUi 'selected profile display' { & $refreshProfileHint; & $refreshCatalog } })
& $refreshProfileHint
