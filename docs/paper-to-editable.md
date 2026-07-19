# Summary

`rfs paper-to-editable` is the end-to-end paper-only workflow. It first runs `paper-to-image` to produce a paper-grounded raster reference figure, then passes that generated image into `rebuild-editable` to create an editable PowerPoint composition.

This command is an orchestration layer. `rfs paper-to-image` and `rfs rebuild-editable` remain independent commands.

## Output Layout

```text
output\paper_to_editable\
  paper_to_image\
    candidates\
    prompts\
    selected_image.png
    candidate_review.json
    paper_review.json
    run_summary.json
  generated_reference_image.png
  editable_composition.pptx
  figure_program.json
  rebuild_result.json
  paper_to_editable_result.json
```

`generated_reference_image.png` is copied from the selected paper-to-image output and is the reference passed into editable rebuild. The full candidate set, reviews, prompts, and evidence artifacts remain under `paper_to_image\`.

## Production Command

```powershell
rfs paper-to-editable `
  --paper "C:\path\paper.pdf" `
  --out "output\paper_to_editable" `
  --paper-image-asset-mode image2 `
  --paper-image-candidates 3 `
  --paper-image-review-mode vlm `
  --rebuild-asset-mode crop `
  --layout-mode hybrid `
  --control-mode hybrid `
  --text-mode ocr `
  --json
```

By default, an Image2 best-effort `selected_image.png` is still handed to rebuild when no candidate passes all paper-image gates. Add `--require-paper-image-pass` to stop before rebuild unless the selected image passed all production checks.

## Offline Smoke Test

```powershell
rfs paper-to-editable `
  --paper "C:\path\paper.md" `
  --out "output\paper_to_editable_placeholder" `
  --planner-mode heuristic `
  --paper-image-asset-mode placeholder `
  --paper-image-review-mode heuristic `
  --allow-engineering-preview `
  --rebuild-asset-mode placeholder `
  --text-mode off `
  --json
```

Placeholder mode writes `engineering_preview.png` instead of production `selected_image.png`. `--allow-engineering-preview` is required before that engineering image can enter editable rebuild.
