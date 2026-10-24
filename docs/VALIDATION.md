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

The fresh-registration check did not approve the profile, run a complete new
conversion, build a native pack, or validate gameplay. No claim is made that
missing model companions, another importer version, an unmodified client, the
optional C# export harness, or experimental native intro/loop deployment works
without the separately documented requirements.
