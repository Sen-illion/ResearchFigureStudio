# Visual Framework Figures

## Summary

Use this route for system overviews, model architecture figures, method pipelines,
algorithm diagrams, Figure 1 style figures, and PPT-ready framework diagrams.

## Principle

Build the figure as an editable composition whose visual mass comes from
AI-generated image blocks. Do not generate the full figure as one bitmap unless
the user explicitly wants a non-editable concept mockup.

This route is not a vector-only diagram route. For image-rich framework
requests, PPT elements are the default structure layer: containers, arrows,
labels, formulas, legends, and panel IDs. SVG/Lark are optional auxiliary routes,
not the default main editable source. The visual content must come from
generated slot-level image blocks unless the user explicitly requests a
vector-only figure or image generation is unavailable and the user accepts a
fallback.

Target composition:

- 60%-80% visual area: AI-generated image blocks
- 20%-40% structure layer: editable arrows, labels, formulas, panel letters,
  grouping boxes, small captions, legends, and callouts
- For detailed paper system figures, default to 25-50 generated non-arrow image
  blocks. Simple figures may use 15-25 blocks; complex system figures may use
  40-50. Arrows, connector lines, dashed loops, transition arrows, panel frames,
  and titles are PPT controls and do not count as image blocks.
  Do not stop at 4-10 macro blocks unless the user explicitly asks for a quick
  draft.

## Process

1. Start from the paper-derived figure brief.
2. If the user provides a full reference image, treat it as
   a visual blueprint and follow `reference_image_alignment.md` before writing
   block prompts. In `reference-primary` mode, split reference elements into
   `image_slots`, `ppt_arrows`, `ppt_shapes`, and `text_regions`.
3. Create the positioning and control artifacts before generation and delivery:
   - **Stylist**: write `reference_style_profile.json` and `style_sheet.md` or
     `style_sheet.json` using `stylist_stage.md` before image2 prompting.
   - **Locator**: write `layout_plan.json` before PPT composition. This file
     records reference-guided normalized coordinates. A VLM may estimate these
     coordinates, but it must not write arbitrary PPT code or generate the
     figure as one bitmap.
   - **Program**: write `figure_program.json` using `figure_program.md` before
     composition or layout scripting.
   - **Reference Text Layer**: write `reference_text_geometry.json`,
     `text_program.json`, and `text_alignment_report.json` before PPT
     composition. Text size, position, color, and hierarchy must follow the
     reference image. Do not apply a default publication-width or minimum-font
     rule that overrides the reference.
   - **Complexity Spec**: write `slot_visual_spec.json` before prompt
     planning. It records reference crop objects, foreground subject,
     secondary objects, micro details, background fill elements, scientific
     mechanism detail, required visual complexity, and forbidden
     simplifications.
   - **Prompt Planner**: write `reference_slot_prompt_brief.json` and
     `slot_prompt_plan.json` before image generation. The default route is a
     VLM/API prompt planner that inspects the reference image, local slot crop,
     and `slot_visual_spec.json`, then outputs a concrete `image_prompt_core`
     for every non-arrow image slot.
   - **Critic**: write `critic_report.md` or `critic_report.json` using
     `critic_stage.md` before final delivery.
4. Divide the framework into three levels:
   - **Macro panels**: layout containers only, such as current context,
     conditioning, speculation, gate, cache, or resource library.
   - **Meso cards**: paper-specific functional units inside macro panels, such
     as a scene card, state board, anchor pin, candidate branch card, cache card,
     or evaluation card.
   - **Micro icons**: small reusable objects, status tokens, metrics, archives,
     model icons, memory chips, option markers, and visual cues.
5. Generate image blocks mainly at the meso-card and micro-icon levels. Macro
   panels should usually be drawn by the editable composition layer, not produced
   as large AI images.
6. For each slot, first write the slot's `slot_visual_spec.json` entry. Then
   let the prompt planner write the slot's `image_prompt_core` from paper
   content, reference-local style, slot geometry, and the visual complexity
   spec. Then write 3-5 targeted prompts using `image_block_prompting.md`.
   Each final prompt must inherit its slot entry from `figure_program.json`, its
   `image_prompt_core` from `slot_prompt_plan.json`, and style constraints from
   the style sheet. Allow only very small non-critical decorative text. Key
   scientific labels, formulas, metrics, variables, arrows, and panel numbers
   must be added by the editable composition layer.
7. Generate multiple candidates per block. Prefer consistent aspect ratios and
   visual grammar: same camera angle, line weight, material, lighting, and color
   family. Reject simple standalone icons for normal slots, local reference crop
   mismatches, and style drift.
8. Select blocks by scientific fit first, style second. Reject beautiful blocks
   that imply a wrong mechanism.
9. Enhance, pad, or regenerate selected blocks if needed. See
   `enhancement_pipeline.md`. Do not crop semantic content. If the generated
   block does not match the slot ratio, prefer regeneration or pad-to-fit over
   cropping.
10. Write `asset_quality_report.json`, `asset_complexity_report.json`,
    `asset_visual_review.json`, selected asset contact sheet, and candidate
    contact sheet. Reject or regenerate blocks below 85% useful content fill,
    with pure empty margin above 10%, with cut-off content, with unresolved
    whitespace issues, with `too_simple`/`generic_icon`, or with
    `reference_crop_ignored`/`style_drift`.
11. Assemble in `editable_composition.pptx` by following `figure_program.json`.
    Add all scientific labels, arrows, connector lines, and dashed loops as PPT
    editable objects. Text objects must come from `text_program.json`, with
    geometry and relative font height bound to `reference_text_geometry.json`.
    Use contain-fit for image blocks; do not crop semantic content.
12. If a reference image was provided, compare the assembled result against it,
    write `visual_critic_iter_0.json`, and automatically adjust large coordinate
    mismatches before final export when the fix is mechanical.
13. Run the critic stage. Fix unresolved major failures before final export.
14. Export a review PNG plus final PDF and 600 DPI raster file. Export SVG only
    when the user, venue, or downstream Illustrator/Inkscape workflow explicitly
    needs it.

## Required Artifacts

For image-rich system figures, leave these artifacts in the output directory:

- `slot_inventory.json` or `slot_inventory.md`
- `reference_geometry.json`
- `reference_controls.json`
- `reference_style_profile.json`
- `style_sheet.md` or `style_sheet.json`
- `input_manifest.json`
- `layout_plan.json`
- `figure_program.json`
- `reference_text_geometry.json`
- `text_program.json`
- `text_alignment_report.json`
- `slot_visual_spec.json`
- `reference_slot_prompt_brief.json`
- `slot_prompt_plan.json`
- `reference_slot_crops/<slot_id>.png` for every non-arrow image slot
- `prompts.md`
- generated slot assets
- `asset_quality_report.json`
- `asset_complexity_report.json`
- `asset_visual_review.json`
- selected asset contact sheet
- candidate asset contact sheet
- `editable_composition.pptx`
- final PDF/PNG export
- `visual_critic_iter_0.json`
- alignment review
- `critic_report.md` or `critic_report.json`

Do not mark the task complete if the only visual artifact is a single generated
full-diagram image, a pure SVG/PPT shape diagram, or a screenshot without
slot-level image assets. Do not mark the task complete with unresolved major
critic failures.

## Prompt Requirements

Each prompt should include:

- paper concept being visualized
- slot function from `slot_prompt_plan.json`
- VLM-planned `image_prompt_core`
- slot visual spec fields: foreground subject, secondary objects, micro
  details, background fill elements, scientific mechanism detail, and forbidden
  simplifications
- visual metaphor
- desired medium or style
- viewpoint and composition
- background and transparency needs
- target slot aspect ratio and fill requirement
- style sheet constraints
- figure program slot ID
- forbidden elements, especially critical text, fake numbers, fake axes, fake
  formulas, and incorrect symbols

Prompt pattern:

```text
Create a dense mini scientific scene/card for [paper concept]. Show [visual
metaphor] representing [paper-specific function]. Recreate the local reference
crop object first, then adapt minor details to the paper concept. Foreground:
[foreground_subject]. Secondary objects: [secondary_objects]. Micro details:
[micro_details]. Background fill: [background_fill_elements]. Mechanism:
[scientific_mechanism_detail]. Style: polished academic paper illustration,
consistent line weight, crisp edges, reference-derived color palette, high
detail. Composition: canvas aspect ratio must be exactly [ratio]. Use a
full-frame composition with a large complete subject, minimal blank canvas, and
supporting detail close to the edge. Useful visual content should fill 90-97%
of the canvas, minimum 85%. Include 2-5 layered objects and edge-to-edge
support detail; do not create a standalone pictogram, simple centered icon, or
single object on a blank canvas. Keep key content complete and uncut inside the
safe area without adding a large blank border. No cut-off edges, no object
extending outside the frame, no tiny centered object. Allow at most tiny
decorative placeholder text; no critical labels, equations, numbers, axes, or
fake charts.
```

## Layout Patterns

Choose based on the paper's method, not habit:

- **Left-to-right pipeline**: sequential data or inference flow
- **Two-stage split**: offline/online, training/inference, construction/evaluation
- **Hub-and-spoke**: central model or memory with multiple interacting modules
- **Loop**: iterative refinement, feedback, self-correction, active learning
- **Stacked panels**: architecture on top, data/results/case below
- **Before/after**: baseline vs proposed mechanism or failure vs correction

## Editable Layer Rules

Always add these outside AI images:

- module labels and method terminology
- arrows and arrow labels
- formulas, tensor shapes, metric names, table values
- panel letters such as A/B/C
- legends and color keys
- section dividers such as training, inference, evaluation, or deployment

For reference-primary figures, editable text must be planned through
`reference_text_geometry.json` and `text_program.json`. Match the reference
image's text bbox, center, relative height, color, and hierarchy. Do not
introduce a default `paper_double_column` or fixed minimum publication font
threshold unless the user explicitly asks to prioritize readability over
reference matching.

Use simple but precise labels. If the paper's terminology is long, keep the full
term in the caption and use a short visible label in the figure.

## PPT-First Routing

- Use PPTX as the default main editable source for image-rich framework figures.
- Put generated image blocks into PPT slots with contain-fit, no semantic crop.
- Draw containers, arrows, labels, formulas, legends, panel IDs, dividers, and
  grouping boxes as editable PPT objects. Do not generate arrows, connector
  lines, dashed loops, or transition arrows as image2 PNG assets.
- Use native PPT charts or PPT shapes for simple editable data panels when this
  does not compromise data correctness.
- Use SVG only as an optional intermediate or export when a venue asks for vector
  files, a Python data figure needs vector embedding, or the user explicitly asks
  for SVG/Illustrator/Inkscape editing.
- Use Lark whiteboard only when cloud collaboration is explicitly more important
  than PPT supervisor editing.

Do not deliver only SVG, PDF, PNG, or a browser screenshot for an image-rich
framework figure unless the user explicitly accepts that the main editable PPTX
will not be produced.

