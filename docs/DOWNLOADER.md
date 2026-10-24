# Fortnite emote downloader menu

Double-click **Download Fortnite Emotes.bat** in the Studio root. This opens a
PowerShell menu backed by the C# batch helper and Python verification tools.
It searches the **full available emote catalog**, without needing favorites.
Availability means the `AthenaDanceItemDefinition` registry in the game version
your configured Fortnite Porting parser can currently load, including hidden
definitions. Unresolved metadata and unsupported body behavior are reported.

## One-time setup

Install/configure Fortnite Porting **4.3.4** normally first so its parser can load
your chosen game source. Close the application before using this separate parser
helper. The helper uses that existing configuration and cache; it does not change
favorites or save application settings.

The source release also needs:

- the matching extracted Fortnite Porting library folder containing
  `FortnitePorting.dll` and the reference DLLs listed in
  `Tools/FortniteBatch/build-references.json`;
- a .NET SDK containing the Roslyn compiler, plus a .NET **10.0.x runtime**;
- Python **3.11+** (Studio can use Blender's bundled Python).

For a single-file Fortnite Porting installation, run that app once. .NET normally
extracts its libraries under the current user's temporary `.net/FortnitePorting`
directory; select the subfolder containing the DLLs. A matching built upstream
application folder can also supply them. The menu does not download or package
someone else's application assemblies.

Choose **1 Configure paths and build helper**. Supply the .NET 10 host, library
folder, and Python path. If a standard installed `dotnet.exe` has .NET 10, accept
its default. A portable runtime needs its own `dotnet.exe` path. The menu discovers
its shared runtime directory, builds the helper, and runs a no-download self-test.
The compiler is found through the SDK's normal `dotnet` command on PATH.

Configuration and built DLLs are local under `Output/`, ignored by Git. Source
changes invalidate the helper fingerprint so the menu asks for a rebuild.

## Download workflow

1. **Scan/refresh full emote catalog and real tags.** This can download game
   metadata to Fortnite Porting's normal cache. Let it finish; an interrupted or
   capped catalog is marked incomplete and cannot be used for selection.
2. **Filter, select, and audit emotes.** Choose the actual Dance tag, choose another
   tag discovered in the catalog, or search all emote definitions. Add an optional
   name/ID search and a maximum count (25 by default; 0 means every match).
3. Choose the policy: **Dance/music only** preserves the original musical-dance
   checks; **Standalone body emotes** also permits a non-musical body performance.
   Both policies require separate medium male/female references and still exclude
   props/co-op behavior and hold unknown effects, missing variants, and unresolved
   animation evidence for review. A tag alone is not export approval.
4. **Review current selection.** Inspect ready, review, and excluded counts and
   reasons. Full candidate/selection CSVs are saved in the run's report folder.
5. **Download/export ready selection and verify files.** The menu confirms the
   number of ready entries. The helper rechecks current registry membership,
   definition hashes, and animation evidence, exports only the selected medium
   performances plus matching source skeletons and available audio, and verifies
   container identities, file sizes/hashes, and WAV sample data. Differing existing
   files are preserved and reported as conflicts. A failed run is not auto-imported.
6. **Import verified downloads into Studio.** Verification runs again, then files
   are copied into managed `Output/FortniteImports/Assets` with the export manifest
   the Studio catalog understands. Open Studio and **Scan Emotes** afterward.
   Supplied `Input/Fortnite` files stay separate.

The Dance tag is incomplete: some musical emotes have no Dance tag. To include
those, choose all definitions or another discovered tag and keep the dance/music
policy; the classifier can recognize audited music references in both graphs.

## Local files and limitations

| Path | Contents |
| --- | --- |
| `Reports/FortniteBatch/Catalog` | Latest full catalog, completion state, actual tags |
| `Reports/FortniteBatch/Runs/<run>` | Selected IDs, audit definitions/graphs, CSVs, exports and verification |
| `Output/FortniteBatchDownloads/Assets` | Verified exporter destination before Studio import |
| `Output/FortniteImports/Assets` | Managed Studio imports |
| `Output/FortniteBatchMenu/settings.json` | Local paths and current run |

Do not publish those folders: they contain game metadata/media and local paths.
The source ZIP and Git ignore rules exclude them.

This is an export/downloader wrapper for the recorded Fortnite Porting version,
not a replacement for its provider, authentication, or game-source setup. A changed
upstream API or unavailable game data may require updating that integration.
Metadata classification and file verification do not replace visual review in
Blender or native client/server testing. Native pack deployment still needs the
documented compatible client and server patches.

API discovery follows the pinned upstream
[emote loader's registry/class filter](https://github.com/h4lfheart/FortnitePorting/blob/8058810ece4405bfde931d97c72467b07034a881/src/FortnitePorting/Services/AssetLoaderService.cs)
and [object-path loading contract](https://github.com/h4lfheart/FortnitePorting/blob/8058810ece4405bfde931d97c72467b07034a881/src/FortnitePorting/Models/Assets/Loading/AssetLoader.cs).
