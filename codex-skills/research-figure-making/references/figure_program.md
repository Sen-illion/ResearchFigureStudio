# Figure Program

## Summary

Use `figure_program.json` as the structured intermediate representation for an
image-rich framework figure. It is required before composition or layout
scripting. The program keeps the figure editable and auditable instead of relying
on ad hoc placement code.

## Required File

Write `figure_program.json` in the output directory.

Minimum top-level keys:

- `summary`: one short overview of the program and output route
- `canvas`: size, aspect ratio, units, background, margin, and export scale
- `locator`: locator mode, reference path, and source `layout_plan.json`
- `panels`: macro containers with IDs, paper concepts, bbox, visual role,
  `editable_in: "pptx"`, and editable layer style
- `slots`: image2 asset slots with IDs, parent panel, paper concept,
  `bbox_percent`, `center_percent`, `width_percent`, `height_percent`,
  `aspect_ratio_decimal`, `aspect_ratio_w_h`, `target_canvas_ratio`,
  `target_pixels`, `target_pixels_exact`, `generation_min_pixels`,
  `safe_area_percent`, `fit_policy`,
  `text_policy`, visual density, prompt ID, prompt plan ID, asset ID,
  `target_content_fill_percent`, `min_content_fill_percent`,
  `max_empty_margin_percent`, `composition_type`, `blank_space_policy`,
  `slot_frame_policy`, `visual_spec_id`, `complexity_kind`,
  `foreground_subject`, `secondary_objects`, `micro_details`,
  `background_fill_elements`, `scientific_mechanism_detail`,
  `required_visual_complexity`, `forbidden_simplification`, optional
  `slot_function`, and optional VLM-planned `image_prompt_core`
- `assets`: generated image files with slot ID, selected candidate, source
  prompt, quality status, local reference crop path, local color token IDs, and
  no-crop fit status plus `visual_spec_id`
- `labels`: PPT-editable text objects, including module names, variables,
  captions, panel IDs, and formulas
- `text_program_path`, `reference_text_geometry_path`, and
  `text_alignment_report_path`: required reference-first text-layer artifacts
  used by the PPT compiler
- `text_program`: embedded editable text items derived from
  `reference_text_geometry.json`; each item must bind to a reference text
  region, record bbox/center/relative font height/color, and render as PPTX
  text
- `arrows`: PPT-editable connectors with `source_id`, `target_id`,
  `source_anchor`, `target_anchor`, multi-point `path_percent`,
  `style_token_id`, `semantic_role`, `route_style`, `bundle_id`,
  `line_cap`, `arrowhead_size`, `editable_in: "pptx"`, and
  `render_policy: "ppt_shape_not_image_asset"`; arrows, connector lines,
  dashed loops, and transition arrows must never be generated image assets
- `control_shapes`: measured non-image controls from `reference_controls.json`
- `groups`: PPT-editable visual groupings, lanes, resource libraries, loops, or
  stages
- `export_targets`: must include `editable_composition.pptx` plus final PDF and
  600 DPI PNG/TIFF exports; SVG is optional

## Minimal Shape

```json
{
  "summary": "PPTX-first image-rich framework figure assembled from slot-level image assets.",
  "canvas": {
    "width": 1800,
    "height": 1050,
    "aspect_ratio": 1.714,
    "units": "px",
    "background": "paper_tint"
  },
  "locator": {
    "mode": "vlm_or_heuristic",
    "layout_plan_path": "layout_plan.json",
    "reference_path": "inputs/reference.png"
  },
  "panels": [
    {
      "id": "panel_method_stage",
      "paper_concept": "paper-specific stage name",
      "bbox_percent": {"x": 0.04, "y": 0.12, "w": 0.22, "h": 0.34},
      "editable_in": "pptx"
    }
  ],
  "slots": [
    {
      "id": "slot_scene_card",
      "parent_panel": "panel_method_stage",
      "paper_concept": "paper-specific visual unit",
      "bbox_percent": {"x": 0.06, "y": 0.18, "w": 0.10, "h": 0.12},
      "center_percent": {"x": 0.11, "y": 0.24},
      "width_percent": 0.10,
      "height_percent": 0.12,
      "aspect_ratio_decimal": 1.429,
      "aspect_ratio_w_h": "1.429:1.000",
      "target_canvas_ratio": "1.429:1.000",
      "target_pixels": {"width": 180.000, "height": 126.000},
      "target_pixels_exact": {"width": 180.000, "height": 126.000},
      "generation_min_pixels": {"width": 512, "height": 512},
      "safe_area_percent": 92,
      "fit_policy": "contain",
      "text_policy": "decorative_only",
      "target_content_fill_percent": 93,
      "min_content_fill_percent": 85,
      "max_empty_margin_percent": 10,
      "composition_type": "full_bleed_card",
      "slot_frame_policy": "frameless_slot",
      "blank_space_policy": "minimal_blank_canvas",
      "visual_spec_id": "visual_spec_slot_scene_card",
      "complexity_kind": "pipeline_module",
      "foreground_subject": "dominant local reference object",
      "secondary_objects": ["supporting object", "input-output cue"],
      "micro_details": ["small glyph texture", "internal line detail"],
      "background_fill_elements": ["edge-to-edge local color surface"],
      "scientific_mechanism_detail": "show the operation as a layered mechanism",
      "required_visual_complexity": "dense",
      "forbidden_simplification": ["simple icon", "centered icon", "clean blank background"],
      "slot_function": "what this small image block does in the paper figure",
      "prompt_plan_id": "prompt_plan_slot_scene_card",
      "image_prompt_core": "VLM-planned concrete prompt core for the slot image",
      "reference_crop_path": "reference_slot_crops/slot_scene_card.png",
      "reference_style_profile_path": "reference_style_profile.json",
      "local_color_token_ids": ["slot_scene_card_local_001"],
      "prompt_id": "prompt_scene_card",
      "asset_id": "asset_scene_card"
    }
  ],
  "assets": [
    {
      "id": "asset_scene_card",
      "slot_id": "slot_scene_card",
      "path": "assets/slot_scene_card.png",
      "reference_crop_path": "reference_slot_crops/slot_scene_card.png",
      "visual_spec_id": "visual_spec_slot_scene_card",
      "local_color_token_ids": ["slot_scene_card_local_001"],
      "quality_status": "ok_no_crop"
    }
  ],
  "labels": [],
  "reference_text_geometry_path": "reference_text_geometry.json",
  "text_program_path": "text_program.json",
  "text_alignment_report_path": "text_alignment_report.json",
  "text_program": {
    "summary": "Reference-first editable PPT text program.",
    "items": [
      {
        "id": "text_panel_method_stage",
        "text": "Method Stage",
        "role": "panel_title",
        "target_id": "panel_method_stage",
        "source_reference_text_id": "ref_text_panel_method_stage",
        "reference_binding": "reference_panel_header_geometry",
        "bbox_percent": {"x": 0.04, "y": 0.12, "w": 0.22, "h": 0.05},
        "center_percent": {"x": 0.15, "y": 0.145},
        "estimated_font_ratio": 0.031,
        "font_size_pt": 9.5,
        "color_hex": "#FFFFFF",
        "editable_in": "pptx"
      }
    ]
  },
  "arrows": [
    {
      "id": "AR01",
      "source_id": "slot_scene_card",
      "target_id": "slot_next_card",
      "source_anchor": "right_mid",
      "target_anchor": "left_mid",
      "control_kind": "elbow_connector",
      "path_percent": [[0.16, 0.24], [0.24, 0.24], [0.24, 0.38], [0.32, 0.38]],
      "style_token_id": "arrow_orange_001",
      "semantic_role": "branch",
      "route_style": "bundled_elbow",
      "bundle_id": "from_slot_scene_card",
      "line_cap": "round",
      "arrowhead_size": "sm",
      "reference_locked": true,
      "reference_path_preserved": true,
      "editable_in": "pptx",
      "render_policy": "ppt_shape_not_image_asset"
    }
  ],
  "groups": [],
  "export_targets": [
    {
      "type": "pptx",
      "path": "editable_composition.pptx",
      "role": "main_editable_source"
    },
    {
      "type": "png",
      "path": "final_600dpi.png",
      "dpi": 600,
      "role": "submission_or_review_export"
    },
    {
      "type": "pdf",
      "path": "review.pdf",
      "role": "fixed_layout_review"
    }
  ]
}
```

## Rules

- `slots` must come from the paper brief and, when available, the reference-image
  slot inventory plus `layout_plan.json`.
- `layout_plan.json` owns normalized positions. VLM locators may produce this
  JSON, but must not write arbitrary PPT code or generate a full diagram.
- `labels`, `arrows`, `groups`, panels, formulas, variables, metrics, and panel
  IDs must be marked as PPT editable objects, usually with `editable_in: "pptx"`.
- Text size and location are reference-first. Generate
  `reference_text_geometry.json` and `text_program.json`; do not add a default
  publication-scale font threshold or `paper_double_column` rule that overrides
  the reference image. Readability notes may be written separately, but they do
  not block delivery unless the user explicitly asks for readability-first
  typography.
- `arrows` must originate from `reference_controls.json` when a reference image
  exists. Heuristic arrows are a fallback only. Every arrow must include
  non-empty source/target IDs, source/target anchors, at least two normalized
  `path_percent` points, and a reference color token.
- `arrow_style_profile.json`, `selected_arrow_routes.json`, and
  `arrow_quality_report.json` must be produced before PPT compilation. They may
  soften connector caps, choose widths, assign line bundles, and report
  crossing/bend/overlap quality, but they must preserve reference-locked paths.
  Orthogonal obstacle-aware routing may synthesize paths only when the path is
  missing or the arrow is explicitly marked
  `route_policy=fallback_reroute_allowed`; every route must record
  `routing_algorithm` and `route_generation_status`.
- `--arrow-style-mode aesthetic` is an optional experimental beautification
  pass. It may use curve connectors, halo underlays, and bundle lane offsets
  only for explicitly opted-in routes and only inside the recorded
  `reference_tunnel_percent`. It must keep source and target IDs unchanged and
  record `reference_original_path_percent`,
  `reference_path_delta_max`, and `reference_tunnel_preserved` for every
  adjusted route.
- `assets` must be slot-level blocks, not one full generated diagram. Asset IDs
  and slot IDs must not contain arrow/control semantics such as `arrow`,
  `transition_arrow`, `dashed_arc`, `dashed_arrows`, or `graph_connector`.
- Every slot asset must bind to a local reference crop and
  `reference_style_profile.json` before generation.
- Every normal non-legend slot must bind to `slot_visual_spec.json`, include a
  foreground subject, at least two secondary objects, at least two micro details,
  and forbidden simplifications such as `simple icon`, `centered icon`, and
  `clean blank background`.
- `fit_policy` must not be center-crop, cover-crop, fill-crop, forced crop, or
  crop-to-ratio.
- `composition_type` should be one of `full_frame_icon`, `full_bleed_card`,
  `scene_thumbnail`, or `symbol_cutout`.
- `target_content_fill_percent` should usually be 90-97. The default target is
  93.
- `min_content_fill_percent` should usually be 85 or higher.
- `max_empty_margin_percent` should usually be 10 or lower.
- `target_canvas_ratio` must be a precise decimal ratio from
  `reference_geometry.json`, not a coarse preset.
- `target_pixels` must equal `target_pixels_exact`; use
  `generation_min_pixels` only for minimum generated asset resolution.
- `slot_frame_policy` should default to `frameless_slot`; do not add extra white
  tiles around image assets unless the reference slot explicitly has that frame.
- `blank_space_policy` should explain how the prompt avoids tiny centered
  subjects and large blank borders.
- `export_targets` must include one PPTX target for the main editable source.
  SVG can be added only as an optional export or intermediate.
- A normal paper system figure should have 25-50 non-arrow image slots. Complex
  figures may use 40-50. Arrows, connector lines, dashed loops, panel frames,
  and titles are editable PPT controls and do not count toward this number.

## Use In Composition

The composition script or manual PPT assembly should read this program as the
source of truth for placement. If the final layout changes, update
`figure_program.json` so the program still matches the delivered figure.

