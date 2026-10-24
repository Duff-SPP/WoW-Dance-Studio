$script:workflowDialog=$null
$script:workflowProcess=$null
$workflowButton=New-Object Windows.Forms.Button
$workflowButton.Text='Convert && Build Pack'; $workflowButton.SetBounds(895,115,95,58)
$openWorkflow={ & $guardUi 'Convert and build pack' {
    if ($script:workflowDialog -and !$script:workflowDialog.IsDisposed) { $script:workflowDialog.Activate(); return }
    $script:workflowDialog=New-Object Windows.Forms.Form
    $script:workflowCombined=($this.Tag -eq 'combined')
    $script:workflowTargets=@{}
    $script:workflowDialog.Text='Convert & Build Pack'; $script:workflowDialog.Size=New-Object Drawing.Size(980,760); $script:workflowDialog.StartPosition='CenterParent'
    $note=New-Object Windows.Forms.Label; $note.Text='Choose one race/gender and every dance you want in this pack, including earlier ones. Run reuses valid conversions, converts missing dances, and builds the client/server pack + addon.'; $note.SetBounds(16,12,930,38)
    $script:workflowModel=New-Object Windows.Forms.ComboBox; $script:workflowModel.DropDownStyle='DropDownList'; $script:workflowModel.DisplayMember='label'; $script:workflowModel.SetBounds(16,55,600,28)
    foreach ($entry in ($script:modelRecords.GetEnumerator() | Sort-Object Key)) {
        $null=$script:workflowModel.Items.Add([pscustomobject]@{label=$entry.Key;model=$entry.Value})
        if ($entry.Value.id -eq $script:selectedTarget) { $script:workflowModel.SelectedIndex=$script:workflowModel.Items.Count-1 }
    }
    if ($script:workflowModel.SelectedIndex -lt 0 -and $script:workflowModel.Items.Count) { $script:workflowModel.SelectedIndex=0 }
    $script:workflowAudio=New-Object Windows.Forms.CheckBox; $script:workflowAudio.Text='Enable music playback when available'; $script:workflowAudio.Checked=$true; $script:workflowAudio.SetBounds(640,55,305,28)
    $script:workflowSearch=New-Object Windows.Forms.TextBox; $script:workflowSearch.SetBounds(16,93,450,26)
    $all=New-Object Windows.Forms.Button; $all.Text='Select visible'; $all.SetBounds(485,90,150,30)
    $clear=New-Object Windows.Forms.Button; $clear.Text='Clear selection'; $clear.SetBounds(645,90,150,30)
    $script:workflowDances=New-Object Windows.Forms.ListView; $script:workflowDances.View='Details'; $script:workflowDances.CheckBoxes=$true; $script:workflowDances.FullRowSelect=$true; $script:workflowDances.SetBounds(16,130,930,355)
    foreach ($col in @(@('Dance',280),@('Variant',90),@('Audio',160),@('Library',360))) { $null=$script:workflowDances.Columns.Add($col[0],$col[1]) }
    $script:workflowChecks=@{}
    $script:workflowCatalog=Get-Content (Join-Path $studioRoot 'Output\Library\emotes.json') -Raw | ConvertFrom-Json
    $script:fillWorkflow={
        $script:workflowFilling=$true
        try {
        $script:workflowDances.Items.Clear()
        if (!$script:workflowModel.SelectedItem) { return }
        $model=$script:workflowModel.SelectedItem.model
        $sex=if ($model.path -match 'female') { 'F' } elseif ($model.path -match 'male') { 'M' } else { '' }
        foreach ($emote in $script:workflowCatalog.emotes) {
            $searchNames=@($emote.name,$emote.internal_name,$emote.id,$emote.export_id) -join ' '
            if ($script:workflowSearch.Text -and $searchNames.IndexOf($script:workflowSearch.Text,[StringComparison]::OrdinalIgnoreCase) -lt 0) { continue }
            $variant=@($emote.variants | Where-Object variant -eq ('CM'+$sex))
            if (!$variant.Count) { $variant=@($emote.variants | Where-Object variant -eq ('CL'+$sex)) }
            if (!$variant.Count) { continue }
            $versions=@($emote.versions | Where-Object { $_.target_id -eq $model.id -and $_.variant -eq $variant[0].variant })
            $item=New-Object Windows.Forms.ListViewItem($emote.name); $item.Tag=$emote.id
            $null=$item.SubItems.Add($variant[0].variant)
            $audio=@($emote.audio.PSObject.Properties | ForEach-Object Name) -join ', '
            if (!$audio) { $audio='Missing (dance can convert)' }
            $null=$item.SubItems.Add($audio)
            $null=$item.SubItems.Add($(if ($versions.Count) { 'Stored - Run verifies cache before reuse' } else { 'Not converted for this model' }))
            $null=$script:workflowDances.Items.Add($item)
            if ($script:workflowChecks.ContainsKey($emote.id)) { $item.Checked=$true }
        }
        } finally { $script:workflowFilling=$false }
    }
    $script:workflowDances.Add_ItemChecked({ param($sender,$e)
        if ($script:workflowFilling) { return }
        if ($e.Item.Checked) { $script:workflowChecks[$e.Item.Tag]=$true } else { $script:workflowChecks.Remove($e.Item.Tag) }
    })
    $script:workflowModel.Add_SelectedIndexChanged({ $script:workflowChecks=@{}; & $script:fillWorkflow })
    $script:workflowSearch.Add_TextChanged({ & $script:fillWorkflow })
    $all.Add_Click({ foreach ($item in $script:workflowDances.Items) { $item.Checked=$true } })
    $clear.Add_Click({ $script:workflowChecks=@{}; foreach ($item in $script:workflowDances.Items) { $item.Checked=$false } })
    $script:workflowStatus=New-Object Windows.Forms.TextBox; $script:workflowStatus.Multiline=$true; $script:workflowStatus.ReadOnly=$true; $script:workflowStatus.ScrollBars='Vertical'; $script:workflowStatus.SetBounds(16,545,930,135)
    $script:workflowStatus.Text='Start with five dances. Existing valid conversions are reused, including earlier sessions. Run authorizes technical export; visual review remains outstanding. Missing audio does not block animation conversion.'
    $script:workflowCode=New-Object Windows.Forms.CheckBox; $script:workflowCode.Text='Include main addon code update (otherwise update catalog only)'; $script:workflowCode.SetBounds(16,710,850,24)
    $script:workflowMontage=New-Object Windows.Forms.CheckBox; $script:workflowMontage.Text='Auto-detect Fortnite playback (intro / loop where needed; includes client DLL update)'; $script:workflowMontage.SetBounds(16,737,900,24)
    $script:workflowMontage.Add_CheckedChanged({ if ($script:workflowMontage.Checked) { $script:workflowCode.Checked=$true } })
    $script:workflowMontage.Checked=$montagePlayback.Checked
    $script:workflowDialog.Height=835
    $script:workflowProgress=New-Object Windows.Forms.ProgressBar; $script:workflowProgress.SetBounds(16,690,930,16)
    $script:workflowRun=New-Object Windows.Forms.Button; $script:workflowRun.Text='Run'; $script:workflowRun.SetBounds(16,500,210,34)
    $script:workflowResume=New-Object Windows.Forms.Button; $script:workflowResume.Text='Resume last run'; $script:workflowResume.SetBounds(245,500,210,34)
    $cancel=New-Object Windows.Forms.Button; $cancel.Text='Cancel after current step'; $cancel.SetBounds(475,500,230,34)
    $open=New-Object Windows.Forms.Button; $open.Text='Open Pack Folder'; $open.SetBounds(725,500,220,34)
    $script:startWorkflow={
        if ($script:workflowProcess -and !$script:workflowProcess.HasExited) { throw 'A workflow is already running.' }
        $python=Get-StudioPython $fields.blender.Text
        if (!(Test-Path -LiteralPath $python)) { throw 'Cannot find Blender bundled Python' }
        $folder=Split-Path $script:workflowRequest
        Remove-Item -LiteralPath (Join-Path $folder 'cancel') -ErrorAction SilentlyContinue
        $args=@('-u','-m','studio_core.workflow',('"'+$script:workflowRequest+'"'))
        $script:workflowProcess=Start-Process -FilePath $python -ArgumentList $args -WorkingDirectory $studioRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $folder 'run.log') -RedirectStandardError (Join-Path $folder 'error.log') -PassThru
        $null=$script:workflowProcess.Handle
        $script:workflowRun.Enabled=$false; $script:workflowResume.Enabled=$false
        $script:workflowStatus.Text='Checking model, profile and cached conversions...'
    }
    $script:workflowRun.Add_Click({ & $guardUi 'Run conversion and pack' {
        if ($script:jobProcess -and !$script:jobProcess.HasExited) { throw 'Wait for the current Studio operation to finish.' }
        if (!$script:workflowCombined -and !$script:workflowChecks.Count) { throw 'Select at least one dance.' }
        if ($script:workflowCombined -and !$script:workflowTargets.Count) { throw 'Add at least one model and its dances to the combined pack.' }
        $folder=Join-Path $studioRoot ('Output\Workflows\'+[guid]::NewGuid().ToString('N')); [IO.Directory]::CreateDirectory($folder) | Out-Null
        $script:workflowRequest=Join-Path $folder 'request.json'
        $request=@{target=$script:workflowModel.SelectedItem.model.id;emotes=@($script:workflowChecks.Keys | Sort-Object);asset_root=$fields.emotes.Text;blender=$fields.blender.Text;include_audio=$script:workflowAudio.Checked;include_addon_code=$script:workflowCode.Checked}
        $request.montage_playback=$script:workflowMontage.Checked
        if ($script:workflowCombined) { $request.targets=@($script:workflowTargets.Values | ForEach-Object { @{target=$_.target;emotes=@($_.emotes)} }) }
        [IO.File]::WriteAllText($script:workflowRequest,($request|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
        [IO.File]::WriteAllText((Join-Path $studioRoot 'Output\Workflows\latest.txt'),$script:workflowRequest)
        if ($script:workflowCombined) { [IO.File]::WriteAllText((Join-Path $studioRoot 'Output\Workflows\latest_combined.txt'),$script:workflowRequest) }
        & $script:startWorkflow
    } })
    $script:workflowResume.Add_Click({ & $guardUi 'Resume conversion and pack' {
        $latest=Join-Path $studioRoot 'Output\Workflows\latest.txt'
        if ($script:workflowCombined) { $latest=Join-Path $studioRoot 'Output\Workflows\latest_combined.txt' }
        if (!(Test-Path -LiteralPath $latest)) { throw 'No previous workflow to resume.' }
        if ($script:jobProcess -and !$script:jobProcess.HasExited) { throw 'Wait for the current Studio operation to finish.' }
        $script:workflowRequest=[IO.File]::ReadAllText($latest)
        $saved=Get-Content $script:workflowRequest -Raw | ConvertFrom-Json
        if ($saved.targets) {
            if (!$script:workflowCombined) { throw 'Resume this request from Build Combined Pack.' }
            $script:workflowTargets=@{}
            foreach ($entry in $saved.targets) { $script:workflowTargets[$entry.target]=[pscustomobject]@{target=$entry.target;emotes=@($entry.emotes);label=$entry.target} }
            & $script:fillWorkflowBasket
        }
        for ($i=0;$i -lt $script:workflowModel.Items.Count;$i++) {
            if ($script:workflowModel.Items[$i].model.id -eq $saved.target) { $script:workflowModel.SelectedIndex=$i; break }
        }
        $script:workflowChecks=@{}; foreach ($id in $saved.emotes) { $script:workflowChecks[$id]=$true }
        $script:workflowAudio.Checked=[bool]$saved.include_audio
        $script:workflowCode.Checked=[bool]$saved.include_addon_code
        $script:workflowMontage.Checked=[bool]$saved.montage_playback
        & $script:fillWorkflow
        & $script:startWorkflow
    } })
    $cancel.Add_Click({ if ($script:workflowRequest) { [IO.File]::WriteAllText((Join-Path (Split-Path $script:workflowRequest) 'cancel'),'cancel'); $script:workflowStatus.Text='Cancellation requested. The current conversion/export step will finish first.' } })
    $open.Add_Click({ & $guardUi 'Open workflow pack' {
        if (!$script:workflowRequest) { throw 'Run or resume a workflow first.' }
        $state=Get-Content (Join-Path (Split-Path $script:workflowRequest) 'status.json') -Raw | ConvertFrom-Json
        if (!$state.complete -or !$state.pack.output) { throw 'A complete pack is not ready yet.' }
        Start-Process explorer.exe -ArgumentList ('"'+$state.pack.output+'"')
    } })
    $script:workflowTimer=New-Object Windows.Forms.Timer; $script:workflowTimer.Interval=1500
    $script:workflowTimer.Add_Tick({
        if (!$script:workflowRequest) { return }
        $folder=Split-Path $script:workflowRequest; $status=Join-Path $folder 'status.json'
        if (Test-Path -LiteralPath $status) {
            try {
                $state=Get-Content $status -Raw | ConvertFrom-Json
                $text=$state.phase
                if ((Test-Path -LiteralPath (Join-Path $folder 'cancel')) -and $script:workflowProcess -and !$script:workflowProcess.HasExited) { $text='Cancellation requested; finishing current step. '+$text }
                if ($state.queue) {
                    $text+="`r`nConverted: $($state.queue.completed) | Reused: $($state.queue.skipped) | Remaining: $($state.queue.remaining) | Failed: $($state.queue.failed) | Blocked: $($state.queue.blocked)"
                    $script:workflowProgress.Maximum=[math]::Max(1,$state.queue.total)
                    $script:workflowProgress.Value=[math]::Min($script:workflowProgress.Maximum,$state.queue.total-$state.queue.remaining)
                }
                if ($state.missing_audio) { $text+="`r`nMissing music: $($state.missing_audio -join ', ')" }
                foreach ($issue in $state.issues) { $text+="`r`n$($issue.emote): $($issue.reason)" }
                if ($state.queues) {
                    foreach ($entry in $state.queues.PSObject.Properties) { $text+="`r`n$($entry.Name): converted $($entry.Value.completed), reused $($entry.Value.skipped), blocked $($entry.Value.blocked)" }
                }
                if ($state.complete) { $text+="`r`n$($state.pack.output)`r`nCopy Client contents into your MPQ, Server/dbc to the server, and Interface/AddOns outside the MPQ. Install the main addon once; routine packs update its catalog. See INSTALL.txt." }
                $script:workflowStatus.Text=$text
            } catch { }
        }
        if ($script:workflowProcess -and $script:workflowProcess.HasExited) {
            $script:workflowProcess.WaitForExit()
            if ($script:workflowProcess.ExitCode -ne 0) {
                $errorText=Get-Content (Join-Path $folder 'error.log') -Raw -ErrorAction SilentlyContinue
                if ($errorText) { $script:workflowStatus.AppendText("`r`n"+$errorText) }
            }
            $script:workflowProcess.Dispose(); $script:workflowProcess=$null
            $script:workflowRun.Enabled=$true; $script:workflowResume.Enabled=$true
        }
    })
    $script:workflowDialog.Add_FormClosed({ $script:workflowTimer.Stop(); $script:workflowTimer.Dispose() })
    $script:workflowDialog.Controls.AddRange(@($note,$script:workflowModel,$script:workflowAudio,$script:workflowSearch,$all,$clear,$script:workflowDances,$script:workflowRun,$script:workflowResume,$cancel,$open,$script:workflowStatus,$script:workflowProgress))
    $script:workflowDialog.Controls.Add($script:workflowCode)
    $script:workflowDialog.Controls.Add($script:workflowMontage)
    if ($script:workflowCombined) {
        $script:workflowDialog.Text='Build Combined Pack'; $script:workflowDialog.Height=950
        $note.Text='Select a model and dances, then Add / Update Model. Repeat for other models. Run builds every listed model against one shared DBC snapshot and addon catalog. Valid conversions are reused.'
        $add=New-Object Windows.Forms.Button; $add.Text='Add / Update Model'; $add.SetBounds(16,490,250,30)
        $remove=New-Object Windows.Forms.Button; $remove.Text='Remove selected model'; $remove.SetBounds(280,490,230,30)
        $script:workflowBasket=New-Object Windows.Forms.ListBox; $script:workflowBasket.DisplayMember='summary'; $script:workflowBasket.SetBounds(16,525,930,100)
        $script:fillWorkflowBasket={
            $script:workflowBasket.Items.Clear()
            foreach ($entry in $script:workflowTargets.Values) { $null=$script:workflowBasket.Items.Add([pscustomobject]@{target=$entry.target;summary=($entry.label+' - '+$entry.emotes.Count+' dances')}) }
        }
        $add.Add_Click({ & $guardUi 'Add model to combined pack' {
            if (!$script:workflowChecks.Count) { throw 'Select dances for this model first.' }
            $model=$script:workflowModel.SelectedItem
            $script:workflowTargets[$model.model.id]=[pscustomobject]@{target=$model.model.id;label=$model.label;emotes=@($script:workflowChecks.Keys | Sort-Object)}
            & $script:fillWorkflowBasket
        } })
        $remove.Add_Click({ if ($script:workflowBasket.SelectedItem) { $script:workflowTargets.Remove($script:workflowBasket.SelectedItem.target); & $script:fillWorkflowBasket } })
        $script:workflowBasket.Add_DoubleClick({
            if (!$script:workflowBasket.SelectedItem) { return }
            $entry=$script:workflowTargets[$script:workflowBasket.SelectedItem.target]
            for ($i=0;$i -lt $script:workflowModel.Items.Count;$i++) { if ($script:workflowModel.Items[$i].model.id -eq $entry.target) { $script:workflowModel.SelectedIndex=$i; break } }
            $script:workflowChecks=@{}; foreach ($id in $entry.emotes) { $script:workflowChecks[$id]=$true }; & $script:fillWorkflow
        })
        $script:workflowRun.Top=640; $script:workflowResume.Top=640; $cancel.Top=640; $open.Top=640
        $script:workflowStatus.Top=685; $script:workflowProgress.Top=830; $script:workflowCode.Top=855
        $script:workflowMontage.Top=882; $script:workflowDialog.Height=980
        $script:workflowDialog.Controls.AddRange(@($add,$remove,$script:workflowBasket))
        $savedPointer=Join-Path $studioRoot 'Output\Workflows\latest_combined.txt'
        if (Test-Path -LiteralPath $savedPointer) {
            $savedPath=[IO.File]::ReadAllText($savedPointer)
            if (Test-Path -LiteralPath $savedPath) {
                $savedRequest=Get-Content $savedPath -Raw | ConvertFrom-Json
                foreach ($entry in $savedRequest.targets) { $script:workflowTargets[$entry.target]=[pscustomobject]@{target=$entry.target;emotes=@($entry.emotes);label=$entry.target} }
                & $script:fillWorkflowBasket
                $script:workflowStatus.Text='Last combined model/dance selection loaded. Add or update models to expand it, or remove models explicitly. Run reuses valid conversions and builds one shared deployment pack.'
            }
        }
    }
    & $script:fillWorkflow
    $script:workflowTimer.Start(); $script:workflowDialog.Show($form)
} }
$workflowButton.Add_Click($openWorkflow)
$form.Controls.Add($workflowButton)
$combinedButton=New-Object Windows.Forms.Button; $combinedButton.Text='Build Combined Pack'; $combinedButton.Tag='combined'; $combinedButton.SetBounds(445,636,235,30)
$combinedButton.Add_Click($openWorkflow); $form.Controls.Add($combinedButton)
$mainAddonButton=New-Object Windows.Forms.Button; $mainAddonButton.Text='Open Main Addon'; $mainAddonButton.SetBounds(690,636,200,30)
$mainAddonButton.Add_Click({ & $guardUi 'Open main addon' {
    $folder=Join-Path $studioRoot 'Output\Addons\Main'; [IO.Directory]::CreateDirectory($folder) | Out-Null
    $latest=Join-Path $folder 'latest.json'
    if (Test-Path -LiteralPath $latest) { $main=Get-Content $latest -Raw | ConvertFrom-Json; $folder=Split-Path $main.folder }
    Start-Process explorer.exe -ArgumentList ('"'+$folder+'"')
} }); $form.Controls.Add($mainAddonButton)
