# Pitch Revised Floor Plan

This folder contains a pitch-ready floor-plan pair for the ArkiRev MVP.

## Files

- `RevA_approved.png` - approved baseline plan
- `RevB_revised.png` - revised plan with visible red markup callouts
- `0000-0009_base_original.png` - archive sample to upload as the approved/original plan
- `0000-0009_revised_mock.png` - mock revised version to upload as the revised plan
- `0000-0009_annotated_demo.png` - example output image with generated change labels
- `revision_analysis.json` - structured change data matching the backend contract
- `generate_pitch_assets.py` - deterministic asset generator
- `generate_0009_mock_revision.py` - generator for the 0009 original/revised/annotated demo trio

## Demo Story

Rev B introduces three field-impacting changes:

1. A new pass-through opening between the living room and kitchen.
2. A shifted bedroom door.
3. A relocated kitchen sink rough-in.

Use `RevA_approved.png` and `RevB_revised.png` for the pitch visual, then feed
`revision_analysis.json` into `run_revision_workflow(...)` to show budget,
schedule, implementation windows, risks, and the MVP report summary.

## 0009 Upload Demo

Use this sequence to pitch the uploaded-plan flow:

1. Upload `0000-0009_base_original.png` as the approved floor plan.
2. Upload `0000-0009_revised_mock.png` as the revised floor plan.
3. Show `0000-0009_annotated_demo.png` as the expected ArkiRev output.

The mock revised image contains blue/yellow draft changes. The annotated output
adds ArkiRev red labels and boxes to map what changed on the revised plan.

## Annotation Note

The archive dataset labels are object-detection boxes, not true revision
ground truth. In the MVP, real change boxes should come from either:

1. comparing approved Rev A against uploaded Rev B with the vision assistant, or
2. user-drawn markup boxes from the canvas.

`annotate_revised_plan(...)` can then draw those detected or user-marked
changes onto the revised floor plan as the output image.
