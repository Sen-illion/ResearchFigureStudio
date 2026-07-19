from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from ..utils import ensure_dir, write_json, write_text
from .analyzer import parse_paper
from .generator import generate_and_select
from .planner import compile_image_prompt, merge_preferences, plan_paper_image, validate_plan_grounding
from .review import build_paper_review, detect_domain_profile, validate_review_coverage
from .templates import build_template_profiles, render_layout_blueprint, select_template


def _load_preferences(path: str | Path | None) -> dict:
    if not path:
        return {}
    source = Path(path).resolve()
    if not source.exists():
        raise FileNotFoundError(f"Preferences file does not exist: {source}")
    raw = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Preferences file must contain a JSON object")
    return raw


def _archive_file(source: str | Path, target_dir: Path, target_name: str | None = None) -> str:
    path = Path(source).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Input file does not exist: {path}")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / (target_name or path.name)
    shutil.copyfile(path, target)
    return str(target)


def run_paper_to_image(
    paper: str | Path,
    out: str | Path,
    preferences_path: str | Path | None = None,
    positive_references: list[str] | None = None,
    negative_references: list[str] | None = None,
    planner_mode: str = "vlm",
    planner_model: str | None = None,
    asset_mode: str = "image2",
    candidates: int = 3,
    aspect_ratio: str | None = None,
    language: str | None = None,
    image_model: str | None = None,
    image_retries: int = 2,
    review_mode: str = "heuristic",
    review_model: str | None = None,
    domain_profile: str = "auto",
    template: str = "auto",
    repair_rounds: int = 1,
    ocr_engine: str = "auto",
    ocr_lang: str = "en_ch",
    ocr_adapter=None,
    critic_adapter=None,
) -> dict:
    started = time.time()
    root = ensure_dir(out).resolve()
    inputs = ensure_dir(root / "inputs")
    positive_dir = ensure_dir(inputs / "positive_references")
    negative_dir = ensure_dir(inputs / "negative_references")

    archived_paper = _archive_file(paper, inputs, f"paper{Path(paper).suffix.lower()}")
    archived_positive = [_archive_file(path, positive_dir) for path in (positive_references or [])]
    archived_negative = [_archive_file(path, negative_dir) for path in (negative_references or [])]
    raw_preferences = _load_preferences(preferences_path)
    preferences = merge_preferences(raw_preferences, aspect_ratio=aspect_ratio, language=language)
    preferences["positive_references"] = archived_positive
    preferences["negative_references"] = archived_negative
    write_json(root / "preferences.json", preferences)
    input_manifest = {
        "summary": "Archived inputs for the paper-to-image run.",
        "paper_original": str(Path(paper).resolve()),
        "paper_archived": archived_paper,
        "preferences_original": str(Path(preferences_path).resolve()) if preferences_path else None,
        "positive_references": archived_positive,
        "negative_references": archived_negative,
    }
    write_json(root / "input_manifest.json", input_manifest)

    parsed = parse_paper(archived_paper)
    evidence_map = {
        "summary": "Page-aware evidence map used by paper summary and figure planning.",
        "source_path": parsed["source_path"],
        "page_count": parsed["page_count"],
        "char_count": parsed["char_count"],
        "headings": parsed["headings"],
        "evidence": parsed["evidence"],
    }
    write_json(root / "evidence_map.json", evidence_map)
    write_json(root / "document_index.json", parsed["document_index"])

    selected_domain = detect_domain_profile(parsed, explicit=domain_profile)
    write_json(root / "domain_profile.json", selected_domain)
    paper_review, review_metadata = build_paper_review(parsed, selected_domain, mode=planner_mode, model=planner_model)
    write_text(root / "prompts" / "paper_review_prompt.txt", review_metadata.pop("prompt"))
    write_json(root / "paper_review_metadata.json", review_metadata)
    write_json(root / "paper_review.json", paper_review)
    production_mode = asset_mode == "image2"
    coverage = validate_review_coverage(paper_review, parsed, selected_domain, strict=production_mode)
    write_json(root / "review_coverage_report.json", coverage)
    if production_mode and review_metadata.get("mode") != "vlm":
        raise RuntimeError("Production Image2 generation requires successful VLM paper review")
    if not coverage["ok"]:
        raise ValueError(f"Paper review failed coverage validation: {coverage['errors']}")

    template_profiles = build_template_profiles(archived_positive, root / "template_profiles", mode=planner_mode, model=planner_model)
    selected_template = select_template(template_profiles, paper_review, requested=template, target_ratio=str(preferences.get("aspect_ratio") or "auto"))
    if str(preferences.get("aspect_ratio") or "auto") == "auto":
        ratio = float(selected_template.get("source_aspect_ratio") or selected_template.get("aspect_ratio") or 16 / 9)
        preferences["aspect_ratio"] = f"{ratio:.3f}:1.000"
        write_json(root / "preferences.json", preferences)
    write_json(root / "selected_template.json", {"summary": "Automatically or explicitly selected content-free architecture template.", **selected_template})
    blueprint_report = render_layout_blueprint(selected_template, root / "layout_blueprint.png", target_ratio=preferences["aspect_ratio"])
    write_json(root / "layout_blueprint.json", blueprint_report)

    references = archived_positive + archived_negative
    plan, planner_metadata = plan_paper_image(
        parsed,
        preferences,
        mode=planner_mode,
        model=planner_model,
        reference_images=references,
        paper_review=paper_review,
    )
    write_text(root / "prompts" / "planning_prompt.txt", planner_metadata.pop("prompt"))
    write_json(root / "planning_metadata.json", {"summary": "Planner execution metadata.", **planner_metadata})
    artifact_names = ["paper_summary", "figure_specification", "design_plan", "layout_intent", "visual_metaphors", "style_plan"]
    for name in artifact_names:
        write_json(root / f"{name}.json", plan[name])
    plan["style_plan"]["selected_template_id"] = selected_template.get("profile_id")
    plan["style_plan"]["template_style"] = selected_template.get("style", {})
    plan["style_plan"]["template_palette"] = selected_template.get("palette", [])
    write_json(root / "style_plan.json", plan["style_plan"])
    planning_validation = validate_plan_grounding(plan, parsed)
    write_json(root / "planning_validation_report.json", planning_validation)
    if not planning_validation["ok"]:
        raise ValueError(f"Paper-to-image planning failed scientific grounding validation: {planning_validation['errors']}")

    final_prompt = compile_image_prompt(plan, preferences, candidate_variant=1, selected_template=selected_template)
    write_text(root / "image_prompt.txt", final_prompt)
    generation_parameters = {
        "summary": "Image generation parameters.",
        "asset_mode": asset_mode,
        "image_model": image_model,
        "aspect_ratio": preferences["aspect_ratio"],
        "language": preferences["language"],
        "candidate_count": max(1, min(4, int(candidates))),
        "image_retries": max(0, min(5, int(image_retries))),
        "review_mode": review_mode,
        "review_model": review_model,
        "domain_profile": selected_domain["id"],
        "template": selected_template["template_id"],
        "repair_rounds": max(0, min(1, int(repair_rounds))),
        "ocr_engine": ocr_engine,
        "ocr_lang": ocr_lang,
    }
    write_json(root / "generation_parameters.json", generation_parameters)

    generation = generate_and_select(
        plan,
        preferences,
        selected_template,
        root / "layout_blueprint.png",
        root,
        asset_mode=asset_mode,
        candidates=candidates,
        image_model=image_model,
        image_retries=image_retries,
        review_mode=review_mode,
        review_model=review_model,
        repair_rounds=repair_rounds,
        ocr_engine=ocr_engine,
        ocr_lang=ocr_lang,
        ocr_adapter=ocr_adapter,
        critic_adapter=critic_adapter,
    )
    elapsed = round(time.time() - started, 3)
    run_summary: dict[str, Any] = {
        "summary": "Paper-to-image workflow completed without PPTX generation.",
        "ok": True,
        "out_dir": str(root),
        "paper": archived_paper,
        "planner_mode": planner_metadata["mode"],
        "planner_model": planner_metadata.get("model"),
        "planner_warning": planner_metadata.get("warning"),
        "paper_review_mode": review_metadata.get("mode"),
        "domain_profile": selected_domain["id"],
        "template_id": selected_template["template_id"],
        "asset_mode": asset_mode,
        "review_mode": review_mode,
        "candidate_count": generation["successful_candidates"],
        "selected_image": generation.get("selected_image"),
        "engineering_preview": generation.get("engineering_preview"),
        "selected_candidate_id": generation["selected_candidate_id"],
        "selected_passed_all_checks": generation["selected_passed_all_checks"],
        "elapsed_seconds": elapsed,
        "pptx_generated": False,
        "artifacts": [
            "input_manifest.json",
            "preferences.json",
            "evidence_map.json",
            "document_index.json",
            "paper_review.json",
            "review_coverage_report.json",
            "domain_profile.json",
            "template_profiles/",
            "selected_template.json",
            "layout_blueprint.png",
            "paper_summary.json",
            "figure_specification.json",
            "design_plan.json",
            "layout_intent.json",
            "visual_metaphors.json",
            "style_plan.json",
            "planning_validation_report.json",
            "image_prompt.txt",
            "generation_parameters.json",
            "image2_request_manifest.json",
            "candidate_review.json",
            "ocr_review.json",
            "template_alignment_report.json",
            "scientific_critic_report.json",
            "aesthetic_critic_report.json",
            "selected_image.png" if generation.get("selected_image") else "engineering_preview.png",
        ],
    }
    write_json(root / "run_summary.json", run_summary)
    return run_summary
