# Summary

The workflow is designed to keep scientific content, layout, image generation, and PPT editability separated. This prevents the project from becoming a fragile script pile where coordinates, prompts, and rendered assets are mixed together.

## Full Workflow

1. Archive the paper and reference image into the output directory.
2. Extract the paper brief: title, method story, named modules, variables, and figure goal.
3. Analyze the reference image and create 25-50 non-arrow image slot targets.
4. Detect arrow/control candidates, write `reference_control_candidates.json`, and render `slot_overlay.png` plus `reference_control_overlay.png` for review or VLM binding.
5. Bind controls to source/target slots with `--control-localizer-mode hybrid` when API access exists, or deterministic heuristic fallback otherwise.
6. Create `arrow_style_profile.json`, `selected_arrow_routes.json`, and `arrow_quality_report.json`; this stage may soften and classify arrows, and may use orthogonal obstacle-aware fallback routing only for missing or explicitly fallback-allowed paths. In `--arrow-style-mode aesthetic`, it may apply curve connectors and halo underlays by default; bundle lane offsets require explicit route opt-in and must stay inside the recorded reference tunnel. It must preserve reference-image flow logic.
7. Create the style sheet before any image prompt is written.
8. Create `layout_plan.json`; use VLM only for normalized coordinate estimation when enabled.
9. Create `figure_program.json`; this is the only layout source for the PPT compiler.
10. Write `reference_slot_prompt_brief.json`; it records what each local reference slot does and what paper concept it carries.
11. Write `slot_prompt_plan.json`; default `--prompt-plan-mode vlm` calls the model for each slot and produces `image_prompt_core`. Use `--prompt-plan-workers` to run these per-slot VLM calls in parallel.
12. Generate multiple image candidates per slot from the model-planned prompt core.
13. Select assets by fill, margin, ratio, and cutoff metrics; never use semantic cropping.
14. Review selected assets with heuristic or VLM review.
15. Compile `editable_composition.pptx` deterministically from the figure program.
16. Export PDF/PNG for review where possible.
17. Run visual critic against the reference image and rendered output.
18. Write alignment review and critic report.
19. Run `rfs validate` before delivery.

## Recommended Development Runs

Offline engineering check:

```powershell
rfs make-framework --paper "C:\path\paper.pdf" --reference "C:\path\reference.png" --out D:\ResearchFigureStudio\output\offline_check --asset-mode placeholder --locator-mode heuristic --control-localizer-mode heuristic --arrow-style-mode reference --prompt-plan-mode heuristic --slot-count 36 --candidates-per-slot 3 --asset-review-mode heuristic --critic-mode heuristic --json
rfs validate --out D:\ResearchFigureStudio\output\offline_check --json
```

Small real image check:

```powershell
rfs make-framework --paper "C:\path\paper.pdf" --reference "C:\path\reference.png" --out D:\ResearchFigureStudio\output\real_small --asset-mode gemini --asset-workers 3 --asset-retries 2 --locator-mode vlm --control-localizer-mode hybrid --arrow-style-mode reference --prompt-plan-mode vlm --prompt-plan-workers 4 --slot-count 25 --candidates-per-slot 1 --asset-review-mode heuristic --critic-mode heuristic --json
```

Full quality run:

```powershell
rfs make-framework --paper "C:\path\paper.pdf" --reference "C:\path\reference.png" --out D:\ResearchFigureStudio\output\full_quality --asset-mode gemini --asset-workers 4 --asset-retries 2 --locator-mode vlm --control-localizer-mode hybrid --arrow-style-mode reference --prompt-plan-mode vlm --prompt-plan-workers 4 --slot-count 36 --candidates-per-slot 3 --asset-review-mode vlm --critic-mode vlm --critic-iterations 1 --json
```

## Parallel Asset Generation

- `--prompt-plan-workers` controls concurrent VLM calls for per-slot prompt planning. Use 4 by default; raise carefully if Yunwu rate limits allow it.
- `--asset-workers` controls concurrent candidate image requests. Use 3-4 for the first Yunwu/Gemini run.
- `--asset-retries` controls retries per candidate. Retry handles transient 429, 5xx, and timeout failures.
- Candidate failures are recorded as rejected candidates. A slot only blocks the run when all of its candidates fail.
- The pipeline does not silently switch to placeholder mode when Gemini fails.

## Failure Policy

Validation should fail if any of these occur:

- fewer than 25 selected slot assets
- missing PPTX main editable source
- missing `layout_plan.json`, `figure_program.json`, `reference_slot_prompt_brief.json`, or `slot_prompt_plan.json`
- missing `reference_control_candidates.json`, `slot_overlay.png`, or `reference_control_overlay.png`
- missing `arrow_style_profile.json`, `selected_arrow_routes.json`, or `arrow_quality_report.json`
- arrow/control objects with empty `source_id`, `target_id`, anchors, or fewer than two `path_percent` points
- missing asset review or visual critic output
- single full diagram image used as the final figure
- vector-only or SVG-only fallback for image-rich requests
- semantic cropping, cover-crop, or crop-to-ratio
- asset fill below 80% or empty margin above 12%
- critical labels or formulas baked into generated images
- arrows, connectors, transitions, or dashed loops baked into generated image assets instead of editable PPT connector shapes
- arrow styling/routing that overrides reference-locked paths without an explicit documented reason
- fallback obstacle routing applied to a reference-locked path
- aesthetic tunnel routing where `reference_tunnel_preserved` is false
