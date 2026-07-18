# ArkiRev

ArkiRev turns a marked-up approved floor plan into a field brief, per-trade budget exposure, and a critical-path construction sequence.

## Run the app

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Open the local URL Streamlit prints, then upload the approved floor plan first.
The revised-plan upload appears after that. Once both drawings are selected,
ArkiRev automatically generates an annotated plan, a site-ready change register,
and budget and programme impacts.

For the pitch pair, use the files in
[`data/samples/pitch_revised_floor_plan`](data/samples/pitch_revised_floor_plan/README.md).
Use [the demo script](docs/DEMO_SCRIPT.md) for the presentation flow.
