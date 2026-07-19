from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Callable

from .editable_rebuild import rebuild_editable
from .paper_to_image import run_paper_to_image
from .utils import ensure_dir, read_json, write_json


def _existing_path(value: str | Path | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.exists() else None


def _candidate_review(paper_out: Path) -> dict:
    path = paper_out / "candidate_review.json"
    if not path.exists():
        return {}
    try:
        data = read_json(path)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _select_generated_reference(
    paper_result: dict,
    paper_out: Path,
    require_paper_image_pass: bool,
    allow_engineering_preview: bool,
) -> tuple[Path, dict]:
    review = _candidate_review(paper_out)
    selected = _existing_path(paper_result.get("selected_image")) or _existing_path(paper_out / "selected_image.png")
    preview = _existing_path(paper_result.get("engineering_preview")) or _existing_path(paper_out / "engineering_preview.png")
    passed = bool(paper_result.get("selected_passed_all_checks"))
    delivery_mode = str(review.get("selected_delivery_mode") or ("production" if passed else "unknown"))

    if require_paper_image_pass and not passed:
        raise RuntimeError("paper-to-editable stopped because paper image did not pass all production gates")

    if selected:
        return selected, {
            "source": "selected_image",
            "delivery_mode": delivery_mode,
            "selected_passed_all_checks": passed,
            "selected_candidate_id": paper_result.get("selected_candidate_id"),
        }
    if allow_engineering_preview and preview:
        return preview, {
            "source": "engineering_preview",
            "delivery_mode": "engineering_preview",
            "selected_passed_all_checks": False,
            "selected_candidate_id": paper_result.get("selected_candidate_id"),
        }
    raise RuntimeError("paper-to-editable could not find selected_image.png; use --allow-engineering-preview for offline placeholder runs")


def run_paper_to_editable(
    paper: str | Path,
    out: str | Path,
    preferences_path: str | Path | None = None,
    positive_references: list[str] | None = None,
    negative_references: list[str] | None = None,
    planner_mode: str = "vlm",
    planner_model: str | None = None,
    paper_image_asset_mode: str = "image2",
    paper_image_candidates: int = 3,
    aspect_ratio: str | None = None,
    language: str | None = None,
    image_model: str | None = None,
    image_retries: int = 2,
    paper_image_review_mode: str = "vlm",
    paper_image_review_model: str | None = None,
    domain_profile: str = "auto",
    template: str = "auto",
    paper_image_repair_rounds: int = 1,
    paper_image_ocr_engine: str = "auto",
    paper_image_ocr_lang: str = "en_ch",
    require_paper_image_pass: bool = False,
    allow_engineering_preview: bool = False,
    rebuild_asset_mode: str = "crop",
    rebuild_asset_workers: int = 4,
    rebuild_asset_retries: int = 1,
    economy_mode: bool = True,
    text_mode: str = "ocr",
    control_mode: str = "hybrid",
    layout_mode: str = "hybrid",
    export_preview: bool = False,
    regenerate_slots: str | list[str] | None = None,
    strict_asset_regeneration: bool = False,
    ocr_engine: str = "paddle",
    ocr_lang: str = "en_ch",
    text_grouping_mode: str = "heuristic",
    text_grouping_model: str | None = None,
    text_role_mode: str = "vlm",
    text_role_model: str | None = None,
    text_intelligence_mode: str = "vlm",
    text_intelligence_model: str | None = None,
    design_plan_mode: str = "vlm",
    design_plan_model: str | None = None,
    arrow_style_mode: str = "reference",
    rebuild_critic_mode: str = "off",
    rebuild_critic_iterations: int = 0,
    rebuild_critic_model: str | None = None,
    ocr_adapter: Callable | None = None,
    text_grouping_adapter: Callable | None = None,
    text_role_adapter: Callable | None = None,
    text_intelligence_adapter: Callable | None = None,
    design_adapter: Callable | None = None,
    vlm_layout_adapter: Callable | None = None,
    control_adapter: Callable | None = None,
    semantic_adapter: Callable | None = None,
) -> dict:
    started = time.time()
    root = ensure_dir(out).resolve()
    paper_out = ensure_dir(root / "paper_to_image")

    paper_result = run_paper_to_image(
        paper=paper,
        out=paper_out,
        preferences_path=preferences_path,
        positive_references=positive_references,
        negative_references=negative_references,
        planner_mode=planner_mode,
        planner_model=planner_model,
        asset_mode=paper_image_asset_mode,
        candidates=paper_image_candidates,
        aspect_ratio=aspect_ratio,
        language=language,
        image_model=image_model,
        image_retries=image_retries,
        review_mode=paper_image_review_mode,
        review_model=paper_image_review_model,
        domain_profile=domain_profile,
        template=template,
        repair_rounds=paper_image_repair_rounds,
        ocr_engine=paper_image_ocr_engine,
        ocr_lang=paper_image_ocr_lang,
    )
    generated_source, source_info = _select_generated_reference(
        paper_result,
        paper_out,
        require_paper_image_pass=require_paper_image_pass,
        allow_engineering_preview=allow_engineering_preview,
    )
    generated_reference = root / "generated_reference_image.png"
    shutil.copyfile(generated_source, generated_reference)

    rebuild_result = rebuild_editable(
        reference=generated_reference,
        out=root,
        asset_mode=rebuild_asset_mode,
        asset_workers=rebuild_asset_workers,
        asset_retries=rebuild_asset_retries,
        economy_mode=economy_mode,
        text_mode=text_mode,
        control_mode=control_mode,
        layout_mode=layout_mode,
        export_preview=export_preview,
        regenerate_slots=regenerate_slots,
        strict_asset_regeneration=strict_asset_regeneration,
        ocr_engine=ocr_engine,
        ocr_lang=ocr_lang,
        text_grouping_mode=text_grouping_mode,
        text_grouping_model=text_grouping_model,
        text_role_mode=text_role_mode,
        text_role_model=text_role_model,
        text_intelligence_mode=text_intelligence_mode,
        text_intelligence_model=text_intelligence_model,
        design_plan_mode=design_plan_mode,
        design_plan_model=design_plan_model,
        arrow_style_mode=arrow_style_mode,
        rebuild_critic_mode=rebuild_critic_mode,
        rebuild_critic_iterations=rebuild_critic_iterations,
        rebuild_critic_model=rebuild_critic_model,
        ocr_adapter=ocr_adapter,
        text_grouping_adapter=text_grouping_adapter,
        text_role_adapter=text_role_adapter,
        text_intelligence_adapter=text_intelligence_adapter,
        design_adapter=design_adapter,
        vlm_layout_adapter=vlm_layout_adapter,
        control_adapter=control_adapter,
        semantic_adapter=semantic_adapter,
    )
    elapsed = round(time.time() - started, 3)
    result = {
        "summary": "Paper-to-editable workflow completed.",
        "ok": bool(rebuild_result.get("ok")),
        "out_dir": str(root),
        "paper_to_image_out": str(paper_out),
        "generated_reference_image": str(generated_reference),
        "generated_reference_source": source_info["source"],
        "paper_image_selected_candidate_id": source_info.get("selected_candidate_id"),
        "paper_image_selected_passed_all_checks": source_info["selected_passed_all_checks"],
        "paper_image_delivery_mode": source_info["delivery_mode"],
        "paper_image_asset_mode": paper_image_asset_mode,
        "paper_image_review_mode": paper_image_review_mode,
        "rebuild_asset_mode": rebuild_asset_mode,
        "pptx": rebuild_result.get("pptx"),
        "preview": rebuild_result.get("preview"),
        "rebuild_result": rebuild_result,
        "paper_to_image_result": paper_result,
        "elapsed_seconds": elapsed,
    }
    write_json(root / "paper_to_editable_result.json", result)
    return result
