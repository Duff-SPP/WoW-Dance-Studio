# Source validation

From the repository root, run `Tools\Development\Check.cmd` after configuring
Blender with Setup. The command runs the synthetic regression suite in `tests/`
and the publishable-source audit. It does not download game files or deploy packs.

With a standalone Python 3.11+ installation:

```powershell
New-Item -ItemType Directory -Force Reports, Output, Output/FortniteImports | Out-Null
python -m unittest discover -s tests -t . -p 'test_*.py'
python Tools/check_release.py
```

The suite covers storage integrity, binary export, audio, queue behavior, profile
authorization, client guards, and downloader selection/import. See
`../../CONTRIBUTING.md` and `../../docs/VALIDATION.md` for integration checks and
their limits. Client x86 harnesses remain with their source integration package.
