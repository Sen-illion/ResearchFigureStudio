# ResearchFigureStudio

## Summary

ResearchFigureStudio is a PPTX-first research figure generation pipeline for paper-grounded, reference-guided scientific framework figures. It turns a paper plus a user-provided visual reference image into an editable PowerPoint composition assembled from many slot-level image assets, not one flattened full-diagram bitmap.

The current workflow is optimized for AI/ML/NLP system figures:

- paper-grounded concept extraction
- reference-primary geometry, style, color, and flow alignment
- 25-50 non-arrow image slots
- `slot_visual_spec.json` for dense mini-scene/image-block planning
- AutoFigure-inspired control candidates and overlays for arrow/source-target binding
- reference-preserving arrow styling/routing reports for softer editable PPT connectors
- reference-constrained orthogonal fallback routing for missing or explicitly fallback-allowed connectors
- optional `--arrow-style-mode aesthetic` for reference-tunnel arrow beautification with curve connectors, halo underlays, and explicit opt-in bundle lane offsets
- multi-candidate image generation through placeholder, Gemini, or Yunwu image2-compatible APIs
- deterministic PPTX composition with editable labels, panels, arrows, connectors, and formulas
- optional Presentations-plugin QA for importing/rendering/inspecting the PPTX without mutating it
- strict validation for no single full diagram, no semantic crop, no vector-only fallback, low blank space, and non-trivial image-block complexity

This repository does not include API keys, papers, reference images, generated outputs, or local run artifacts.

## Current Capability Boundary

ResearchFigureStudio is an early engineering prototype. Its current practical
ability is limited to placing many small generated image blocks into precise
PowerPoint positions, then keeping surrounding labels, arrows, panels, formulas,
and grouping elements editable in PPTX.

It does **not** yet solve the harder goal of generating truly publication-grade,
fully editable scientific figures end to end. The image blocks themselves are
still raster assets, not editable scientific vector objects. The system can
produce a PPTX composition that is easier to manually revise, but it should not
be treated as a finished top-tier-paper figure generator.

## Help Wanted

The most important open problem is reliable arrow and connector localization.
The current implementation now has an initial AutoFigure-inspired
`reference_control_candidates.json` plus `slot_overlay.png` /
`reference_control_overlay.png` workflow, plus reference-preserving
`arrow_style_profile.json`, `selected_arrow_routes.json`, and
`arrow_quality_report.json`. It now includes a conservative orthogonal fallback
router for missing or explicitly fallback-allowed connectors. It is still
fragile for complex scientific diagrams: source-target binding, truly curved
routes, dense bundle routing, dashed loops, and preserving reference-image logic
need stronger methods.

If you have experience with vision-language layout parsing, diagram structure
reconstruction, PowerPoint object routing, graph drawing, or editable scientific
figure generation, guidance and contributions are very welcome.

![Current capability vs target capability](docs/assets/current-vs-target.png)

See [CONTRIBUTING.md](CONTRIBUTING.md) and
[docs/help-wanted.md](docs/help-wanted.md) for concrete contribution areas.

## Installation

```powershell
git clone https://github.com/yiweiqin/ResearchFigureStudio.git
cd ResearchFigureStudio
python -m pip install --upgrade pip
python -m pip install -e .
rfs doctor --json
```

Optional local OCR support for reference-derived editable text:

```powershell
python -m pip install -e ".[ocr]"
```

Windows with PowerPoint installed gives the best PPTX/PDF/PNG export path. The Python package itself can still generate and validate most intermediate artifacts without external image APIs when using `--asset-mode placeholder`.

## Offline Smoke Test

Use placeholder assets to validate the local pipeline without calling any API:

```powershell
rfs make-framework `
  --paper "C:\path\paper.pdf" `
  --reference "C:\path\reference.png" `
  --out "output\demo_placeholder" `
  --slot-count 25 `
  --slot-source reference-primary `
  --complexity-profile reference-dense `
  --candidates-per-slot 2 `
  --locator-mode heuristic `
  --control-localizer-mode heuristic `
  --arrow-style-mode reference `
  --prompt-plan-mode heuristic `
  --asset-mode placeholder `
  --asset-workers 4 `
  --asset-review-mode heuristic `
  --critic-mode heuristic `
  --text-extractor-mode ocr `
  --ocr-engine paddle `
  --ocr-lang en_ch `
  --json

rfs validate --out "output\demo_placeholder" --json
```

`output/` is intentionally ignored by Git.

## Real VLM + Image Generation

Set API credentials only through environment variables. Do not write keys into source files.

```powershell
$env:API_BASE='https://yunwu.ai/v1'
$env:API_KEY='<your key>'
$env:GEMINI_API_KEY=$env:API_KEY
$env:GEMINI_GEN_IMG_URL='https://yunwu.ai/v1beta/models/gemini-2.5-flash-image:generateContent'
$env:MODEL_VLM='gemini-3-pro-preview-thinking'
$env:RFS_PROMPT_PLANNER_MODEL=$env:MODEL_VLM
$env:RFS_CONTROL_LOCALIZER_MODEL=$env:MODEL_VLM
$env:RFS_IMAGE_MODEL='image-2'
```

For the reference-only image-to-editable-PPT workflow, configure the same VLM
credentials plus the image-generation endpoint:

```powershell
$env:API_BASE='https://your-openai-compatible-provider/v1'
$env:API_KEY='<your key>'
$env:MODEL_VLM='your-vision-language-model'

# Optional model overrides for rfs rebuild-editable.
$env:RFS_REBUILD_LAYOUT_MODEL=$env:MODEL_VLM
$env:RFS_REBUILD_CONTROL_MODEL=$env:MODEL_VLM
$env:RFS_REBUILD_SEMANTIC_MODEL=$env:MODEL_VLM
$env:RFS_REBUILD_DESIGN_MODEL=$env:MODEL_VLM

# Required only for --asset-mode api slot-level image generation.
$env:GEMINI_API_KEY=$env:API_KEY
$env:GEMINI_GEN_IMG_URL='https://your-provider/v1beta/models/your-image-model:generateContent'
```

Best quality, using VLM layout/control/semantic planning plus generated slot
assets:

```powershell
rfs rebuild-editable `
  --reference "C:\path\figure.png" `
  --out "output\editable_rebuild" `
  --asset-mode api `
  --design-plan-mode vlm `
  --layout-mode hybrid `
  --control-mode hybrid `
  --text-mode ocr `
  --text-grouping-mode hybrid `
  --text-role-mode vlm `
  --text-intelligence-mode vlm `
  --rebuild-critic-mode vlm `
  --rebuild-critic-iterations 2 `
  --export-preview
```

Lower-cost mode, using VLM structure planning but keeping reference crops as
slot assets:

```powershell
rfs rebuild-editable `
  --reference "C:\path\figure.png" `
  --out "output\editable_rebuild_crop" `
  --asset-mode crop `
  --layout-mode hybrid `
  --control-mode hybrid
```

Offline smoke test with no API:

```powershell
rfs rebuild-editable `
  --reference "C:\path\figure.png" `
  --out "output\editable_rebuild_placeholder" `
  --asset-mode placeholder `
  --layout-mode heuristic `
  --control-mode heuristic
```

The rebuild workflow writes `reference_geometry_overlay.png` and
`reference_controls_overlay.png` for inspection. If the automatic layout or
arrows need correction, edit `reference_geometry.json` or
`reference_controls_raw.json`; `reference_controls.json` is the routed
PPT-ready controls contract.

Global design planning writes `reference_logic_plan.json`,
`reference_layer_plan.json`, `reference_generation_plan.json`, and
`reference_flow_graph.json`. The flow graph is a semantic prior for control VLM
arrow binding, while visible arrow pixels and overlays remain the final
reference for editable connector geometry.

Text reconstruction writes raw OCR, grouping, and ownership artifacts:
`reference_text_geometry_raw.json`, `text_grouping_plan.json`,
`text_grouping_report.json`, `ocr_refinement_report.json`,
`ocr_text_corrections.json`, `text_layer_ownership_plan.json`, and
`text_layer_ownership_report.json`. `--text-grouping-mode off|heuristic|vlm|hybrid`
controls whether OCR lines are merged locally or arbitrated by a VLM.

The compiled-preview critic is opt-in through
`--rebuild-critic-mode off|heuristic|vlm` and
`--rebuild-critic-iterations`. VLM critic patches must be concrete JSON updates
to text bbox/font/align/visible/z-index/layer ownership, slot/panel bbox, or
arrow path/style. The critic cannot change text content, write PPT code, or
request crop masking.

Recompile without another API call:

```powershell
rfs rebuild-editable `
  --reference "C:\path\figure.png" `
  --out "output\editable_rebuild" `
  --compile-only
```

To validate whether VLM planning is improving a given reference image, run the
paired evaluator. It creates `case_heuristic`, global-planning cases, and
`case_vlm` outputs under the same directory and defaults to `--asset-mode crop`
so it does not spend image generation credits:

```powershell
rfs rebuild-editable-eval `
  --reference "C:\path\figure.png" `
  --out "output\editable_rebuild_eval" `
  --asset-mode crop `
  --export-preview
```

Review `rebuild_vlm_eval_summary.json`,
`case_heuristic/reference_geometry_overlay.png`, and
`case_vlm/reference_geometry_overlay.png` before running a full
`--asset-mode api` rebuild. Each rebuild also writes
`rebuild_vlm_validation_report.json` with layout/control/semantic validation
counts, fallback status, and API request counts.

Recommended real run:

```powershell
rfs make-framework `
  --paper "C:\path\paper.pdf" `
  --reference "C:\path\reference.png" `
  --out "output\paper_reference_image2" `
  --slot-count 40 `
  --slot-source reference-primary `
  --complexity-profile reference-dense `
  --candidates-per-slot 4 `
  --locator-mode vlm `
  --control-localizer-mode hybrid `
  --arrow-style-mode reference `
  --prompt-plan-mode vlm `
  --prompt-plan-workers 8 `
  --asset-mode image2 `
  --asset-workers 6 `
  --asset-retries 3 `
  --asset-review-mode heuristic `
  --critic-mode heuristic `
  --text-extractor-mode ocr `
  --ocr-engine paddle `
  --ocr-lang en_ch `
  --json
```

Use lower worker counts if your API provider rate-limits requests.

## Workflow

```text
input archive -> paper brief -> reference_geometry.json/reference_control_candidates.json ->
slot_overlay.png/reference_control_overlay.png -> reference_controls.json ->
arrow_style_profile.json/selected_arrow_routes.json/arrow_quality_report.json ->
reference_style_profile.json/style_sheet.md -> layout_plan.json -> figure_program.json ->
slot_visual_spec.json -> reference_slot_prompt_brief.json -> slot_prompt_plan.json ->
multi-candidate slot assets -> asset_quality_report.json -> asset_complexity_report.json ->
asset_visual_review.json/contact sheets -> editable_composition.pptx -> PDF/PNG export ->
visual_critic_iter_0.json -> critic_report.md -> validation
```

Optional Presentations-plugin QA can run after validation:

```text
editable_composition.pptx -> rfs presentations-qa -> presentations_plugin_qa_report.json/.md
```

Optional whole-image Creator/Judge refinement can run before conversion:

```text
structured Ground Truth -> Creator Agent candidates -> Online Judge repair feedback ->
Frozen Judge acceptance -> approved_image.png -> existing editable PPTX workflow
```

See [docs/coevolution.md](docs/coevolution.md) for the `rfs coevolve-image` command and Ground Truth contract.
The long-term data, training, evaluation, rollout, and Creator-coordination plan is maintained in [docs/judge_model_training_roadmap.md](docs/judge_model_training_roadmap.md).
User content hierarchy, emphasis, aesthetic, reference-image, and A/B preference criteria can be collected with [docs/aesthetic_ground_truth_questionnaire.md](docs/aesthetic_ground_truth_questionnaire.md).

Key rules:

- The reference image is the source of truth for layout, local visual object choice, color, visual rhythm, and arrow logic when `--slot-source reference-primary` is used.
- The paper provides scientific terminology and concept mapping; it should not override the reference image into a generic template.
- Arrows, connector lines, dashed loops, panel frames, labels, formulas, and critical text are PPT editable objects, not image assets.
- Arrow/control localization is reference-driven: CV detects candidates, overlays label them, optional VLM binding assigns source/target semantics, and the PPT compiler renders editable connectors.
- Arrow styling is reference-preserving: it may soften line caps, assign bundle IDs, vary widths/dashes, and report aesthetics, but it must not replace reference-image flow logic with a generic router.
- Obstacle-aware routing is fallback-only: it may synthesize orthogonal paths for missing routes or `route_policy=fallback_reroute_allowed`, but it must not rewrite reference-locked paths.
- Aesthetic mode is experimental: `--arrow-style-mode aesthetic` may offset reference-locked arrows only when the route explicitly opts in, only within `reference_tunnel_percent`; it records the original path and must keep `reference_tunnel_preserved=true`.
- Normal non-legend slots should be dense mini scientific scenes/cards with layered objects and micro-details, not simple centered icons.
- Generated images are inserted with no semantic cropping.
- The Presentations plugin is QA-only in this project. It can import/render a PPTX, extract layout JSON, and expose renderer/font/connector drift, but RFS remains the authoritative compiler for reference-locked geometry and connector-heavy figures.

Optional arrow-beautification pass:

```powershell
rfs make-framework `
  --paper "C:\path\paper.pdf" `
  --reference "C:\path\reference.png" `
  --out D:\ResearchFigureStudio\output\aesthetic_experiment `
  --slot-count 40 `
  --slot-source reference-primary `
  --control-localizer-mode hybrid `
  --arrow-style-mode aesthetic `
  --prompt-plan-mode vlm `
  --asset-mode image2
```

For publication-safe comparison, keep both `--arrow-style-mode reference` and
`--arrow-style-mode aesthetic` outputs. Use the aesthetic version only when the
small reference-tunnel deviations improve readability without changing the
reference image's flow logic.

Optional Presentations-plugin QA for an existing output:

```powershell
rfs presentations-qa `
  --out "output\paper_reference_image2" `
  --scale 2 `
  --json
```

Optional QA during a new run:

```powershell
rfs make-framework `
  --paper "C:\path\paper.pdf" `
  --reference "C:\path\reference.png" `
  --out "output\paper_reference_image2" `
  --slot-source reference-primary `
  --asset-mode image2 `
  --presentations-qa `
  --json
```

If the plugin reports `autoRouteConnectorPx failed`, treat that as a QA signal,
not as a reason to let the plugin rewrite the figure. The PPTX generated by RFS
remains the source of truth.

## Output Contract

A valid image-rich framework run should include:

- `input_manifest.json`
- `paper_brief.md` / `paper_brief.json`
- `reference_geometry.json`
- `reference_control_candidates.json`
- `slot_overlay.png`
- `reference_control_overlay.png`
- `reference_controls.json`
- `reference_text_geometry.json`
- `text_program.json`
- `ocr_text_quality_report.json`
- `text_alignment_report.json`
- `arrow_style_profile.json`
- `selected_arrow_routes.json`
- `arrow_quality_report.json`
- `reference_style_profile.json`
- `style_sheet.md`
- `layout_plan.json`
- `figure_program.json`
- `slot_visual_spec.json`
- `reference_slot_prompt_brief.json`
- `slot_prompt_plan.json`
- `prompts.md`
- `reference_slot_crops/<slot_id>.png`
- `assets/*.png` with at least 25 selected non-arrow image assets
- `asset_candidates/*/candidate_*.png`
- `asset_quality_report.json`
- `asset_complexity_report.json`
- `asset_visual_review.json`
- `asset_contact_sheet.png`
- `asset_candidate_contact_sheet.png`
- `editable_composition.pptx`
- `review.pdf` and `final_600dpi.png` when local export is available
- `visual_critic_iter_0.json`
- `alignment_review.md`
- `critic_report.md`

Optional QA outputs:

- `presentations_plugin_qa_report.json`
- `presentations_plugin_qa_report.md`
- `presentations_plugin_qa_workspace/` when using the default workspace

Run validation:

```powershell
rfs validate --out "output\paper_reference_image2" --json
python codex-skills\research-figure-making\scripts\validate_framework_outputs.py "output\paper_reference_image2"
```

## Codex Skill

This repository includes the Codex skill under:

```text
codex-skills/research-figure-making
```

To install it locally into Codex:

```powershell
$dst = Join-Path $env:USERPROFILE ".codex\skills\research-figure-making"
if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
Copy-Item -Recurse "codex-skills\research-figure-making" $dst
```

The skill documents the full research-figure workflow and includes the standalone framework-output validator.

## Development

```powershell
python -m compileall -q rfs
python -m unittest discover -s tests -q
python -m py_compile codex-skills\research-figure-making\scripts\validate_framework_outputs.py
```

## Repository Hygiene

Do not commit:

- `output/`
- papers, manuscripts, private datasets, or user reference images
- generated PPTX/PDF/PNG/JPG/SVG assets
- `.env` files or API keys
- cache folders such as `__pycache__/` or `*.egg-info/`

## License

MIT License. See [LICENSE](LICENSE).
