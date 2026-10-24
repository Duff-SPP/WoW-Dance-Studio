# Setup on Windows

## Requirements

- Windows with Windows PowerShell 5.1 (included with supported Windows installations).
- A complete Blender installation. Development used Blender 5.2; other versions
  need validation, especially their action-slot and importer APIs.
- Elune M2 **1.9.1**, installed and enabled in that Blender user's preferences.
- The Fortnite Porting **4.3.4** Blender addon/UEFormat importer, installed and
  enabled in the same Blender environment.
- Your own compatible WoW models and exported Fortnite animation/skeleton files.
- For optional section/montage processing, `zstandard` in the Python environment
  running Studio's controller. See the dependency commands below.
- For native packs: matching build-12340 WDBC baselines, a validated compatible
  client, and a server core with the necessary dance behavior.

Install external tools from their authors:

- [Blender](https://www.blender.org/download/)
- [Elune M2 installation](https://elune-m2.github.io/documentation.html)
- [Fortnite Porting source and releases](https://github.com/h4lfheart/FortnitePorting)

Studio imports `bl_ext.user_default.elune_m2.m2_import.factory` and `.builder`,
and `fortnite_porting.ueformat`. Installing Elune into a differently named Blender
extension repository will not satisfy that module path. Use the default user
repository or adapt and validate the adapter. New importer versions are not
automatically compatible. Save Blender preferences after enabling the addons.

## 1. Supply local inputs

Keep the original names and directory layout of exported companions:

```text
Input/
  WoW/
    MyCharacter/
      mycharacter.m2
      mycharacter00.skin
      ... original matching .anim / texture files as needed
  Fortnite/
    ... exported .ueanim, source .uemodel skeleton, and .wav files
  DBC/
    ... matching original .dbc files
Blender/
  PreparedSource.blend     # created automatically from your skeleton
```

Models must be flat Wrath MD20 version 264 with usable geometry and a matching
SKIN. The catalog needs the actual exported source skeleton, not just an animation
file. Preserve Fortnite Porting's filenames and folder structure so variant,
skeleton, and audio resolution can work. Do not rename male/female variants into
one another. Not every export or game version is supported.

For DBC packs, supply the tables required by `studio_core/dbc_schema.py`, including
`AnimationData`, `Emotes`, `SoundEntries`, `EmotesText`, `EmotesTextData`,
`EmotesTextSound`, and `DanceMoves`. The DBC scan reports missing/invalid tables.
Use one consistent baseline matching your actual client and server; no DBCs are
downloaded or generated as substitutes for original baselines.
See [DBC baselines and exports](DBC.md) for the full table list and requirements.

For optional section/montage processing, use the selected Blender installation's
bundled Python (or the standalone Python running your CLI controller):

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe' -m pip install -r requirements-montage.txt
```

The standard full-clip workflow does not require `zstandard`. Installing the
package alone does not provide saved montage graphs or the native sampler build.

## 2. Automatic source preparation

Studio creates `Blender/PreparedSource.blend` from your exported skeleton automatically.
No manual Blender scene setup is required. Enable the importers and save Blender
preferences first. Setup prepares the scene if exports are already available;
otherwise **Register Folder** prepares it when you register your first model.
The downloader's imported exports are searched alongside `Input/Fortnite`.

The importer keeps bone reorientation disabled and socket import enabled. Studio
names the source object `Fortnite_M_Avg_Player_Skeleton`, preserves the imported
bones and rest pose, and saves a local reference scene. Existing scenes are reused
unchanged. Each registered WoW target still receives its own generated scene.

If several different skeletons exist, use **Prepare Source** in the main window
and select the matching `.uemodel`. The Scene field must point to a new filename
inside `Blender` or `Output` when creating a reference. To replace a reference,
choose a new filename rather than overwriting the old scene. Advanced CLI usage:

```powershell
python studio.py prepare-source --source-skeleton 'C:\exports\Fortnite_M_Avg_Player_Skeleton.uemodel'
```

Conversion still checks source bones, parent links, and rest matrices against the
reference. If they differ, prepare a matching reference and register/regenerate
the target profile. Do not bypass these checks. Game assets remain local.

## 3. Configure and check

From PowerShell in the repository folder:

```powershell
.\Setup.ps1 -Blender 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' -Scene '.\Blender\PreparedSource.blend' -CheckImporters
```

If script execution is restricted, use:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Setup.ps1 -Blender 'C:\path\to\blender.exe' -Scene '.\Blender\PreparedSource.blend' -CheckImporters
```

`Setup.cmd` also accepts those parameters. Setup creates local working directories,
checks Python, optionally checks real importer modules in background Blender, prepares
the source reference when exports are available, and
saves `studio.local.json`. It never downloads game data or modifies a client/server.
It installs the conservative client compatibility template only if no active
local profile exists. Setup does not certify native playback.

GUI and CLI defaults read `studio.local.json`; the GUI also lets you browse to
different files. `WDS_BLENDER` overrides the configured Blender path. The Python
runtime is resolved from the selected Blender installation rather than a fixed
version subfolder. A normal standalone Python 3.11+ can run the CLI and unit tests;
Blender-only work still runs through Blender.

## 4. Launch

Double-click `Launch Studio.cmd`, then follow [Usage](USAGE.md).
Local settings, supplied assets, generated profiles, logs, and outputs are ignored
by Git. Keep them out of source archives as well.
