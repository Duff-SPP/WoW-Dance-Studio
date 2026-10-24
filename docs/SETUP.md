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
  PreparedSource.blend     # create this yourself below
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

## 2. Create the prepared source scene

The original development `.blend` is intentionally absent because it contains
game assets. A blank Blender scene is not sufficient for model registration.

1. Open the Blender installation you will use with Studio and enable the importers.
2. Start a new scene and import your exported Fortnite reference `.uemodel` using
   its UEFormat importer. Keep bone reorientation disabled and socket import
   enabled, matching Studio's `UEModelOptions(reorient_bones=False, import_sockets=True)`.
3. Identify the imported source armature. The GUI registration path expects the
   object name `Fortnite_M_Avg_Player_Skeleton`. Set that exact object name if
   needed; do not rename bones, change rest matrices, or apply transforms to
   manufacture compatibility. CLI users may instead pass `--source-rig` with the
   actual source object name.
4. Save as `Blender/PreparedSource.blend`. It must retain the imported armature
   and its original rest pose. A WoW target is not needed in this source scene:
   normal Register Folder imports each supplied target and saves its own scene.
5. Select this scene in Studio before Register Folder. Select the registered target
   afterward; Studio switches to that target's generated scene/profile.

The first conversion checks actual source bones, parent links, and rest matrices.
If they differ from the reference, use the matching source export/scene and
regenerate the target profile. Do not bypass these checks.

Avoid placing your first model at `Input/WoW/Human_Male/humanmale2.m2` when using
older copies of Studio: that development path had a special baseline behavior.
The source-only release routes all GUI/CLI registrations through normal import.

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
checks Python, optionally checks real importer modules in background Blender, and
saves `studio.local.json`. It never downloads game data or modifies a client/server.
It installs the conservative client compatibility template only if no active
local profile exists. Setup does not certify source-scene contents or native playback.

GUI and CLI defaults read `studio.local.json`; the GUI also lets you browse to
different files. `WDS_BLENDER` overrides the configured Blender path. The Python
runtime is resolved from the selected Blender installation rather than a fixed
version subfolder. A normal standalone Python 3.11+ can run the CLI and unit tests;
Blender-only work still runs through Blender.

## 4. Launch

Double-click `Launch Studio.cmd`, then follow [Usage](USAGE.md).
Local settings, supplied assets, generated profiles, logs, and outputs are ignored
by Git. Keep them out of source archives as well.
