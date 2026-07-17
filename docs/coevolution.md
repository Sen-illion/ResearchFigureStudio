# Whole-Image Creator/Judge Co-Evolution

> This command is an inference-time refinement baseline. It is not the paper's full GenEvolve training algorithm, which requires a tool-orchestrating Qwen3-VL policy, SFT, GRPO, best-worst visual experience extraction, and teacher-only SDL. See `docs/genevolve_reproduction.md`.

`rfs coevolve-image` refines one complete scientific framework image before the existing image-to-editable-PPTX workflow.

## Ground Truth

The input is JSON. Paths are resolved relative to the JSON file.

```json
{
  "paper_path": "paper.pdf",
  "scientific_truth": {
    "figure_goal": "Explain the complete method pipeline.",
    "must_show": ["input", "feature encoder", "reasoning module", "output"],
    "relations": [{"source": "feature encoder", "target": "reasoning module"}],
    "must_not_invent": ["external knowledge base"],
    "terminology": {"Feature Encoder": "Use this exact label"}
  },
  "aesthetic_preferences": {
    "description": "Top-conference academic style, dense but readable, restrained blue and teal palette.",
    "positive_references": ["references/good.png"],
    "negative_references": []
  },
  "weights": {"scientific": 0.5, "aesthetic": 0.35, "visual_quality": 0.15},
  "thresholds": {"total": 0.85, "scientific": 0.9, "aesthetic": 0.8},
  "generation": {"aspect_ratio": "16:9", "language": "English"}
}
```

## Run

```powershell
rfs coevolve-image `
  --ground-truth ground_truth.json `
  --out output\coevolution_run `
  --candidates 3 `
  --repair-candidates 2 `
  --max-rounds 4 `
  --online-judge-model gemini-3-pro-preview-thinking `
  --frozen-judge-model another-independent-vlm `
  --json
```

Set `RFS_IMAGE_EDIT_URL` for an OpenAI-compatible image edit endpoint. Without it, Gemini reference editing is used when `GEMINI_GEN_IMG_URL` is configured; if editing fails, the Creator falls back to complete regeneration with explicit preserve/repair instructions.

The run writes `approved_image.png`, per-round summaries, `preference_pairs.jsonl`, `repair_trajectories.jsonl`, `critique_outcomes.jsonl`, and `run_report.json`. Re-running the same completed output returns the existing report; incomplete runs resume after the last committed round.

It also writes `reproduction_metrics.json` and `reproduction_metrics.md`, which summarize score gains, blocker resolution, candidate acceptance, feedback effectiveness, side effects, and Online/Frozen Judge isolation. Rebuild those metrics for any existing run with:

```powershell
rfs coevolution-report --run output\coevolution_run --json
```
