# Optional Fortnite favorites batch tools

These are advanced helpers for **Fortnite Porting 4.3.4**, tested against source
revision `8058810ece4405bfde931d97c72467b07034a881`. They are separate from Studio's
normal conversion queue, which uses your already exported UEFormat files.

No game assets, saved favorites, audit reports, application assemblies, .NET
runtime, or compiled helper executable are included. The current upstream
application may have different APIs; use the recorded revision when reproducing
this integration.

## C# exporter source

`Program.cs` initializes the user's installed Fortnite Porting services, loads
existing settings with saving disabled, audits favorite dance definitions and
their medium animation graphs, and optionally exports approved selections. Its
parser may download required data into Fortnite Porting's normal cache. Run it
only against your own configured application environment.

This source was built as a local harness using the application's existing
extracted libraries and a .NET 10 runtime. The original build project and matching
dependency bundle were temporary and are not part of this checkout. Consequently
this C# source is provided as an integration reference, **not a standalone
rebuildable exporter**. To use it, create a host project against the exact
application revision and its dependency graph, with this `Program` as the entry
point, following upstream build requirements. Do not expect `dotnet run` in this
directory to work. Normal Studio conversion does not require this harness.

Once built in that environment, its command arguments are:

```text
BatchHelper <report-directory> <maximum-favorites>
BatchHelper <report-directory> <maximum-favorites> --inspect-ids <comma-separated-ids>
BatchHelper <report-directory> <maximum-favorites> --export
```

Audit first, inspect the selection, then export. The default maximum without
arguments is 3. Export mode rechecks saved audit hashes, definitions, and graphs,
stages files, preserves differing existing files, and reports conflicts.

## Python helpers

From the repository root with Python 3.11+ and your own generated audit:

```powershell
python Tools/FortniteBatch/classify.py Reports/FortniteBatch
python Tools/FortniteBatch/verify.py Reports/FortniteBatch
python Tools/FortniteBatch/build_playback.py Reports/FortniteBatch/audit.json
```

`classify.py` regenerates the selection from `audit.json` and the referenced
definition files. Selection uses resolved male/female medium performances, music
evidence, prop/co-op exclusions, and known behavior checks. The optional Dance tag
is not a mandatory condition when both graphs provide verified music evidence.
Unknown behavior stays held for review. Classification is not visual approval.

`verify.py` checks manifest identity, file sizes/hashes, UEANIM headers and WAV
samples. `build_playback.py` creates normalized section playback plans from an
audit under `Reports`; it preserves the raw audit. Native intro/loop deployment
still has the separate DLL requirements in `docs/CLIENT_COMPATIBILITY.md`.

Other scripts retain the development report layout:

- `import_additional.py` reads `Reports/FortniteBatch/TagCorrection/exports.json`
  and publishes verified additions under `Output/FortniteImports`.
- `audit_catalog.py`, `audit_sections.py`, and `audit_playback.py` reconcile/audit
  the local catalog and the user's generated graphs/exports. Inspect their input
  paths before running; no old reports are bundled or downloaded.

Do not publish the generated game-definition JSON or exported media with the
source repository. Do not launch a second parser instance while changing exports
or application settings in the primary application.

## API references used during development

- [AssetInfo medium variants](https://github.com/h4lfheart/FortnitePorting/blob/8058810ece4405bfde931d97c72467b07034a881/src/FortnitePorting/Models/Assets/Asset/AssetInfo.cs)
- [ExportService](https://github.com/h4lfheart/FortnitePorting/blob/8058810ece4405bfde931d97c72467b07034a881/src/FortnitePorting/Services/ExportService.cs)
- [AnimExport](https://github.com/h4lfheart/FortnitePorting/blob/8058810ece4405bfde931d97c72467b07034a881/src/FortnitePorting.Exporting/Types/AnimExport.cs)
- [CUE4Parse montage parser](https://github.com/h4lfheart/CUE4Parse/blob/33a2bed814778283a6b976adf3eeed017e6b1494/CUE4Parse/UE4/Assets/Exports/Animation/AnimMontage.cs)
