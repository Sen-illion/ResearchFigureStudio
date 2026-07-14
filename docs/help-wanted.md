# Help Wanted: Reference-Guided Editable PPT Scientific Figures

## Summary

ResearchFigureStudio is trying to turn a paper plus a reference image into an editable PowerPoint scientific framework figure. The current prototype can place many small generated image blocks into PPT positions and keep surrounding structure editable, but it does not yet solve true publication-grade editable scientific figure generation.

![Current capability vs target capability](assets/current-vs-target.png)

## What Works Today

- Read a paper and reference image.
- Build structured intermediate files such as `reference_geometry.json`, `layout_plan.json`, and `figure_program.json`.
- Generate 25-50 non-arrow image slots.
- Insert selected raster image blocks into an editable PPTX.
- Keep labels, panels, arrows, connectors, formulas, and grouping boxes as editable PPT objects.
- Validate no single full-diagram image, no vector-only fallback, no semantic crop, and basic asset quality.

## Current Limitation

The current system is best described as **reference-guided PPT positioning for small image blocks**, not a complete scientific figure generator.

The image blocks are still raster assets. They are easier to reposition and replace in PPT, but they are not editable vector scientific objects. The final figure still requires human review and manual polishing before serious paper submission.

## Main Technical Problem

The highest-priority unsolved problem is **arrow and connector localization**.

Complex scientific diagrams often depend on arrows, dashed loops, feedback paths, cross-panel connectors, and multi-step routing. We need better methods to:

- detect arrows and connectors from a reference image
- infer source and target objects
- distinguish arrows from decorative shapes or image slots
- recover multi-segment routes and dashed loops
- avoid overlapping generated connectors with important visual content
- represent the result as editable PPT objects
- validate that the final PPT connector still matches the reference logic

## Why This Is Hard

A reference image may contain:

- dense panels and nested cards
- arrows crossing between modules
- loops and return paths
- small arrowheads or curved connectors
- overlapping text and shapes
- raster screenshots with no object metadata

A VLM can often describe the diagram, but it may not return stable geometry or source-target bindings. A pure CV detector can find lines, but often misses semantic direction and graph structure. We likely need a hybrid method.

## Contributions We Need

We welcome help on:

- VLM-based diagram layout parsing
- arrow/source-target graph reconstruction
- PPT connector routing algorithms
- synthetic benchmarks for connector localization
- evaluation metrics for reference-vs-PPT diagram structure
- robust JSON schemas for arrows, loops, controls, and editable PPT objects

## Relevant Files

- `rfs/reference_analyzer.py`
- `rfs/layout_locator.py`
- `rfs/program_builder.py`
- `rfs/ppt_compiler.py`
- `rfs/visual_critic.py`
- `rfs/validator.py`
- `codex-skills/research-figure-making/references/reference_image_alignment.md`
- `codex-skills/research-figure-making/references/figure_program.md`

## Desired End State

A user should be able to provide:

1. a research paper or method section
2. a visual reference figure
3. optional style constraints

The system should output:

1. an editable PPTX
2. editable arrows and connectors
3. editable labels and formulas
4. replaceable image blocks
5. machine-readable layout/graph JSON
6. validation reports that identify mismatches before delivery

The immediate goal is not to replace expert designers. The goal is to make AI-assisted scientific figure drafting substantially more structured, inspectable, and editable.
