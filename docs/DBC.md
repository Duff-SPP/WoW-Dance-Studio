# DBC baselines and exported files

Supply your own original `.dbc` baselines under `Input/DBC`. Studio supports the
explicit **Wrath build-12340 WDBC** layouts in `studio_core/dbc_schema.py`, not
retail DB2 files. Use a consistent set matching your actual client and server.
The source repository does not distribute or download game DBCs.

| Table | Role |
| --- | --- |
| `AnimationData.dbc` | Primary; animation definitions and fallback links |
| `Emotes.dbc` | Primary; emote-to-animation records |
| `SoundEntries.dbc` | Primary; sound definitions/templates |
| `EmotesText.dbc` | Required with EmotesTextData when creating text-emote commands |
| `EmotesTextData.dbc` | Required with EmotesText when creating text-emote commands |
| `EmotesTextSound.dbc` | Needed for explicit text-emote race/sex sound mapping |
| `ChrRaces.dbc` | Needed for explicit race-based text-emote sound mapping; race/model references |
| `SoundEntriesAdvanced.dbc` | Optional schema; referenced advanced sound metadata may require it |
| `CreatureDisplayInfo.dbc` | Optional schema; referenced race/model metadata may require it |
| `CreatureModelData.dbc` | Optional schema; referenced display/model metadata may require it |
| `DanceMoves.dbc` | Optional supported dance-move metadata table |

The three primary tables are always required by the export plan. Optional tables
can become necessary when selected options or preserved references need them.
Supplying all eleven matching originals is the least ambiguous baseline setup.
The DBC manager reports missing/unsupported tables, malformed records, duplicate
IDs, and reference problems. It does not invent missing original baselines.

## Export workflow

1. Scan the supplied DBC folder in Studio's DBC manager.
2. Select technically eligible converted dances and the desired text/audio options.
   The collection addon needs text-emote tokens to play dances through `DoEmote`.
3. Preview and validate the proposed linked records, then export/build the pack.
   Existing IDs are preserved; new records use append-only allocations recorded
   in the local registry. Do not edit allocation manifests or merge unrelated packs.
4. Install the matching generated files from one completed pack.

The exporter writes real binary `.dbc` tables. Pack assembly places the exported
DBC set under `Client/DBFilesClient/`. Its current server allowlist copies
`Emotes.dbc`, `EmotesText.dbc`, and `SoundEntries.dbc` to `Server/dbc/` when supplied.
Do not assume every client table also belongs on the server. Review the generated
`INSTALL.txt` and your server's loaders for any version-specific requirements.

Original baseline files stay separate from the exported snapshots. Building a
pack does not install an MPQ or modify a live client/server. Back up your deployed
files and install the client/server/addon output from the same pack together.

Correct DBCs do not fix native client animation limits or persistent server
emote behavior. See [Client compatibility](CLIENT_COMPATIBILITY.md), the
[client patch package](../Tools/ClientIntegration/README.md), and the
[server patch](../Tools/ServerIntegration/README.md).
