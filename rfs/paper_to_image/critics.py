from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from ..reference_text_extractor import run_easyocr, run_paddle_ocr
from ..vlm_client import call_vlm_json, resolve_vlm_model, vlm_credentials_available


def _normalize_text(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", str(value or "").casefold())


def required_labels(plan: dict) -> list[str]:
    labels: list[str] = []
    spec = plan.get("figure_specification", {})
    terminology = spec.get("terminology", {})
    if isinstance(terminology, dict):
        labels.extend(str(value) for value in terminology.values())
    elif isinstance(terminology, list):
        labels.extend(str(item.get("visible_label") or item.get("statement") or "") for item in terminology if isinstance(item, dict))
    for module in spec.get("modules", []):
        if isinstance(module, dict):
            labels.append(str(module.get("name") or module.get("statement") or ""))
    result = []
    for label in labels:
        label = label.strip()
        if label and len(label) <= 48 and label not in result:
            result.append(label)
    return result[:24]


def _local_ocr(path: Path, engine: str, lang: str, adapter: Callable | None = None) -> tuple[list[dict], str, str | None]:
    try:
        if adapter:
            records = adapter(path, lang)
            return records, "adapter", None
        if engine == "easyocr":
            return run_easyocr(path, lang), "easyocr", None
        if engine == "paddle":
            return run_paddle_ocr(path, lang), "paddle", None
    except Exception as exc:
        return [], engine, str(exc)
    return [], engine, "local OCR disabled"


def _vlm_critic(path: Path, blueprint: Path, plan: dict, template: dict, labels: list[str], forbidden_labels: list[str], model: str | None, adapter: Callable | None = None) -> dict:
    prompt = f"""
# Summary

Act as a strict production critic for a scientific framework image. The first image is the generated candidate; the second is a content-free layout blueprint. Return JSON only.

Required exact labels:
{json.dumps(labels, ensure_ascii=False)}

Forbidden copied reference labels:
{json.dumps(forbidden_labels, ensure_ascii=False)}

Scientific specification:
{json.dumps(plan.get('figure_specification', {}), ensure_ascii=False, indent=2)}

Selected template:
{json.dumps({key: template.get(key) for key in ['template_id', 'panels', 'connectors', 'visual_density', 'style']}, ensure_ascii=False, indent=2)}

Return:
{{
  "summary": "Production candidate review.",
  "ocr": {{"detected_labels": [], "missing_labels": [], "misspelled_labels": [], "duplicate_labels": [], "forbidden_labels_found": [], "score": 0.0, "passed": false}},
  "scientific": {{"missing_modules": [], "missing_relations": [], "reversed_relations": [], "invented_items": [], "innovation_visible": true, "score": 0.0, "passed": false}},
  "template": {{"macro_panel_match": 0.0, "reading_order_match": 0.0, "connector_rhythm_match": 0.0, "visual_density_match": 0.0, "copied_reference_content": [], "score": 0.0, "passed": false}},
  "aesthetic": {{"hierarchy": 0.0, "balance": 0.0, "whitespace": 0.0, "color": 0.0, "icon_consistency": 0.0, "readability": 0.0, "score": 0.0, "passed": false}},
  "preserve": [],
  "repair": [],
  "remove": [],
  "repair_regions": [],
  "hard_errors": [],
  "production_pass": false,
  "overall_score": 0.0
}}

Hard failures: any missing/misspelled critical label, copied reference term, missing core module, reversed relation, invented mechanism, or template score below 0.72. Aesthetic quality cannot compensate for scientific or OCR failure.
""".strip()
    if adapter:
        return adapter(path, blueprint, prompt)
    resolved = resolve_vlm_model("RFS_PAPER_TO_IMAGE_REVIEW_MODEL", "RFS_CRITIC_MODEL", explicit_model=model)
    raw = call_vlm_json(prompt, [path, blueprint], model=resolved, timeout=240, retries=1)
    raw.setdefault("summary", "Production candidate review.")
    raw["model"] = resolved
    return raw


def _normalize_section(raw: Any, name: str) -> dict:
    section = raw if isinstance(raw, dict) else {}
    section.setdefault("summary", f"{name} review.")
    try:
        section["score"] = max(0.0, min(1.0, float(section.get("score", 0.0))))
    except Exception:
        section["score"] = 0.0
    section["passed"] = bool(section.get("passed", False))
    return section


def review_candidate(
    path: str | Path,
    blueprint: str | Path,
    plan: dict,
    template: dict,
    mode: str = "vlm",
    model: str | None = None,
    ocr_engine: str = "auto",
    ocr_lang: str = "en_ch",
    ocr_adapter: Callable | None = None,
    critic_adapter: Callable | None = None,
) -> dict:
    candidate = Path(path)
    blueprint_path = Path(blueprint)
    labels = required_labels(plan)
    forbidden = [str(value) for value in template.get("forbidden_copy_terms", []) if str(value).strip()]
    with Image.open(candidate) as image:
        width, height = image.size
    with Image.open(blueprint_path) as image:
        bw, bh = image.size
    ratio_error = abs((width / max(height, 1)) - (bw / max(bh, 1))) / max(bw / max(bh, 1), 0.01)
    basic = {"summary": "Deterministic candidate checks.", "valid_image": width > 0 and height > 0, "width": width, "height": height, "blueprint_width": bw, "blueprint_height": bh, "aspect_ratio_error": round(ratio_error, 5), "passed": ratio_error <= 0.08 and min(width, height) >= 512}

    local_records: list[dict] = []
    local_engine = "not_run"
    local_warning = None
    requested_engine = ocr_engine
    if requested_engine == "auto":
        requested_engine = "paddle"
    if requested_engine in {"paddle", "easyocr"}:
        local_records, local_engine, local_warning = _local_ocr(candidate, requested_engine, ocr_lang, adapter=ocr_adapter)

    vlm_raw: dict = {}
    vlm_warning = None
    if mode == "vlm" and (vlm_credentials_available() or critic_adapter):
        try:
            vlm_raw = _vlm_critic(candidate, blueprint_path, plan, template, labels, forbidden, model, adapter=critic_adapter)
        except Exception as exc:
            vlm_warning = str(exc)
    elif mode == "vlm":
        vlm_warning = "VLM review credentials unavailable"

    detected_local = [str(item.get("text") or "").strip() for item in local_records if str(item.get("text") or "").strip()]
    ocr = _normalize_section(vlm_raw.get("ocr"), "OCR")
    if detected_local:
        joined = _normalize_text(" ".join(detected_local))
        missing = [label for label in labels if _normalize_text(label) not in joined]
        forbidden_found = [label for label in forbidden if _normalize_text(label) and _normalize_text(label) in joined]
        ocr.update({
            "local_engine": local_engine,
            "local_detected_text": detected_local,
            "missing_labels": missing,
            "forbidden_labels_found": forbidden_found,
            "score": round((len(labels) - len(missing)) / max(len(labels), 1), 4),
            "passed": not missing and not forbidden_found,
        })
    else:
        ocr.setdefault("local_engine", local_engine)
        ocr.setdefault("local_detected_text", [])
    scientific = _normalize_section(vlm_raw.get("scientific"), "Scientific")
    template_review = _normalize_section(vlm_raw.get("template"), "Template")
    aesthetic = _normalize_section(vlm_raw.get("aesthetic"), "Aesthetic")
    ocr_issues = sum(len(ocr.get(field, [])) for field in ["missing_labels", "misspelled_labels", "duplicate_labels", "forbidden_labels_found"])
    ocr["passed"] = bool(ocr.get("passed")) and ocr["score"] >= 0.999 and ocr_issues == 0
    scientific_issues = sum(len(scientific.get(field, [])) for field in ["missing_modules", "missing_relations", "reversed_relations", "invented_items"])
    has_innovations = bool(plan.get("figure_specification", {}).get("innovations"))
    innovation_ok = not has_innovations or bool(scientific.get("innovation_visible", False))
    scientific["passed"] = bool(scientific.get("passed")) and scientific["score"] >= 0.95 and scientific_issues == 0 and innovation_ok
    copied = template_review.get("copied_reference_content", [])
    template_review["passed"] = bool(template_review.get("passed")) and template_review["score"] >= 0.72 and not copied
    aesthetic["passed"] = bool(aesthetic.get("passed")) and aesthetic["score"] >= 0.75
    if mode != "vlm":
        template_review.update({"score": 1.0 if basic["passed"] else 0.0, "passed": basic["passed"], "engineering_only": True})
        aesthetic.update({"score": 0.0, "passed": False, "engineering_only": True})
        scientific.update({"score": 0.0, "passed": False, "engineering_only": True})
        ocr.update({"score": 0.0, "passed": False, "engineering_only": True})
    hard_errors = list(vlm_raw.get("hard_errors", []))
    production_pass = bool(basic["passed"] and ocr["passed"] and scientific["passed"] and template_review["passed"] and aesthetic["passed"] and not hard_errors)
    score = 0.30 * scientific["score"] + 0.25 * ocr["score"] + 0.25 * template_review["score"] + 0.20 * aesthetic["score"]
    return {
        "summary": "Four-layer production candidate review.",
        "path": str(candidate),
        "mode": mode,
        "basic": basic,
        "ocr": ocr,
        "scientific": scientific,
        "template": template_review,
        "aesthetic": aesthetic,
        "hard_errors": hard_errors,
        "preserve": list(vlm_raw.get("preserve", [])),
        "repair": list(vlm_raw.get("repair", [])),
        "remove": list(vlm_raw.get("remove", [])),
        "repair_regions": list(vlm_raw.get("repair_regions", [])),
        "local_ocr_warning": local_warning,
        "vlm_warning": vlm_warning,
        "production_pass": production_pass,
        "overall_score": round(score, 4),
    }


def aggregate_reviews(records: list[dict]) -> dict:
    def collect(section: str) -> dict:
        return {"summary": f"Aggregated {section} candidate reviews.", "candidates": [{"candidate_id": item["candidate_id"], **item["review"][section]} for item in records]}
    return {
        "ocr_review": collect("ocr"),
        "scientific_critic_report": collect("scientific"),
        "template_alignment_report": collect("template"),
        "aesthetic_critic_report": collect("aesthetic"),
    }
