# Pitch Revised Floor Plan

This folder contains a pitch-ready floor-plan pair for the ArkiRev MVP.

## Files

- `RevA_approved.png` - approved baseline plan
- `RevB_revised.png` - revised plan with visible red markup callouts
- `revision_analysis.json` - structured change data matching the backend contract
- `generate_pitch_assets.py` - deterministic asset generator

## Demo Story

Rev B introduces three field-impacting changes:

1. A new pass-through opening between the living room and kitchen.
2. A shifted bedroom door.
3. A relocated kitchen sink rough-in.

Use `RevA_approved.png` and `RevB_revised.png` for the pitch visual, then feed
`revision_analysis.json` into `run_revision_workflow(...)` to show budget,
schedule, implementation windows, risks, and the MVP report summary.
