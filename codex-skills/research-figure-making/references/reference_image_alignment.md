# Reference Image Alignment

## Summary

Use this reference only when the user provides a complete reference framework
image and wants the final editable framework figure to follow that image while
replacing it with controllable small visual blocks. Do not generate the reference
image yourself unless the user explicitly asks for that separate step.

## Role Of The Reference Image

The user-provided reference image is the visual blueprint. In
`reference-primary` mode, it is the highest authority for layout, visual object
choice, flow logic, framework colors, style, and visual rhythm. The paper only
calibrates terminology, scientific labels, and whether a reference visual needs
minor semantic adaptation. Use the reference image to preserve:

- overall composition and visual rhythm
- approximate module count and spatial grouping
- color mood, lighting, and illustration style
- relative emphasis of major regions
- useful metaphors or icon ideas

If the user explicitly says the reference image should dominate layout or
positioning, switch to reference-primary positioning: the reference image's
macro-panel order, slot bboxes, flow direction, and relative scale become the
layout source-of-truth. The paper then calibrates names, labels, scientific
claims, and missing/incorrect details; it should not replace the visual logic
with a generic paper-derived grid.

Do not preserve reference-image mistakes:

- hallucinated text or symbols
- wrong scientific relationships
- missing paper modules
- decorative elements that make the figure harder to read
- layout choices that fail at paper scale

## Alignment Workflow

1. Inspect the reference image and write a visual blueprint:
   - canvas orientation and aspect ratio
   - major regions and their approximate positions
   - visual style, palette, and density
   - implied flow direction
   - candidate small visual blocks
   - parts that conflict with the paper
2. Run reference image parameter analysis:
   - read or estimate the reference image pixel size
   - compute the overall canvas aspect ratio
   - identify reusable visual slots inside the macro panels
   - classify reference elements into `image_slots`, `ppt_arrows`,
     `ppt_shapes`, and `text_regions`; arrows, dashed loops, connector lines,
     and transition arrows must not become image2 slots
   - estimate each slot's relative bounding box as `x,y,w,h` in 0-1 canvas units
   - write `reference_geometry.json` with each panel/slot's `bbox_percent`,
     `center_percent`, `width_percent`, `height_percent`,
     `aspect_ratio_decimal`, `aspect_ratio_w_h`, and `target_pixels_exact`
   - record each slot's exact canvas ratio from pixel geometry, target pixel
     size, visual density, safe area, and fit policy
   - produce a slot inventory table before generating image2 prompts
   - write `reference_control_candidates.json` as an AutoFigure-inspired
     boxlib-like candidate layer for arrows, connector lines, dashed loops,
     branch connectors, and transition symbols detected from the reference
   - render `slot_overlay.png` and `reference_control_overlay.png`; the first
     labels image slots, while the second labels control candidates as
     `AR01`, `AR02`, and so on for human or VLM source-target binding
   - write `reference_controls.json` with each bound arrow/control's
     `bbox_percent`, `center_percent`, `width_percent`, `height_percent`,
     `source_id`, `target_id`, `source_anchor`, `target_anchor`,
     multi-point `path_percent`, `style_token_id`, `editable_in: pptx`, and
     `render_policy: ppt_shape_not_image_asset`
   - write `arrow_style_profile.json`, `selected_arrow_routes.json`, and
     `arrow_quality_report.json` before PPT compilation. This stage should
     improve softness and visual variation with reference-derived styles, but
     must not replace the reference image's source-target logic or locked paths
   - write `reference_style_profile.json` with reference-derived color tokens,
     style summary, illustration mode, line weight, shadows, corner radius,
     texture, icon detail level, visual density, and text policy
   - write `layout_plan.json` as the normalized positioning layer
   - import the slot inventory and layout plan into `figure_program.json` before
     composition
   - in reference-primary positioning, preserve each extracted `bbox_percent`
     through `slot_inventory.json`, `layout_plan.json`, `figure_program.json`,
     and PPT placement; do not recalculate these slots with a generic grid
   - write `reference_slot_prompt_brief.json` before image generation; this file
     records, for each slot, what the local reference region does, what paper
     concept it carries, and what concrete visual evidence should be sent to the
     prompt-planning model
3. Map the blueprint to the paper-derived figure brief:
   - keep only blocks that correspond to paper concepts
   - add missing paper-required blocks
   - remove visual-only blocks that carry no information
   - note every intentional deviation from the reference image
4. Generate small image blocks:
   - first generate `slot_prompt_plan.json` with a VLM/API planner by default
   - the planner should inspect the full reference image and, when possible,
     each local slot crop before writing the slot's prompt plan
   - save every local crop as `reference_slot_crops/<slot_id>.png`; write this
     path into `slot_inventory.json`, `reference_slot_prompt_brief.json`,
     `slot_prompt_plan.json`, and `figure_program.json`
   - use prompts that cite the reference style and the paper-specific concept
   - keep aspect ratios compatible with the target slot
   - require the generated canvas to match the exact decimal target slot ratio
     from the start; do not replace it with coarse presets
   - keep all useful content inside a 92% safe area
   - require 90-97% useful content fill and less than 10% empty margin on every
     edge
   - allow only very small non-critical decorative text
   - generate several variants per slot if the first attempt is off-style
5. Assemble the editable figure:
   - place blocks in the same broad spatial arrangement as the reference
   - add arrows, labels, formulas, groups, and panel marks as editable objects
   - keep the reference image available as a temporary background or side-by-side
     comparison during layout
6. Export a review image and run the mismatch check below.

Reference-image alignment must happen before image generation. Do not use the
reference image only as a loose style hint after creating a single full diagram.
The reference image should produce a slot inventory that drives image2 prompts
and final placement.

After the slot inventory is written, create `layout_plan.json` for slot and
panel coordinates, then convert it into the `slots` section of
`figure_program.json`. The final composition should use the program as the
placement source of truth, not a separate temporary script or manual layout note.
If a VLM is used for positioning, it may only output `layout_plan.json`
coordinates and arrow routes; it must not write PPT code or generate the whole
figure.
In reference-primary positioning, VLM coordinates are advisory only unless the
system has no extracted bbox for that slot. Existing reference-derived slot
bboxes must not be overwritten by a freeform locator.

## Slot Inventory

Before generating image blocks, write a table or JSON-like list with:

- `slot_id`: stable ID such as `p1_scene_card` or `library_llm_icon`
- `paper_concept`: concept from the paper or an explicitly marked visual support
- `macro_panel`: parent panel or region
- `bbox_percent`: approximate `{x,y,w,h}` relative to the full reference image
- `center_percent`: `{x,y}` center of the slot relative to the full reference image
- `width_percent`: slot width divided by full reference image width
- `height_percent`: slot height divided by full reference image height
- `aspect_ratio_decimal`: exact slot pixel width divided by slot pixel height
- `aspect_ratio_w_h`: precise decimal ratio such as `1.429:1.000`
- `target_canvas_ratio`: same precise decimal ratio; never a coarse preset
- `target_pixels`: exact pixel width and height derived from the reference;
  must match `target_pixels_exact`
- `target_pixels_exact`: exact pixel width and height derived from the reference
- `generation_min_pixels`: minimum image-generation request size; this is not
  the reference geometry and must not replace `target_pixels`
- `visual_density`: low, medium, high, or very_high
- `text_policy`: none, decorative_only, or editable_overlay_required
- `safe_area_percent`: usually 92, meaning important content stays inside the
  inner 92% of the generated canvas without creating a large blank border
- `fit_policy`: contain, pad_to_fit, background_extend, regenerate_for_ratio, or
  preserve_outer_shape
- `target_content_fill_percent`: usually 90-97
- `min_content_fill_percent`: usually 85 or higher
- `max_empty_margin_percent`: usually 10 or lower
- `composition_type`: full_frame_icon, full_bleed_card, scene_thumbnail, or
  symbol_cutout
- `slot_frame_policy`: usually `frameless_slot`; do not add a white PPT tile
  unless that frame exists in the reference image
- `blank_space_policy`: how the slot avoids tiny centered subjects and large
  blank canvas
- `figure_program_slot`: matching slot ID in `figure_program.json`
- `prompt_notes`: visual metaphor and style constraints
- `slot_function`: what this block does in the system figure
- `reference_slot_role`: local role of this slot in the reference layout
- `reference_shape_language`: local shape, aspect ratio, and card/icon treatment
- `reference_local_style`: local palette, density, line, shadow, and visual
  rhythm
- `reference_prompt_hint`: one sentence binding the local reference style to the
  paper concept
- `reference_crop_path`: local crop file for this slot, usually
  `reference_slot_crops/<slot_id>.png`
- `reference_style_profile_path`: usually `reference_style_profile.json`
- `local_color_token_ids`: exact color token IDs extracted from the local
  reference crop or nearby framework region

After `figure_program.json`, write `reference_slot_prompt_brief.json`, then ask
the VLM prompt planner to output `slot_prompt_plan.json`. Each slot prompt plan
must contain `image_prompt_core`, a concrete image-generation prompt core for
that slot. Do not skip this stage and let a generic template decide what every
small image should depict.

Default target counts:

- simple framework: 15-25 slots
- normal paper system figure: 25-50 slots
- complex system figure: 40-50 slots

Do not use only macro panels as slots unless the user asks for a rough draft.

## Mismatch Check

Compare the assembled result to the reference image at three levels:

- **Structure**: slot count, module count, group positions, flow direction, major
  empty spaces
- **Style**: palette, line weight, visual density, lighting, background treatment
- **Semantics**: whether each visual block still represents the paper concept

Classify mismatches:

- **Major**: changed flow direction, missing key module, wrong grouping, or visual
  block implies the wrong scientific mechanism
- **Medium**: layout proportions differ strongly, style is inconsistent, one block
  is much more/less visually important than intended
- **Minor**: small spacing, padding, color, or edge-cleanup issue

## Automatic Adjustment Rules

If a major mismatch exists, revise without waiting for the user unless the fix
requires a scientific decision that is not in the paper:

- regenerate the mismatching block with a tighter prompt
- replace the block with a better candidate
- move or resize blocks to match the reference structure
   - revise arrows or grouping boxes when flow direction is unclear; use
     arrow-only patches that update `arrow_id`, anchors, and `path_percent`,
     never a full figure rewrite
- regenerate blocks whose useful visual content occupies less than 80% of the
  image area, or is below the 88%-95% target without a documented reason
- regenerate or pad-to-fit blocks whose canvas ratio differs from the target slot
  by more than 10%; do not crop semantic content
- regenerate any block with a cut-off subject, card, character, icon, or
  meaningful visual detail
- simplify a decorative block if it harms readability
- update the blueprint notes to explain intentional deviations

If only medium or minor mismatches exist, adjust layout, padding, color balance,
background extension, or arrow routing before final export.

Do not overfit to the reference image. Prefer paper correctness over visual
similarity whenever they conflict.

## Deliverables

Keep these artifacts when practical:

- reference image
- visual blueprint notes
- slot inventory
- block-to-paper mapping
- generated block prompts
- `layout_plan.json`
- `figure_program.json`
- `reference_slot_prompt_brief.json`
- `slot_prompt_plan.json`
- generated slot assets and contact sheet
- asset visual review
- visual critic report
- side-by-side review image
- mismatch notes and automatic adjustments
- editable composition and final export

