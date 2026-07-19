# Summary

`rfs paper-to-image` produces a reviewed raster scientific framework image without creating PPTX. Production mode requires successful VLM paper review, a content-free architecture blueprint, reference-conditioned Image2 edit generation, and four production quality gates.

## Production Command

```powershell
$env:API_BASE='https://yunwu.ai/v1'
$env:API_KEY='<rotated-new-key>'
$env:RFS_IMAGE_MODEL='image-2'
$env:RFS_IMAGE_EDIT_URL='https://yunwu.ai/v1/images/edits'

rfs paper-to-image `
  --paper "C:\path\paper.pdf" `
  --out "output\paper_to_image" `
  --domain-profile auto `
  --positive-reference "C:\path\reference1.png" `
  --positive-reference "C:\path\reference2.png" `
  --template auto `
  --planner-mode vlm `
  --asset-mode image2 `
  --candidates 3 `
  --aspect-ratio auto `
  --review-mode vlm `
  --repair-rounds 1 `
  --ocr-engine auto `
  --json
```

Never reuse a key that has appeared in chat, source control, an issue, or a terminal transcript. The command records only `api_key_present`; it never records a key value.

## Paper Review Contract

`paper_review.json` uses a universal core plus a selected domain profile. Facts use stable IDs, evidence IDs, expanded page/section/quote references, confidence, importance, `required|optional|forbidden|unknown` status, and a figure role. The coverage validator rejects ungrounded required facts, invalid relation endpoints, missing profile sections, and duplicated training/inference steps in production mode.

Available profiles:

- `general`
- `ai-ml-method`
- `system-platform`
- `dataset-benchmark`
- `empirical-science`
- `survey-review`

## Template Contract

Positive references are classified as `arbor`, `linear`, `tripanel`, or `dense-multimodal`. Each becomes a content-free profile containing normalized panels, topology, connector rhythm, density, palette, and forbidden copied content. Automatic selection uses module count, loops/tree structure, multimodality, retrieval structure, and requested ratio.

The selected profile is rendered as `layout_blueprint.png`. The blueprint contains no reference text or reference-specific objects and is the only image supplied to Image2 edit for initial candidates.

## Production Gates

Every Image2 candidate must pass:

- exact-label OCR with no missing, misspelled, duplicate, or copied reference labels;
- scientific module and relation checks with no invention or reversal;
- template alignment score of at least `0.72` with no copied reference content;
- aesthetic score of at least `0.75`;
- valid image resolution and blueprint aspect ratio.

Scientific score must be at least `0.95`; OCR must be exact. If three candidates fail, the best candidate receives one localized Image2 edit repair. If the repair still fails, the command stops without writing `selected_image.png`.

## Engineering Mode

`--asset-mode placeholder --planner-mode heuristic --review-mode heuristic` validates contracts without API cost. It writes `engineering_preview.png`, never `selected_image.png`, and is not production eligible.
