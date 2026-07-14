# Contributing to ResearchFigureStudio

## Summary

ResearchFigureStudio is an early-stage research engineering prototype. The most useful contributions right now are not cosmetic changes, but improvements to reference-guided layout parsing, editable PowerPoint object routing, and reliable evaluation of generated figure structure.

## Current Scope

The project currently focuses on:

- converting a paper plus a visual reference image into a structured figure program
- positioning many small raster image blocks inside an editable PPTX
- keeping labels, arrows, panels, formulas, and grouping objects editable in PowerPoint
- validating that the output is not a single flattened full-diagram image

The project does not yet generate fully editable, publication-grade scientific figures end to end. Generated image blocks are still raster assets.

## High-Impact Contribution Areas

The most important open area is arrow and connector localization:

- parse arrows, dashed loops, and multi-segment connectors from a reference image
- infer source-target relationships between slots and panels
- route PPT connectors without crossing important content
- preserve reference-image flow logic in `reference_controls.json` and `figure_program.json`
- evaluate whether generated arrows are editable and semantically correct

Other useful areas:

- VLM layout parsing for dense scientific diagrams
- diagram structure reconstruction into JSON
- better visual complexity scoring for generated slot images
- PPTX object generation and post-editability checks
- benchmark cases for paper/reference-image-to-PPT workflows

## Development Setup

```powershell
git clone https://github.com/yiweiqin/ResearchFigureStudio.git
cd ResearchFigureStudio
python -m pip install -e .
python -m compileall -q rfs
python -m unittest discover -s tests -q
```

## Before Opening a Pull Request

Please run:

```powershell
python -m compileall -q rfs
python -m unittest discover -s tests -q
python -m py_compile codex-skills\research-figure-making\scripts\validate_framework_outputs.py
```

Do not commit:

- API keys or `.env` files
- private papers, manuscripts, datasets, or user reference images
- generated `output/` artifacts
- generated PPTX/PDF/PNG/JPG/SVG files unless explicitly discussed

## Useful PR Format

Please describe:

- what problem you are solving
- which JSON contract or PPT behavior changes
- how you tested the change
- whether it affects existing outputs or validation rules

For arrow/connector work, include a small reference image or synthetic test case when possible.
