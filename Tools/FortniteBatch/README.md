# Fortnite catalog and favorites batch tools

For the interactive full-catalog workflow, open `Download Fortnite Emotes.bat`
in the repository root and follow [the menu guide](../../docs/DOWNLOADER.md).
The menu supports actual tag filters, name/ID search, candidate limits, audit
review, verified export including source skeletons, and managed Studio import.

These are advanced helpers for **Fortnite Porting 4.3.4**, tested against source
revision `8058810ece4405bfde931d97c72467b07034a881`. They are separate from Studio's
normal conversion queue, which uses your already exported UEFormat files.

No game assets, saved favorites, audit reports, application assemblies, .NET
runtime, or compiled helper executable are included. The current upstream
application may have different APIs; use the recorded revision when reproducing
this integration.

## C# exporter source

`Program.cs` initializes the user's installed Fortnite Porting services, loads
existing settings with saving disabled, audits selected emote definitions and
their medium animation graphs, and optionally exports approved selections. Its
parser may download required data into Fortnite Porting's normal cache. Run it
only against your own configured application environment.

`Build.ps1` and `build-references.json` reproduce the recorded Roslyn compilation
recipe with user-supplied directories. The list contains reference filenames, not
the original machine's paths. Supply the exact application's extracted library
folder, a .NET 10.0.x shared runtime directory, and an installed .NET SDK containing
Roslyn. The recovery build was checked with SDK 9.0.305's compiler and runtime
10.0.13 reference assemblies; runtime execution requires the matching .NET 10 host.

```powershell
.\Tools\FortniteBatch\Build.ps1 -RuntimeDirectory 'C:\dotnet\shared\Microsoft.NETCore.App\10.0.13' -LibrariesDirectory 'C:\your-tools\FortnitePorting-libraries'
```

The build writes the helper, runtime configuration, and copied external DLL
dependencies under gitignored `Output/FortniteBatchBuild`. It does not start the
parser, download game data, or publish dependencies. Run the built `Batch.dll`
with a matching .NET 10 host. There is no SDK-style project for `dotnet run` in
this folder; the documented build script is the build entry point. Normal Studio
conversion does not require this helper.

Once built in that environment, its command arguments are:

```text
BatchHelper <report-directory> <maximum-favorites>
BatchHelper <report-directory> <maximum-favorites> --inspect-ids <comma-separated-ids>
BatchHelper <report-directory> <maximum-favorites> --export
BatchHelper <report-directory> <maximum> --source catalog --catalog-only
BatchHelper <report-directory> <maximum> --source catalog --ids-file ids.json
BatchHelper <report-directory> <maximum> --source catalog --export --destination <asset-folder>
```

Legacy commands default to favorites. `--source catalog` enumerates all actual
`AthenaDanceItemDefinition` registry objects using upstream's class filter.
`--catalog-only` scans lightweight metadata/tags; `--ids-file` restricts the full
animation audit to selected identifiers. `--help` and `--self-test` do not start
the parser. `--destination` overrides the usual application export directory.

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

`classify.py` accepts the actual nonzero audit count, not a fixed favorites count.
It regenerates the selection from `audit.json` and the referenced
definition files. Selection uses resolved male/female medium performances, music
evidence, prop/co-op exclusions, and known behavior checks. The optional Dance tag
is not a mandatory condition when both graphs provide verified music evidence.
Unknown behavior stays held for review. `--allow-non-musical` explicitly permits
standalone non-musical body emotes while preserving the other checks.
Classification is not visual approval.

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
