# Summary

ResearchFigureStudio is organized as a small deterministic pipeline, not a patched copy of LiveFigure. The borrowed ideas are reference-image-based positioning and AutoFigure-style structured control localization: the system writes overlay/candidate JSON for visual elements, then renders editable PPT objects from deterministic programs.

## Architecture

```text
Input Loader
  -> Paper Analyzer
  -> Reference Analyzer
  -> Control Localizer
  -> Arrow Stylist/Router
  -> Stylist
  -> Layout Locator
  -> Figure Program Builder
  -> Prompt Planner
  -> Asset Generator
  -> Asset Reviewer
  -> PPT Compiler
  -> Exporter
  -> Visual Critic
  -> Validator
```

## Modules

- `rfs/input_archive.py`: copies paper and reference into `out/inputs/` and writes `input_manifest.json`.
- `rfs/input_loader.py`: extracts text from source documents.
- `rfs/paper_analyzer.py`: creates paper-grounded figure brief.
- `rfs/reference_analyzer.py`: creates 25-50 non-arrow slot inventory from the reference image geometry and paper figure goal; it also detects arrow/control candidates, writes overlays, and emits `reference_control_candidates.json` / `reference_controls.json`.
- `rfs/arrow_router.py`: assigns reference-preserving arrow aesthetics, bundle metadata, line softness, and route QA reports without changing reference-image flow logic. It also provides reference-constrained orthogonal fallback routing for missing or explicitly fallback-allowed connectors only. In aesthetic mode it records original paths and applies reference-tunnel bundle offsets only for explicitly opted-in routes.
- `rfs/stylist.py`: writes the style sheet before image prompting.
- `rfs/layout_locator.py`: creates `layout_plan.json`; heuristic mode is local, VLM mode returns JSON coordinates only.
- `rfs/program_builder.py`: creates `figure_program.json`, the single source for PPT compilation, preserving control source/target anchors and normalized routes from `reference_controls.json`.
- `rfs/prompt_planner.py`: creates `reference_slot_prompt_brief.json` and `slot_prompt_plan.json`; default VLM mode inspects the full reference image plus local slot crops and writes `image_prompt_core` for each slot. Per-slot calls can run in parallel via `--prompt-plan-workers`.
- `rfs/asset_generator.py`: generates 1-5 candidates per slot, selects the best block, and writes contact sheets and QA metrics.
- `rfs/asset_reviewer.py`: performs heuristic or VLM visual review of selected assets.
- `rfs/ppt_compiler.py`: renders editable PPTX from `figure_program.json` with contain-fit images and editable labels/arrows/groups; multi-segment arrows and dashed loops are rendered as PPT connector shapes, not image assets.
- `rfs/exporter.py`: exports PDF/PNG where local tooling supports it.
- `rfs/visual_critic.py`: compares reference and final render; VLM mode can propose JSON coordinate corrections and arrow-only patches without rewriting the whole figure.
- `rfs/validator.py`: blocks delivery when required artifacts or hard constraints are missing.

## Non-Goals

- Do not import LiveFigure as a dependency.
- Do not let a VLM write arbitrary PowerPoint code.
- Do not generate a single full architecture image and crop it into pieces.
- Do not make SVG the main editing source.
- Do not bake critical scientific text, formulas, arrows, or labels into image blocks.
- Do not count arrows, connector lines, dashed loops, or transition symbols as generated image slots.

## Data Contracts

- `slot_inventory.json`: paper concept plus candidate slot metadata.
- `reference_control_candidates.json`: AutoFigure-inspired boxlib-like candidate list for arrows, connectors, loops, and branch routes.
- `slot_overlay.png`: visual overlay of detected slot IDs for human/VLM binding.
- `reference_control_overlay.png`: visual overlay of control candidate IDs such as `AR01`.
- `reference_controls.json`: bound editable PPT controls with `source_id`, `target_id`, anchors, path, style token, and render policy.
- `arrow_style_profile.json`: reference-first arrow style rules, fallback routing policy, and routing algorithm metadata for main flow, branch, convergence, feedback loops, and module flow.
- `selected_arrow_routes.json`: selected route/style assignments, bundle IDs, lane indices, reference-lock status, route generation status, and routing algorithm.
- `arrow_quality_report.json`: crossing, bend, obstacle-overlap, and aesthetic-score diagnostics for PPT connectors.
- `composition_quality_report.json`: records PPT arrow connector type, halo usage, route style, and editability alongside slot composition checks.
- `layout_plan.json`: normalized positions, panels, arrows, and z order.
- `figure_program.json`: final composition program consumed by the PPT compiler.
- `reference_slot_prompt_brief.json`: per-slot paper concept, local reference role, geometry, and function briefing sent before prompt planning.
- `slot_prompt_plan.json`: VLM-generated per-slot prompt plan, including `image_prompt_core`, `must_show`, and `avoid_showing`.
- `asset_quality_report.json`: fill/margin/ratio/cutoff/candidate-selection metrics.
- `asset_visual_review.json`: semantic and visual review of selected image blocks.
- `visual_critic_iter_*.json`: reference alignment and optional coordinate correction proposals.
