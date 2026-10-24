# Publishing this source package

This folder is the public repository root. Do not initialize/push Git from the
parent development folder containing working game assets and outputs.

## Package scope

Included: the application, GUI, worker scripts, batch/audit helper source, addon
source with empty `Data.lua`, server patch, synthetic tests, setup scripts,
license texts, and current user guides.

Excluded: original models/textures/animations/music, DBCs, the asset-containing
prepared `.blend`, generated profiles/registries, local settings, historical
reports/handoffs, cache/output libraries, test packs, client binaries/DLLs, and
one-off local deployment/repair scripts tied to private paths. The development
README mixed historical experimental states; this release has a new current guide.

The optional Fortnite C# favorites exporter source is retained, but its original
temporary build project/dependency bundle is unavailable; see its README. The
ordinary Studio batch conversion workflow is included. The experimental native
client DLL implementation is not included: do not advertise stock-client native
playback or turnkey intro/loop deployment.

## Before uploading

1. Read `THIRD_PARTY_NOTICES.md` and retain `LICENSE` (GPL-3.0-only for original
   Studio code) plus the patch's upstream GPLv2-or-later notice/license.
2. Run `Run Tests.cmd` and `python Tools/check_release.py`. The source audit checks
   publishable files for disallowed types, personal Windows paths, obvious secret
   formats, and broken local Markdown links. It is a useful check, not a complete
   security or copyright audit.
3. Try Setup and the documented registration/conversion flow using your own
   separately supplied assets in a clean checkout. Check real importer behavior
   and client/server deployment separately; synthetic tests cannot certify those.
4. Review what Git will publish. Keep local asset/profile/log folders ignored.
   Never force-add ignored inputs, packs, binaries, or `studio.local.json`.

## Create the GitHub repository

Create an empty public repository in your own GitHub account. Do not select an
additional auto-generated license/README if you will push this complete folder.
From this folder (replace the example remote with your actual URL):

```powershell
git init -b main
git add .
git status --short
git diff --cached --stat
python Tools/check_release.py
git commit -m "Initial source release"
git remote add origin https://github.com/Duff-SPP/WoW-Dance-Studio.git
git push -u origin main
```

No GitHub repository is created and nothing is pushed by the setup scripts.
Check that GitHub displays GPL-3.0 and that the README links resolve after upload.

## Source ZIP

Run `python Tools/make_source_zip.py` to create a sibling
`WoW-Dance-Studio-source.zip`. It includes audited source files only, even after
local conversions have created working assets/state. It refuses to overwrite an
existing archive; pass `--output <new-path.zip>` for a later version.

Do not use an unrestricted Compress-Archive of a development/working folder:
that can include ignored game assets. GitHub's source archives contain tracked
files, so review the tracked list before a release. Generated client/server packs
are a separate distribution and may contain third-party content outside the
software license.
