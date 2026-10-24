# Validation and supported environment

Checked on 24 October 2026 with Windows, Blender 5.2.2 LTS, its Python 3.13.13,
Elune M2 1.9.1, and the locally installed Fortnite Porting importer.

- All 65 synthetic regression tests passed without bundled game assets.
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

## Client and batch builds

The client integration package contains a patch/overlay against a pinned upstream
checkout. The batch helper includes a portable compiler recipe with external
dependencies supplied separately.

- The client patch applied cleanly to an exported copy of upstream commit
  `03744a1a451efc08790ddc6750b145a2a5780bb8`.
- All three x86 harnesses passed: 21 safety checks, 10,000 repeated native resolver
  calls, clock boundary checks, and 20,000 real sampler-hook calls with fallback cases.
- A clean full x86 DLL build with both animation safety and dance-loop regions
  enabled completed using the published build script and copied overlay. Existing
  upstream conversion warnings were emitted; the build linked `Extensions.dll`.
- The C# reference list/build script compiled the helper using SDK
  9.0.305's Roslyn compiler and .NET 10.0.13 runtime assemblies plus separately
  supplied Fortnite Porting libraries. Compiler warning CS1701 reports an existing
  dependency's System.ObjectModel 8/10 identity assumption. No parser/export run
  or data download was performed by that build check.

The fresh-registration check did not approve the profile, run a complete new
conversion, build a native pack, or validate gameplay. Build/harness success does
not establish compatibility with another executable layout, missing model
companions, changed importer versions, or the actual client/server runtime.

## Full-catalog BAT downloader

The menu workflow was checked against the configured Fortnite Porting 4.3.4
provider on 24 October 2026:

- Full registry scan: 2,222 `AthenaDanceItemDefinition` objects attempted; the
  completion marker recorded the full count and actual metadata tags were listed.
- A name filter selected Dance Monkey from that catalog, without a favorites
  requirement. Its audited medium pair passed the default music policy.
- Export, independent verification, and managed Studio import completed: two
  animations, one matching source skeleton, and one soundtrack; zero verification
  errors. A fresh Studio catalog scan indexed both variants with no missing source
  dependencies. Those game assets/reports are local ignored outputs, not source.
- The console menu's configure/build/exit flow and no-parser smoke test passed.
  C# option/tag self-tests and all 65 Python regression tests passed, covering filtering,
  variable audit counts, partial-catalog rejection, policy gates, and preserved
  existing assets during import.

This is one actual export/import example. It does not establish that every tag,
emote, game version, model conversion, or native gameplay combination is supported.
