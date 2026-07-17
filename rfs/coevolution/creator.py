from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .providers import ImageProvider


class CreatorAgent:
    def __init__(self, provider: ImageProvider):
        self.provider = provider

    def design_plan(self, ground_truth: dict, feedback: dict | None = None) -> dict:
        scientific = ground_truth["scientific_truth"]
        aesthetics = ground_truth["aesthetic_preferences"]
        return {
            "figure_goal": scientific.get("figure_goal") or scientific.get("goal") or "Explain the paper method clearly",
            "must_show": scientific.get("must_show", []),
            "relations": scientific.get("relations", []),
            "must_not_invent": scientific.get("must_not_invent", []),
            "terminology": scientific.get("terminology", {}),
            "aesthetic_preferences": aesthetics,
            "preserve": (feedback or {}).get("preserve", []),
            "repair": (feedback or {}).get("repair", []),
        }

    def build_prompt(self, ground_truth: dict, plan: dict, variant: int, repair_round: bool) -> str:
        mode = "Revise the supplied previous figure" if repair_round else "Create a complete new figure"
        return "\n".join([
            "You are the Creator Agent for a publication-quality scientific framework figure.",
            f"{mode} as one complete raster image, not separate assets.",
            f"Candidate variant: {variant}.",
            f"Target aspect ratio: {ground_truth['generation']['aspect_ratio']}.",
            f"Text language: {ground_truth['generation']['language']}.",
            "Scientific truth and human aesthetic preferences are equally binding according to their configured weights.",
            "Never invent modules, relations, datasets, formulas, or results that are absent from scientific_truth.",
            "Render a coherent academic architecture figure with readable hierarchy, meaningful arrows, and consistent visual grammar.",
            "Design plan JSON:",
            json.dumps(plan, ensure_ascii=False, indent=2),
            "Keep every item in preserve visually and semantically stable.",
            "Execute every repair instruction while avoiding regressions elsewhere.",
        ])

    def generate_candidates(
        self,
        ground_truth: dict,
        round_dir: Path,
        count: int,
        feedback: dict | None = None,
        source_image: str | Path | None = None,
    ) -> tuple[list[dict], dict]:
        plan = self.design_plan(ground_truth, feedback=feedback)
        round_dir.mkdir(parents=True, exist_ok=True)
        (round_dir / "design_plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
        candidates = []
        failures = []
        for index in range(1, count + 1):
            candidate_id = f"candidate_{index:02d}"
            path = round_dir / f"{candidate_id}.png"
            prompt_path = round_dir / f"{candidate_id}_prompt.txt"
            prompt = self.build_prompt(ground_truth, plan, index, repair_round=source_image is not None)
            if path.exists() and path.stat().st_size > 0 and prompt_path.exists():
                candidates.append({
                    "candidate_id": candidate_id,
                    "path": str(path),
                    "generation": {"mode": "resume_existing", "model": "previous_attempt"},
                    "prompt_path": str(prompt_path),
                })
                continue
            prompt_path.write_text(prompt, encoding="utf-8")
            metadata: dict[str, Any]
            try:
                if source_image is not None and self.provider.supports_edit:
                    try:
                        metadata = self.provider.edit(Path(source_image), prompt, path, ground_truth["generation"]["aspect_ratio"])
                    except Exception as edit_exc:
                        metadata = self.provider.generate(prompt, path, ground_truth["generation"]["aspect_ratio"])
                        metadata["edit_fallback_error"] = str(edit_exc)
                        metadata["mode"] = "generate_fallback"
                else:
                    metadata = self.provider.generate(prompt, path, ground_truth["generation"]["aspect_ratio"])
                candidates.append({"candidate_id": candidate_id, "path": str(path), "generation": metadata, "prompt_path": str(prompt_path)})
            except Exception as exc:
                failures.append({"candidate_id": candidate_id, "error": str(exc)})
        if not candidates:
            raise RuntimeError(f"All image candidates failed: {failures}")
        return candidates, {"plan": plan, "failures": failures}
