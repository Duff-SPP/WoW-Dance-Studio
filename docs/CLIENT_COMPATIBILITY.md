# Native client compatibility

Blender conversion and native WoW playback have separate requirements. This
repository does not include an extended-animation client executable, DLL, or a
rebuildable source implementation of the locally tested client modification.

The original tested client used a fixed native animation resolver limit of 506
(exclusive); extended IDs caused a crash/freeze. This is evidence about that
tested client, not a universal contract for every build-12340 executable. A server
change or addon cannot increase a native client array's capacity.

Setup copies `Profiles/Clients/conservative.example.json` to the gitignored
`Profiles/Clients/active.json` only if no active profile exists. It conservatively
blocks IDs >= 506. Lower IDs are not automatically verified, and the existing DBC
namespace is not overwritten to squeeze new dances below the limit. Therefore a
baseline with no safe append-only slots may be unable to build native packs.
An absent active profile also blocks native export in this release.

To support another client, inspect and independently validate that client's
resolver and required runtime changes. Record its real limit and identity in a
local compatibility profile. Where applicable, the existing guard supports:

- `schema: 1`, `client`, and `animation_id_limit_exclusive`;
- `installed_client_dll: {"path": "...", "sha256": "..."}` for an installed binary;
- `required_client_dll: {"path": "...", "sha256": "..."}` for a required binary
  stored inside this checkout's `Output/` directory.

Do not remove the profile, invent a higher bound, or remove DLL identity checks
as a substitute for fixing and testing a native resolver. Profile JSON does not
patch the client. Keep binary paths/hashes local and do not publish third-party
client binaries with the source repository.

The optional Fortnite section-based native intro/loop pack path also expects a
locally built experimental sampler DLL at the path defined in
`studio_core/loop_regions.py` and its explicit environment gate. That build is not
part of this release. Keep this pack option disabled unless you provide and
validate that separate implementation. General conversion, ordinary full clips,
and Blender preview do not require that DLL.

For server persistence, see `Tools/ServerIntegration/README.md`. Test each actual
model/dance/client/server combination before deployment. Prior local successful
playback is not certification of this source-only package on another installation.
