# Release preparation checks

Checked on 24 October 2026 with Windows, Blender 5.2.2 LTS, its Python 3.13.13,
Elune M2 1.9.1, and the locally installed Fortnite Porting importer.

- 58 synthetic regression tests passed without bundled game assets.
- Python source compilation and PowerShell syntax parsing passed.
- Setup completed and found all required importer modules/API entry points in
  a real background Blender process.
- The GUI opened and exited its smoke test with an empty initial catalog.
- A fresh reference scene was created from a separately supplied source skeleton.
  The public CLI registered a separately supplied MD20 character, saved its
  target scene, and generated a 23-mapping profile marked **Review Needed**.
  Registration correctly reported incomplete original animation companions.
  That test scene, model registration, and generated profile are excluded from
  the published source.
- The public-source audit checks file types, obvious secrets, personal Windows
  paths, and local documentation links. Generated working files are excluded
  from the archive and upload.

## Recovered client and batch build sources

A subsequent full working-folder audit found the local client modifications
under `Output/Research` and a C# compiler recipe under `Output/Tools`. The source
release now contains a portable patch/overlay and build instructions for these.

- The client patch applied cleanly to an exported copy of upstream commit
  `03744a1a451efc08790ddc6750b145a2a5780bb8`.
- All three x86 harnesses passed: 21 safety checks, 10,000 repeated native resolver
  calls, clock boundary checks, and 20,000 real sampler-hook calls with fallback cases.
- A clean full x86 DLL build with both animation safety and dance-loop regions
  enabled completed using the published build script and copied overlay. Existing
  upstream conversion warnings were emitted; the build linked `Extensions.dll`.
- The recovered C# reference list/build script compiled `Program.cs` using SDK
  9.0.305's Roslyn compiler and .NET 10.0.13 runtime assemblies plus separately
  supplied Fortnite Porting libraries. Compiler warning CS1701 reports an existing
  dependency's System.ObjectModel 8/10 identity assumption. No parser/export run
  or data download was performed by that build check.

The fresh-registration check did not approve the profile, run a complete new
conversion, build a native pack, or validate gameplay. Build/harness success does
not establish compatibility with another executable layout, missing model
companions, changed importer versions, or the actual client/server runtime.
