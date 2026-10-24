# License scope and third-party notices

Original WoW Dance Studio code is distributed under GPL-3.0-only. Copyright
2026 WoW Dance Studio contributors. The full license is in `LICENSE`.

## AzerothCore server patch

`Tools/ServerIntegration/persistent-dance-state.patch` contains modifications and
context from AzerothCore's `src/server/game/Handlers/ChatHandler.cpp`, tested in
a CoA/Manastorm integration checkout. That source header states:

> This file is part of the AzerothCore Project. See AUTHORS file for Copyright information

Its header permits GPL version 2 or any later version. Preserve that attribution
and GPL-2.0-or-later context when distributing/applying this patch. A copy of
GPLv2 is in `LICENSES/GPL-2.0-or-later.txt`. The top-level GPL-3.0-only choice for
original Studio code does not remove upstream rights in the patch context.

Upstream: [AzerothCore](https://github.com/azerothcore/azerothcore-wotlk).
The patch does not include the complete server and must be reviewed against
the chosen core before application.

## External dependencies (installed separately)

The dance-specific client integration patch targets the public MIT-licensed
[Ascension Extensions Reconstruction](https://github.com/firstoni-dev/ascension-extensions-reconstruction)
at commit `03744a1a451efc08790ddc6750b145a2a5780bb8`. Its upstream notice is
preserved in `Tools/ClientIntegration/UPSTREAM-LICENSE.txt`. The patch package
does not vendor that whole project, compiled client binaries, or game assets.

- [Blender](https://www.blender.org/about/license/): Blender's own license applies;
  this repository does not distribute Blender or its bundled Python/libraries.
- [Elune M2](https://elune-m2.github.io/): development used version 1.9.1; its
  installed manifest declares GPL-3.0-or-later. Its source is not bundled here.
- [Fortnite Porting](https://github.com/h4lfheart/FortnitePorting): development
  used 4.3.4 at revision `8058810ece4405bfde931d97c72467b07034a881`.
  Its code, libraries, Blender addon, and runtime are installed separately and
  retain their own licenses. The optional batch helper references its APIs.
- CUE4Parse, Newtonsoft.Json, .NET, Python, and optional NumPy remain separately
  licensed dependencies. No matching binary distribution is bundled here.

`studio_core/dbc_schema.py` records layout references to WDBX commit `d34cee1`
and TrinityCore 3.3.5. It contains layout definitions, not original game DBC data.
`Tools/FortniteBatch/README.md` records the source revisions used for its adapters.

## Assets, names, and rights

World of Warcraft and Fortnite names and assets belong to their respective
owners. No game models, textures, animations, soundtracks, DBCs, client binaries,
or modified client DLLs are included or licensed by this repository. Users must
supply inputs they are entitled to use and handle any separate permissions for
their use or redistribution. Generated packs can contain those third-party
assets; the code's GPL license does not grant rights to that content.
