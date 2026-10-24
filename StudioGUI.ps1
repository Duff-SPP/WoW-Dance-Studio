param([switch]$SmokeTest, [switch]$ScanEmotesTest, [switch]$BatchTest, [switch]$ModelsTest, [switch]$ApprovalHintTest, [switch]$VariantFilterTest, [switch]$FemaleModelsTest, [switch]$UiRecoveryTest, [switch]$DBCTest, [switch]$M2Test, [switch]$PackTest, [switch]$HDModelsTest)
if ($ScanEmotesTest -or $BatchTest) { $ErrorActionPreference = 'Stop' }
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$studioRoot = $PSScriptRoot
. (Join-Path $studioRoot 'StudioRuntime.ps1')
$studioDefaults = Get-StudioDefaults
foreach ($folder in @('Reports','Output')) { $null = New-Item -ItemType Directory -Path (Join-Path $studioRoot $folder) -Force }
$form = New-Object Windows.Forms.Form
$form.Text = 'WoW Dance Studio 0.4'
$form.Size = New-Object Drawing.Size(1020,1020)
$form.StartPosition = 'CenterScreen'
$fields = @{}
$rows = @(
    @('wow','WoW models folder',(Join-Path $studioRoot 'Input\WoW')),
    @('emotes','Fortnite emotes folder',(Join-Path $studioRoot 'Input\Fortnite')),
    @('blender','Blender executable',$studioDefaults.blender),
    @('scene','Prepared Blender scene',$studioDefaults.scene),
    @('profile','Bone profile JSON',(Join-Path $studioRoot 'Profiles\profile.json'))
)
$rowIndex = 0
foreach ($row in $rows) {
    $label = New-Object Windows.Forms.Label
    $label.Text = $row[1]; $label.SetBounds(12,(15+$rowIndex*35),155,24)
    $box = New-Object Windows.Forms.TextBox
    $box.Text = $row[2]; $box.SetBounds(170,(12+$rowIndex*35),620,25)
    $fields[$row[0]] = $box
    $button = New-Object Windows.Forms.Button
    $button.Text = 'Browse'; $button.Tag = $row[0]; $button.SetBounds(800,(10+$rowIndex*35),85,27)
    $button.Add_Click({
        $key = $this.Tag
        if ($key -in @('wow','emotes')) { $dialog = New-Object Windows.Forms.FolderBrowserDialog }
        else { $dialog = New-Object Windows.Forms.OpenFileDialog }
        if ($dialog.ShowDialog() -eq 'OK') {
            if ($key -in @('wow','emotes')) { $fields[$key].Text = $dialog.SelectedPath }
            else { $fields[$key].Text = $dialog.FileName }
            if ($key -eq 'emotes') { & $refreshAudio }
        }
        $dialog.Dispose()
    })
    $form.Controls.AddRange(@($label,$box,$button)); $rowIndex++
}
$log = New-Object Windows.Forms.TextBox
$log.Multiline = $true; $log.ReadOnly = $true; $log.ScrollBars = 'Vertical'
$log.SetBounds(12,795,975,170)
$log.Text = "v0.4: Select a target, Scan Emotes, Convert Selected, then Preview. Use Models to register and review new profiles.`r`nConvert Animation uses the prepared scene; the batch buttons import exported emotes.`r`nBody-only conversion; visual review required. Prop exports are cataloged but omitted.`r`n"
$form.Controls.Add($log)
$guardUi = {
    param([string]$operation,[scriptblock]$action)
    $ErrorActionPreference = 'Stop'
    try { & $action }
    catch {
        $failure = $_
        $script:lastUiError = $failure
        $errorReport = Join-Path $studioRoot ('Reports\gui_error_'+[guid]::NewGuid().ToString()+'.txt')
        try {
            [IO.File]::WriteAllText($errorReport,($operation+"`r`n"+$failure.Exception.ToString()+"`r`n"+$failure.ScriptStackTrace))
        } catch { $errorReport = 'Could not write diagnostic report' }
        if ($log -and !$log.IsDisposed) {
            $log.AppendText("UI error during ${operation}: $($failure.Exception.Message)`r`nDiagnostic: $errorReport`r`n")
        }
    }
}
$includeAudio = New-Object Windows.Forms.CheckBox
$includeAudio.Text = 'Include Audio'; $includeAudio.SetBounds(12,170,150,22)
$form.Controls.Add($includeAudio)
$refreshAudio = {
    $includeAudio.Checked = $false
    if (Test-Path -LiteralPath $fields.emotes.Text -PathType Container) {
        $found = Get-ChildItem -LiteralPath $fields.emotes.Text -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension.ToLowerInvariant() -in @('.wav','.ogg','.flac','.mp3') } | Select-Object -First 1
        $includeAudio.Checked = $null -ne $found
    }
}
$fields.emotes.Add_Leave($refreshAudio)
& $refreshAudio
$script:jobProcess = $null
$script:jobLog = $null
$script:jobLogSeen = 0
$script:completedJobs = 0
$script:lastExitCode = $null
$searchLabel = New-Object Windows.Forms.Label
$searchLabel.Text = 'Search'; $searchLabel.SetBounds(12,242,65,22)
$search = New-Object Windows.Forms.TextBox
$search.SetBounds(80,238,300,25)
$targetLabel = New-Object Windows.Forms.Label
$targetLabel.Text = 'Target Model:'; $targetLabel.SetBounds(420,242,110,22)
$targetModel = New-Object Windows.Forms.ComboBox
$targetModel.DropDownStyle = 'DropDownList'; $targetModel.SetBounds(530,238,180,25)
$null = $targetModel.Items.Add('Human2 Male'); $targetModel.SelectedIndex = 0
$form.Controls.Add($targetModel)
$emoteList = New-Object Windows.Forms.ListView
$emoteList.SetBounds(12,270,975,200); $emoteList.View = 'Details'
$emoteList.FullRowSelect = $true; $emoteList.MultiSelect = $true; $emoteList.HideSelection = $false
foreach ($column in @(@('Emote',190),@('Variants',160),@('Status',235),@('Audio',90),@('Props',270))) {
    $null = $emoteList.Columns.Add($column[0],$column[1])
}
$variantLabel = New-Object Windows.Forms.Label
$variantLabel.Text = 'Variant'; $variantLabel.SetBounds(12,487,60,22)
$variants = New-Object Windows.Forms.ComboBox
$variants.DropDownStyle = 'DropDownList'; $variants.SetBounds(80,480,140,28)
$details = New-Object Windows.Forms.TextBox
$details.Multiline = $true; $details.ReadOnly = $true; $details.ScrollBars = 'Vertical'
$details.SetBounds(12,525,975,82)
$form.Controls.AddRange(@($searchLabel,$search,$targetLabel,$emoteList,$variantLabel,$variants,$details))
$selectAll = New-Object Windows.Forms.Button
$selectAll.Text = 'Select All'; $selectAll.SetBounds(735,236,115,28)
$selectAll.Add_Click({ foreach ($item in $emoteList.Items) { $item.Selected = $true } })
$clearSelection = New-Object Windows.Forms.Button
$clearSelection.Text = 'Clear Selection'; $clearSelection.SetBounds(860,236,125,28)
$clearSelection.Add_Click({ foreach ($item in $emoteList.Items) { $item.Selected = $false } })
$form.Controls.AddRange(@($selectAll,$clearSelection))
$getTargetSex = {
    $model = if ($script:modelRecords) { $script:modelRecords[$targetModel.Text] } else { $null }
    foreach ($value in @($model.sex, [IO.Path]::GetFileNameWithoutExtension($model.path), $script:selectedTarget)) {
        if ($value -match 'female') { return 'F' }
        if ($value -match 'male') { return 'M' }
    }
    if (!$model) { return 'M' }
    return ''
}
$refreshCatalog = {
    $selectedIds = @($emoteList.SelectedItems | ForEach-Object { $_.Tag.id })
    $emoteList.Items.Clear()
    $catalogPath = Join-Path $studioRoot 'Output\Library\emotes.json'
    if (Test-Path -LiteralPath $catalogPath) {
        $catalog = Get-Content -LiteralPath $catalogPath -Raw | ConvertFrom-Json
        $cachePath = Join-Path $studioRoot 'Output\Library\cache_status.json'
        $cacheInfo = if (Test-Path -LiteralPath $cachePath) { Get-Content -LiteralPath $cachePath -Raw | ConvertFrom-Json } else { $null }
        $profileRequirement = if ($getProfileRequirement) { & $getProfileRequirement } else { '' }
        $targetSex = & $getTargetSex
        foreach ($entry in $catalog.emotes) {
            $entry = $entry.PSObject.Copy()
            if ($targetSex) { $entry.variants = @($entry.variants | Where-Object { $_.variant -in @(('CM'+$targetSex),('CL'+$targetSex)) }) }
            if (!$entry.variants.Count) { continue }
            $searchNames=@($entry.name,$entry.internal_name,$entry.id,$entry.export_id) -join ' '
            if ($search.Text -and $searchNames.IndexOf($search.Text,[StringComparison]::OrdinalIgnoreCase) -lt 0) { continue }
            $item = New-Object Windows.Forms.ListViewItem($entry.name)
            $item.Tag = $entry
            $null = $item.SubItems.Add(($entry.variants.variant -join ', '))
            $targetVersions = @($entry.versions | Where-Object { $_.variant -in $entry.variants.variant -and ($_.target_id -eq $script:selectedTarget -or (!$_.target_id -and $script:selectedTarget -eq 'human2_male')) })
            $displayStatus = if ($targetVersions.Count) { 'Converted - Review Needed' } else { 'Not Converted' }
            if ($cacheInfo -and $cacheInfo.target -eq $script:selectedTarget -and $cacheInfo.profile -eq $fields.profile.Text -and
                !($script:jobProcess -and !$script:jobProcess.HasExited)) {
                $cacheRow = $cacheInfo.items.PSObject.Properties[$entry.id]
                if ($cacheRow -and (($cacheRow.Value.variant -in $entry.variants.variant) -or ($cacheInfo.variant -in $entry.variants.variant))) {
                    $displayStatus = $cacheRow.Value.status
                    if ($cacheRow.Value.version -and $cacheRow.Value.status -ne 'Outdated' -and
                        $entry.approvals.PSObject.Properties.Name -contains $cacheRow.Value.version) { $displayStatus = 'Approved' }
                }
            }
            $null = $item.SubItems.Add($displayStatus)
            if ($profileRequirement) { $item.SubItems[2].Text = $profileRequirement }
            if (!@($entry.variants | Where-Object { !$_.missing_dependencies.Count }).Count) { $item.SubItems[2].Text = 'Missing source skeleton' }
            $audioLabel = $entry.audio.PSObject.Properties.Name -join ', '
            if (!$audioLabel) { $audioLabel = if ($entry.audio_match.status -eq 'ambiguous') { 'Ambiguous' } else { 'Missing' } }
            $null = $item.SubItems.Add($audioLabel)
            $null = $item.SubItems.Add($entry.prop_status)
            $null = $emoteList.Items.Add($item)
            if ($entry.id -in $selectedIds) { $item.Selected = $true }
        }
    }
}
$updateDetails = {
    if (!$emoteList.SelectedItems.Count) { return }
    $entry = $emoteList.SelectedItems[0].Tag
    $asset = $entry.variants | Where-Object variant -eq $variants.Text | Select-Object -First 1
    $lines = @('Emote: '+$entry.id+' | '+$entry.prop_status)
    if ($getProfileRequirement) {
        $requirement = & $getProfileRequirement
        if ($requirement) { $lines += $requirement+': Open Models to review and approve the selected bone profile.' }
    }
    $cachePath = Join-Path $studioRoot 'Output\Library\cache_status.json'
    if (Test-Path -LiteralPath $cachePath) {
        $currentCache = Get-Content -LiteralPath $cachePath -Raw | ConvertFrom-Json
        if ($currentCache.target -eq $script:selectedTarget -and $currentCache.profile -eq $fields.profile.Text) {
            $problem = $currentCache.items.PSObject.Properties[$entry.id]
            if ($problem -and $problem.Value.error) { $lines += 'Conversion requirement: '+$problem.Value.error }
        }
    }
    if ($asset) { $lines += 'Animation: '+$asset.path; $lines += 'Skeleton: '+$asset.source_skeleton; $lines += 'Dependencies: '+($asset.missing_dependencies -join '; ') }
    if ($asset.source_compatibility) { $lines += 'Source compatibility: '+$asset.source_compatibility }
    if ($asset.missing_dependencies.Count) { $lines += 'Selected variant: Missing Dependencies' }
    elseif (!($entry.versions | Where-Object variant -eq $variants.Text)) { $lines += 'Selected variant: Not Converted' }
    foreach ($sound in $entry.audio.PSObject.Properties) { $lines += 'Audio '+$sound.Name+': '+$sound.Value.path }
    if ($entry.audio_match.reason) { $lines += 'Audio matched by: '+$entry.audio_match.reason }
    foreach ($warning in $entry.audio_warnings) { $lines += 'Audio: '+$warning }
    if ($entry.audio_match.status -eq 'ambiguous') {
        foreach ($candidate in $entry.audio_match.candidates) { $lines += 'Audio candidate: '+$candidate.path }
    }
    $lines += 'Stored versions: '+$entry.versions.Count+' | Visual quality: review required'
    if ($entry.last_error) { $lines += 'Last error: '+$entry.last_error }
    $details.Text = $lines -join "`r`n"
}
$emoteList.Add_SelectedIndexChanged({
    if (!$emoteList.SelectedItems.Count) { $variants.Items.Clear(); $details.Clear(); return }
    $variants.Items.Clear()
    foreach ($asset in $emoteList.SelectedItems[0].Tag.variants) { $null = $variants.Items.Add($asset.variant) }
    $preferredVariant = 'CM'+(& $getTargetSex)
    if ($variants.Items.Contains($preferredVariant)) { $variants.SelectedItem = $preferredVariant }
    elseif ($variants.Items.Count) { $variants.SelectedIndex = 0 }
    & $updateDetails
})
$variants.Add_SelectedIndexChanged($updateDetails)
$search.Add_TextChanged($refreshCatalog)
& $refreshCatalog
$runCommand = {
        if ($script:jobProcess -and !$script:jobProcess.HasExited) { return }
        $python = Get-StudioPython $fields.blender.Text
        if (!(Test-Path -LiteralPath $python)) { $log.AppendText("Cannot find bundled Python: $python`r`n"); return }
        $script:jobLog = Join-Path $studioRoot ('Reports\gui_'+[guid]::NewGuid().ToString()+'.log')
        $script:jobLogSeen = 0
        $script:jobCommand = $this.Tag
        $script:jobTarget = $script:selectedTarget
        $values = @('-u',(Join-Path $studioRoot 'studio.py'),$this.Tag)
        if ($this.Tag -eq 'prepare-source') {
            $picker = New-Object Windows.Forms.OpenFileDialog
            $picker.Filter = 'Exported source skeleton (*.uemodel)|*.uemodel'
            if (Test-Path -LiteralPath $fields.emotes.Text -PathType Container) { $picker.InitialDirectory = $fields.emotes.Text }
            try {
                if ($picker.ShowDialog() -ne 'OK') { return }
                $values += '--source-skeleton'; $values += $picker.FileName
            } finally { $picker.Dispose() }
        }
        if ($this.Tag -like 'dbc-*') {
            if (!(& $prepareDBCCommand $this.Tag)) { return }
            $values += $script:dbcExtraArgs
        }
        if ($this.Tag -like 'pack-*') {
            & $preparePackCommand $this.Tag
            $values += $script:packExtraArgs
        }
        if ($this.Tag -like 'm2-*') {
            if (!(& $prepareM2Command $this.Tag)) { return }
            $values += $script:m2ExtraArgs
        }
        foreach ($key in @('wow','emotes','blender','scene','profile')) { $values += '--'+$key; $values += $fields[$key].Text }
        if ($includeAudio.Checked) { $values += '--include-audio' } else { $values += '--no-include-audio' }
        $values += '--target'; $values += $script:selectedTarget
        if ($this.Tag -like 'profile-*') {
            if ($fields.profile.Text -like '*\Profiles\human2_male\*' -or $script:selectedTarget -ne 'human2_male') {
                if (Test-Path -LiteralPath $fields.profile.Text) { $values += '--previous-profile'; $values += $fields.profile.Text }
            }
            if ($script:pendingOverrides) { $values += '--overrides'; $values += $script:pendingOverrides; $script:pendingOverrides = $null }
        }
        if ($forceConvert.Checked) { $values += '--force' }
        if ($montagePlayback.Checked) { $values += '--montage-playback' } else { $values += '--no-montage-playback' }
        if ($this.Tag -in @('library-convert','preview','approve')) {
            if (!$emoteList.SelectedItems.Count -or !$variants.Text) { $log.AppendText("Select an emote and variant first.`r`n"); return }
            if ($this.Tag -in @('preview','approve') -and $emoteList.SelectedItems.Count -ne 1) { $log.AppendText("Select one emote for Preview or approval.`r`n"); return }
            $values += '--emote'; $values += (($emoteList.SelectedItems | ForEach-Object { $_.Tag.id }) -join ',')
            $values += '--variant'; $values += $(if ($this.Tag -eq 'library-convert' -and $emoteList.SelectedItems.Count -gt 1) { 'AUTO' } else { $variants.Text })
        }
        else { $values += '--variant'; $values += 'AUTO' }
        if ($this.Tag -eq 'preview') { $values += '--open' }
        $quoted = ($values | ForEach-Object { '"'+$_+'"' }) -join ' '
        $script:jobProcess = Start-Process -FilePath $python -ArgumentList $quoted -WorkingDirectory $studioRoot -WindowStyle Hidden -RedirectStandardOutput $script:jobLog -RedirectStandardError ($script:jobLog+'.err') -PassThru
        # Keep the native handle so ExitCode remains available for fast jobs.
        $null = $script:jobProcess.Handle
        $log.AppendText("Started $($this.Tag)...`r`n")
}
$prepareSource = New-Object Windows.Forms.Button
$prepareSource.Text = 'Prepare Source'; $prepareSource.Tag = 'prepare-source'; $prepareSource.SetBounds(895,10,105,62)
$prepareSource.Add_Click($runCommand); $form.Controls.Add($prepareSource)
$commands = @(@('Scan Assets','assets'),@('Scan Skeletons','scan'),@('Generate Profile','profile-generate'),@('Convert Animation','convert'))
$index = 0
foreach ($entry in $commands) {
    $button = New-Object Windows.Forms.Button
    $button.Text = $entry[0]; $button.Tag = $entry[1]; $button.SetBounds((12+$index*145),195,140,32)
    $button.Add_Click($runCommand)
    $form.Controls.Add($button); $index++
}
$index = 0
foreach ($entry in @(@('Scan Emotes','catalog'),@('Convert Selected','library-convert'),@('Preview','preview'),@('Mark Approved','approve'))) {
    $button = New-Object Windows.Forms.Button
    $button.Text = $entry[0]; $button.Tag = $entry[1]; $button.SetBounds((250+$index*170),480,160,32)
    $button.Add_Click($runCommand); $form.Controls.Add($button); $index++
}
$review = New-Object Windows.Forms.Button
$review.Text = 'Review Profile'; $review.SetBounds(600,195,140,32)
$review.Add_Click({ Start-Process notepad.exe -ArgumentList ('"'+$fields.profile.Text+'"') })
$form.Controls.Add($review)
$output = New-Object Windows.Forms.Button
$output.Text = 'Open Output'; $output.SetBounds(748,195,140,32)
$output.Add_Click({ Start-Process explorer.exe -ArgumentList ('"'+(Join-Path $studioRoot 'Output')+'"') })
$form.Controls.Add($output)
$forceConvert = New-Object Windows.Forms.CheckBox
$forceConvert.Text = 'Force new versions (ignore current cache)'; $forceConvert.SetBounds(12,640,420,24)
$form.Controls.Add($forceConvert)
$montagePlayback = New-Object Windows.Forms.CheckBox
$montagePlayback.Text = 'Auto-detect Fortnite playback (use intro / loop sections only when needed)'
$montagePlayback.Checked = $true
$montagePlayback.SetBounds(12,610,975,24)
$form.Controls.Add($montagePlayback)
$queueInfo = New-Object Windows.Forms.Label
$queueInfo.Text = 'Queue: no jobs'; $queueInfo.SetBounds(12,737,970,22)
$queueProgress = New-Object Windows.Forms.ProgressBar
$queueProgress.SetBounds(12,762,975,18)
$form.Controls.AddRange(@($queueInfo,$queueProgress))
$queueIndex = 0
foreach ($entry in @(@('Convert Missing','convert-missing'),@('Convert All','convert-all'),@('Start','queue-start'),@('Pause','queue-pause'),@('Resume','queue-resume'),@('Cancel','queue-cancel'),@('Retry Failed','retry-failed'),@('Verify Cache','verify-cache'))) {
    $control = New-Object Windows.Forms.Button
    $control.Text = $entry[0]; $control.Tag = $entry[1]
    $control.SetBounds((12+($queueIndex%4)*245),(670+[math]::Floor($queueIndex/4)*32),237,29)
    if ($entry[1] -in @('queue-pause','queue-cancel','queue-start','queue-resume')) {
        $control.Add_Click({
            if ($this.Tag -in @('queue-start','queue-resume') -and !$script:jobProcess) { & $runCommand; return }
            $python = Get-StudioPython $fields.blender.Text
            $controlLog = Join-Path $studioRoot ('Reports\queue_control_'+[guid]::NewGuid().ToString()+'.log')
            Start-Process -FilePath $python -ArgumentList @('-u',('"'+(Join-Path $studioRoot 'studio.py')+'"'),$this.Tag,'--control-only') -WorkingDirectory $studioRoot -WindowStyle Hidden -RedirectStandardOutput $controlLog -RedirectStandardError ($controlLog+'.err')
        })
    } else { $control.Add_Click($runCommand) }
    $form.Controls.Add($control); $queueIndex++
}
$timer = New-Object Windows.Forms.Timer
$timer.Interval = 500
$timer.Add_Tick({
    & $guardUi 'job status / profile refresh' {
    $queuePath = Join-Path $studioRoot 'Output\Library\queue.json'
    if (Test-Path -LiteralPath $queuePath) {
        $queueState = Get-Content -LiteralPath $queuePath -Raw | ConvertFrom-Json
        $jobs = @($queueState.jobs | Where-Object batch -eq $queueState.batch)
        $remaining = @($jobs | Where-Object status -in @('Pending','Running')).Count
        $skipped = @($jobs | Where-Object status -like 'Skipped*').Count
        $failed = @($jobs | Where-Object status -eq 'Failed').Count
        $blocked = @($jobs | Where-Object status -like 'Blocked*').Count
        $completed = @($jobs | Where-Object { $_.status -like 'Converted*' -or $_.status -eq 'Approved' }).Count
        $current = ($jobs | Where-Object status -eq 'Running' | Select-Object -First 1).emote
        $queueInfo.Text = "Queue: $($queueState.mode) | Current: $current | Completed: $completed | Remaining: $remaining | Skipped: $skipped | Failed: $failed | Blocked: $blocked"
        if ($queueState.preparation.status -eq 'running') {
            $queueInfo.Text = if ($queueState.preparation.cancel_requested) { 'Cancelling preparation after the current check...' } else { 'Preparing conversion queue — Pause or Cancel stops preparation safely.' }
        }
        $queueProgress.Maximum = [math]::Max(1,$jobs.Count)
        $queueProgress.Value = [math]::Min($queueProgress.Maximum,$jobs.Count-$remaining)
        $runningJob = $jobs | Where-Object status -eq 'Running' | Select-Object -First 1
        if ($script:jobProcess -and $runningJob.log -and (Test-Path -LiteralPath $runningJob.log -PathType Leaf)) {
            if ($script:workerProgressLog -ne $runningJob.log) {
                $script:workerProgressLog = $runningJob.log
                $script:workerProgressLines = 0
            }
            $workerLines = @(Get-Content -LiteralPath $runningJob.log)
            for ($lineIndex=$script:workerProgressLines; $lineIndex -lt $workerLines.Count; $lineIndex++) {
                if ($workerLines[$lineIndex] -like 'STUDIO:*') { $log.AppendText($workerLines[$lineIndex]+"`r`n") }
            }
            $script:workerProgressLines = $workerLines.Count
        }
        $catalogQueueStamp = "$($queueState.batch):$completed`:$skipped"
        if ($script:catalogQueueStamp -ne $catalogQueueStamp) {
            $script:catalogQueueStamp = $catalogQueueStamp
            & $refreshCatalog
            & $updateDetails
        }
    }
    if ($script:jobProcess -and (Test-Path -LiteralPath $script:jobLog)) {
        $content = Get-Content -LiteralPath $script:jobLog -Raw
        if ($content -and $content.Length -gt $script:jobLogSeen) {
            $log.AppendText($content.Substring($script:jobLogSeen))
            $script:jobLogSeen = $content.Length
        }
    }
    if ($script:jobProcess -and $script:jobProcess.HasExited) {
        $finishedProcess = $script:jobProcess
        try {
            $finishedProcess.WaitForExit()
            $errorPath = $script:jobLog+'.err'
            if (Test-Path -LiteralPath $errorPath -PathType Leaf) {
                $errorText = Get-Content -LiteralPath $errorPath -Raw
                # Get-Content -Raw returns null for an empty file. WinForms
                # AppendText cannot accept that value.
                if (![string]::IsNullOrEmpty($errorText)) { $log.AppendText($errorText) }
            }
            $script:lastExitCode = $finishedProcess.ExitCode
            $log.AppendText("Process exit: $($script:lastExitCode)`r`n")
        }
        finally {
            $finishedProcess.Dispose()
            $script:jobProcess = $null
            $script:completedJobs++
        }
        $useLatestProfile = $script:jobCommand -in @('profile-generate','profile-validate','profile-approve') -and $script:jobTarget -eq $script:selectedTarget
        & $refreshModels -UseLatest:$useLatestProfile
        & $refreshCatalog
        & $updateDetails
        if ($script:jobCommand -like 'dbc-*' -and $refreshDBC) { & $refreshDBC $script:jobCommand $script:lastExitCode }
        if ($script:jobCommand -like 'pack-*' -and $refreshPack) { & $refreshPack $script:jobCommand $script:lastExitCode }
        if ($script:jobCommand -like 'm2-*' -and $refreshM2) { & $refreshM2 $script:jobCommand $script:lastExitCode }
        if ($script:jobCommand -eq 'profile-validate' -and $script:lastExitCode -eq 0) {
            $log.AppendText("Validation completed successfully. Review the profile in Models, then Approve when ready.`r`n")
        }
    }
    }
})
. (Join-Path $studioRoot 'StudioModels.ps1')
. (Join-Path $studioRoot 'StudioDBC.ps1')
. (Join-Path $studioRoot 'StudioM2.ps1')
. (Join-Path $studioRoot 'StudioPack.ps1')
. (Join-Path $studioRoot 'StudioWorkflow.ps1')
$timer.Start()
if ($PackTest) {
    $form.Show(); [Windows.Forms.Application]::DoEvents(); $packButton.PerformClick()
    $script:packTestPhase=0; $script:packTestDeadline=[DateTime]::UtcNow.AddSeconds(55)
    $packTestTimer=New-Object Windows.Forms.Timer; $packTestTimer.Interval=100
    $packTestTimer.Add_Tick({
        if ([DateTime]::UtcNow -gt $script:packTestDeadline) { $script:testFailure='Pack GUI timed out'; $packTestTimer.Stop(); $form.Close(); return }
        if ($script:jobProcess) { return }
        if ($script:lastExitCode -ne 0 -or $script:lastUiError) { $script:testFailure='Pack CLI or UI failed'; $packTestTimer.Stop(); $form.Close(); return }
        $blocked=0
        for ($i=0;$i -lt $script:packList.Items.Count;$i++) {
            $item=$script:packList.Items[$i]
            if ($item.label -like '*Client compatibility blocked*') {
                $blocked++
                if ($item.eligible) { $script:testFailure='Known unsafe export enabled' }
                $script:packList.SetItemChecked($i,$true)
                if ($script:packList.GetItemChecked($i)) { $script:testFailure='Known unsafe export selectable' }
            }
        }
        if ($blocked -lt 2) { $script:testFailure='Client compatibility blockers not displayed' }
        $packTestTimer.Stop(); $script:packDialog.Close(); $form.Close()
    }); $packTestTimer.Start()
}
if ($M2Test) {
    $form.Show(); [Windows.Forms.Application]::DoEvents(); $m2Button.PerformClick()
    ($script:m2Dialog.Controls | Where-Object Tag -eq 'm2-scan').PerformClick()
    $script:m2TestDeadline=[DateTime]::UtcNow.AddSeconds(40)
    $m2TestTimer=New-Object Windows.Forms.Timer; $m2TestTimer.Interval=100
    $m2TestTimer.Add_Tick({
        if ([DateTime]::UtcNow -gt $script:m2TestDeadline) { $script:testFailure='M2 GUI timed out'; $m2TestTimer.Stop(); $form.Close(); return }
        if ($script:jobProcess) { return }
        if ($script:lastExitCode -ne 0 -or $script:lastUiError -or !$script:m2Dances.Items.Count) { $script:testFailure='M2 model eligibility scan failed' }
        if ($script:m2ExportButton.Enabled) { $script:testFailure='M2 export enabled before preview/validation' }
        for ($i=0;$i -lt $script:m2Dances.Items.Count;$i++) { if (!$script:m2Dances.Items[$i].eligible) {
            $script:m2Dances.SetItemChecked($i,$true)
            if ($script:m2Dances.GetItemChecked($i)) { $script:testFailure='Unapproved/unregistered dance enabled' }; break
        } }
        $m2TestTimer.Stop(); $script:m2Dialog.Close(); $form.Close()
    }); $m2TestTimer.Start()
}
if ($DBCTest) {
    $form.Show(); [Windows.Forms.Application]::DoEvents(); $dbcButton.PerformClick()
    if ($script:dbcExportButton.Enabled) { throw 'DBC export enabled before validation' }
    ($script:dbcDialog.Controls | Where-Object Tag -eq 'dbc-scan').PerformClick()
    $script:dbcTestPhase=0; $script:dbcTestDeadline=[DateTime]::UtcNow.AddSeconds(40)
    $dbcTestTimer=New-Object Windows.Forms.Timer; $dbcTestTimer.Interval=100
    $dbcTestTimer.Add_Tick({
        if ([DateTime]::UtcNow -gt $script:dbcTestDeadline) { $script:testFailure='DBC GUI timed out'; $dbcTestTimer.Stop(); $form.Close(); return }
        if ($script:jobProcess) { return }
        if ($script:lastExitCode -ne 0 -or $script:lastUiError) { $script:testFailure='DBC CLI or UI operation failed'; $dbcTestTimer.Stop(); $form.Close(); return }
        if ($script:dbcTestPhase -eq 0) {
            if ($script:dbcFiles.Items.Count -ne 11 -or !$script:dbcPreviewButton.Enabled) { $script:testFailure='DBC schemas/status not loaded' }
            for ($i=0;$i -lt $script:dbcDances.Items.Count;$i++) {
                if (!$script:dbcDances.Items[$i].eligible) {
                    $script:dbcDances.SetItemChecked($i,$true)
                    if ($script:dbcDances.GetItemChecked($i)) { $script:testFailure='Unapproved dance selectable for export' }
                    break
                }
            }
            $script:dbcFindID.Text='69'
            ($script:dbcDialog.Controls | Where-Object Tag -eq 'dbc-ids').PerformClick()
            $script:dbcTestPhase=1
        }
        else {
            if ($script:dbcDetails.Text -notlike '*EmoteDance*') { $script:testFailure='Existing DBC ID detail missing' }
            $dbcTestTimer.Stop(); $script:dbcDialog.Close(); $form.Close()
        }
    })
    $dbcTestTimer.Start()
}
if ($VariantFilterTest) {
    $form.Show(); [Windows.Forms.Application]::DoEvents()
    foreach ($selection in @('human2_female_c5b51db1','Human2 Male')) {
        $targetModel.SelectedItem = $selection
        [Windows.Forms.Application]::DoEvents()
        $sex = & $getTargetSex
        if (!$emoteList.Items.Count) { throw 'Sex filter hid all actual emotes' }
        foreach ($item in $emoteList.Items) {
            foreach ($asset in $item.Tag.variants) { if (!$asset.variant.EndsWith($sex)) { throw 'Opposite-sex variant visible' } }
        }
        $emoteList.Items[0].Selected = $true
        [Windows.Forms.Application]::DoEvents()
        if ($variants.Text -ne ('CM'+$sex)) { throw 'Wrong automatic variant selection' }
    }
    $hintTimer = New-Object Windows.Forms.Timer
    $hintTimer.Interval = 300; $hintTimer.Add_Tick({ $hintTimer.Stop(); $form.Close() }); $hintTimer.Start()
}
if ($ApprovalHintTest) {
    $form.Show(); [Windows.Forms.Application]::DoEvents()
    $targetModel.SelectedItem = 'human2_female_c5b51db1'
    [Windows.Forms.Application]::DoEvents()
    $expectedModel = $script:modelRecords[$targetModel.Text]
    if ($fields.scene.Text -ne $expectedModel.scene -or $fields.profile.Text -ne $expectedModel.profile) { throw 'Target selection did not resolve its matching scene/profile' }
    if ($profileHint.Text -notlike '*Profile approval required*') { throw 'Missing visible bone-profile approval explanation' }
    foreach ($item in $emoteList.Items) { if ($item.SubItems[2].Text -notin @('Profile approval required','Missing source skeleton')) { throw 'Misleading dependency status remains' } }
    $emoteList.Items[0].Selected = $true; & $updateDetails
    if ($details.Text -notlike '*Profile approval required*') { throw 'Details omit the profile blocker' }
    $hintTimer = New-Object Windows.Forms.Timer
    $hintTimer.Interval = 300; $hintTimer.Add_Tick({ $hintTimer.Stop(); $form.Close() }); $hintTimer.Start()
}
if ($HDModelsTest) {
    $form.Show(); [Windows.Forms.Application]::DoEvents()
    $hdLabels = @($script:modelRecords.Keys | Where-Object { $_ -like '* (Client HD)' })
    if ($hdLabels.Count -ne 20) { throw 'Expected 20 separate Client HD model choices' }
    foreach ($label in $hdLabels) {
        $targetModel.SelectedItem = $label
        [Windows.Forms.Application]::DoEvents()
        $expectedModel = $script:modelRecords[$label]
        if ($script:selectedTarget -ne $expectedModel.id -or $fields.scene.Text -ne $expectedModel.scene -or $fields.profile.Text -ne $expectedModel.profile) { throw ('HD selection resolved a different model/profile: '+$label) }
        if ($script:lastUiError) { throw $script:lastUiError }
    }
    $targetModel.SelectedItem = 'Human2 Male'
    $hdTimer = New-Object Windows.Forms.Timer
    $hdTimer.Interval = 300; $hdTimer.Add_Tick({ $hdTimer.Stop(); $form.Close() }); $hdTimer.Start()
}
if ($ModelsTest -or $FemaleModelsTest) {
    $form.Show(); [Windows.Forms.Application]::DoEvents()
    if ($FemaleModelsTest) {
        $targetModel.SelectedItem = 'human2_female_c5b51db1'
        $emoteList.Items[0].Selected = $true
        [Windows.Forms.Application]::DoEvents()
    }
    $modelsButton.PerformClick(); [Windows.Forms.Application]::DoEvents()
    if ($UiRecoveryTest) {
        $savedProfile = $fields.profile.Text
        $badProfile = Join-Path $studioRoot ('Reports\invalid_profile_'+[guid]::NewGuid().ToString()+'.json')
        [IO.File]::WriteAllText($badProfile,'invalid JSON for UI recovery test')
        $fields.profile.Text = $badProfile
        & $guardUi 'profile refresh recovery test' { & $refreshProfileGrid }
        if (!$script:lastUiError -or $log.Text -notlike '*Diagnostic:*') { throw 'UI failure was not logged' }
        $fields.profile.Text = $savedProfile
        & $refreshProfileGrid
        $script:lastUiError = $null
    }
    if ($script:mappingGrid.Rows.Count -ne 24) { throw 'Profile manager did not display 24 legacy mappings' }
    $validateButton = $script:profileDialog.Controls | Where-Object Tag -eq 'profile-validate' | Select-Object -First 1
    $validateButton.PerformClick()
    $script:modelDeadline = [DateTime]::UtcNow.AddSeconds(30)
    $modelTestTimer = New-Object Windows.Forms.Timer
    $modelTestTimer.Interval = 100
    $modelTestTimer.Add_Tick({
        if ([DateTime]::UtcNow -gt $script:modelDeadline) { $script:testFailure='Profile validation GUI timeout'; $modelTestTimer.Stop(); $form.Close(); return }
        if ($script:jobProcess) { return }
        if ($script:lastExitCode -ne 0 -or $script:mappingGrid.Rows.Count -ne 24 -or $script:profileStatus.Text -notlike '*Validated Technically*') { $script:testFailure='Profile manager CLI/refresh failed' }
        if ($script:lastUiError) { $script:testFailure='Unhandled profile refresh error: '+$script:lastUiError.Exception.Message }
        $modelTestTimer.Stop(); $script:profileDialog.Close(); $form.Close()
    })
    $modelTestTimer.Start()
}
if ($ScanEmotesTest) {
    $form.Show()
    [Windows.Forms.Application]::DoEvents()
    $scanButton = $form.Controls | Where-Object Tag -eq 'catalog' | Select-Object -First 1
    $script:testDeadline = [DateTime]::UtcNow.AddSeconds(25)
    $scanButton.PerformClick()
    $testTimer = New-Object Windows.Forms.Timer
    $testTimer.Interval = 100
    $testTimer.Add_Tick({
        if ([DateTime]::UtcNow -gt $script:testDeadline) {
            $script:testFailure = 'Scan Emotes completion timed out'
            $testTimer.Stop(); $form.Close(); return
        }
        if ($script:jobProcess) { return }
        $expectedCount = @((Get-Content -LiteralPath (Join-Path $studioRoot 'Output\Library\emotes.json') -Raw | ConvertFrom-Json).emotes).Count
        if ($script:lastExitCode -ne 0 -or $emoteList.Items.Count -ne $expectedCount) {
            $script:testFailure = 'Scan did not report exit 0 and refresh the indexed families'
            $testTimer.Stop(); $form.Close(); return
        }
        if ($script:completedJobs -eq 1) {
            # Explicitly exercise the empty-stderr case as well as the actual
            # catalog command and allow another scan after completion.
            $emptyLog = Join-Path $studioRoot ('Reports\gui_empty_'+[guid]::NewGuid().ToString()+'.log')
            [IO.File]::WriteAllText($emptyLog,'')
            [IO.File]::WriteAllText(($emptyLog+'.err'),'')
            $script:jobLog = $emptyLog; $script:jobLogSeen = 0
            $script:jobProcess = Start-Process -FilePath $env:ComSpec -ArgumentList '/c exit 0' -WindowStyle Hidden -PassThru
            $null = $script:jobProcess.Handle
        }
        elseif ($script:completedJobs -eq 2) { $scanButton.PerformClick() }
        elseif ($script:completedJobs -eq 3) {
            $testTimer.Stop(); $form.Close()
        }
    })
    $testTimer.Start()
}
if ($SmokeTest) {
    $form.Show()
    [Windows.Forms.Application]::DoEvents()
    if ($emoteList.Items.Count) { $emoteList.Items[0].Selected = $true }
    $smokeTimer = New-Object Windows.Forms.Timer
    $smokeTimer.Interval = 800
    $smokeTimer.Add_Tick({ $smokeTimer.Stop(); $form.Close() })
    $smokeTimer.Start()
}
if ($BatchTest) {
    $form.Show(); [Windows.Forms.Application]::DoEvents()
    $emoteList.Items[0].Selected = $true
    $convertButton = $form.Controls | Where-Object Tag -eq 'library-convert' | Select-Object -First 1
    $convertButton.PerformClick()
    $script:testDeadline = [DateTime]::UtcNow.AddSeconds(25)
    $batchTimer = New-Object Windows.Forms.Timer
    $batchTimer.Interval = 100
    $batchTimer.Add_Tick({
        if ([DateTime]::UtcNow -gt $script:testDeadline) { $script:testFailure = 'GUI batch timed out'; $batchTimer.Stop(); $form.Close(); return }
        if (!$script:jobProcess -and $script:completedJobs -gt 0) {
            if ($script:lastExitCode -ne 0 -or $log.Text -notmatch '"skipped": 1') { $script:testFailure = 'GUI did not return a verified cache hit' }
            $batchTimer.Stop(); $form.Close()
        }
    })
    $batchTimer.Start()
}
$form.Add_FormClosed({ $timer.Stop(); $timer.Dispose() })
[Windows.Forms.Application]::Run($form)
if ($HDModelsTest) { $hdTimer.Dispose(); Write-Output 'PASS: all 20 Client HD selections resolved their exact target, scene and profile' }
if ($M2Test) { $m2TestTimer.Dispose(); if ($script:testFailure) { throw $script:testFailure }; Write-Output 'PASS: M2 Manager scanned the real model and enforced DBC/approval/preview gates' }
if ($DBCTest) { $dbcTestTimer.Dispose(); if ($script:testFailure) { throw $script:testFailure }; Write-Output 'PASS: DBC Manager scanned real layouts, blocked unapproved dances and showed existing record 69' }
if ($VariantFilterTest) { $hintTimer.Dispose(); Write-Output 'PASS: male/female model switches filter emotes and automatically select matching variants' }
if ($ApprovalHintTest) { $hintTimer.Dispose(); Write-Output 'PASS: target auto-resolves matching profile; approval hint, emote status and details identify the actual blocker' }
if ($ModelsTest -or $FemaleModelsTest) {
    $modelTestTimer.Dispose()
    if ($script:testFailure) { throw $script:testFailure }
    Write-Output 'PASS: Model/profile manager displayed mappings, ran validation asynchronously and refreshed the revision'
}
if ($ScanEmotesTest) {
    $testTimer.Dispose()
    if ($script:testFailure) { throw $script:testFailure }
    Write-Output 'PASS: Scan Emotes twice, empty stderr, exit code 0, catalog refresh and repeat-job cleanup'
}
if ($BatchTest) {
    $batchTimer.Dispose()
    if ($script:testFailure) { throw $script:testFailure }
    Write-Output 'PASS: GUI Convert Selected used the shared scheduler and returned a verified cache hit'
}

if ($PackTest) { $packTestTimer.Dispose(); if ($script:testFailure) { throw $script:testFailure }; Write-Output 'PASS: Build Pack GUI displayed client compatibility blockers and prevented selection of known unsafe exports' }
