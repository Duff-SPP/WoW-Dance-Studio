# Using Studio

## Register and review a target

1. Set the WoW models folder, Fortnite emotes folder, Blender executable, and
   prepared source scene as described in [Setup](SETUP.md).
2. Click **Scan Emotes** to build the local catalog. Inspect missing skeleton,
   variant, and audio diagnostics before conversion.
3. Open **Models** and choose **Register Folder**. Pick the folder containing your
   model and matching companions. Wait for registration to finish.
4. Select the newly registered target in the main window. Studio selects its
   generated target scene. In Models choose **Generate**, inspect the bone mapping,
   correct ambiguous Target cells, **Save Corrections**, and **Validate**.
5. Use **Open Target Scene** for visual inspection. Only **Approve** a profile after
   checking it. Profile approval and a converted animation's visual approval are
   separate records.

Registrations and target scenes are under `Output/Models`. Generated profile
revisions are under `Profiles`. Keep these local: they record your asset identities
and paths. Do not substitute another person's pre-approved profile.

## Convert and preview

Select a target and dances, then use **Convert Selected**, **Convert Missing**, or
**Convert All**. Each target resolves matching male/female performance variants;
unsupported or unresolved sources remain blocked. The queue supports pause,
resume, cancellation, retry, and checked reuse of existing conversions.

Open **Preview** for the selected stored conversion and inspect the entire clip,
including feet, root movement, hands, and loop boundaries. Use **Mark Approved**
only after visual review. Technical validation does not certify appearance.

Keep **Use Fortnite intro / loop sections** disabled for an ordinary source-only
setup. Its native pack path may require a separate experimental sampler DLL that
this repository does not provide. Ordinary full-clip conversion remains available.

## Build a pack

Complete [client compatibility setup](CLIENT_COMPATIBILITY.md) before native export.
Supply matching original DBCs in `Input/DBC`; use the DBC manager to inspect them.

Open **Convert & Build Pack**, select a registered model and every dance wanted
in the resulting pack, including earlier conversions, then **Run**. Valid cached
conversions are reused. Inspect partial-success/blocked results rather than
assuming every selected dance was included. **Build Combined Pack** supports
several targets: select each target and its full dance selection, use **Add /
Update Model**, and then run the combined request.

Completed workflows are under `Output/Workflows`; open the resulting pack and read
its generated `INSTALL.txt`. Do not merge arbitrary older packs with independent
DBC allocations.

## Install and verify

- Back up the affected client files and server DBCs before installation.
- Install the generated Client contents using your client archive/patch workflow.
  Studio produces a deployment folder, not an MPQ editor.
- Install the matching Server/dbc files on the server.
- Install the reusable addon in `Interface/AddOns/WoWDanceStudio` outside MPQs,
  then apply the generated catalog from the matching pack's Interface folder.
  **Open Main Addon** builds/opens the reusable addon bundle. Include its code update
  in the pack when updating addon code.
- Apply/adapt the documented server source integration if your core needs it;
  rebuild and restart that server using its own supported workflow.
- Test animation and audio together. Check Stop, movement/jump, casting, combat,
  another emote, model changes, and death on the actual client/server combination.

The addon exposes `/wds` controls including `/wds loop` and `/wds once <dance-token>`.
Generated dance tokens and aliases come from the installed catalog, which starts
empty in this repository. Installing addon source alone does not install dances.

## Troubleshooting

| Symptom | Next step |
| --- | --- |
| Blender/Python not found | Run Setup with the real executable from a complete Blender installation |
| Importer module missing | Enable both required addons in that Blender user profile; run `-CheckImporters` |
| Reference source missing | Prepare/select the source scene with the expected armature object name |
| Source rest pose differs | Use the skeleton export matching the reference scene and regenerate the profile |
| Profile approval required | Review/generate/validate/approve in Models, then select that target again |
| Missing variant or skeleton | Preserve the complete export folder and supply the matching medium performance |
| Native IDs blocked | Read Client compatibility; a higher number in JSON is not a client fix |
| Animation stops while music continues | Check persistent-dance server integration and rebuild deployment |
| Cached result is rejected | Inspect the logged dependency/profile change; regenerate instead of editing manifests |

Logs and detailed results are under `Reports` and each workflow's output folder.
They can contain private paths and asset metadata: redact before sharing issues.
