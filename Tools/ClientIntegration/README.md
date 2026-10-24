# Dance client patch source

The working Studio folder contains a modified checkout of
[Ascension Extensions Reconstruction](https://github.com/firstoni-dev/ascension-extensions-reconstruction).
This directory publishes the dance-specific changes and tests against upstream
commit **03744a1a451efc08790ddc6750b145a2a5780bb8**. It does not contain a game
executable, DLL, or the rest of that separate upstream project.

## What is included

- `client-integration.patch`: CMake options, native animation-count integration,
  and diagnostic build label changes to existing upstream files.
- `overlay/src/Ascension/AscAnimationSafety.*`: bounded model lookup/fallback
  resolver and guarded native hook installation for the tested executable layout.
- `overlay/src/Ascension/AscDanceLoopClock.hpp` and `AscDanceLoops.cpp`:
  optional experimental intro-once/loop-region sampling and configuration reader.
- `overlay/tests/`: the original synthetic x86 safety, clock, and sampler harnesses.
- `build.cmd` and `test.cmd`: build/test commands using tools on the user's PATH.

These patches target the inspected Ascension/Wrath 12340 executable addresses.
They are not a universal stock WoW client patch. The upstream DLL reconstruction
also changes other client behavior; review its documentation before replacing a
client extension. Do not install this DLL into an unrelated client.

## Obtain and patch the upstream source

Use a separate checkout, not this Studio repository root:

```powershell
git clone https://github.com/firstoni-dev/ascension-extensions-reconstruction.git extensions-wds
git -C extensions-wds checkout 03744a1a451efc08790ddc6750b145a2a5780bb8
$integration = (Resolve-Path '.\Tools\ClientIntegration').Path
git -C extensions-wds apply --check "$integration\client-integration.patch"
git -C extensions-wds apply "$integration\client-integration.patch"
Copy-Item -Path "$integration\overlay\*" -Destination '.\extensions-wds' -Recurse -Force
```

Keep the upstream checkout's dependencies and notices. The overlay adds new files;
it does not replace the rest of upstream source. Never force a patch that fails
its compatibility check.

## Build and test

Install Visual Studio 2022 C++ tools with the x86 toolchain/Windows SDK, CMake
3.25+, and Ninja. Open the **x86 Native Tools Command Prompt** so `cl`, `cmake`,
and `ninja` are on PATH. From the Studio root:

```bat
Tools\ClientIntegration\test.cmd extensions-wds
Tools\ClientIntegration\build.cmd extensions-wds
```

The ordinary compatibility build produces
`extensions-wds\build-wds-animation-safety\Extensions.dll`.
For the optional experimental native section sampler:

```bat
Tools\ClientIntegration\build.cmd extensions-wds loops
```

That produces `extensions-wds\build-wds-dance-loops\Extensions.dll`.
Harness tests do not certify in-game playback. Independently test the actual
client, models, server, and packs before deploying.

## Use with Studio

With the client closed, back up its existing DLL and install only a build suited
to that executable. Configure `Profiles/Clients/active.json` with the validated
animation limit and exact DLL path/hash described in `docs/CLIENT_COMPATIBILITY.md`.
Building a DLL does not automatically configure Studio or verify gameplay.

For experimental intro/loop packs, put the built loop DLL at Studio's current
local artifact path:
`Output/Research/ascension-extensions-reconstruction/build-dance-loop-regions/Extensions.dll`.
Set `WDS_MONTAGE_PREVIEW=1` in the process launching Studio. Pack assembly requires
that local DLL and produces matching `ClientRoot/Extensions.dll` and
`WoWDanceStudio.loops`. Install both beside the tested executable, outside MPQs.
The source-only repository never includes that generated DLL or loop data.

The upstream project is MIT-licensed; its notice is retained in
`UPSTREAM-LICENSE.txt`. Original Studio patch additions are GPL-3.0-only under the
top-level license. This package does not relicense upstream or supply game assets.
