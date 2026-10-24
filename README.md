# WoW Dance Studio

Windows desktop tooling for retargeting exported Fortnite body animations onto
Wrath-era WoW character models, reviewing bone profiles, and building matching
client/server dance packs and an in-game collection addon.

**Source-only release.** Supply your own game assets, DBC baselines, Blender scene,
and third-party importers. No models, textures, animations, music, DBCs, client
executables, or compatibility DLLs are included.

## Start here

1. Follow [Setup](docs/SETUP.md), including preparation of your own source scene.
2. Run `Setup.cmd` (or `Setup.ps1` with your Blender and scene paths).
3. Open `Launch Studio.cmd`.
4. Follow the [Usage guide](docs/USAGE.md) to register a model, review its profile,
   convert a dance, and build a pack.

The development environment used **Windows, Blender 5.2, Elune M2 1.9.1, and
Fortnite Porting 4.3.4**. The Python code needs Python 3.11+; normal GUI operation
uses Blender's bundled Python. No mandatory pip install is needed. NumPy is an
optional audio acceleration path.

## Features and boundaries

- Register Wrath MD20 version 264 models with matching SKIN/ANIM companions.
- Infer, correct, validate, and explicitly approve per-model bone profiles.
- Catalog exported UEFormat animations and audio; choose matching performances.
- Queue conversion with pause/resume, validated cache reuse, and Blender preview.
- Build matching DBC, M2/ANIM, soundtrack, and addon catalogs; combine selected models.
- Keep supplied source assets separate from generated `Output/` and `Reports/`.

Body animation is the supported scope. Props, cooperative emotes, unsupported
additive animation, and ambiguous anatomy can require review or be rejected.
Technical validation does not replace visual review or in-game testing.

**Native playback requires a compatible client and server.** The release does
not include a compiled extended-animation client DLL. The dance-specific
[client patch source and build/test instructions](Tools/ClientIntegration/README.md)
are included against a pinned external upstream checkout. Standard clients
must not be assumed to handle new IDs. Read [Client compatibility](docs/CLIENT_COMPATIBILITY.md)
before exporting. Fortnite intro/loop composition can additionally require an
experimental native sampler DLL built from those optional sources. Keep that
option off unless you build and validate its requirements.

For the tested CoA/AzerothCore integration, custom persistent dances also require
the [server source patch](Tools/ServerIntegration/README.md). This is not a
universal patch for every core or client version.

## Repository contents

| Path | Purpose |
| --- | --- |
| `studio.py`, `studio_core/` | CLI, conversion, validation, packing, and storage |
| `Studio*.ps1`, `Launch Studio.cmd` | Windows GUI and workflows |
| `blender_worker.py`, `m2_worker.py`, `hd_batch_worker.py` | Blender workers |
| `run_hd_batch.py`, `Tools/` | Advanced batch, audit, and diagnostic helpers |
| `Addon/WoWDanceStudio/` | Reusable addon source with an empty dance catalog |
| `Input/`, `Blender/`, `Profiles/` | User-supplied inputs and local generated profiles |
| `Output/`, `Reports/` | Local generated results; excluded from Git |

## Development and publishing

Run `Run Tests.cmd` for the asset-free regression suite. See
[Contributing](CONTRIBUTING.md) for CLI commands and test limitations, and
[Publishing](docs/PUBLISHING.md) for the public-package audit and upload steps.
The [DBC guide](docs/DBC.md) lists baseline tables and exported locations.
The optional Fortnite batch helper has its own [instructions](Tools/FortniteBatch/README.md).

Original Studio code is licensed under **GPL-3.0-only**. See [LICENSE](LICENSE)
and [third-party notices](THIRD_PARTY_NOTICES.md). The server integration patch
retains its upstream GPLv2-or-later context. The software license does not grant
rights to Blizzard, Epic, or other third-party assets. This is an independent
project, not affiliated with or endorsed by Blizzard Entertainment or Epic Games.
