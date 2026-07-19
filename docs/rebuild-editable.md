# Image-to-Editable-PPT Rebuild

`rfs rebuild-editable` is the reference-only workflow for turning one figure image into an editable PowerPoint-first rebuild.

The v1 goal is reproducibility and inspectability: panels, text, connectors, and simple structure are PPT objects; complex visual blocks are slot-level raster assets. The command does not place the full reference image as the final slide background.

## Quick Start

```powershell
rfs rebuild-editable --reference input.png --out output\demo --asset-mode api --economy-mode
```

Offline engineering run:

```powershell
rfs rebuild-editable --reference input.png --out output\demo_placeholder --asset-mode placeholder --export-preview
```

Only rerun selected assets:

```powershell
rfs rebuild-editable --reference input.png --out output\demo --regenerate-slots slot_03,slot_07
```

High-cost strict regeneration:

```powershell
rfs rebuild-editable --reference input.png --out output\demo --asset-mode api --strict-asset-regeneration --asset-retries 5
```

## Main Options

```text
--reference              Input reference image.
--out                    Output directory.
--asset-mode             api | crop | placeholder. Default: api.
--asset-workers          Parallel asset workers. Default: 4.
--asset-retries          Retries used by strict regeneration. Default: 1.
--economy-mode           Reuse accepted/passing assets. Enabled by default.
--no-economy-mode        Disable economy reuse decisions.
--regenerate-slots       Comma-separated slot ids to rerun.
--text-mode              ocr | manual | off. Default: ocr.
--text-grouping-mode     off | heuristic | vlm | hybrid. Default: heuristic.
--text-grouping-model    Optional VLM model for text grouping arbitration.
--text-role-mode         heuristic | vlm. Default: vlm.
--text-intelligence-mode off | heuristic | vlm. Default: vlm.
--layout-mode            heuristic | vlm | hybrid. Default: hybrid.
--ocr-engine             paddle | easyocr | off. Default: paddle.
--ocr-lang               en | ch | en_ch. Default: en_ch.
--control-mode           heuristic | vlm | hybrid | manual. Default: hybrid.
--rebuild-critic-mode    off | heuristic | vlm. Default: off.
--rebuild-critic-iterations
                         Compiled-preview critic iterations, clamped to 0-3.
--rebuild-critic-model   Optional VLM model for compiled-preview critic.
--skip-analysis          Reuse existing JSON contracts in --out.
--compile-only           Recompile PPTX from existing JSON contracts and assets.
--export-preview         Export rebuild_preview.png when PowerPoint is available.
```

## API Environment

`--asset-mode api` uses the same image-generation route as the specialized rebuild scripts:

```text
GEMINI_API_KEY or API_KEY
GEMINI_GEN_IMG_URL
```

Hybrid VLM layout/control/semantic planning uses an OpenAI-compatible chat completions endpoint:

```text
API_BASE
API_KEY or GEMINI_API_KEY
MODEL_VLM
RFS_REBUILD_LAYOUT_MODEL    optional
RFS_REBUILD_CONTROL_MODEL   optional
RFS_REBUILD_SEMANTIC_MODEL  optional
RFS_TEXT_GROUPING_MODEL     optional
RFS_REBUILD_CRITIC_MODEL    optional
```

PowerShell example:

```powershell
$env:API_BASE='https://your-openai-compatible-provider/v1'
$env:API_KEY='<your key>'
$env:MODEL_VLM='your-vision-language-model'
$env:RFS_REBUILD_LAYOUT_MODEL=$env:MODEL_VLM
$env:RFS_REBUILD_CONTROL_MODEL=$env:MODEL_VLM
$env:RFS_REBUILD_SEMANTIC_MODEL=$env:MODEL_VLM
$env:GEMINI_API_KEY=$env:API_KEY
$env:GEMINI_GEN_IMG_URL='https://your-provider/v1beta/models/your-image-model:generateContent'
```

If the API call fails for a slot, v1 falls back to the reference crop for that slot and records the failure in `asset_generation_report.json`.

## Output Files

The workflow writes these files:

```text
input_manifest.json
reference_geometry.json
reference_geometry_overlay.png
reference_text_geometry_raw.json
reference_text_geometry.json
text_grouping_plan.json
text_grouping_report.json
text_layer_ownership_plan.json
text_layer_ownership_report.json
reference_controls_raw.json
reference_controls.json
reference_controls_overlay.png
slot_inventory.json
slot_semantic_report.json
asset_generation_specs.json
asset_generation_report.json
asset_economy_report.json
asset_ratio_fit_report.json
figure_program.json
composition_quality_report.json
rebuild_vlm_validation_report.json
rebuild_visual_quality_report.json
rebuild_visual_critic_iter_N.json when --rebuild-critic-mode is enabled
rebuild_corrections_iter_N.json when critic patches are applied
editable_composition.pptx
rebuild_preview.png or preview_export_error.txt
```

`figure_program.json` is the PPT compiler source of truth. `reference_text_geometry_raw.json` stores raw line-level OCR, `text_grouping_plan.json` records line-to-paragraph grouping, and `reference_text_geometry.json` stores the final grouped OCR or fallback text geometry. `text_layer_ownership_report.json` records whether each OCR text region belongs in the editable PPT text layer, the raster asset layer, decorative asset text, or should be ignored. `reference_controls_raw.json` stores localized connector candidates before routing, while `reference_controls.json` stores the final routed editable connector contract. `slot_inventory.json` stores non-text visual asset slots.

## Text Grouping And Layer Ownership

OCR often returns one line at a time. By default, rebuild-editable now runs
heuristic text grouping before role classification so multi-line body text can
become one paragraph textbox. Use `--text-grouping-mode hybrid` to let a VLM
arbitrate raw OCR ids against the heuristic groups. The VLM may choose groups,
ignored OCR ids, role, and alignment, but it cannot invent freeform bboxes; code
computes each grouped bbox from the union of raw OCR boxes.

Text ownership is explicit. Critical labels such as panel titles, section
titles, arrows, legends, method labels, modality labels, and slot captions stay
in the editable PPT text layer. Non-critical OCR text visually inside a raster
slot can be assigned to `raster_asset_layer` so it is not duplicated as an
editable textbox. The workflow does not mask or erase crop asset pixels.

## Compiled-Preview Visual Critic

`--rebuild-critic-mode heuristic` writes deterministic visual quality reports
without mutating the program. It checks text overlap, text bboxes outside the
canvas, same-group misalignment, slot/panel overlap, missing arrow paths, and
text ownership conflicts.

`--rebuild-critic-mode vlm --rebuild-critic-iterations N` compares the reference
image against the exported preview PNG and requests concrete JSON patches. The
critic is not allowed to write PPT code, change text content, request crop
masking, or make vague requests such as "optimize the layout." It must return
specific operations such as:

```json
{"op":"update_text","text_id":"text_ref_text_ocr_012","font_size_pt":10,"z_index":8}
```

Allowed patch fields are intentionally narrow: text bbox/font/align/visible/
z_index/layer ownership, slot/panel bbox, and arrow path/style. Application is
hard-limited per iteration: text centers move at most 3%, text font size changes
at most 20%, slot/panel centers move at most 5%, and slot/panel sizes change at
most 20%. If a slot bbox changes, only that slot is regenerated or recopied.

## Analysis And Manual Correction

`--layout-mode hybrid` uses local CV candidates first and can accept a VLM layout planner when one is wired in. Without a VLM adapter, it falls back to heuristic layout and records that status in `reference_geometry.json`.

`--control-mode hybrid` uses CV line detection plus fallback sequence connectors and can accept a VLM/control planner for source-target binding. Detected connector paths are written to `reference_controls_raw.json`; `reference_controls.json` records the routed PPT-ready arrows after `--arrow-style-mode` is applied.

Review overlays:

```text
reference_geometry_overlay.png
reference_controls_overlay.png
```

After manually editing JSON contracts, recompile without rerunning analysis or image generation:

```powershell
rfs rebuild-editable --reference input.png --out output\demo --compile-only
```

To keep existing analysis contracts but rerun OCR, asset specs, and placeholder/API asset handling:

```powershell
rfs rebuild-editable --reference input.png --out output\demo --skip-analysis --asset-mode placeholder
```

## VLM Evaluation

Use the paired evaluator before spending image-generation credits. It runs one
heuristic case and one hybrid VLM case, both using `--asset-mode crop` by
default:

```powershell
rfs rebuild-editable-eval --reference input.png --out output\eval --asset-mode crop --export-preview
```

The evaluator writes:

```text
rebuild_vlm_eval_summary.json
case_heuristic/
case_vlm/
```

Compare the two cases using:

```text
reference_geometry_overlay.png
reference_controls_overlay.png
rebuild_vlm_validation_report.json
rebuild_preview.png
editable_composition.pptx
```

Only run a full `--asset-mode api` rebuild after the VLM case clearly improves
layout, control binding, and slot semantics.

## Cost Control

Economy mode is on by default:

- Existing assets are reused when they pass type-aware fill thresholds.
- Assets listed as accepted in `accepted_assets.json` are locked and reused.
- Each failed slot generates one candidate by default.
- `--regenerate-slots` reruns only named slots.
- `--strict-asset-regeneration --asset-retries N` opts into higher-cost retries.

Accepted assets file example:

```json
{
  "slot_03": {"accepted": true},
  "slot_07": {"accepted": true}
}
```

Type-aware fill thresholds:

```text
character:      80%-95%
document_stack: 75%-95%
chart_card:     75%-95%
tool_icon:      80%-95%
inspection:     70%-95%
tool_combo:     70%-95%
device:         70%-95%
screenshot_card:75%-95%
legend_marker:  80%-95%
thin_tool:      50%-95%
```

## Current Limits

This is a reusable baseline, not a pixel-perfect designer replacement. Hybrid mode is designed to accept stronger VLM layout/control planners, but it still falls back safely when they are unavailable. Complex layouts, curved arrows, and panel semantics may still need manual JSON correction. OCR is optional and falls back safely when local OCR is unavailable.
