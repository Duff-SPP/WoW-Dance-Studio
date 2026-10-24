# Optional diagnostics

These tools are for investigating an existing local setup. They are not required
to install Studio, download emotes, convert animations, or build packs.

Run commands from the repository root with Python 3.11+:

```powershell
python Tools/Diagnostics/measure_pipeline.py --label sample --target YOUR_REGISTERED_MODEL_ID
python Tools/Diagnostics/capture_animation_state.py PROCESS_ID --output Reports/animation_state.json
```

`measure_pipeline.py` measures checked cache/planning workloads using your local
registered model and available exports. It writes measurements under
`Reports/Performance`; missing optional workloads are reported as unavailable.

`capture_animation_state.py` is a read-only Windows process diagnostic for the
specific inspected Ascension/Wrath 12340 executable layout. It does not suspend
threads or write process memory. Its addresses are not universal client APIs;
do not interpret results from an unrelated executable as valid state.

Diagnostic reports can contain local paths and process data. Keep them out of
source commits and redact them before sharing an issue.
