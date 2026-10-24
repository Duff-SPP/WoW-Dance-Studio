# Contributing

Use Windows and the tested Blender/importer versions in `docs/SETUP.md` for
conversion work. Keep third-party assets out of commits and pull requests.
Submit synthetic fixtures or reproduction instructions that use the reporter's
own local files. Redact absolute paths, account details, and client identifiers
from reports.

## Tests

Run `Tools/Development/Check.cmd` after Setup, or use Python 3.11+ from the repository root:

```powershell
New-Item -ItemType Directory -Force Reports, Output, Output/FortniteImports | Out-Null
python -m unittest discover -s tests -t . -p 'test_*.py'
python -m compileall -q studio_core Tools studio.py blender_worker.py m2_worker.py hd_batch_worker.py run_hd_batch.py
python Tools/check_release.py
```

The public suite uses synthetic data. Local development tests requiring supplied
models, exported Fortnite graphs, pre-existing conversion libraries, DBCs, or
private client reports are intentionally omitted. Passing this suite does not
verify Blender conversion, the optional C# helper, server deployment, or gameplay.
For those changes, also test the real importers and your own matching assets.

Useful CLI inspection commands (run from the checkout root):

```powershell
python studio.py --help
python studio.py models-scan --wow '.\Input\WoW'
python studio.py catalog --emotes '.\Input\Fortnite'
python studio.py models-list
python studio.py queue-status
```

Worker scripts that import `bpy` run inside Blender, not ordinary Python.
The PowerShell GUI is the primary supported interface; the retained Tkinter
fallback is older and is not the full Windows workflow.

Preserve original assets and immutable output/profile identities. Do not silently
auto-approve visual quality, bypass compatibility guards, replace native DBC IDs,
or accept changed skeletons as matching. Add a meaningful synthetic regression
test for changes to conversion planning, caching, binary writing, or safety guards.

Contributions to original Studio code are under GPL-3.0-only. Retain third-party
notices and the server patch's separate upstream license context.
