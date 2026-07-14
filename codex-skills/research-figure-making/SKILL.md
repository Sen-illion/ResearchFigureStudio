---
name: research-figure-making
description: >-
  Use this skill when the user provides a research paper, manuscript, method
  section, experiment section, LaTeX/Word/PDF/Markdown draft, result table, CSV,
  figure sketch, or old paper figure and asks to create, redesign, or improve
  publication-quality scientific figures, including paper-driven framework
  figures, system overview diagrams, model architecture figures, pipeline
  diagrams, data plots, main-result figures, multi-panel figures, or PPT/Lark
  editable figures. Prioritize AI/ML/NLP research papers, paper-grounded visual
  extraction, AI-generated visual blocks for framework figures, reproducible
  Python plots for data figures, and PPTX-first editable outputs with optional
  Lark/SVG exports. Also use for
  Chinese-language requests that mean drawing figures from a paper, making paper
  framework diagrams, system diagrams, data figures, main paper figures, PPT
  figures, Lark whiteboard figures, method figures, result figures, or
  top-tier-publication figures.
---

# Research Figure Making

## Summary

Create publication-oriented research figures from the user's actual paper content.
Do not use generic architecture templates until the paper has been read and the
paper-specific concepts, variables, modules, and claims have been extracted.
For image-rich framework figures, default to many slot-level image2 blocks,
PPTX-first editable composition, front Summary sections, no semantic cropping,
and hard asset-fill validation.

## Trigger

Use this skill when the user asks for figures based on:

- a paper draft, method section, experiment section, abstract, related work, or notes
- LaTeX, Word, PDF, Markdown, plain text, tables, CSV/Excel, logs, or existing figures
- requests such as "draw Figure 1 from my paper", "make a system overview",
  "create a framework diagram", "turn this paper into PPT figures", "improve my
  data plot", or "redesign this figure for a top-tier paper"
- Chinese-language requests that mean drawing framework figures from a paper,
  making system diagrams from method sections, turning experimental results into
  data figures, creating main paper figures, PPT figures, or top-tier paper figures

## Mandatory Framework Protocol

For system architecture, framework, pipeline, model overview, or Figure 1 style
requests where the user wants an image-rich figure, this protocol is mandatory:

## Front Summary Rule

Every text artifact must start with a `Summary` section before details. This
applies to the figure brief, slot inventory, style sheet, figure program,
prompts, asset quality report, asset visual review, layout plan, visual critic,
alignment review, critic report, and final response. For Markdown, the first
non-empty heading must be `# Summary` or `## Summary`. For JSON, use a top-level
non-empty `summary` field.

## Local RFS Route

When `D:\ResearchFigureStudio` and the `rfs` CLI are available, use them as the
default implementation for image-rich framework figures:

```powershell
rfs make-framework --paper <paper> --reference <reference_image> --out <output_dir> --slot-count 40 --slot-source reference-primary --complexity-profile reference-dense --candidates-per-slot 4 --locator-mode vlm --control-localizer-mode hybrid --arrow-style-mode reference --prompt-plan-mode vlm --prompt-plan-workers 8 --asset-mode image2 --asset-workers 6 --asset-retries 3 --asset-review-mode heuristic --critic-mode heuristic
```

Use `--asset-mode image2` for real image generation through the Yunwu
OpenAI-compatible Images API. The logical `image-2` target maps to Yunwu's listed
`gpt-image-2` model unless `RFS_IMAGE_MODEL` or `IMAGE_MODEL` overrides it. Keep
`--asset-mode gemini` as a fallback and use `--asset-mode placeholder` only for
engineering validation. Use `--locator-mode vlm` when a
VLM should borrow the LiveFigure-style positioning idea by returning
`layout_plan.json` coordinates. The VLM must not write arbitrary PPT code or
generate a single full diagram. For API-cost control, run a small real pass first
with `--slot-count 25 --candidates-per-slot 1 --asset-workers 3`, then a full
pass after the contract validates. Yunwu image2/Gemini slot generation may run
concurrently through RFS workers; do not fall back to manual one-by-one image2
generation unless the API path is unavailable.
Prompt planning is not a cost-saving heuristic stage by default: use
`--prompt-plan-mode vlm` so the model inspects the reference image and each
local slot before producing `slot_prompt_plan.json`. Use heuristic prompt
planning only for offline engineering validation. Use `--prompt-plan-workers`
to parallelize per-slot VLM prompt planning; use `--asset-workers` separately to
parallelize Yunwu image2/Gemini image generation.
Use `--control-localizer-mode hybrid` by default for arrow and connector
localization. This AutoFigure-inspired stage writes
`reference_control_candidates.json`, `slot_overlay.png`, and
`reference_control_overlay.png`; VLM binding may assign source-target semantics
from those overlays, while the fallback heuristic keeps the workflow offline.
The VLM may patch arrow IDs, anchors, and normalized paths only; it must not
write PPT code, rasterize arrows, or redraw the full figure.
Use `--arrow-style-mode reference` by default. This stage may soften PPT
connector line caps, vary stroke widths, assign bundle/lane metadata, and score
crossing/bend/overlap quality, but the reference image remains the hard
constraint. It must not replace reference-derived flow logic with a generic
graph router. Orthogonal obstacle-aware routing is allowed only for missing
paths or arrows explicitly marked `route_policy=fallback_reroute_allowed`; it
must never rewrite reference-locked `path_percent` values.
Use `--arrow-style-mode aesthetic` only for an explicit experimental
beautification pass. In that mode, the router may apply curve connectors and
halo underlays by default. Bundle lane offsets require explicit route opt-in
and must stay inside `reference_tunnel_percent`; the router must record
`reference_original_path_percent`, `reference_path_delta_max`, and
`reference_tunnel_preserved`, and it must not change source-target logic.
Use `rfs presentations-qa --out <output_dir>` only as an optional QA pass when
the Presentations plugin is available. Presentations may import/render the PPTX,
extract layout JSON, and report connector/font/rendering drift, but it must not
mutate the PPTX, rewrite arrows, regenerate layout, or replace RFS as the
authoritative compiler for reference-locked connector-heavy figures.

Before execution, read these references in this order:

1. `references/paper_to_figure.md`
2. `references/visual_framework_figures.md`
3. `references/reference_image_alignment.md` when a reference image is provided
4. `references/stylist_stage.md` before writing image2 prompts
5. `references/figure_program.md` before composition or scripting
6. `references/image_block_prompting.md` before writing image2 prompts
7. `references/critic_stage.md` before final delivery
8. `references/journal_quality_checklist.md` before final delivery

Execution checklist:

1. Read the paper and write a paper-grounded figure brief.
2. If the user provides a reference image, parameterize it before generation:
   identify slots, canvas ratios, safe areas, and fit policies.
   When the user says the reference image should guide the figure, treat its
   slot positions and flow logic as layout source-of-truth. The paper calibrates
   terminology and scientific labels; it must not cause a generic paper-derived
   grid to replace the reference image's spatial logic.
   In reference-primary mode, the reference image is the highest authority for
   layout, visual object choice, style, framework colors, arrow logic, and
   visual rhythm. The paper only assists terminology and scientific mapping.
   Write `reference_geometry.json` with precise panel/slot geometry before any
   prompt generation. Every panel and slot must include `bbox_percent`,
   `center_percent`, `width_percent`, `height_percent`,
   `aspect_ratio_decimal`, `aspect_ratio_w_h`, `target_pixels`,
   `target_pixels_exact`, and `generation_min_pixels` with at least three
   decimals where numeric precision matters. `target_pixels` must equal
   `target_pixels_exact`; use `generation_min_pixels` only for the image
   generator's minimum resolution safeguard.
   Also write `reference_control_candidates.json`,
   `slot_overlay.png`, `reference_control_overlay.png`, and
   `reference_controls.json` for measured arrows, connector lines, dashed
   loops, transition arrows, framework shapes, and text regions. Control
   candidates are analogous to a boxlib/overlay layer: they identify possible
   arrows and connectors from the reference image before semantic binding.
   Bound controls must record geometry, `source_id`, `target_id`,
   `source_anchor`, `target_anchor`, multi-point `path_percent`, color token,
   and `render_policy: ppt_shape_not_image_asset`.
   Then write `arrow_style_profile.json`, `selected_arrow_routes.json`, and
   `arrow_quality_report.json`. These files must state
   `reference_image_hard_constraint`, preserve locked reference paths, and only
   synthesize missing or explicitly fallback-allowed paths. If fallback routing
   is used, record `routing_algorithm`, `route_generation_status`, candidate
   count, and obstacle/crossing metrics.
   If `--arrow-style-mode aesthetic` is used, also record original reference
   paths, tunnel width, path delta, halo settings, connector type, and whether
   each adjusted route stayed inside the reference tunnel.
3. Create a slot inventory before using image2. Default to 25-50 image slots for
   a normal paper system figure. This count means non-arrow image slots only;
   arrows, connector lines, dashed loops, panel frames, and titles must not be
   counted as image2 assets.
4. Write `reference_style_profile.json` and `style_sheet.md` before writing
   image2 prompts. They must define reference-derived color tokens, palette,
   line weight, shadows, viewpoint, icon complexity, background, visual density,
   font-layer rules, and image2 text policy.
5. Write `layout_plan.json` and `figure_program.json` before composition.
   `layout_plan.json` records normalized reference-guided coordinates; it may be
   produced by heuristic rules or VLM positioning, but never by freeform PPT
   code. `figure_program.json` must record `canvas`,
   `panels`, `slots`, `assets`, `labels`, `arrows`, `groups`, and
   `export_targets`; slots must bind paper concepts, reference bboxes, target
   ratios, safe areas, fit policies, and asset IDs. `export_targets` must
   include the main editable PPTX target, usually `editable_composition.pptx`.
   In reference-primary mode, `bbox_percent` values extracted from the reference
   image must be preserved into `layout_plan.json`, `figure_program.json`, and
   PPT placement. A VLM locator may refine arrows or identify missing slots, but
   it must not freely redraw the macro framework or overwrite reference-derived
   slot positions. Do not convert exact reference ratios into coarse presets
   like `1:1`, `4:3`, `3:4`, `16:9`, or `9:16`; use precise decimal ratios such
   as `0.538:1.000`.
   Text size, position, color, and hierarchy are reference-primary too. Do not
   create a default `publication_scale.json`, do not enforce a fixed
   `paper_double_column` target width, and do not fail a figure only because a
   reference-matched label would be small after manuscript scaling. Instead,
   write `reference_text_geometry.json`, `text_program.json`, and
   `text_alignment_report.json`. These files must preserve the reference
   image's text bbox, center, relative font height, color, role, and hierarchy.
   The paper may adapt terminology, but the PPT text layer must stay editable
   and must not override the reference layout with a generic typography rule.
6. Write `slot_visual_spec.json`, `reference_slot_prompt_brief.json`, and
   `slot_prompt_plan.json` before image generation. `slot_visual_spec.json`
   records each slot's reference crop objects, foreground subject, secondary
   objects, micro details, background fill elements, scientific mechanism
   detail, required visual complexity, and forbidden simplifications. Except
   explicit legend/badge slots, normal image slots must be planned as dense mini
   scientific scenes/cards with 2-5 layered objects, not simple standalone
   icons. The brief records what each reference slot does and what paper concept
   it carries. `slot_prompt_plan.json` must be generated by a VLM by default and
   include per-slot `slot_function`, local reference style, concrete
   `visual_metaphor`, `must_show`, `avoid_showing`, visual-complexity fields,
   and `image_prompt_core`. Every image slot must have
   `reference_slot_crops/<slot_id>.png`, and the prompt planner must use the
   full reference image, the local slot crop, the global style profile, local
   color token ids, precise geometry, and the paper concept. Arrows and
   connector controls never receive image prompts. For normal 25-50 slot
   figures, run VLM prompt planning in parallel unless rate limits force a lower
   worker count.
7. Generate image assets per slot, preferably through RFS Gemini/Yunwu
   concurrent workers when configured. Manual image2 generation is only a
   fallback. Do not generate one full architecture image as the final figure.
8. Create `asset_quality_report.json`, `asset_complexity_report.json`,
   `composition_quality_report.json`, `asset_visual_review.json`, selected asset
   contact sheet, and candidate contact sheet. The quality report must record
   `content_fill_percent`, `empty_margin_percent`, `edge_cutoff_status`,
   `ratio_status`, selected candidate, and `action` for every image block. The
   complexity report must record `detail_score`, `object_count_estimate`,
   `simple_icon_risk`, `reference_crop_match`, `style_match`, and
   `selected_reason`; unresolved `too_simple`, `generic_icon`,
   `reference_crop_ignored`, `single_object_on_blank_background`, or
   `style_drift` must block delivery.
   `composition_quality_report.json` must prove that PPT insertion used
   frameless image slots, no extra white tile, no caption inside the image slot,
   and at least 95% image-slot area fill.
9. Compose the final figure in `editable_composition.pptx` by default. Use PPT
   editable layers for containers, arrows, connector lines, dashed loops, labels,
   formulas, legends, and panel IDs. Image slots are direct frameless assets;
   arrows are PPT shapes/connectors, not generated PNGs.
10. Write an alignment review noting source grounding, slot count, rejected assets,
   and reference-image mismatches.
11. Write `visual_critic_iter_0.json` and `critic_report.md` or
    `critic_report.json` before final delivery.
    It must check paper faithfulness, slot count, text controllability, whether
    the output used a single full diagram, vector-only fallback, semantic
    cropping, incomplete image blocks, asset fill quality, asset complexity,
    reference-crop match, style match, and PPT editability.
    Major failures must be fixed or the delivery must stop.
12. Run `scripts/validate_framework_outputs.py <output_dir>` before final
    delivery when a local output directory exists.
13. Optionally run `rfs presentations-qa --out <output_dir>` after validation.
    Treat `autoRouteConnectorPx failed` or similar plugin connector fallback
    warnings as QA evidence. Do not let the Presentations plugin rebuild the
    figure or override RFS connector geometry.

Hard workflow order:

`input archive -> paper brief -> reference slot/control analysis -> reference_geometry.json ->
reference_control_candidates.json -> slot_overlay.png/reference_control_overlay.png ->
reference_controls.json -> arrow_style_profile.json/selected_arrow_routes.json/arrow_quality_report.json ->
reference_style_profile.json/style sheet ->
layout_plan.json -> figure_program.json -> reference_text_geometry.json/text_program.json/text_alignment_report.json -> slot_visual_spec.json ->
reference_slot_prompt_brief.json -> slot_prompt_plan.json -> image2/Gemini slot prompts -> generated
assets/asset_quality_report/asset_complexity_report/composition_quality_report/asset_visual_review/contact sheets ->
editable_composition.pptx -> PDF/PNG export -> visual critic -> critic report ->
final validation/export -> optional presentations QA report`

Image block fill rules:

- Target useful visual content fill: 90%-97% of the canvas.
- Minimum passing content fill: 85% unless the slot is explicitly marked as a
  sparse symbol with a documented reason.
- Maximum pure empty margin in any direction: 10%.
- Safe area means the key subject is not cut off; it does not mean leaving a
  large blank border. Background texture, secondary details, card surfaces, and
  non-critical supporting marks should extend close to the canvas edge.
- If a block has too much whitespace, regenerate or redesign the prompt. Padding
  is only for ratio matching, not for fixing a tiny subject on a blank canvas.

Forbidden shortcuts:

- Do not satisfy an image-rich framework request with vector-only shapes unless
  the user explicitly asks for a vector-only diagram.
- Do not silently replace image2 blocks with PPT shapes, SVG, or Lark shapes
  because that is faster or easier.
- Do not deliver only an SVG source file for an editable research figure unless
  the user explicitly asks for SVG-only or Illustrator/Inkscape-first work.
- Do not generate a single full diagram image and then screenshot or crop it as
  the final result.
- Do not use a browser or canvas screenshot as the primary artifact unless it is
  a rendered composition assembled from generated slot assets.
- Do not use the Presentations plugin as the primary compiler for image-rich
  research figures; it is QA-only unless the user explicitly asks for a
  separate presentation deck workflow.
- If image2/image generation is unavailable, say so and stop or ask for a
  fallback; do not silently switch to a vector-only workflow.

Required output files for image-rich framework figures:

- `slot_inventory.json` or `slot_inventory.md`
- `reference_geometry.json`
- `reference_control_candidates.json`
- `slot_overlay.png`
- `reference_control_overlay.png`
- `reference_controls.json`
- `arrow_style_profile.json`
- `selected_arrow_routes.json`
- `arrow_quality_report.json`
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
- at least 25 generated image assets for normal system figures
- `asset_candidate_contact_sheet.png`
- `asset_quality_report.json`
- `asset_complexity_report.json`
- `composition_quality_report.json`
- `asset_visual_review.json`
- `asset_contact_sheet.png`
- `editable_composition.pptx`
- final figure export
- `visual_critic_iter_0.json`
- `alignment_review.md`
- `critic_report.md` or `critic_report.json`

Optional Presentations-plugin QA outputs:

- `presentations_plugin_qa_report.json`
- `presentations_plugin_qa_report.md`
- `presentations_plugin_qa_workspace/`

Validation must fail if the output uses only a single generated full-diagram
image, lacks slot assets, lacks prompts, lacks a contact sheet, or records
semantic cropping as the fitting strategy. Validation must also fail when the
style sheet, layout plan, figure program, reference text geometry, text program,
text alignment report, slot visual spec, reference slot
prompt brief, slot prompt plan, reference geometry, asset quality report, asset
complexity report, composition quality report, asset visual review, visual
critic report, critic report, or editable PPTX source is missing.
Validation must fail when any unresolved image block has `content_fill_percent`
below its minimum or `empty_margin_percent` above its maximum.
Validation must fail when a slot uses a coarse preset ratio, when PPT insertion
adds an extra white tile, or when an inserted image fills less than 95% of its
slot area.
Validation must fail when PPT text is not bound to
`reference_text_geometry.json`, when text center/bbox/font-ratio drift from the
reference exceeds the recorded alignment tolerance, or when critical text is
not editable in PPTX. Validation must not fail only because the text would be
small under a default paper-double-column scaling assumption.
Validation must fail when a normal non-legend slot lacks `secondary_objects` or
`micro_details`, or when a selected asset has unresolved `too_simple`,
`generic_icon`, `reference_crop_ignored`, `single_object_on_blank_background`,
or `style_drift`.
Validation must fail when arrow, dashed loop, transition, or connector elements
appear in `slots`/`assets`; they must appear in `reference_controls.json` and
`figure_program.json` as editable PPT controls with source/target logic and
style tokens. Validation must also fail when `reference_control_candidates.json`
or the slot/control overlay images are missing, when a bound control lacks
`source_id`, `target_id`, `source_anchor`, `target_anchor`, or at least two
`path_percent` points, or when composition reports that a control was not
rendered as an editable PPT connector. Validation must fail when
`arrow_style_profile.json`, `selected_arrow_routes.json`, or
`arrow_quality_report.json` are missing, or when an arrow style stage overrides
a locked reference path without a documented reason. Validation must also fail
when fallback obstacle routing is applied to a reference-locked path, or when
route artifacts omit `routing_algorithm` / `route_generation_status`.
For aesthetic mode, validation or critic review must fail when
`reference_tunnel_preserved` is false, when source-target binding changes, or
when a curve/bundle/halo style is baked into raster images instead of PPT
editable connector shapes.
Validation must also fail when image slots lack local reference crops, local color token ids, or
`reference_style_profile.json` grounding.

## Core Workflow

1. Read the source material first. Extract the research problem, method story,
   inputs/outputs, named components, training/inference flow, datasets, baselines,
   metrics, and main claims before planning any figure.
2. Create a candidate figure inventory. Include only figures that carry paper
   information: method overview, system pipeline, model architecture, data
   construction, main results, ablation, case study, error analysis, or appendix
   figures.
3. Route each figure:
   - **Framework / architecture / pipeline**: use the visual-block workflow in
     `references/visual_framework_figures.md`.
     If the user provides a full reference image first,
     also use `references/reference_image_alignment.md`.
     Before image2 prompting, write a style sheet using
     `references/stylist_stage.md` and a structured program using
     `references/figure_program.md`.
     Then create `reference_slot_prompt_brief.json` and VLM-generated
     `slot_prompt_plan.json`; for image2 visual blocks, use
     `references/image_block_prompting.md` to
     generate slot-level prompts with target aspect ratios and low-blank-space
     requirements.
     Before delivery, run the critic stage in `references/critic_stage.md`.
   - **Data / statistical / result plots**: use `references/data_figures.md`.
   - **Mixed paper figure or multi-panel layout**: combine both routes, then use
     PPTX-first composition for the editable working file.
4. Keep scientific structure editable. Use generated images for visual blocks,
   but add labels, formulas, arrows, panel marks, grouping boxes, legends, and
   captions with editable PPT tools by default.
5. For reference-image-driven framework figures, parameterize the reference image
   first: identify visual slots, estimate each slot's relative bounding box and
   aspect ratio, then generate many small blocks for those slots instead of a few
   large macro-panel images.
6. Run the journal-quality check before final delivery. See
   `references/journal_quality_checklist.md`.

## Required Grounding Rules

- Every framework module name must come from the user's paper or be explicitly
  introduced as an inferred simplification.
- Never insert stock modules such as encoder, retriever, memory, or decoder unless
  the paper actually uses that concept or the user approves the abstraction.
- AI-generated visual blocks may illustrate scientific objects, data flow,
  model components, reasoning stages, or experimental settings, but must not be
  trusted for exact text, formulas, numbers, axes, or citations.
- For data figures, Python remains the source of truth for computation and plots.
  PPT editing is for layout, annotation, panel assembly, and presentation polish,
  not for changing plotted values.
- Keep source artifacts: raw input, extracted figure brief, generated prompts,
  full reference image when provided, original image blocks, enhanced blocks,
  slot inventory, layout plan, style sheet, figure program, asset quality
  report, asset visual review, visual critic report, critic report, alignment
  review notes, editable composition, and final exports.

## Output Policy

Default outputs:

- editable working file: `editable_composition.pptx` by default
- publication export: PDF plus 600 DPI PNG/TIFF by default
- optional SVG/PDF vector export only when the venue, user, or downstream
  Illustrator/Inkscape workflow explicitly needs it
- reproducibility files: Python plotting script and cleaned data for data plots
- prompt record: visual-block prompts and selected/rejected image notes
- for image-rich framework figures: slot inventory, image2 prompts, generated
  assets, asset quality report, asset visual review, contact sheets, style
  sheet, layout plan, figure program, editable composition, visual critic,
  critic report, final export, and alignment review that pass
  `rfs validate` or `scripts/validate_framework_outputs.py` when outputs are
  local

Use `references/paper_to_figure.md` for paper analysis and figure planning. Use
`references/enhancement_pipeline.md` when generated images need upscaling,
sharpening, background removal, or artifact cleanup. Use
`references/reference_image_alignment.md` only when the user supplies a complete
reference framework image as the visual blueprint for the final editable
composition. Do not create a full reference image yourself unless the user
explicitly asks for one. Use `references/stylist_stage.md` to lock style before
prompting. Use `references/figure_program.md` to define the structured
intermediate layout before scripting or composition. Use
`references/image_block_prompting.md` whenever image2 prompts are needed for
framework sub-blocks. Use `references/critic_stage.md` to block final delivery
when the workflow violates the required image-rich, editable, no-crop rules.

