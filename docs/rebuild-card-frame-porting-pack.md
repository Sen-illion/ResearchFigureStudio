# Summary

This note packages the editable card/frame support introduced by `85bd4c7 Add editable card frame support` so it can be reproduced intentionally from the earlier `codex/back-to-a6e459a` branch.

## Target

- Target branch: `codex/back-to-a6e459a`
- Source commit: `85bd4c77c2f71e02fcf069adecffafc62b12b638`
- Goal: make visible card/frame boundaries editable PowerPoint shapes instead of treating them as generated raster assets or baking them into slot crops.
- Non-goal: do not import the whole generation-plan stack unless Sen-illion explicitly wants it.

The source commit is not a clean standalone cherry-pick onto `a6e459a` because it also touches files that were changed by the later generation-plan commits. Use it as a reference patch and port the card/frame pieces in small commits.

## What The Feature Does

Editable card/frame support adds a separate `program["cards"]` layer. These objects represent visible reference-image containers such as rounded cards, hollow module frames, dashed boxes, and group boundaries.

The important policy is:

- Cards are PPT-native editable shapes.
- Cards are not slots.
- Cards are not assets.
- Slot crops should avoid card strokes when the slot is inside a card.
- Asset prompts must forbid card borders, so image generation does not bake them into raster assets.
- Arrows can bind to cards as source/target objects.
- Validator must fail if a card id is reused as a slot/asset id.

## Source Files In `85bd4c7`

Core implementation:

- `rfs/layout_planner.py`
  - Adds CV detection for hollow frame components.
  - Adds `_find_frame_components(...)`.
  - Excludes detected frames from normal visual component/slot detection.
  - Writes detected frames into layout `cards`.
- `rfs/editable_rebuild.py`
  - Adds `_containing_cards_for_slot(...)`.
  - Adds `_crop_bbox_avoiding_card_strokes(...)`.
  - Adds `containing_card_ids`, `crop_bbox_percent`, and `crop_inset_reason` to asset specs.
  - Updates prompts and forbidden elements so generated assets do not include card borders.
- `rfs/ppt_compiler.py`
  - Adds `_add_card_frame(...)`.
  - Renders `program["cards"]` before arrows and slots as native PPT shapes.
  - Includes rendered cards in `composition_quality_report.json`.
- `rfs/program_builder.py`
  - Preserves `cards` from layout plans into `figure_program.json`.
  - Allows arrows/source-target maps to include cards.
- `rfs/validator.py`
  - Validates cards as editable PPTX items.
  - Fails card-slot/card-asset id collisions.
  - Validates composition cards rendered as native PPT shapes.

Supporting surfaces:

- `rfs/layout_locator.py`
  - Carries card-like objects through VLM/local layout object normalization.
- `rfs/rebuild_preview_renderer.py`
  - Draws card frames in fallback preview renderings.
- `rfs/rebuild_visual_critic.py`
  - Allows controlled patch operations for cards.
- `rfs/rebuild_vlm_adapters.py`
  - Teaches VLM planning prompts that card/frame objects are editable controls, not image slots.
- `rfs/rebuild_vlm_validation.py`
  - Reports card counts and coverage risks.

Tests:

- `tests/test_cards_contract.py`
- `tests/test_ppt_compiler.py`
- `tests/test_rebuild_editable.py`
- `tests/test_rebuild_visual_critic.py`
- `tests/test_validator.py`

## Minimal Porting Plan For `a6e459a`

Port in this order.

1. Program contract
   - Add `cards` to layout/program contracts.
   - Preserve `layout_plan["cards"]` in `build_figure_program(...)`.
   - Update object maps so arrows can bind to card ids.

2. Layout detection
   - Add `_find_frame_components(...)` to `rfs/layout_planner.py`.
   - Call it before `_find_visual_components(...)`.
   - Pass detected cards into `_find_visual_components(..., excluded_frames=cards)` so hollow frames do not become visual slots.
   - Normalize card fields:
     - `id`
     - `bbox_percent`
     - `semantic_role`
     - `shape_kind`
     - `fill_color`
     - `fill_transparency`
     - `stroke_color`
     - `stroke_width_pt`
     - `dash_style`
     - `corner_radius`
     - `editable_in`
     - `render_policy`

3. Asset crop/prompt safety
   - Add `_containing_cards_for_slot(...)`.
   - Add `_crop_bbox_avoiding_card_strokes(...)`.
   - In `_make_asset_specs(...)`, crop from the inset bbox when a slot is inside a card.
   - Add `containing_card_ids`, `crop_bbox_percent`, and `crop_inset_reason` to each relevant asset spec.
   - Add `"card borders"` to forbidden elements and prompt hard constraints.

4. PPT rendering
   - Add `_add_card_frame(...)` to `rfs/ppt_compiler.py`.
   - Render cards after panel backgrounds and before arrows/slots.
   - Use native PowerPoint shape types: rectangle or rounded rectangle.
   - Set transparent fill via `shape.fill.background()` when `fill_transparency >= 1.0`.
   - Write rendered card metadata under `composition_quality_report.json["cards"]`.

5. Validation
   - Validate `figure_program.json["cards"]`.
   - Ensure every card has valid bbox, positive stroke width, stroke color, valid dash style, and `editable_in == "pptx"`.
   - Fail if a card id is also a slot id or asset id.
   - Validate `composition_quality_report.json["cards"]` says `rendered_as == "ppt_native_shape"`.

6. Tests
   - Add a focused `tests/test_cards_contract.py`.
   - Add or update PPT compiler and validator tests for cards.
   - Run the narrow tests first, then full unit tests.

## Avoid Direct Cherry-Pick Unless You Want Dependencies

Directly applying `85bd4c7` on top of `a6e459a` can collide with later generation-plan changes because the commit also modifies:

- `rfs/rebuild_generation_planner.py`
- `tests/test_rebuild_generation_planner.py`
- generation-plan-aware parts of `rfs/editable_rebuild.py`

If you want card/frame support only, manually port the card-specific hunks listed above.

If you want to preserve the exact historical stack, use this order instead:

```powershell
git cherry-pick d247950
git cherry-pick 43862c7
git cherry-pick 85bd4c7
```

That path also imports the later generation-plan behavior, which may be undesirable for front-loaded global planning work.

## Reproduction Commands

Start from a clean worktree:

```powershell
cd D:\ResearchFigureStudio
git worktree add ..\ResearchFigureStudio-a6e-cards codex/back-to-a6e459a
cd ..\ResearchFigureStudio-a6e-cards
git switch -c codex/a6e-card-frames
```

Inspect the source commit:

```powershell
git show --stat 85bd4c7
git show 85bd4c7 -- rfs/layout_planner.py rfs/editable_rebuild.py rfs/ppt_compiler.py rfs/program_builder.py rfs/validator.py
```

After porting the first milestone:

```powershell
python -m compileall -q rfs
python -m unittest tests.test_cards_contract -q
python -m unittest tests.test_ppt_compiler tests.test_rebuild_editable tests.test_validator -q
```

For a small smoke run, manually inject `.env` values first if using API modes. For structural verification without asset spend:

```powershell
rfs rebuild-editable `
  --reference "C:\path\reference.png" `
  --out "output\a6e_card_frame_check" `
  --asset-mode crop `
  --layout-mode hybrid `
  --control-mode hybrid `
  --text-mode ocr `
  --export-preview `
  --json
```

Expected artifacts to inspect:

- `reference_geometry.json`
- `figure_program.json`
- `asset_generation_specs.json`
- `composition_quality_report.json`
- `editable_composition.pptx`

Expected checks:

- `figure_program.json.cards` is present for detected card/frame boundaries.
- `figure_program.json.slots` does not duplicate card ids.
- `asset_generation_specs.json` uses inset crop boxes for slots inside cards.
- `composition_quality_report.json.cards` reports `rendered_as: ppt_native_shape`.
- The final PPTX has editable card shapes, not rasterized card borders.

## Suggested Commit Split

1. Preserve card contract in layout/program.
2. Render card frames in PPT compiler.
3. Prevent card borders from entering slot crops/assets.
4. Add validator and tests.
5. Update docs.

